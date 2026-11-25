"""Wie viel Versorgung ist in Stufe 4 ueberhaupt moeglich? (Uplink-Kapazitaet vs. Bedarf)"""
import torch
import train_with_guard as tg

mcfg = tg.MissionConfig.load(str(tg.SIM / "netzabdeckung_config.yaml"), stage=4)
for seed in range(6):
    env = tg.NetCovEnv(mcfg, num_envs=1, device="cpu", seed=seed)
    env.reset()
    act = env.hs_active[0]
    dem = env.hs_demand[0][act]
    prio = env.hs_prio[0][act]
    up = float(env.U * env.uplink_cap) if not torch.is_tensor(env.uplink_cap) else float((env.U * env.uplink_cap).flatten()[0])
    # Obergrenze: Uplink-Budget optimal nach Prioritaet verteilt (hoechste Prio pro Bedarf zuerst)
    order = torch.argsort(prio, descending=True)
    left, got = up, 0.0
    for i in order.tolist():
        take = min(float(dem[i]), left)
        got += prio[i].item() * take / float(dem[i])
        left -= take
    ceil = got / prio.sum().item()
    print(f"seed {seed}: Hotspots {int(act.sum())}, Bedarf {dem.sum():.0f}, Uplink {up:.0f} "
          f"(U={env.U}), Drohnen-Kap {float(env.cap_drone):.0f} x {int(env.alive.sum())}, "
          f"Obergrenze Versorgung ~{100 * ceil:.1f}%")
