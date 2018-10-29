"""Train an agent with TensorForce.

Call this with a config, a game, and a list of agents, one of which should be a
tensorforce agent. The script will start separate threads to operate the agents
and then report back the result.

An example with all three simple agents running ffa:
python train_with_tensorforce.py \
 --agents=tensorforce::ppo,test::agents.SimpleAgent,test::agents.SimpleAgent,test::agents.SimpleAgent \
 --config=PommeFFACompetition-v0
"""

import atexit
import functools
import os, sys

import argparse
import docker
from tensorforce.execution import Runner
from tensorforce.contrib.openai_gym import OpenAIGym
import gym

sys.path.append('.')

from pommerman import helpers, make
from pommerman.agents import TensorForceAgent
from ctrl.agents import TensorForcePpoAgent

CLIENT = docker.from_env()

def clean_up_agents(agents):
    """Stops all agents"""
    return [agent.shutdown() for agent in agents]


class WrappedEnv(OpenAIGym):
    '''An Env Wrapper used to make it easier to work
    with multiple agents'''
    def __init__(self, gym, visualize=False):
        self.gym = gym
        self.visualize = visualize

    def execute(self, action):
        if self.visualize:
            self.gym.render()

        obs = self.gym.get_observations()
        all_actions = self.gym.act(obs)
        all_actions.insert(self.gym.training_agent, action)
        state, reward, terminal, _ = self.gym.step(all_actions)
        agent_state = self.gym.featurize(state[self.gym.training_agent])
        agent_reward = reward[self.gym.training_agent]
        return agent_state, terminal, agent_reward

    def reset(self):
        obs = self.gym.reset()
        agent_obs = self.gym.featurize(obs[3])
        return agent_obs

def create_ppo_agent(agent):
    if type(agent) == TensorForceAgent:
        print("create_ppo_agent({})".format(agent))
        return TensorForcePpoAgent()
    return agent

def main():
    '''CLI interface to bootstrap taining'''
    parser = argparse.ArgumentParser(description="Playground Flags.")
    parser.add_argument("--game", default="pommerman", help="Game to choose.")
    parser.add_argument(
        "--config",
        default="PommeFFACompetition-v0",
        help="Configuration to execute. See env_ids in "
        "configs.py for options.")
    parser.add_argument(
        "--agents",
        default="tensorforce::ppo,test::agents.SimpleAgent,"
        "test::agents.SimpleAgent,test::agents.SimpleAgent",
        help="Comma delineated list of agent types and docker "
        "locations to run the agents.")
    parser.add_argument(
        "--agent_env_vars",
        help="Comma delineated list of agent environment vars "
        "to pass to Docker. This is only for the Docker Agent."
        " An example is '0:foo=bar:baz=lar,3:foo=lam', which "
        "would send two arguments to Docker Agent 0 and one to"
        " Docker Agent 3.",
        default="")
    parser.add_argument(
        "--record_pngs_dir",
        default=None,
        help="Directory to record the PNGs of the game. "
        "Doesn't record if None.")
    parser.add_argument(
        "--record_json_dir",
        default=None,
        help="Directory to record the JSON representations of "
        "the game. Doesn't record if None.")
    parser.add_argument(
        "--render",
        default=False,
        action='store_true',
        help="Whether to render or not. Defaults to False.")
    parser.add_argument(
        "--game_state_file",
        default=None,
        help="File from which to load game state. Defaults to "
        "None.")
    parser.add_argument(
        "--checkpoint",
        default="models/ppo",
        help="Directory where checkpoint file stored to."
    )
    parser.add_argument(
        "--num_of_episodes",
        default="10",
        help="Number of episodes"
    )
    parser.add_argument(
        "--max_timesteps",
        default="2000",
        help="Number of steps"
    )
    args = parser.parse_args()

    config = args.config
    record_pngs_dir = args.record_pngs_dir
    record_json_dir = args.record_json_dir
    agent_env_vars = args.agent_env_vars
    game_state_file = args.game_state_file
    checkpoint = args.checkpoint
    num_of_episodes = int(args.num_of_episodes)
    max_timesteps = int(args.max_timesteps)

    # TODO: After https://github.com/MultiAgentLearning/playground/pull/40
    #       this is still missing the docker_env_dict parsing for the agents.
    agents = [
        create_ppo_agent(helpers.make_agent_from_string(agent_string, agent_id + 1000))
        for agent_id, agent_string in enumerate(args.agents.split(","))
    ]

    env = make(config, agents, game_state_file)
    training_agent = None

    for agent in agents:
        if type(agent) == TensorForcePpoAgent:
            print("Ppo agent initiazlied : {}, {}".format(agent, type(agent)))
            training_agent = agent
            env.set_training_agent(agent.agent_id)
            # break
        print("[{}] : id[{}]".format(agent, agent.agent_id))

    if args.record_pngs_dir:
        assert not os.path.isdir(args.record_pngs_dir)
        os.makedirs(args.record_pngs_dir)
    if args.record_json_dir:
        assert not os.path.isdir(args.record_json_dir)
        os.makedirs(args.record_json_dir)

    # Create a Proximal Policy Optimization agent
    agent = training_agent.initialize(env)

    atexit.register(functools.partial(clean_up_agents, agents))
    wrapped_env = WrappedEnv(env, visualize=args.render)
    runner = Runner(agent=agent, environment=wrapped_env)
    runner.run(episodes=num_of_episodes, max_episode_timesteps=max_timesteps)
    # runner.run(episodes=10, max_episode_timesteps=2000)
    print("Stats: ",
        runner.episode_rewards[-30:],
        runner.episode_timesteps,
        runner.episode_times)

    agent.save_model(checkpoint)

    rewards = runner.episode_rewards
    import numpy as np
    mean = np.mean(rewards)
    print('last 30 rewards {}'.format(rewards[-30:]))
    print('mean of rewards {}'.format(mean))

    try:
        runner.close()
    except AttributeError as e:
        pass

if __name__ == "__main__":
    main()

