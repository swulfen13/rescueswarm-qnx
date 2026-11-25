"""RescueSwarm – Bruecke zwischen der Schwarm-Simulation (PC) und QNX.

Laesst EINE Arena der bestehenden Netzabdeckungs-Simulation (swarm-sim,
env_netcov.py) auf der CPU laufen. In jedem Takt:

  1. Zustand aller Drohnen packen  -> UDP an das gateway auf QNX
  2. Antwort (eine Aktion pro Drohne) vom QNX-controller empfangen
  3. Simulation mit diesen Aktionen einen Schritt weiterrechnen

Kommt keine Antwort rechtzeitig, schweben alle Drohnen (Aktion 0) und der Takt
zaehlt als "verpasst".

  python qnx_bridge.py --qnx 192.168.56.103 --steps 600
  python qnx_bridge.py --qnx 192.168.56.103 --steps 2000 --csv out/run1.csv

Der Pfad zur swarm-sim wird ueber --sim oder die Umgebungsvariable SWARM_SIM
gesetzt (Standard: ../../../../ml projekts/drohene schwarm (ML)).
"""

from __future__ import annotations

import argparse
import csv
import math
import os
import socket
import struct
import sys
import time
from pathlib import Path

import numpy as np

# --- Protokoll (muss zu qnx/proto.h passen) ---
MAGIC_OBS = 0x31575352
MAGIC_ACT = 0x31415352
MAX_AGENTS = 32
AGENT_FLOATS = 24
OBS_HDR = struct.Struct("<IIHHff3f")            # magic, seq, n, agent_floats, reserve, diag, team_global[3]
ACT_HDR = struct.Struct("<IIHHIIHH")            # magic, seq, n, flags, compute_us, roundtrip_us, n_charging, n_overrides
FLAG_FALLBACK = 0x0001
FLAG_SAFETY = 0x0002

DEFAULT_SIM = Path(__file__).resolve().parents[4] / "ml projekts" / "drohene schwarm (ML)"


def load_sim(sim_dir: Path):
    sys.path.insert(0, str(sim_dir))
    from swarm_sim.mission_config import MissionConfig          # noqa: E402
    from swarm_sim.env_netcov import NetCovEnv                  # noqa: E402
    return MissionConfig, NetCovEnv


def pack_obs(seq: int, obs: dict, reserve: float, diag: float) -> tuple[bytes, int]:
    alive = obs["alive"][0].float().cpu().numpy()[:, None]           # (A,1)
    ent = obs["entities"][0].cpu().numpy()                           # (A,7)
    sg = obs["self_global"][0].cpu().numpy()                         # (A,16)
    tg = obs["team_global"][0, 0].cpu().numpy()                      # (3,)
    rows = np.concatenate([alive, ent, sg], axis=1).astype("<f4")    # (A,24)
    n = rows.shape[0]
    assert rows.shape[1] == AGENT_FLOATS and n <= MAX_AGENTS
    hdr = OBS_HDR.pack(MAGIC_OBS, seq, n, AGENT_FLOATS, reserve, diag, *tg.tolist())
    return hdr + rows.tobytes(), n


def main() -> None:
    p = argparse.ArgumentParser()
    ip_file = Path(__file__).resolve().parents[1] / "vm_ip.txt"
    default_ip = ip_file.read_text().strip() if ip_file.exists() else "192.168.56.101"
    p.add_argument("--qnx", default=default_ip, help="IP der QNX-VM (Standard: aus vm_ip.txt)")
    p.add_argument("--port", type=int, default=5555)
    p.add_argument("--steps", type=int, default=600)
    p.add_argument("--stage", type=int, default=4)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--timeout-ms", type=float, default=200.0)
    p.add_argument("--csv", default=None, help="Messwerte je Takt als CSV speichern")
    p.add_argument("--realtime", action="store_true",
                   help="im echten Takt der Simulation laufen (dt = 0,1 s -> 10 Hz) statt so schnell wie moeglich")
    p.add_argument("--live", action="store_true", help="Live-Ansicht (Karte + Kurven) anzeigen")
    p.add_argument("--sim", default=os.environ.get("SWARM_SIM", str(DEFAULT_SIM)))
    args = p.parse_args()

    sim_dir = Path(args.sim)
    MissionConfig, NetCovEnv = load_sim(sim_dir)
    import torch

    mcfg = MissionConfig.load(str(sim_dir / "netzabdeckung_config.yaml"), stage=args.stage)
    env = NetCovEnv(mcfg, num_envs=1, device="cpu", seed=args.seed)
    reserve = env.reserve_pct / 100.0
    diag = math.hypot(env.map_w, env.map_h)
    print(f"Simulation bereit: {env.A} Drohnen-Plaetze, Karte {env.map_w:.0f}x{env.map_h:.0f} m, "
          f"Takt {env.dt:.2f} s, Reserve {reserve*100:.0f} %, Stufe {args.stage}")

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(args.timeout_ms / 1000.0)
    target = (args.qnx, args.port)

    writer = None
    if args.csv:
        Path(args.csv).parent.mkdir(parents=True, exist_ok=True)
        fcsv = open(args.csv, "w", newline="")
        writer = csv.writer(fcsv)
        writer.writerow(["step", "served_pct", "alive_frac", "mean_battery", "charging_now",
                         "qnx_charging", "overrides", "compute_us", "qnx_roundtrip_us",
                         "pc_roundtrip_ms", "fallback", "missed"])

    obs = env.reset()
    missed = fallbacks = 0
    rtts, served_hist = [], []
    t_start = time.time()

    view = None
    if args.live:
        from live_view import LiveView
        view = LiveView(env)
    t_next = time.perf_counter()

    for step in range(1, args.steps + 1):
        if args.realtime:
            t_next += env.dt
            delay = t_next - time.perf_counter()
            if delay > 0:
                time.sleep(delay)
        payload, n = pack_obs(step, obs, reserve, diag)
        actions = np.zeros(n, dtype=np.int64)
        flags = compute_us = qnx_rt = n_chg = n_ov = 0
        got = False

        t0 = time.perf_counter()
        sock.sendto(payload, target)
        try:
            while True:                                   # alte, verspaetete Antworten verwerfen
                data, _ = sock.recvfrom(4096)
                magic, seq, rn, flags, compute_us, qnx_rt, n_chg, n_ov = ACT_HDR.unpack_from(data)
                if magic == MAGIC_ACT and seq == step:
                    actions = np.frombuffer(data, dtype=np.uint8, count=rn,
                                            offset=ACT_HDR.size).astype(np.int64)
                    got = True
                    break
        except socket.timeout:
            missed += 1
        rtt_ms = (time.perf_counter() - t0) * 1000.0
        if got:
            rtts.append(rtt_ms)
        if flags & FLAG_FALLBACK:
            fallbacks += 1

        act_t = torch.as_tensor(actions[: env.A], dtype=torch.long).unsqueeze(0)
        obs, _, _, info = env.step(act_t)
        served_hist.append(info["served_pct"])
        if view is not None:
            view.update(step, info, actions, compute_us, rtt_ms, bool(flags & FLAG_FALLBACK), n_ov)

        if writer:
            writer.writerow([step, f"{info['served_pct']:.2f}", f"{info['alive_frac']:.3f}",
                             f"{info['mean_battery']:.1f}", f"{info['charging_now']:.0f}",
                             n_chg, n_ov, compute_us, qnx_rt, f"{rtt_ms:.2f}",
                             int(bool(flags & FLAG_FALLBACK)), int(not got)])

        if step % 50 == 0 or step == args.steps:
            last = served_hist[-50:]
            print(f"Takt {step:5d} | versorgt {np.mean(last):5.1f} % | Akku {info['mean_battery']:5.1f} % "
                  f"| laden {info['charging_now']:4.1f} | lebend {info['alive_frac']*100:5.1f} % "
                  f"| QNX {compute_us:4d} us | Rundweg {np.median(rtts[-50:]) if rtts else float('nan'):5.2f} ms "
                  f"| verpasst {missed} | Fallback {fallbacks}")

    dur = time.time() - t_start
    print("\n=== Zusammenfassung ===")
    print(f"Takte: {args.steps} in {dur:.1f} s | verpasst: {missed} | Fallback (controller weg): {fallbacks}")
    if rtts:
        print(f"Rundweg PC->QNX->PC: Median {np.median(rtts):.2f} ms, 99 % {np.percentile(rtts, 99):.2f} ms")
    print(f"Versorgung im Schnitt: {np.mean(served_hist):.1f} %, Minimum {np.min(served_hist):.1f} %")
    if writer:
        fcsv.close()
        print(f"CSV: {args.csv}")


if __name__ == "__main__":
    main()
