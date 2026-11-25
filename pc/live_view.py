"""RescueSwarm – Live-Ansicht fuer die Demo.

Links: Draufsicht (Uplink, Ladestationen, Hotspots, Drohnen, Funkverbindungen).
Rechts: Versorgung, Drohnen in der Luft, QNX-Rechenzeit und Notbetrieb/Waechter-Eingriffe.

Wird von qnx_bridge.py mit --live benutzt. Ohne Bildschirm (z. B. Test) kann man
RS_LIVE_SAVE=ordner setzen, dann werden Bilder gespeichert statt angezeigt.
"""
from __future__ import annotations

import os
from collections import deque

import numpy as np

_TYPE_COLORS = ["#1f77b4", "#d62728", "#2ca02c", "#ff7f0e"]


class LiveView:
    def __init__(self, env, every: int = 3, history: int = 3000):
        import matplotlib
        self.save_dir = os.environ.get("RS_LIVE_SAVE")
        if self.save_dir:
            matplotlib.use("Agg")
            os.makedirs(self.save_dir, exist_ok=True)
        import matplotlib.pyplot as plt
        from matplotlib.collections import LineCollection
        self.plt = plt
        self.env = env
        # Video-Modus (RS_LIVE_VIDEO=1): 1920x1080, JPEG; RS_LIVE_EVERY = jeder n-te Takt ein Bild
        self.video = os.environ.get("RS_LIVE_VIDEO") == "1"
        self.every = int(os.environ.get("RS_LIVE_EVERY", every))
        self.frame = 0
        self.fb_hold = 0      # Notbetrieb-Hinweis ein paar Bilder stehen lassen (sonst nur 1 Bild sichtbar)

        plt.ion()
        self.fig = plt.figure(figsize=(16, 9) if self.video else (15, 8.2), facecolor="#0f1117")
        gs = self.fig.add_gridspec(4, 2, width_ratios=[1.25, 1], hspace=0.55, wspace=0.12)
        self.ax_map = self.fig.add_subplot(gs[:, 0])
        self.ax_srv = self.fig.add_subplot(gs[0, 1])
        self.ax_alive = self.fig.add_subplot(gs[1, 1])
        self.ax_cpu = self.fig.add_subplot(gs[2, 1])
        self.ax_evt = self.fig.add_subplot(gs[3, 1])
        for ax in (self.ax_map, self.ax_srv, self.ax_alive, self.ax_cpu, self.ax_evt):
            ax.set_facecolor("#161a23")
            ax.tick_params(colors="#9aa4b2", labelsize=8)
            for s in ax.spines.values():
                s.set_color("#2a3140")

        W, H = env.map_w, env.map_h
        m = self.ax_map
        m.set_xlim(0, W); m.set_ylim(0, H); m.set_aspect("equal")
        m.set_xticks([]); m.set_yticks([])
        self.links = LineCollection([], colors="#4fc3f7", linewidths=1.4, alpha=0.8, zorder=2)
        m.add_collection(self.links)
        self.sc_hs = m.scatter([], [], s=[], zorder=3)
        self.sc_st = m.scatter([], [], marker="s", s=200, c="#90caf9", edgecolors="white", zorder=4)
        self.sc_up = m.scatter([], [], marker="*", s=600, c="gold", edgecolors="black", zorder=5)
        self.sc_dr = m.scatter([], [], s=60, zorder=6, edgecolors="black", linewidths=0.5)
        self.title = m.set_title("", color="white", fontsize=10, loc="left")
        m.text(0.99, 0.99, "★ uplink   ■ charger   ● sites (size = demand)   • drones (colour = battery)\n"
               "lines = radio path to the uplink", transform=m.transAxes, ha="right", va="top",
               color="#b0bec5", fontsize=8)
        self.badge = m.text(0.01, 0.01, "", transform=m.transAxes, color="white", fontsize=10,
                            bbox=dict(facecolor="#2e7d32", edgecolor="none", boxstyle="round,pad=0.4"))

        self.t = deque(maxlen=history)
        self.srv = deque(maxlen=history)
        self.upl = deque(maxlen=history)
        self.alive = deque(maxlen=history)
        self.cpu = deque(maxlen=history)
        self.fb = deque(maxlen=history)
        self.ov = deque(maxlen=history)

        def mk(ax, title, color, ylim=None):
            ax.set_title(title, color="white", fontsize=9, loc="left")
            (ln,) = ax.plot([], [], color=color, lw=1.4)
            if ylim:
                ax.set_ylim(*ylim)
            return ln
        self.l_srv = mk(self.ax_srv, "Sites online (blue) · uplink capacity used (green), %", "#4fc3f7", (0, 105))
        (self.l_upl,) = self.ax_srv.plot([], [], color="#66bb6a", lw=1.4)
        self.l_alive = mk(self.ax_alive, "Drones in the air", "#4fc3f7", (0, env.A + 1))
        self.l_cpu = mk(self.ax_cpu, "QNX: AI + safety guard per control step (ms)  ·  step = 100 ms", "#ffca28")
        self.l_fb = mk(self.ax_evt, "Fail-safe hover (controller down) / safety-guard overrides", "#ef5350")
        (self.l_ov,) = self.ax_evt.plot([], [], color="#ab47bc", lw=1.0)
        self.fig.suptitle("RescueSwarm  ·  swarm AI on QNX 8.0", color="white", fontsize=14, x=0.02, ha="left")

    def _links(self, pos, alive, up, radius):
        """Nur den Funkbaum zeichnen: jede Drohne mit ihrem naechsten Schritt Richtung Uplink (BFS)."""
        idx = [int(i) for i in np.where(alive)[0]]
        nodes = [up[u] for u in range(up.shape[0])] + [pos[i, :2] for i in idx]
        n_up = up.shape[0]
        parent = {u: None for u in range(n_up)}
        frontier = list(range(n_up))
        while frontier:
            nxt = []
            for a in frontier:
                for b in range(n_up, len(nodes)):
                    if b not in parent and np.linalg.norm(nodes[a] - nodes[b]) <= radius:
                        parent[b] = a
                        nxt.append(b)
            frontier = nxt
        return [[nodes[b], nodes[a]] for b, a in parent.items() if a is not None]

    def update(self, step, info, actions, compute_us, rtt_ms, fallback, overrides):
        e = self.env
        tmin = step * e.dt / 60.0
        self.t.append(tmin)
        self.srv.append(info.get("linked_pct", info["served_pct"]))
        self.upl.append(info.get("uplink_pct", 0.0))
        self.alive.append(float(e.alive[0].sum()))
        self.cpu.append(compute_us / 1000.0)
        self.fb.append(1.0 if fallback else 0.0)
        self.ov.append(float(overrides))
        if fallback:
            self.fb_hold = 25
        if step % self.every:
            return

        pos = e.pos[0].cpu().numpy()
        alive = e.alive[0].cpu().numpy()
        batt = (e.battery[0] / 100.0).cpu().numpy()
        up = e.up_pos[0].cpu().numpy()
        st = e.st_pos[0].cpu().numpy()[e.st_active[0].cpu().numpy()]
        hs_a = e.hs_active[0].cpu().numpy()
        hs = e.hs_pos[0].cpu().numpy()[hs_a]
        hs_t = e.hs_type[0].cpu().numpy()[hs_a]
        hs_d = e.hs_demand[0].cpu().numpy()[hs_a]

        self.links.set_segments(self._links(pos, alive, up, e.dd_range * max(1.0 - e.min_sig, 0.0) ** 0.5))
        if len(hs):
            self.sc_hs.set_offsets(hs)
            self.sc_hs.set_sizes(80 + 400 * hs_d / max(hs_d.max(), 1e-6))
            self.sc_hs.set_color([_TYPE_COLORS[int(t) % 4] for t in hs_t])
            self.sc_hs.set_alpha(0.45)
        self.sc_st.set_offsets(st if len(st) else np.zeros((0, 2)))
        self.sc_up.set_offsets(up)
        p = pos[alive, :2]
        self.sc_dr.set_offsets(p if len(p) else np.zeros((0, 2)))
        if len(p):
            b = batt[alive]
            self.sc_dr.set_facecolor(self.plt.cm.RdYlGn(np.clip(b, 0, 1)))
        self.title.set_text(f"t = {tmin:5.1f} min   |   sites online {info.get('linked_pct', 0):3.0f} %   |   "
                            f"uplink used {info.get('uplink_pct', 0):3.0f} %   |   drones {int(alive.sum())}")
        if self.fb_hold > 0:
            self.fb_hold -= 1
            self.badge.set_text("QNX: controller killed – swarm holds position – watchdog restarted it")
            self.badge.get_bbox_patch().set_facecolor("#c62828")
        else:
            self.badge.set_text(f"QNX: AI {compute_us/1000:.2f} ms  ·  round trip {rtt_ms:.1f} ms  ·  guard overrides {overrides}")
            self.badge.get_bbox_patch().set_facecolor("#2e7d32")

        t = list(self.t)
        for ln, data, ax in ((self.l_srv, self.srv, self.ax_srv), (self.l_upl, self.upl, self.ax_srv),
                             (self.l_alive, self.alive, self.ax_alive),
                             (self.l_cpu, self.cpu, self.ax_cpu), (self.l_fb, self.fb, self.ax_evt),
                             (self.l_ov, self.ov, self.ax_evt)):
            ln.set_data(t, list(data))
            ax.set_xlim(t[0], max(t[-1], t[0] + 0.1))
        self.ax_cpu.set_ylim(0, max(2.0, max(self.cpu) * 1.2))
        self.ax_evt.set_ylim(-0.1, max(1.5, max(self.ov) + 0.5))

        if self.save_dir:
            if self.video:
                self.fig.savefig(os.path.join(self.save_dir, f"frame_{self.frame:05d}.jpg"), dpi=120,
                                 facecolor=self.fig.get_facecolor(), pil_kwargs={"quality": 92})
            else:
                self.fig.savefig(os.path.join(self.save_dir, f"frame_{self.frame:05d}.png"), dpi=80,
                                 facecolor=self.fig.get_facecolor())
        else:
            self.fig.canvas.draw_idle()
            self.fig.canvas.flush_events()
        self.frame += 1
