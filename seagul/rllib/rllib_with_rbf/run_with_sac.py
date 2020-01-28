import ray
from ray import tune
import ray.rllib.agents.ppo as ppo
from ray.rllib.models import ModelCatalog
from ray.rllib.models.tf.tf_modelv2 import TFModelV2
from tensorflow.keras.layers import Layer
from keras.initializers import RandomNormal
from tensorflow.keras import backend as K
import tensorflow as tf
from ray.rllib.models.tf.misc import normc_initializer
from ray.rllib.agents.dqn.distributional_q_model import DistributionalQModel
from ray.rllib.utils import try_import_tf
from ray.rllib.models.tf.visionnet_v2 import VisionNetwork as MyVisionNetwork
import datetime

from custom_rbf_layer_model_v2 import RBFModel1, RBFModel2
from custom_keras_model_v2 import MyKerasModel1, MyKerasModel2

ModelCatalog.register_custom_model("rbf_model_1", RBFModel1)
ModelCatalog.register_custom_model("rbf_model_2", RBFModel2)
ModelCatalog.register_custom_model("my_keras_model_1", MyKerasModel1)
ModelCatalog.register_custom_model("my_keras_model_2", MyKerasModel2)

log_dir="logs/fit/" + datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
tensorboard_callback = tf.keras.callbacks.TensorBoard(log_dir=log_dir, histogram_freq=1)

# ray.init(local_mode=True) # local mode for debugging
ray.init()
tune.run(
    "SAC",
    stop={"episode_reward_mean": -150},
    checkpoint_freq=10000,
    max_failures=5,
    checkpoint_at_end=True,
    config={
        "model": {
            "custom_model": "rbf_model_2", # tune.grid_search(["rbf_model_2", "my_keras_model_2"]), # tune.grid_search(["rbf_model_1", "rbf_model_2"]),
            "custom_options": {},  # extra options to pass to your model
        },
        # "lr": 0.01, #tune.grid_search([0.1, 0.01]),
        # "eager": False,
        "env": "Pendulum-v0",
        "horizon": 200,
        "soft_horizon": False,
        # Q_model:
        #   hidden_activation: relu
        #   hidden_layer_sizes: [256, 256]
        # policy_model:
        #   hidden_activation: relu
        #   hidden_layer_sizes: [256, 256]
        "tau": 0.005,
        "target_entropy": "auto",
        "no_done_at_end": True,
        "n_step": 1,
        "sample_batch_size": 1,
        "prioritized_replay": False,
        "train_batch_size": 256,
        "target_network_update_freq": 1,
        "timesteps_per_iteration": 1000,
        "learning_starts": 256,
        "exploration_enabled": True,
        "optimization": {
            "actor_learning_rate": 0.0003,
            "critic_learning_rate": 0.0003,
            "entropy_learning_rate": 0.0003,
        },
        "num_workers": 0,
        "num_gpus": 0,
        "clip_actions": False,
        # "normalize_actions": True,
        "evaluation_interval": 1,
        "metrics_smoothing_episodes": 5,
        # "checkpoint_at_end": True
    },
)