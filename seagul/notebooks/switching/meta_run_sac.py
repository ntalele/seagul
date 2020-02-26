from multiprocessing import Process
import seagul.envs

import gym

env_name = "su_acrobot-v0"

env = gym.make(env_name)

import torch
import torch.nn as nn
import numpy as np

# init policy, valuefn
input_size = 4
output_size = 1
layer_size = 16
num_layers = 1
activation = nn.ReLU

from seagul.rl.run_utils import run_sg, run_and_save_bs
from seagul.rl.algos import sac
from seagul.rl.models import SACModel, SACModelActHold
from seagul.nn import MLP, CategoricalMLP

proc_list = []
trial_num = input("What trial is this?\n")

for seed in np.random.randint(0, 2 ** 32, 4):

    max_torque = 5

    policy = MLP(input_size, output_size*2, num_layers, layer_size, activation)
    value_fn = MLP(input_size, 1, num_layers, layer_size, activation)
    q1_fn = MLP(input_size + output_size, 1, num_layers, layer_size, activation)
    q2_fn = MLP(input_size + output_size, 1, num_layers, layer_size, activation)



    # model = SACModelActHold(
    #     policy=policy,
    #     value_fn = value_fn,
    #     q1_fn = q1_fn,
    #     q2_fn = q2_fn,
    #     act_limit = 25,
    #     hold_count = 20,
    # )


    model = SACModel(
        policy=policy,
        value_fn = value_fn,
        q1_fn = q1_fn,
        q2_fn = q2_fn,
        act_limit = max_torque,
    )


    def reward_fn(ns, act):
        return -1e-2 * (np.cos(ns[0]) + np.cos(ns[0] + ns[1]))



    env_config = {
        "max_torque": max_torque,
        "init_state": [0.0, 0.0, 0.0, 0.0],
        "init_state_weights": np.array([0, 0, 0, 0]),
        "dt": .01,
        "max_t": 10,
        "act_hold": 20,
        "reward_fn": reward_fn,
    }

    alg_config = {
        "env_name": env_name,
        "model": model,
        "seed": seed,  # int((time.time() % 1)*1e8),
        "total_steps" : 5e5,
        "exploration_steps" : 10000,
        "min_steps_per_update" : 200,
        "reward_stop" : 1500,
        "gamma": 1,
        "env_config": env_config
    }



    p = Process(
        target=run_sg,
        args=(alg_config, sac, "sac-test", "no act hold this time", "/data2_sac/trial" + trial_num),
    )
    p.start()
    proc_list.append(p)


for p in proc_list:
    print("joining")
    p.join()
