"""Exportiert die trainierte Actor-Policy (AttnActorCritic) nach policy.bin fuer QNX.

  python export_policy.py "<pfad>/checkpoints/netcov_final.pt" ../qnx/policy.bin

Format: 5 x uint32 [magic, H, De, Dsg, Na], danach float32 little-endian in fester Reihenfolge:
embed.0 (W,b), embed.2 (W,b), q, k, v, actor_head.0, actor_head.2
"""
import struct
import sys

import numpy as np
import torch

MAGIC = 0x31504352
ORDER = ["embed.0", "embed.2", "q", "k", "v", "actor_head.0", "actor_head.2"]


def main():
    ckpt, out = sys.argv[1], sys.argv[2]
    sd = torch.load(ckpt, map_location="cpu")
    H, De = sd["embed.0.weight"].shape
    Na = sd["actor_head.2.weight"].shape[0]
    Dsg = sd["actor_head.0.weight"].shape[1] - 3 * H
    with open(out, "wb") as f:
        f.write(struct.pack("<5I", MAGIC, H, De, Dsg, Na))
        n = 0
        for name in ORDER:
            for part in ("weight", "bias"):
                arr = sd[f"{name}.{part}"].detach().numpy().astype("<f4")
                f.write(arr.tobytes())
                n += arr.size
    print(f"{out}: H={H} De={De} Dsg={Dsg} Aktionen={Na}, {n} Gewichte ({n*4/1024:.0f} KB)")


if __name__ == "__main__":
    main()
