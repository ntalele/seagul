import matplotlib.pyplot as plt
from seagul.baselines.run import load_model
import numpy as np
import seagul.envs
from numpy import pi
from mpl_toolkits.mplot3d import Axes3D

from seagul.nn import fit_model
import torch
from tqdm import trange
import tqdm

import torch.nn as nn

torch.set_default_dtype(torch.float32)

# Load data from runs done outside this notebook

# save_path = './data/car/bullet_car_v0_acktr_1e7'
# save_path = './data/car/signed_bullet_car'
# save_path = './data/car/new_baselines'
# save_path = './data/car/2_64_long'
# save_path = './data/ppo_bench/ppo_test'
save_path = "./data/bullet_car_ast/bullet_ast"

model, env = load_model(save_path)  # This is loading the trained model for analysis