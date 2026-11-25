"""Diagnose: warum erreichen Drohnen bei manchen Seeds die Ladestation nicht?
Laeuft die Simulation mit Policy + Waechter (Python-Kopie) und protokolliert fuer Drohnen,
die der Waechter zum Laden schickt: echte Distanz zur naechsten Station, Akku, Wind, Geschwindigkeit.

  python diag_seed.py --seed 1 --ckpt <pfad.pt>
"""
import argparse
import math
import torch
import train_with_guard as tg

p = argparse.ArgumentParser()
p.add_argument("--seed", type=int, default=1)
p.add_argument("--ckpt", default=str(tg.SIM / "checkpoints" / "netcov_final.pt"))
p.add_argument("--steps", type=int, default=4000)
p.add_argument("--steer", default="v2")
a = p.parse_args()

mcfg = tg.MissionConfig.load(str(tg.SIM / "netzabdeckung_config.yaml"), stage=4)
env = tg.NetCovEnv(mcfg, num_envs=1, device="cpu", seed=a.seed)
net = tg.AttnActorCritic(env.entity_dim, env.self_global_dim, env.team_global_dim, tg.NUM_ACTIONS, hidden=128)
net.load_state_dict(torch.load(a.ckpt, map_location="cpu"))
guard = tg.Guard(1, env.A, env.reserve_pct / 100.0, math.hypot(env.map_w, env.map_h), "cpu", steer=a.steer)
obs = env.reset()
print(f"Karte {env.map_w:.0f}x{env.map_h:.0f} m, Stationen aktiv {int(env.st_active.sum())}, "
      f"Wind {env.wind[0].tolist()} m/s, max Speed {env.max_speed:.1f} m/s, Reserve {env.reserve_pct:.0f} %")
print("Stationen:", [tuple(round(v) for v in env.st_pos[0, s].tolist()) for s in range(env.S) if env.st_active[0, s]])
for t in range(a.steps):
    with torch.no_grad():
        act = net.policy(obs["entities"], obs["alive"], obs["team"], obs["self_global"]).probs.argmax(-1)
    act, ch = guard.apply(obs, act)
    if t % 250 == 0:
        d = torch.cdist(env.pos[..., :2], env.st_pos)
        d = torch.where(env.st_active.unsqueeze(1), d, torch.full_like(d, 1e9)).min(-1).values[0]
        alive = env.alive[0]
        rows = []
        for i in range(env.A):
            if alive[i] and ch[0, i]:
                rows.append(f"#{i} d={d[i]:.0f}m b={env.battery[0, i]:.0f} v={env.vel[0, i, :2].norm():.1f} "
                            f"pos=({env.pos[0, i, 0]:.0f},{env.pos[0, i, 1]:.0f}) a={int(act[0, i])}")
        print(f"t={t} lebend={int(alive.sum())} laden_sim={int(env._charging_mask()[0].sum())} "
              f"wind={(env.wind + env.gust)[0].norm():.1f} | " + "; ".join(rows[:5]))
    obs, _, _, _ = env.step(act)
