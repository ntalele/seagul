import gym
import seagul.envs
import numpy as np
from tqdm import trange
import copy

import torch
import pybullet_envs
from torch.utils import data
from torch.distributions import Normal, Categorical

from numpy import pi, sin, cos

variance = .1

#============================================================================================
def ppo_switch(env_name, num_epochs, policy, value_fn, gate_fn, epoch_batch_size = 2048,
            gamma = .99, lam = .99, eps = .2, seed=0, policy_batch_size = 1024,
            value_batch_size = 1024, gate_batch_size=1024, policy_lr = 1e-3, value_lr = 1e-3, gate_lr = 1e-3, p_epochs = 10,
            v_epochs = 1, use_gpu = False, reward_stop = None):

    """

    Implements a proximal policy optimization with clipping

    :param env_name: name of the openAI gym environment to solve
    :param num_epochs: number of epochs to run the PPO for
    :param policy: policy function, must be a pytorch module
    :param value_fn: value function, must be a pytorch module
    :param epoch_batch_size: number of environment steps to take per batch, total steps will be num_epochs*epoch_batch_size
    :param seed: seed for all the rngs
    :param gamma: discount applied to future rewards, usually close to 1
    :param lam: lambda for the Advantage estimmation, usually close to 1
    :param eps: epsilon for the clipping, usually .1 or .2
    :param policy_batch_size: batch size for policy updates
    :param value_batch_size: batch size for value function updates
    :param policy_lr: learning rate for policy p_optimizer
    :param value_lr: learning rate of value function p_optimizer
    :param p_epochs: how many epochs to use for each policy update
    :param v_epochs: how many epochs to use for each value update
    :param use_gpu:  want to use the GPU? set to true
    :param reward_stop: reward value to stop if we achieve
    :return:
    """

    env = gym.make(env_name)

    #car_env = env.envs[0].env.env
    env.num_steps = 250 # TODO

    if isinstance(env.action_space, gym.spaces.discrete.Discrete):
        raise NotImplementedError("Discrete action spaces are not implemnted yet, why are you using PPO for a discrete action space anyway?")
        #select_action = select_discrete_action
        #get_logp = get_discrete_logp
        #action_size = 1
    elif isinstance(env.action_space, gym.spaces.Box):
        select_action = select_cont_action
        get_logp = get_cont_logp
        action_size = env.action_space.shape[0]
    else:
        raise NotImplementedError("trying to use unsupported action space", env.action_space)


    # need a copy of the old policy for the ppo loss
    old_policy = copy.deepcopy(policy)

    # intialize our optimizers
    p_optimizer = torch.optim.Adam(policy.parameters(), lr=policy_lr)
    v_optimizer = torch.optim.Adam(value_fn.parameters(), lr=value_lr)
    g_optimizer = torch.optim.Adam(gate_fn.parameters(), lr=gate_lr)

    # seed all our RNGs
    env.seed(seed)
    torch.manual_seed(seed)
    np.random.seed(seed)


    # set defaults, and decide if we are using a GPU or not
    torch.set_default_dtype(torch.double)
    use_cuda = torch.cuda.is_available() and use_gpu
    device = torch.device("cuda:0" if use_cuda else "cpu")

    avg_reward_hist = []

    for epoch in trange(num_epochs):

        episode_reward_sum = []
        batch_steps = 0  # tracks steps taken in current batch
        traj_steps = 0   # tracks steps taken in current trajector
        traj_count = 1   # tracks number of trajectories in current batch


        # tensors for holding training information for each batch
        adv_tensor = torch.empty(0)
        disc_rewards_tensor = torch.empty(0)
        state_tensor = torch.empty(0)
        action_tensor = torch.empty(0)
        path_tensor = torch.empty(0, dtype=torch.long)


        # Check if we have maxed out the reward, so that we can stop early
        if traj_count > 2:
            if avg_reward_hist[-1] >= reward_stop and avg_reward_hist[-2] >= reward_stop:
                break


        # keep doing rollouts until we fill a single batch of examples
        while True:
            # reset the environment
            state = torch.as_tensor(env.reset())
            action_list = []; state_list = []; reward_list = []; path_list = [];
            nn_state_list = []; nn_reward_list = []; nn_action_list = [];
            traj_steps = 0

            # Do a single policy rollout
            for t in range(env.num_steps):

                state_list.append(state)

                path, path_logprob = select_discrete_action(gate_fn, state)

                if (path):
                    action, logprob = select_action(policy, state)
                else:
                    action = control(env, state)

                state_np, reward, done, _ = env.step(action.numpy())
                state = torch.as_tensor(state_np)

                path_list.append(path)
                reward_list.append(reward)
                action_list.append(torch.as_tensor(action, dtype=torch.double))

                batch_steps += 1
                traj_steps += 1

                if done:
                    traj_count += 1
                    break

            # if we failed at the first time step start again
            if traj_steps <= 1:
                traj_steps = 0
                break

            # make a tensor storing the current episodes state, actions, and rewards
            ep_state_tensor  = torch.stack(state_list).reshape(-1,env.observation_space.shape[0])
            ep_action_tensor = torch.stack(action_list).reshape(-1, action_size)
            ep_disc_rewards  = torch.as_tensor(discount_cumsum(reward_list, gamma)).reshape(-1, 1)
            ep_path_tensor   = torch.stack(path_list).reshape(-1, 1)

            # calculate our advantage for this rollout
            value_preds = value_fn(ep_state_tensor)
            deltas = torch.as_tensor(reward_list[:-1]) + gamma*value_preds[1:].squeeze() - value_preds[:-1].squeeze()
            ep_adv = discount_cumsum(deltas.detach(), gamma*lam).reshape(-1,1)

            # append to the tensors storing information for the whole batch
            state_tensor  = torch.cat((state_tensor , ep_state_tensor[:-1]))
            action_tensor = torch.cat((action_tensor, ep_action_tensor[:-1]))
            disc_rewards_tensor  = torch.cat((disc_rewards_tensor , ep_disc_rewards[:-1]))
            adv_tensor    = torch.cat((adv_tensor, ep_adv))
            path_tensor   = torch.cat((path_tensor, ep_path_tensor[:-1]))

            # keep track of rewards for metrics later
            episode_reward_sum.append(sum(reward_list))

            # once we have enough data, update our policy and value function
            if batch_steps > epoch_batch_size:

                p_state_list = []; p_action_list = []; p_adv_list = [];
                for state, action, adv, path in zip(state_tensor, action_tensor, adv_tensor, path_tensor):
                    if(path):
                        p_state_list.append(state)
                        p_action_list.append(action)
                        p_adv_list.append(adv)


                if(len(p_state_list)):
                    p_state_tensor  = torch.stack(p_state_list).reshape(-1, env.observation_space.shape[0])
                    p_action_tensor = torch.stack(p_action_list).reshape(-1, action_size)
                    p_adv_tensor    = torch.stack(p_adv_list).reshape(-1, 1)

                    # keep track of rewards for metrics later
                    avg_reward_hist.append(sum(episode_reward_sum) / len(episode_reward_sum))
                    # construct a training data generator
                    training_data = data.TensorDataset(p_state_tensor, p_action_tensor, p_adv_tensor)
                    training_generator = data.DataLoader(training_data, batch_size=policy_batch_size, shuffle=True)

                    # iterate through the data, doing the updates for our policy
                    for epoch in range(p_epochs):
                        for local_states, local_actions, local_adv in training_generator:
                            # Transfer to GPU (if GPU is enabled, else this does nothing)
                            local_states, local_actions, local_adv = local_states.to(device), local_actions.to(device), local_adv.to(device)

                            # predict and calculate loss for the batch
                            logp = get_logp(policy, local_states, local_actions.squeeze()).reshape(-1,action_size)
                            old_logp = get_logp(old_policy, local_states, local_actions.squeeze()).reshape(-1,action_size)
                            r = torch.exp(logp - old_logp)
                            p_loss = -torch.sum(torch.min(r*local_adv, local_adv*torch.clamp(r, (1 - eps), (1 + eps))))/r.shape[0]

                            # do the normal pytorch update
                            p_loss.backward(retain_graph=True)
                            p_optimizer.step()
                            p_optimizer.zero_grad()

                    p_loss.backward()

                # Now we do the update for our value function
                # construct a training data generator
                training_data = data.TensorDataset(state_tensor, disc_rewards_tensor)
                training_generator = data.DataLoader(training_data, batch_size=value_batch_size, shuffle=True)

                for epoch in range(v_epochs):
                    for local_states, local_values in training_generator:
                        # Transfer to GPU (if GPU is enabled, else this does nothing)
                        local_states, local_values = local_states.to(device), local_values.to(device)

                        # predict and calculate loss for the batch
                        value_preds = value_fn(local_states)
                        v_loss = torch.sum(torch.pow(value_preds - local_values,2))

                        # do the normal pytorch update
                        v_optimizer.zero_grad()
                        v_loss.backward()
                        v_optimizer.step()


                old_policy = copy.deepcopy(policy)

                # Now we do the update for our value function
                # construct a training data generator
                training_data = data.TensorDataset(state_tensor, path_tensor)
                training_generator = data.DataLoader(training_data, batch_size=gate_batch_size, shuffle=True)
                gate_loss_fn = nn.BCELoss()
                for epoch in range(v_epochs):
                    for local_states, local_values in training_generator:
                        # Transfer to GPU (if GPU is enabled, else this does nothing)
                        local_states, local_agl = local_states.to(device), local_values.to(device)

                        # predict and calculate loss for the batch
                        path_preds = gate_fn(local_states)
                        gate_loss = gate_loss_fn(path_preds, torch.as_tensor(local_agl,dtype=torch.double))

                        # do the normal pytorch update
                        g_optimizer.zero_grad()
                        gate_loss.backward()
                        g_optimizer.step()

                old_policy = copy.deepcopy(policy)

                break

    return (env, policy, value_fn, avg_reward_hist)



# helper functions
#============================================================================================

# takes a policy and the states and sample an action from it... (can we make this faster?)
def select_cont_action(policy, state):
    means = policy(torch.as_tensor(state)).squeeze()
    m = Normal(loc = means, scale = torch.ones_like(means)*variance)
    action = m.sample()
    logprob = m.log_prob(action)
    return action.detach(), logprob


# given a policy plus a state/action pair, what is the log liklihood of having taken that action?
def get_cont_logp(policy, states, actions):
    means = policy(torch.as_tensor(states)).squeeze()
    m = Normal(loc = means, scale = torch.ones_like(means)*variance)
    logprob = m.log_prob(actions)
    return logprob


# takes a policy and the states and sample an action from it... (can we make this faster?)
def select_discrete_action(policy, state):
    probs = torch.tensor([policy(torch.as_tensor(state)), 1 - policy(torch.as_tensor(state))])
    m = Categorical(probs)
    action = m.sample()
    logprob = m.log_prob(action)
    return action.detach(), logprob

# given a policy plus a state/action pair, what is the log liklihood of having taken that action?
def get_discrete_logp(policy, state, action):
    m = Categorical(policy(torch.as_tensor(state)))
    logprob = m.log_prob(action)
    return logprob

# can make this faster I think?
def discount_cumsum(rewards, discount):
    future_cumulative_reward = 0
    cumulative_rewards = torch.empty_like(torch.as_tensor(rewards))
    for i in range(len(rewards) - 1, -1, -1):
        cumulative_rewards[i] = rewards[i] + discount * future_cumulative_reward
        future_cumulative_reward = cumulative_rewards[i]
    return cumulative_rewards


def control(env, q):
    # Ausutay Ozmen
    if (q[0] < 140 * pi / 180) or (q[0] > 220 * pi / 180):
        # swing up
        # energy error: Ee
        Ee = 0.5 * env.mp * env.L * env.L * q[2] ** 2 - env.mp * env.g * env.L * (1 + cos(q[0]))
        # energy conrol gain:
        k = 0.23

        # input acceleration: A (of cart)
        A = k * Ee * cos(q[0]) * q[2]
        # convert A to u (using EOM)
        delta = env.mp * sin(q[0]) ** 2 + env.mc
        u = A * delta - env.mp * env.L * (q[2] ** 2) * sin(q[0]) - env.mp * env.g * sin(q[2]) * cos(q[2])
    else:
        # balancing
        # LQR: K values from MATLAB
        k1 = 140.560
        k2 = -3.162
        k3 = 41.772
        k4 = -8.314
        print("balancing")
        u = -25 * (k1 * (q[0] - pi) + k2 * q[1] + k3 * q[2] + k4 * q[3])
    return u


#============================================================================================
if __name__ == '__main__':
    import torch.nn as nn
    from seagul.rl.ppo import ppo
    from seagul.nn import Categorical_MLP, MLP
    import torch

    import matplotlib.pyplot as plt
    torch.set_default_dtype(torch.double)

    #policy = Categorical_MLP(input_size=4, output_size=1, layer_size=12, num_layers=2, activation=nn.ReLU)
    policy =  MLP(input_size=4, output_size=1, layer_size=12, num_layers=2, activation=nn.ReLU)
    value_fn = MLP(input_size=4, output_size=1, layer_size=12, num_layers=2, activation=nn.ReLU)
    gate_fn = Categorical_MLP(input_size=4, output_size=1, layer_size=12, num_layers=2, activation=nn.ReLU)


    # Define our hyper parameters
    num_epochs = 100
    batch_size = 2048  # how many steps we want to use before we update our gradients
    num_steps = 1000  # number of steps in an episode (unless we terminate early)
    max_reward = num_steps
    p_batch_size = 1024
    v_epochs = 1
    p_epochs = 10
    p_lr = 1e-2
    v_lr = 1e-2

    gamma = .99
    lam = .99
    eps = .2

    variance = 0.2  # feel like there should be a better way to do this...

    # env2, t_policy, t_val, rewards = ppo('InvertedPendulum-v2', 100, policy, value_fn)
    env2, t_policy, t_val, rewards = ppo_switch('su_cartpole-v0', 30, policy, value_fn, gate_fn)

    print(rewards)