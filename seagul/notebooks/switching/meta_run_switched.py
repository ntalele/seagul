import gym
import seagul.envs

env_name = "su_acro_drake-v0"
env = gym.make(env_name)

from seagul.rl.run_utils import run_sg, run_and_save_bs
from seagul.rl.algos import ppo, ppo_switch
from seagul.rl.models import PPOModel, SwitchedPPOModel, SwitchedPPOModelActHold
from seagul.nn import MLP, CategoricalMLP, DummyNet

import torch
import torch.nn as nn

import numpy as np
from numpy import pi

from multiprocessing import Process

# init policy, value fn
input_size = 4
output_size = 1
layer_size = 12
num_layers = 2
activation = nn.ReLU
proc_list = []

torch.set_num_threads(1)

for seed in [1, 2, 3, 4]:
    env_name = "su_acro_drake-v0"
    env = gym.make(env_name)

    def control(q):
        k = np.array([[1316.85000612, 555.41763935, 570.32667002, 272.57631536]], dtype=np.float32)
        # k = np.array([[278.44223126, 112.29125985, 119.72457377,  56.82824017]])
        gs = np.array([pi, 0, 0, 0], dtype=np.float32)
        # return 0
        return (-k.dot(gs - np.asarray(q)))


    model = SwitchedPPOModelActHold(
        # policy = MLP(input_size, output_size, num_layers, layer_size, activation),
        policy=torch.load("warm/ppo2_warm_pol"),
        value_fn=torch.load("warm/ppo2_warm_val"),
        # MLP(input_size, 1, num_layers, layer_size, activation),
        gate_fn=torch.load("warm/gate_fn_ppo2_nz128"),
        nominal_policy=control,
        hold_count=20,
    )

    def reward_fn(ns):
        reward = -(np.cos(ns[0]) + np.cos(ns[0] + ns[1]))
        reward -= (abs(ns[2]) > 10)
        reward -= (abs(ns[3]) > 30)
        return reward

    env_config = {
        "max_torque" : 25,
        "init_state" : [0.0, 0.0, 0.0, 0.0],
        "init_state_weights" : np.array([0, 0, 0, 0]),
        "dt" : .01,
        "max_t" : 5,
        "act_hold" : 1,
        "fixed_step" : True,
        "int_accuracy" : .01,
        "reward_fn" : reward_fn
    }


    arg_dict = {
        "env_name": env_name,
        "model": model,
        "total_steps": 5e5,
        "epoch_batch_size": 2048,
        "act_var_schedule": [1, 1],
        "gate_var_schedule": [0.1, 0.1],
        "gamma": 1,
        "seed": seed,
        "reward_stop": 1500,
        "env_config": env_config
    }

    run_name = "25_ppo2_2ag" +  str(seed)

    p = Process(
        target=run_sg,
        args=(
            arg_dict,
            ppo_switch,
            run_name,
            "now with penalties for velocity",
            "/data/drake_ppo2/",
        ),
    )
    p.start()
    proc_list.append(p)

for p in proc_list:
    print("joining")
    p.join()


print("finished run ", run_name)