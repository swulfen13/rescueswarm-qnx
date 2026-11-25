"""RescueSwarm-Video: Karten-/Diagramm-Szenen zeichnen, Live-Clips beschriften, alles zusammensetzen.

  python3 make_video.py                 # alle Szenen + Zusammenschnitt (ohne Ton)
  python3 make_video.py --only s4       # nur eine Szene neu
Dauer je Szene steht in DUR (spaeter an die Sprecher-Laenge anpassen).
"""
import argparse
import csv
import json
import math
import os
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H, FPS = 1920, 1080, 30
HERE = Path(__file__).parent
IN, OUT = HERE / "in", HERE / "scenes"
OUT.mkdir(exist_ok=True)

BG, PANEL, LINE = (15, 17, 23), (24, 28, 38), (42, 49, 64)
TEXT, MUTED = (232, 234, 240), (154, 164, 178)
AMBER, SKY, GREEN, RED, GREY = (255, 202, 40), (79, 195, 247), (124, 203, 127), (239, 108, 108), (92, 100, 116)

FONT_DIR = "/usr/share/fonts/opentype/inter/"
def font(size, weight="Regular"):
    return ImageFont.truetype(FONT_DIR + f"Inter-{weight}.otf", size)

DUR_FILE = HERE / "durations.json"
DUR = {"s1": 18.0, "s2": 21.0, "s3": 19.0, "s4": 21.0, "s5": 16.0, "s6": 16.0, "s7": 24.0, "s8": 14.0}
if DUR_FILE.exists():
    DUR.update(json.loads(DUR_FILE.read_text()))

ENC = ["-c:v", "libx264", "-crf", "18", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-r", str(FPS)]


def ease(x):
    x = max(0.0, min(1.0, x))
    return x * x * (3 - 2 * x)


def alpha_col(c, a, bg=BG):
    return tuple(int(bg[i] + (c[i] - bg[i]) * a) for i in range(3))


class Writer:
    """Frames per Pipe an ffmpeg; schreibt erst unter .tmp.mp4, benennt nach Erfolg um."""
    def __init__(self, name):
        self.final = OUT / f"{name}.mp4"
        self.tmp = OUT / f"{name}.tmp.mp4"
        self.p = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
                                   "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", *ENC, str(self.tmp)],
                                  stdin=subprocess.PIPE)

    def add(self, img):
        self.p.stdin.write(img.tobytes())

    def close(self):
        self.p.stdin.close()
        if self.p.wait() == 0:
            os.replace(self.tmp, self.final)
        else:
            raise RuntimeError(f"ffmpeg failed for {self.final}")


def fade_global(t, dur, fin=0.5, fout=0.5):
    return min(ease(t / fin), ease((dur - t) / fout))


def text(d, xy, s, f, col, anchor="la"):
    if col == BG:          # unsichtbar: nicht zeichnen (sonst ueberdeckt BG-Text andere Schrift)
        return
    d.text(xy, s, font=f, fill=col, anchor=anchor)


def eyebrow(d, s, a):
    text(d, (140, 120), s.upper(), font(28, "SemiBold"), alpha_col(AMBER, a))


# ---------------------------------------------------------------- Szene 1: Titel + Problem
def s1():
    dur = DUR["s1"]; w = Writer("s1")
    for i in range(int(dur * FPS)):
        t = i / FPS
        img = Image.new("RGB", (W, H), BG); d = ImageDraw.Draw(img)
        g = fade_global(t, dur, 0.8, 0.5)
        # Titelphase 0..6 s, dann wandert der Titel nach oben, Problem-Saetze erscheinen
        k = ease((t - 2.6) / 1.2)
        ty = 430 - 290 * k
        a = ease(t / 1.2) * g
        text(d, (W // 2, ty), "RescueSwarm", font(150, "Bold"), alpha_col(TEXT, a), "mm")
        text(d, (W // 2, ty + 115), "Swarm AI on QNX 8.0", font(48, "Medium"), alpha_col(SKY, a * (1 - 0.0 * k)), "mm")
        lines = [("Earthquake. Flood.", 3.3), ("Cell towers go dark.", 6.3), ("Rescue teams lose contact.", 8.3)]
        for j, (s, t0) in enumerate(lines):
            aa = ease((t - t0) / 0.8) * g
            text(d, (W // 2, 520 + j * 110), s, font(72, "SemiBold"), alpha_col(TEXT, aa), "mm")
        aa = ease((t - 12.9) / 0.8) * g
        text(d, (W // 2, 900), "A drone swarm rebuilds the network – with its brain on QNX.",
             font(40, "Medium"), alpha_col(AMBER, aa), "mm")
        w.add(img)
    w.close()


# ---------------------------------------------------------------- Szene 2: Architektur
def box(d, x, y, bw, bh, title, sub, col, a):
    d.rounded_rectangle((x, y, x + bw, y + bh), 18, fill=alpha_col(PANEL, a), outline=alpha_col(col, a), width=3)
    text(d, (x + bw // 2, y + bh // 2 - (18 if sub else 0)), title, font(38, "SemiBold"), alpha_col(TEXT, a), "mm")
    if sub:
        text(d, (x + bw // 2, y + bh // 2 + 26), sub, font(26), alpha_col(MUTED, a), "mm")


def arrow(d, x1, y1, x2, y2, col, a, label=None, lab_dy=-26):
    c = alpha_col(col, a)
    d.line((x1, y1, x2, y2), fill=c, width=4)
    ang = math.atan2(y2 - y1, x2 - x1)
    for s in (+1, -1):
        d.line((x2, y2, x2 - 18 * math.cos(ang + s * 0.45), y2 - 18 * math.sin(ang + s * 0.45)), fill=c, width=4)
    if label:
        text(d, ((x1 + x2) // 2, (y1 + y2) // 2 + lab_dy), label, font(26, "Medium"), alpha_col(MUTED, a), "mm")


def s2():
    dur = DUR["s2"]; w = Writer("s2")
    for i in range(int(dur * FPS)):
        t = i / FPS
        img = Image.new("RGB", (W, H), BG); d = ImageDraw.Draw(img)
        g = fade_global(t, dur)
        A = lambda t0: ease((t - t0) / 0.7) * g
        eyebrow(d, "How it works", A(0))
        text(d, (140, 175), "The AI flies. QNX keeps it safe.", font(64, "Bold"), alpha_col(TEXT, A(0)))
        # PC-Seite
        box(d, 140, 420, 420, 200, "Simulation (PC)", "swarm-sim · PyTorch physics", GREY, A(1.0))
        # QNX-Rahmen
        qa = A(3.0)
        d.rounded_rectangle((760, 300, 1780, 960), 28, outline=alpha_col(SKY, qa), width=3)
        text(d, (790, 330), "QNX 8.0", font(34, "Bold"), alpha_col(SKY, qa))
        box(d, 800, 420, 330, 200, "gateway", "UDP ↔ messages", SKY, A(3.5))
        ca = A(6.0)
        d.rounded_rectangle((1300, 380, 1740, 680), 18, fill=alpha_col(PANEL, ca), outline=alpha_col(SKY, ca), width=3)
        text(d, (1520, 425), "controller", font(38, "SemiBold"), alpha_col(TEXT, ca), "mm")
        text(d, (1520, 495), "AI policy in C", font(30, "SemiBold"), alpha_col(AMBER, A(6.5)), "mm")
        text(d, (1520, 535), "120k weights · ~1 ms", font(26), alpha_col(MUTED, A(6.5)), "mm")
        text(d, (1520, 600), "safety guard", font(30, "SemiBold"), alpha_col(GREEN, A(15.0)), "mm")
        text(d, (1520, 640), "batteries · wind · radio links", font(26), alpha_col(MUTED, A(15.0)), "mm")
        box(d, 1040, 760, 440, 150, "watchdog", "restarts crashed processes", RED, A(11.5))
        arrow(d, 560, 520, 800, 520, MUTED, A(2.0), "UDP · 10 Hz")
        arrow(d, 1130, 520, 1300, 520, SKY, A(4.5), "MsgSend", -26)
        arrow(d, 1100, 760, 990, 626, RED, A(12.0))
        arrow(d, 1420, 760, 1500, 686, RED, A(12.0))
        w.add(img)
    w.close()


# ---------------------------------------------------------------- Live-Clips mit Bauchbinde
def caption_png(name, title, sub, col=AMBER):
    """Kompakte Bauchbinde oben rechts (unten links sitzt das QNX-Statusfeld der Live-Ansicht)."""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(img)
    f1, f2 = font(32, "Bold"), font(24, "Medium")
    tw = max(d.textlength(title, font=f1), d.textlength(sub, font=f2)) + 56
    x1 = W - 30; x0 = x1 - tw
    d.rounded_rectangle((x0, 10, x1, 98), 14, fill=(15, 17, 23, 235), outline=col + (255,), width=3)
    d.text((x0 + 28, 20), title, font=f1, fill=col + (255,))
    d.text((x0 + 28, 62), sub, font=f2, fill=TEXT + (255,))
    p = OUT / f"cap_{name}.png"; img.save(p); return p


def clip_scene(name, src, dur, title, sub, col=AMBER, start=0.0, freeze=None):
    """freeze=(t_src, secs): an dieser Stelle des Quell-Clips das Bild so lange anhalten."""
    cap = caption_png(name, title, sub, col)
    tmp, final = OUT / f"{name}.tmp.mp4", OUT / f"{name}.mp4"
    if freeze:
        tf, fs = freeze
        vf = (f"[0:v]trim=start={start}:end={tf},setpts=PTS-STARTPTS[a];"
              f"[0:v]trim=start={tf}:end={tf + 1 / FPS},setpts=PTS-STARTPTS,loop=loop={int(fs * FPS)}:size=1:start=0,setpts=N/{FPS}/TB[b];"
              f"[0:v]trim=start={tf},setpts=PTS-STARTPTS[c];[a][b][c]concat=n=3:v=1:a=0[v0];")
    else:
        vf = f"[0:v]trim=start={start},setpts=PTS-STARTPTS[v0];"
    vf += (f"[v0]trim=duration={dur},setpts=PTS-STARTPTS[v1];[1:v]format=rgba,fade=in:st=0.6:d=0.5:alpha=1[cp];"
           f"[v1][cp]overlay=0:0,fade=in:st=0:d=0.4,fade=out:st={dur - 0.4}:d=0.4,format=yuv420p[v]")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(IN / src), "-loop", "1", "-framerate", str(FPS),
                    "-t", str(dur), "-i", str(cap), "-filter_complex", vf, "-map", "[v]", *ENC, "-t", str(dur),
                    str(tmp)], check=True)
    os.replace(tmp, final)


def s3():
    clip_scene("s3", "clip_disaster.mp4", DUR["s3"], "Live · QNX 8.0",
               "20 simulated drones · AI + safety guard decide every 100 ms in ~1 ms · shown at 9× speed")


def s5():
    clip_scene("s5", "clip_crash.mp4", DUR["s5"], "Stress test 2 · controller killed mid-flight",
               "swarm holds position · watchdog restart in 417 µs · 0 missed control steps",
               col=RED, start=2.0, freeze=(5.95, 3.0))


# ---------------------------------------------------------------- Szene 4: Akku-Diagramm
def load_alive(fn):
    r = list(csv.DictReader(open(IN / fn)))
    return [round(float(x["alive_frac"]) * 20) for x in r]


def chart_frame(t, dur, series, title, eyebrow_s, note, xmax_min=15.0, ymax=16, xlabel="minutes", ylabel="drones in the air"):
    img = Image.new("RGB", (W, H), BG); d = ImageDraw.Draw(img)
    g = fade_global(t, dur)
    A = lambda t0: ease((t - t0) / 0.7) * g
    eyebrow(d, eyebrow_s, A(0)); text(d, (140, 175), title, font(60, "Bold"), alpha_col(TEXT, A(0)))
    x0, y0, x1, y1 = 260, 340, 1400, 900
    ca = A(0.5)
    for k in range(0, ymax + 1, 4):
        y = y1 - (y1 - y0) * k / ymax
        d.line((x0, y, x1, y), fill=alpha_col(LINE, ca), width=2)
        text(d, (x0 - 20, y), str(k), font(28), alpha_col(MUTED, ca), "rm")
    for m in range(0, int(xmax_min) + 1, 5):
        x = x0 + (x1 - x0) * m / xmax_min
        text(d, (x, y1 + 36), f"{m}", font(28), alpha_col(MUTED, ca), "mm")
    text(d, ((x0 + x1) // 2, y1 + 80), f"{xlabel}  ·  y: {ylabel}", font(28), alpha_col(MUTED, ca), "mm")
    text(d, (x0 - 20, y0 - 30), ylabel, font(26), alpha_col(MUTED, ca), "rs") if False else None
    grow = ease((t - 1.5) / 10.0)
    lx = 560
    for vals, col, label, ly in series:
        la = A(1.0)
        d.line((lx, 290, lx + 50, 290), fill=alpha_col(col, la), width=7)
        text(d, (lx + 66, 290), label, font(30, "SemiBold"), alpha_col(col, la), "lm")
        lx += 120 + int(d.textlength(label, font=font(30, "SemiBold")))
        n = max(2, int(len(vals) * grow))
        step = max(1, len(vals) // 700)
        pts = [(x0 + (x1 - x0) * j / (len(vals) - 1), y1 - (y1 - y0) * vals[j] / ymax) for j in range(0, n, step)]
        if len(pts) > 1:
            d.line(pts, fill=alpha_col(col, g), width=7, joint="curve")
    text(d, (140, 1000), note, font(26), alpha_col(MUTED, A(0.5)))
    return img


def s4():
    dur = DUR["s4"]; w = Writer("s4")
    without = load_alive("guardv2_ohne_waechter_seed0.csv")
    withg = load_alive("policy_guardv2_seed0.csv")
    series = [(without, RED, "AI alone", 40), (withg, GREEN, "AI + QNX safety guard", -40)]
    for i in range(int(dur * FPS)):
        t = i / FPS
        img = chart_frame(t, dur, series, "Without the guard, the whole swarm falls out of the sky.",
                          "Stress test 1 · batteries", "Same mission, same seed, measured on QNX 8.0 · out/guardv2_ohne_waechter_seed0.csv, out/policy_guardv2_seed0.csv")
        d = ImageDraw.Draw(img)
        a = ease((t - 12.0) / 0.8) * fade_global(t, dur)
        text(d, (1780, 370), "16 / 16", font(72, "Bold"), alpha_col(GREEN, a), "rm")
        text(d, (1780, 430), "still flying after 15 min", font(28), alpha_col(MUTED, a), "rm")
        text(d, (1780, 830), "0 / 16", font(72, "Bold"), alpha_col(RED, a), "rm")
        text(d, (1780, 890), "all down after 11.5 min", font(28), alpha_col(MUTED, a), "rm")
        w.add(img)
    w.close()


# ---------------------------------------------------------------- Balken-Szenen
def bars_scene(name, eyebrow_s, title, rows, note, footer, unit_max):
    dur = DUR[name] if name in DUR else 8.0
    w = Writer(name)
    for i in range(int(dur * FPS)):
        t = i / FPS
        img = Image.new("RGB", (W, H), BG); d = ImageDraw.Draw(img)
        g = fade_global(t, dur)
        A = lambda t0: ease((t - t0) / 0.7) * g
        eyebrow(d, eyebrow_s, A(0)); text(d, (140, 175), title, font(58, "Bold"), alpha_col(TEXT, A(0)))
        y = 350
        for j, row in enumerate(rows):
            label, val, shown, col = row[:4]
            umax = row[4] if len(row) > 4 else unit_max
            t0 = 1.0 + j * 1.2
            a = A(t0)
            text(d, (140, y + 40), label, font(34, "Medium"), alpha_col(TEXT, a), "lm")
            d.rounded_rectangle((900, y, 1600, y + 80), 14, fill=alpha_col(PANEL, a))
            bw = int(max(700 * min(val / umax, 1.0), 16) * ease((t - t0) / 1.2))
            if bw > 6:
                d.rounded_rectangle((900, y, 900 + bw, y + 80), 14, fill=alpha_col(col, a))
            text(d, (1630, y + 40), shown, font(38, "Bold"), alpha_col(col, a), "lm")
            y += 130
        text(d, (140, 920), note, font(34, "Medium"), alpha_col(AMBER, A(1.0 + len(rows) * 1.2 + 0.5)))
        text(d, (140, 1000), footer, font(26), alpha_col(MUTED, A(0.5)))
        w.add(img)
    w.close()


def s6():
    bars_scene("s6", "Stress test 3 · full CPU load", "A runaway process eats the CPU.",
               [("100 Hz loop, worst delay · normal", 764, "764 ms", RED, 764),
                ("100 Hz loop, worst delay · SCHED_FIFO", 27, "27 ms", GREEN, 764),
                ("Swarm round trip, median · normal", 12.6, "12.6 ms", RED, 12.6),
                ("Swarm round trip, median · SCHED_FIFO", 1.7, "1.7 ms", GREEN, 12.6)],
               "Real-time priority keeps the swarm on time.",
               "Measured during a CPU hog on QNX 8.0 in a VirtualBox VM (the remaining ms are the hypervisor) · pc/test_echtzeit.ps1, pc/test_last.ps1", 764)


def s7():
    # Stadt: erst der Live-Clip, dann die Balken; beides in eine Datei
    dur = DUR["s7"]; bars_d = 7.5; clip_d = dur - bars_d
    clip_scene("s7a", "clip_city.mp4", clip_d, "Scenario 2 · city, 4 × 4 km, 3 network nodes",
               "drones can only reach each other over ~1.2 km → they form relay chains · 9× speed", col=SKY)
    DUR["s7b"] = bars_d
    bars_scene("s7b", "Scenario 2 · city", "Demand served, mean of 4 runs × 15 min",
               [("AI from the disaster zone", 46, "46 %", GREY),
                ("AI trained in the city", 50, "50 %", GREY),
                ("City AI + QNX link guard", 62, "62 %", GREEN)],
               "The link guard brings lost drones back into the network.",
               "Last row measured on QNX 8.0 (out/stadt_seed*.csv) · rows 1–2 in simulation", 100)
    lst = OUT / "s7.txt"
    lst.write_text(f"file '{OUT / 's7a.mp4'}'\nfile '{OUT / 's7b.mp4'}'\n")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
                    "-c", "copy", str(OUT / "s7.tmp.mp4")], check=True)
    os.replace(OUT / "s7.tmp.mp4", OUT / "s7.mp4")


# ---------------------------------------------------------------- Szene 8: Schluss
def s8():
    dur = DUR["s8"]; w = Writer("s8")
    for i in range(int(dur * FPS)):
        t = i / FPS
        img = Image.new("RGB", (W, H), BG); d = ImageDraw.Draw(img)
        g = fade_global(t, dur, 0.5, 1.0)
        A = lambda t0: ease((t - t0) / 0.8) * g
        text(d, (W // 2, 230), "QNX 8.0 in a virtual machine · simulated drones · measured numbers",
             font(34, "Medium"), alpha_col(MUTED, A(0.3)), "mm")
        text(d, (W // 2, 440), "The AI flies.", font(110, "Bold"), alpha_col(TEXT, A(7.7)), "mm")
        text(d, (W // 2, 580), "QNX keeps it safe.", font(110, "Bold"), alpha_col(AMBER, A(9.3)), "mm")
        text(d, (W // 2, 780), "RescueSwarm", font(56, "Bold"), alpha_col(TEXT, A(11.2)), "mm")
        text(d, (W // 2, 860), "github.com/swulfen13/rescueswarm-qnx", font(40, "Medium"), alpha_col(SKY, A(11.2)), "mm")
        text(d, (W // 2, 930), "open source · MIT  ·  voice: ElevenLabs", font(30), alpha_col(MUTED, A(11.2)), "mm")
        w.add(img)
    w.close()


SCENES = {"s1": s1, "s2": s2, "s3": s3, "s4": s4, "s5": s5, "s6": s6, "s7": s7, "s8": s8}


def assemble(audio=None):
    lst = OUT / "all.txt"
    lst.write_text("".join(f"file '{OUT / (k + '.mp4')}'\n" for k in SCENES))
    silent = HERE / "rescueswarm_silent.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy",
                    str(silent)], check=True)
    if audio:
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(silent), "-i", str(audio), "-map", "0:v",
                        "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest",
                        str(HERE / "rescueswarm.mp4")], check=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--audio")
    ap.add_argument("--no-assemble", action="store_true")
    a = ap.parse_args()
    for k in (a.only or SCENES):
        SCENES[k]()
        print("fertig:", k, flush=True)
    if not a.no_assemble:
        assemble(a.audio)
