"""Wie gut nutzt der Schwarm die Uplink-Kapazitaet? (Policy + Waechter v2, 9000 Takte)

  python uplink_use.py --ckpt checkpoints/guard_v2_tag_best.pt --seeds 0 2 5
"""
import argparse
import math
import torch
import train_with_guard as tg

p = argparse.ArgumentParser()
p.add_argument("--ckpt", default=str(tg.SIM / "checkpoints" / "netcov_final.pt"))
p.add_argument("--seeds", type=int, nargs="+", default=[0, 2, 5])
p.add_argument("--steps", type=int, default=9000)
a = p.parse_args()
mcfg = tg.MissionConfig.load(str(tg.SIM / "netzabdeckung_config.yaml"), stage=4)
for seed in a.seeds:
    env = tg.NetCovEnv(mcfg, num_envs=1, device="cpu", seed=seed)
    net = tg.AttnActorCritic(env.entity_dim, env.self_global_dim, env.team_global_dim, tg.NUM_ACTIONS, hidden=128)
    net.load_state_dict(torch.load(a.ckpt, map_location="cpu"))
    guard = tg.Guard(1, env.A, env.reserve_pct / 100.0, math.hypot(env.map_w, env.map_h), "cpu", steer="v2")
    obs = env.reset()
    up = float(env.U * env.uplink_cap)
    use = served = linked = 0.0
    for t in range(a.steps):
        with torch.no_grad():
            act = net.policy(obs["entities"], obs["alive"], obs["team"], obs["self_global"]).probs.argmax(-1)
        act, _ = guard.apply(obs, act)
        obs, _, _, info = env.step(act)
        _, connected, cap = env._connectivity()
        sf, delivered, hole, _ = env._serve(connected, cap)
        use += delivered.sum().item() / up
        linked += 1.0 - (hole[0] & env.hs_active[0]).sum().item() / env.hs_active[0].sum().item()
        served += info["served_pct"]
    n = a.steps
    print(f"seed {seed}: Versorgung {served / n:.1f}% | Uplink ausgelastet {100 * use / n:.0f}% | "
          f"Hotspots mit Netz {100 * linked / n:.0f}% | lebend Ende {int(env.alive.sum())}", flush=True)
