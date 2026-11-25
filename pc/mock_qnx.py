"""Test-Attrappe fuer gateway+controller (nur zum Testen der Bruecke ohne QNX).

Spiegelt die Regeln aus qnx/controller.c in Python. Nicht Teil der Demo.
  python mock_qnx.py            # lauscht auf 127.0.0.1:5555
"""
import math
import socket
import struct

import numpy as np

OBS_HDR = struct.Struct("<IIHHff3f")
ACT_HDR = struct.Struct("<IIHHIIHH")
C_ALIVE, C_ALT, C_ST_DX, C_ST_DY, C_ST_D, C_GAP_DX, C_GAP_DY, C_GAP_D, C_BATT = 0, 3, 11, 12, 13, 14, 15, 16, 17
charging = np.zeros(32, dtype=bool)


def dir_to_action(dx, dy):
    if abs(dx) < 1e-6 and abs(dy) < 1e-6:
        return 0
    k = int(round(math.atan2(dy, dx) / (math.pi / 4))) % 8
    return 1 + k


def control(rows, reserve, diag, net=None, safety=True):
    n = rows.shape[0]
    act = np.zeros(n, dtype=np.uint8)
    if net is not None:
        import torch
        t = torch.from_numpy(rows.copy()).unsqueeze(0)
        with torch.no_grad():
            lg = net.actor_logits(t[..., 1:8], t[..., 0] > 0.5, torch.zeros(1, n, dtype=torch.long), t[..., 8:24])
        act = lg[0].argmax(-1).numpy().astype(np.uint8)
        if not safety:
            return act, 0, 0
    for i, r in enumerate(rows if net is None else []):
        if r[C_ALIVE] < 0.5:
            continue
        if r[C_ALT] < 0.25:
            act[i] = 9
        elif r[C_GAP_D] * diag < 120:
            act[i] = 0
        else:
            act[i] = dir_to_action(r[C_GAP_DX], r[C_GAP_DY])
    if not safety:
        return act, 0, 0
    alive = rows[:, C_ALIVE] >= 0.5
    for i in range(n):
        if not alive[i]:
            charging[i] = False
            continue
        if charging[i] and rows[i, C_BATT] >= 0.95:
            charging[i] = False
        if rows[i, C_BATT] < reserve:
            charging[i] = True
    limit = math.ceil(alive.sum() * 0.3)
    while charging[:n].sum() < limit:
        cand = [i for i in range(n) if alive[i] and not charging[i] and rows[i, C_BATT] < reserve + 0.15]
        if not cand:
            break
        charging[min(cand, key=lambda i: rows[i, C_BATT])] = True
    ov = 0
    for i in range(n):
        if alive[i] and charging[i]:
            a = 0 if rows[i, C_ST_D] * diag < 100 else dir_to_action(rows[i, C_ST_DX], rows[i, C_ST_DY])
            ov += int(a != act[i])
            act[i] = a
    return act, int(charging[:n].sum()), ov


def main():
    import argparse, sys
    ap = argparse.ArgumentParser()
    ap.add_argument("--policy", default=None, help="Checkpoint (.pt) fuer KI-Flug statt Regeln")
    ap.add_argument("--sim", default=None)
    ap.add_argument("--no-safety", action="store_true")
    ap.add_argument("--port", type=int, default=5555)
    a = ap.parse_args()
    net = None
    if a.policy:
        import torch
        sys.path.insert(0, a.sim)
        from swarm_sim.attn import AttnActorCritic
        net = AttnActorCritic(7, 16, 3, 11, hidden=128)
        net.load_state_dict(torch.load(a.policy, map_location="cpu")); net.eval()
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(("127.0.0.1", a.port))
    print("mock_qnx: lausche auf 127.0.0.1:5555")
    while True:
        data, addr = s.recvfrom(8192)
        magic, seq, n, af, reserve, diag, *_ = OBS_HDR.unpack_from(data)
        rows = np.frombuffer(data, dtype="<f4", offset=OBS_HDR.size, count=n * af).reshape(n, af)
        act, nchg, ov = control(rows, reserve, diag, net, not a.no_safety)
        s.sendto(ACT_HDR.pack(0x31415352, seq, n, 2 if ov else 0, 1, 1, nchg, ov) + act.tobytes(), addr)


if __name__ == "__main__":
    main()
