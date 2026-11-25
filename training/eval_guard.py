"""Vergleicht Waechter v1 (gerade Linie zur Station) mit v2 (wind-kompensiert) in der Simulation.
Gleiche Policy, gleiche Seeds, 9000 Takte (15 min).

  python eval_guard.py --seeds 0 1 2 3 4 5
"""
import argparse
import math
import torch
import train_with_guard as tg

p = argparse.ArgumentParser()
p.add_argument("--seeds", type=int, nargs="+", default=[0, 1, 2, 3])
p.add_argument("--ckpt", default=str(tg.SIM / "checkpoints" / "netcov_final.pt"))
p.add_argument("--steps", type=int, default=9000)
a = p.parse_args()

mcfg = tg.MissionConfig.load(str(tg.SIM / "netzabdeckung_config.yaml"), stage=4)
print(f"{'Seed':>4} {'Wind':>5} | {'Waechter':>8} {'versorgt':>8} {'lebend Start':>12} {'lebend Ende':>11} {'Akku':>5}")
for seed in a.seeds:
    for steer in ("v1", "v2"):
        env = tg.NetCovEnv(mcfg, num_envs=1, device="cpu", seed=seed)
        net = tg.AttnActorCritic(env.entity_dim, env.self_global_dim, env.team_global_dim, tg.NUM_ACTIONS, hidden=128)
        net.load_state_dict(torch.load(a.ckpt, map_location="cpu"))
        guard = tg.Guard(1, env.A, env.reserve_pct / 100.0, math.hypot(env.map_w, env.map_h), "cpu", steer=steer)
        obs = env.reset()
        alive0 = int(env.alive.sum())
        served, batt = 0.0, 0.0
        for t in range(a.steps):
            with torch.no_grad():
                act = net.policy(obs["entities"], obs["alive"], obs["team"], obs["self_global"]).probs.argmax(-1)
            act, _ = guard.apply(obs, act)
            obs, _, _, info = env.step(act)
            served += info["served_pct"] / 100.0
            batt += info["mean_battery"]
        print(f"{seed:>4} {env.wind[0].norm():5.1f} | {steer:>8} {100 * served / a.steps:7.1f}% "
              f"{alive0:>12} {int(env.alive.sum()):>11} {batt / a.steps:5.1f}", flush=True)
