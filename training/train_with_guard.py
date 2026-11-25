"""Nachtraining der Netzabdeckungs-Policy MIT dem QNX-Sicherheitswaechter in der Simulation.

Idee: Auf QNX ueberstimmt der Waechter die KI beim Laden. Also trainieren wir die KI genau so:
jede Drohne, die der Waechter gerade zum Laden schickt, fliegt nach Waechter-Regel, und diese
Entscheidungen zaehlen NICHT fuer den PPO-Verlust (die KI hat sie ja nicht getroffen).
Die KI lernt nur noch das, was sie auf QNX wirklich entscheidet: wo die Drohnen stehen.

Basiert auf train_netcov.py aus swarm-sim (unveraendert, nur importiert). Checkpoints landen in
./checkpoints dieses Ordners, NICHT bei swarm-sim.

  python train_with_guard.py --resume <swarm-sim>/checkpoints/netcov_final.pt --updates 1500
"""
from __future__ import annotations

import argparse
import math
import os
import sys
import time
from collections import deque
from pathlib import Path

import torch
import torch.nn as nn

HERE = Path(__file__).resolve().parent
SIM = Path(os.environ.get("SWARM_SIM", HERE.parents[3] / "ml projekts" / "drohene schwarm (ML)"))
sys.path.insert(0, str(SIM))

from swarm_sim import TrainConfig, MetricsLogger                      # noqa: E402
from swarm_sim.mission_config import MissionConfig                     # noqa: E402
from swarm_sim.env_netcov import NetCovEnv, NUM_ACTIONS                # noqa: E402
from swarm_sim.attn import AttnActorCritic                             # noqa: E402
from swarm_sim.mappo import compute_gae                                # noqa: E402

# Spalten in self_global (siehe qnx/proto.h: Index dort minus 8)
SG_ST_DX, SG_ST_DY, SG_ST_D, SG_BATT = 3, 4, 5, 9
ENT_ALT = 2
# Parameter wie im QNX-controller (qnx/controller.c)
CHARGE_START_MARGIN, CHARGE_DONE, MAX_CHARGING_FRAC, HOLD_STATION_M = 0.15, 0.95, 0.30, 100.0
# Wind-Steuerung (v2): Werte aus netzabdeckung_config.yaml (drone.max_geschwindigkeit_ms / max_beschleunigung_ms2)
V_MAX, A_MAX, STEER_TAU, APPROACH_GAIN, APPROACH_OFFSET = 15.0, 5.0, 1.5, 0.3, 40.0
SG_WIND_X, SG_WIND_Y, ENT_VX, ENT_VY = 11, 12, 3, 4
SG_UP_DX, SG_UP_DY, SG_UP_D, SG_CONN = 0, 1, 2, 10
_DIR9 = torch.tensor([[0.0, 0.0]] + [[math.cos(k * math.pi / 4), math.sin(k * math.pi / 4)] for k in range(8)])


class Guard:
    """Vektorisierte Kopie des Sicherheitswaechters aus qnx/controller.c."""

    def __init__(self, E: int, A: int, reserve: float, diag: float, device, steer: str = "v1", link: bool = False):
        self.charging = torch.zeros(E, A, dtype=torch.bool, device=device)
        self.reserve, self.diag, self.steer, self.link = reserve, diag, steer, link

    def reset(self):
        self.charging.zero_()

    def apply(self, obs, action):
        alive = obs["alive"]
        sg = obs["self_global"]
        batt = sg[..., SG_BATT]
        ch = self.charging & alive
        ch &= ~(batt >= CHARGE_DONE)
        ch |= alive & (batt < self.reserve)
        limit = torch.ceil(alive.float().sum(-1) * MAX_CHARGING_FRAC)              # (E,)
        free = (limit - ch.float().sum(-1)).clamp(min=0)                           # (E,)
        cand = alive & ~ch & (batt < self.reserve + CHARGE_START_MARGIN)
        key = torch.where(cand, batt, torch.full_like(batt, 9.0))
        order = key.argsort(dim=-1)
        rank = torch.empty_like(order)
        rank.scatter_(-1, order, torch.arange(order.shape[-1], device=order.device).expand_as(order))
        ch |= cand & (rank < free.unsqueeze(-1))
        self.charging = ch

        if self.steer == "v2":
            a_guard = self.steer_v2(obs)
        else:
            # v1: Richtung zur Station -> Aktion 1..8, nah dran -> schweben (0)
            ang = torch.atan2(sg[..., SG_ST_DY], sg[..., SG_ST_DX])
            k = torch.round(ang / (math.pi / 4)).long() % 8
            a_guard = torch.where(sg[..., SG_ST_D] * self.diag < HOLD_STATION_M, torch.zeros_like(k), 1 + k)
        out = torch.where(ch, a_guard, action)
        if self.link:
            # Funk-Waechter: Drohne ohne Verbindung zum Uplink fliegt Richtung Uplink, bis sie wieder im Netz ist
            lost = alive & ~ch & (sg[..., SG_CONN] < 0.5)
            a_link = self._steer(obs, SG_UP_DX, SG_UP_DY, SG_UP_D)
            out = torch.where(lost, a_link, out)
        return out, ch

    def steer_v2(self, obs):
        return self._steer(obs, SG_ST_DX, SG_ST_DY, SG_ST_D)

    def _steer(self, obs, ix, iy, idist):
        """Wind-kompensierte Steuerung: Wunschgeschwindigkeit zur Station (am Ziel 0),
        benoetigte Beschleunigung = (v_soll - v)/tau - Wind, dann die passendste der 9 Aktionen."""
        sg, ent = obs["self_global"], obs["entities"]
        u = sg[..., [ix, iy]]
        d = sg[..., idist] * self.diag
        v = ent[..., [ENT_VX, ENT_VY]] * V_MAX
        w = sg[..., [SG_WIND_X, SG_WIND_Y]] * V_MAX
        speed = ((d - APPROACH_OFFSET) * APPROACH_GAIN).clamp(0.0, V_MAX)
        a_req = (u * speed.unsqueeze(-1) - v) / STEER_TAU - w
        cand = _DIR9.to(sg.device) * A_MAX                                         # (9,2)
        err = (a_req.unsqueeze(-2) - cand).norm(dim=-1)                            # (...,9)
        return err.argmin(dim=-1)


def train(args):
    mcfg = MissionConfig.load(args.config, stage=args.stage)
    env = NetCovEnv(mcfg, num_envs=args.envs, device="cpu" if args.cpu else "cuda")
    dev = env.device
    tcfg = TrainConfig()
    tcfg.gamma = 0.9995
    tcfg.rollout_len = 64
    tcfg.lr = args.lr

    net = AttnActorCritic(env.entity_dim, env.self_global_dim, env.team_global_dim,
                          NUM_ACTIONS, hidden=tcfg.hidden).to(dev)
    if args.resume:
        net.load_state_dict(torch.load(args.resume, map_location=dev))
        print(f"Start von {args.resume}")
    opt = torch.optim.Adam(net.parameters(), lr=tcfg.lr)
    team_row = env.agent_team_index().to(dev)
    guard = Guard(env.E, env.A, env.reserve_pct / 100.0, math.hypot(env.map_w, env.map_h), dev,
                  steer=args.steer)

    E, A, T, R = env.E, env.A, env.T, tcfg.rollout_len
    ckpt_dir = HERE / "checkpoints"
    ckpt_dir.mkdir(parents=True, exist_ok=True)
    obs = env.reset()
    best = -1.0
    served_hist = deque(maxlen=25)

    def policy_value(o):
        dist = net.policy(o["entities"], o["alive"], o["team"], o["self_global"])
        val = net.agent_values(o["entities"], o["alive"], o["team"], o["team_global"])
        return dist, val

    with MetricsLogger(run_name=args.name, logdir=str(HERE / "runs")) as log:
        print(f"Training MIT Waechter auf {dev}: {E} Arenen, Stufe {args.stage}, {args.updates} Updates")
        gstep, t0 = 0, time.perf_counter()
        for update in range(1, args.updates + 1):
            ent_b = torch.empty(R, E, A, env.entity_dim, device=dev)
            alive_b = torch.empty(R, E, A, dtype=torch.bool, device=dev)
            sg_b = torch.empty(R, E, A, env.self_global_dim, device=dev)
            tg_b = torch.empty(R, E, T, env.team_global_dim, device=dev)
            act_b = torch.empty(R, E, A, dtype=torch.long, device=dev)
            logp_b = torch.empty(R, E, A, device=dev)
            val_b = torch.empty(R, E, A, device=dev)
            rew_b = torch.empty(R, E, A, device=dev)
            own_b = torch.empty(R, E, A, dtype=torch.bool, device=dev)   # Entscheidung von der KI?
            acc = {}
            for r in range(R):
                with torch.no_grad():
                    dist, val = policy_value(obs)
                    action = dist.sample()
                    logp = dist.log_prob(action)
                    exec_action, overridden = guard.apply(obs, action)
                ent_b[r] = obs["entities"]; alive_b[r] = obs["alive"]
                sg_b[r] = obs["self_global"]; tg_b[r] = obs["team_global"]
                act_b[r] = action; logp_b[r] = logp; val_b[r] = val
                own_b[r] = ~overridden
                obs, reward, done, info = env.step(exec_action)
                if bool(done.any()):
                    guard.reset()
                rew_b[r] = reward
                for k, vv in info.items():
                    acc[k] = acc.get(k, 0.0) + (vv if isinstance(vv, (int, float)) else 0.0)
                gstep += E

            with torch.no_grad():
                _, last_val = policy_value(obs)
            adv, returns = compute_gae(rew_b, val_b, last_val, tcfg.gamma, tcfg.gae_lambda)
            M = R * E
            ent = ent_b.reshape(M, A, env.entity_dim); alive = alive_b.reshape(M, A)
            sg = sg_b.reshape(M, A, env.self_global_dim); tg = tg_b.reshape(M, T, env.team_global_dim)
            acts = act_b.reshape(M, A); old_logp = logp_b.reshape(M, A)
            rets = returns.reshape(M, A); adv_a = adv.reshape(M, A); own = own_b.reshape(M, A)
            team_b = team_row.unsqueeze(0).expand(M, A)
            pm = (alive & own).float()                        # Policy-Maske: nur eigene KI-Entscheidungen
            mean = (adv_a * pm).sum() / pm.sum().clamp(min=1)
            var = ((adv_a - mean) ** 2 * pm).sum() / pm.sum().clamp(min=1)
            adv_a = (adv_a - mean) / (var.sqrt() + 1e-8)

            mb = max(1, M // tcfg.minibatches)
            for _ in range(tcfg.epochs):
                perm = torch.randperm(M, device=dev)
                for b in range(tcfg.minibatches):
                    sl = perm[b * mb:(b + 1) * mb]
                    if sl.numel() == 0:
                        continue
                    o = {"entities": ent[sl], "alive": alive[sl], "team": team_b[sl],
                         "self_global": sg[sl], "team_global": tg[sl]}
                    dist, val = policy_value(o)
                    logp = dist.log_prob(acts[sl])
                    am = alive[sl].float(); pmb = pm[sl]
                    ratio = torch.exp(logp - old_logp[sl])
                    a = adv_a[sl]
                    pl = -(torch.min(ratio * a, torch.clamp(ratio, 1 - tcfg.clip, 1 + tcfg.clip) * a) * pmb).sum() \
                        / pmb.sum().clamp(min=1)
                    entropy = (dist.entropy() * pmb).sum() / pmb.sum().clamp(min=1)
                    vl = (((val - rets[sl]) ** 2) * am).sum() / am.sum().clamp(min=1)
                    loss = pl - tcfg.entropy_coef * entropy + tcfg.value_coef * vl
                    opt.zero_grad(); loss.backward()
                    nn.utils.clip_grad_norm_(net.parameters(), tcfg.max_grad_norm)
                    opt.step()

            served = acc.get("served_pct", 0.0) / R
            served_hist.append(served)
            log.log({"guard/served_pct": served,
                     "guard/alive_frac": acc.get("alive_frac", 0.0) / R,
                     "guard/charging_now": acc.get("charging_now", 0.0) / R,
                     "guard/mean_battery_pct": acc.get("mean_battery", 0.0) / R,
                     "guard/override_frac": 1.0 - own.float().mean().item()}, gstep)
            if update % 25 == 0 or update == 1:
                sps = gstep / (time.perf_counter() - t0)
                print(f"Update {update:5d} | versorgt {served:5.1f}% (Schnitt 25: {sum(served_hist)/len(served_hist):5.1f}%) "
                      f"| Akku {acc.get('mean_battery', 0.0)/R:4.0f}% | Waechter {100*(1-own.float().mean().item()):4.1f}% "
                      f"| {sps:,.0f} steps/s", flush=True)
            avg = sum(served_hist) / len(served_hist)
            if len(served_hist) == served_hist.maxlen and avg > best:
                best = avg
                torch.save(net.state_dict(), ckpt_dir / f"{args.name}_best.pt")
            if update % 100 == 0:
                torch.save(net.state_dict(), ckpt_dir / f"{args.name}_update{update}.pt")
        torch.save(net.state_dict(), ckpt_dir / f"{args.name}_final.pt")
        print(f"Fertig. Bestes 25er-Mittel: {best:.1f}%  ->  checkpoints/{args.name}_best.pt")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--resume", default=str(SIM / "checkpoints" / "netcov_final.pt"))
    p.add_argument("--updates", type=int, default=1500)
    p.add_argument("--envs", type=int, default=256)
    p.add_argument("--stage", type=int, default=4)
    p.add_argument("--lr", type=float, default=1e-4)
    p.add_argument("--name", default=f"guard_{int(time.time())}")
    p.add_argument("--cpu", action="store_true")
    p.add_argument("--config", default=str(SIM / "netzabdeckung_config.yaml"), help="Missions-Config (z. B. ../scenarios/stadt.yaml)")
    p.add_argument("--steer", default="v2", choices=["v1", "v2"], help="Waechter-Steuerung wie im controller (v2 = wind-kompensiert)")
    train(p.parse_args())


if __name__ == "__main__":
    main()
