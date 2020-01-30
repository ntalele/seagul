import ray
from ray import tune
import ray.rllib.agents.ppo as ppo
import seagul.envs

config = ppo.DEFAULT_CONFIG.copy()
config["num_workers"] = 1
config["lambda"] = 0.2
config["gamma"] = 0.95
config["num_gpus"] = 0
config["eager"] = False
config["model"]["free_log_std"] = True
config["lr"] = 0.0001
config["kl_coeff"] = 1.0
config["num_sgd_iter"] = 10
config["batch_mode"] = "truncate_episodes"
config["observation_filter"] = "MeanStdFilter"
config["sgd_minibatch_size"] = 512
# config["train_batch_size"] = tune.sample_from(lambda spec: spec.config.sgd_minibatch_size*32)
config["train_batch_size"] = 2048
config["vf_clip_param"] = 10
config["seed"] = tune.grid_search([2, 3, 4, 5])  #
env_name = "lorenz-v0"
config["env"] = env_name
# import pprint
# pprint.pprint(config)

analysis = tune.run(
    ppo.PPOTrainer,
    config=config,
    stop={"timesteps_total": 5e5},
    local_dir="./data/bench_model/",
    checkpoint_at_end=True,
)
