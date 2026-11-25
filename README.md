# RescueSwarm – a safety-critical drone-swarm brain on QNX 8.0

> After an earthquake, power and mobile networks are down. A swarm of drones takes off,
> spreads out over the disaster area and becomes an emergency radio network for rescue teams.
> The swarm's "brain" must never hang, never let the whole swarm run out of battery at once,
> and must survive its own software crashing. That is exactly what QNX is built for.

RescueSwarm runs a **multi-agent reinforcement-learning policy** (trained on a PC) **inside QNX 8.0**,
in plain C, behind a **hard real-time safety guard** and a **watchdog** – connected live to a
physics simulation of the swarm.

**Category:** Robotics & Medical  ·  **Target:** QNX SDP 8.0, x86_64 (VirtualBox, built with `mkqnximage`)

---

## Results (measured on QNX 8.0)

| What | Result |
|---|---|
| AI policy ported to C (119,819 weights, attention network) | **5,100 / 5,100** decisions identical to PyTorch |
| AI + safety guard, whole swarm (20 drones) per control step | **~1.1 ms** median, 1.8 ms max (step = 100 ms) |
| Round trip PC → QNX → PC | **~1.6 ms** median, 2.2 ms 99th percentile |
| Controller process killed / crashed (SIGTERM, SIGSEGV) | watchdog restarts it in **0.6–1.8 ms**, swarm loses **1 control step** (hovers safely), 0 missed steps |
| Gateway process killed | restarted in **1.4 ms**, **0** missed steps |
| AI **without** safety guard (15 min mission) | swarm drains its batteries together – **all drones down after 10 min, 0 % coverage** |
| AI **with** QNX safety guard (same seed) | **16 of 16 drones still flying after 15 min**, coverage stable (guard v2) |
| Guard v2 (wind-compensated) vs. v1 (straight line), 4 seeds on QNX | more drones survive in calm/moderate wind (16 vs 14, 14 vs 11); no guard can help when the wind is stronger than the drones (see notes) |
| 100 Hz control loop vs. CPU hog, **normal** priority | median **392 ms** late, max 764 ms |
| 100 Hz control loop vs. CPU hog, **SCHED_FIFO 50** | median **4.2 ms** late, max 27 ms (VM floor, see notes) |
| Full swarm loop at 10 Hz during 20 s CPU hog, normal priority | round trip median 12.6 ms, 99 % 39 ms |
| Same, controller + gateway at **SCHED_FIFO 50** | round trip median **1.7 ms**, 99 % **3.0 ms** |

(See `out/` for the raw CSV logs. Timing jitter numbers are discussed honestly below.)

---

## Architecture

```
┌──────────────────────── PC (Windows) ────────────────────────┐
│  swarm-sim (PyTorch physics: mesh radio, batteries, wind,    │
│  charging stations, failures)  ──  pc/qnx_bridge.py          │
│  pc/live_view.py (map + live charts)                         │
└───────────────────────────┬──────────────────────────────────┘
                            │ UDP, 10 Hz (state of all drones ↔ one action per drone)
┌───────────────────────────┴──────── QNX 8.0 ─────────────────┐
│  watchdog   posix_spawn + waitpid → restarts children in ms   │
│     ├── gateway     UDP ⇄ QNX message passing (MsgSend)       │
│     │               answers "hover" by itself if controller   │
│     │               is gone → the swarm never gets no answer  │
│     └── controller  name_attach / MsgReceive / MsgReply       │
│           ├── policy.c  attention policy in plain C           │
│           └── safety guard  battery planner, overrides AI,    │
│                             max. 30 % of swarm charging       │
│   all control processes run SCHED_FIFO priority 50            │
└──────────────────────────────────────────────────────────────┘
```

### Where QNX is used

| QNX feature | File | Functions |
|---|---|---|
| Synchronous message passing (the heart of the system) | `qnx/controller.c`, `qnx/gateway.c` | `name_attach`, `MsgReceive`, `MsgReply`, `MsgError`, `name_open`, `MsgSend`, `ConnectDetach`, `_PULSE_CODE_DISCONNECT` |
| Process supervision / self-healing | `qnx/watchdog.c` | `posix_spawn`, `waitpid` |
| Real-time scheduling | `qnx/controller.c`, `qnx/gateway.c`, `qnx/rtbench.c`, `qnx/hog.c` | `pthread_setschedparam(SCHED_FIFO)` |
| High-resolution timing | all | `ClockCycles`, `SYSPAGE_ENTRY(qtime)->cycles_per_sec`, `clock_nanosleep(TIMER_ABSTIME)` |
| Networking | `qnx/gateway.c` | BSD sockets on `io-sock` (`-lsocket`) |
| Target image | `vm_start.sh` | `mkqnximage --type=vbox` |
| Toolchain | `qnx/build.sh` | `qcc -Vgcc_ntox86_64` |

### The idea: AI flies, QNX keeps it safe ("mixed criticality")

The RL policy decides **where** each drone flies (coverage of hotspots such as shelters, hospitals,
the incident command). It was trained in the companion project swarm-sim and has a known weakness:
the whole swarm tends to drain its batteries at the same time ("sawtooth") – coverage collapses.

Instead of hoping the network learns perfect battery management, a **deterministic safety guard on QNX**
sits between the AI and the drones:

* below the battery reserve a drone **must** return to charge – the AI is overridden,
* charging slots are handed out to the lowest batteries first,
* **never more than 30 % of the swarm charges at the same time,**
* the flight to the station is **wind-compensated** (guard v2): the guard picks the thrust direction
  that brings the drone's velocity closest to "towards the station, slowing down on arrival",
  minus the wind. The first version (v1) flew a straight line and "hovered" at the station –
  but hovering keeps the current velocity, so drones overshot or were blown away and died
  next to the charger.

The AI stays fast and flexible, the safety rules stay simple, verifiable and real-time.

---

## Build & run

### Requirements
* QNX SDP 8.0 (free non-commercial "QNX Everywhere" license), installed to `C:\Users\<you>\qnx800`
  (adjust the two paths at the top of `tools/qnx.bat` and in `qnx/deploy.ps1` / `pc/*.ps1` if yours differ)
* VirtualBox (7.x)
* Python 3.10+ with PyTorch, NumPy, PyYAML, Matplotlib
* [swarm-sim](https://github.com/swulfen13/swarm-sim) checked out next to this repo (or set `SWARM_SIM`)

### 1. Start QNX
```bat
tools\qnx.bat bash tools/vm_start.sh   :: builds + starts the QNX 8.0 VM (mkqnximage --type=vbox), writes its IP to vm_ip.txt
```
`mkqnximage` cannot handle spaces in paths – the VM is created in `C:\Users\<you>\qnxvm`.
SSH to the VM needs `-o Ciphers=aes128-ctr -o MACs=hmac-sha2-256` (VirtualBox NIC issue, see Challenges).

### 2. Build and deploy the QNX side
```powershell
python pc\export_policy.py <swarm-sim>\checkpoints\netcov_final.pt qnx\policy.bin
tools\qnx.bat bash qnx/build.sh                     # qcc → qnx/bin/{watchdog,controller,gateway,rtbench,hog}
powershell -File qnx\deploy.ps1                     # copies to /tmp/rs and starts the watchdog
#   -Mode ki | ki-ohne (AI without guard) | regeln (rules)    -Prio 0 (no real-time priority)
```

### 3. Run the swarm
```powershell
python pc\qnx_bridge.py --realtime --live --steps 6000      # 10 minutes at 10 Hz with live view
python pc\qnx_bridge.py --steps 9000 --csv out\run.csv      # as fast as possible, logged
```

### 4. Tests
```powershell
powershell -File pc\vergleich.ps1        # AI with vs. without safety guard (same seed)
powershell -File pc\vergleich_waechter_v2.ps1   # guard v2 on seeds 0-3 (compare with v1 CSVs in out/)
powershell -File pc\vergleich_policies.ps1      # original policy vs. policy retrained with the guard
powershell -File pc\test_watchdog.ps1    # kills controller twice and gateway once during a 10 Hz run
powershell -File pc\test_echtzeit.ps1    # 100 Hz loop vs. CPU hog: no load / normal prio / SCHED_FIFO
powershell -File pc\test_last.ps1        # full swarm loop during CPU hog, normal vs. FIFO priority
```
`pc/mock_qnx.py` is a Python stand-in for the QNX side for testing the bridge without QNX.

---

## Honest notes

* **Prior work:** the simulation and the training code (swarm-sim) existed before the hackathon.
  Everything in this repository – the QNX side, the C port of the policy, the safety guard,
  the watchdog, the bridge, the tests and the live view – was built during the hackathon period.
* **Coverage is low (~14 %)** with the current policy, with or without the guard. The guard fixes
  *survival*, not *placement*. Retraining the policy with the guard in the loop
  (`training/train_with_guard.py`, 3000 PPO updates) did **not** clearly beat the original policy on
  QNX (4 seeds: 13.5 vs 13.4 %, 6.9 vs 7.3 %, 17.7 vs 18.4 %, 3.7 vs 3.0 %), so the original policy stays.
* **Strong wind is not survivable in this simulation.** Wind acts as an acceleration of up to
  10 m/s² at the hardest stage, the drones can only push with 5 m/s². When the wind is stronger than
  the drone, a station upwind cannot be reached by any controller – in 2 of 4 test seeds
  (wind 5.0 and 5.9) all drones are lost with guard v1 and v2 alike. A real system would need to
  keep drones upwind of a station or ground the swarm; that is mission planning, not a guard rule.
* **Timing jitter in a VM:** on the development PC, VirtualBox runs on top of Hyper-V
  (“NEM” mode, because WSL/Docker are enabled). Timer jitter inside the guest is therefore
  dominated by the hypervisor (milliseconds), not by QNX. Control-step computation times
  (~1 ms) are measured with `ClockCycles()` inside QNX and are not affected by this.
  Clean jitter numbers need real hardware (e.g. Raspberry Pi 5) – planned next.
  A multi-core guest (`--cpu=4`) froze completely under the CPU-saturation test, so the VM runs single-core.

## What's next
* Run on a Raspberry Pi 5 with QNX 8.0 and measure real-time behaviour on bare metal
* Wind-aware mission planning: keep drones upwind of a charger, ground the swarm when wind > thrust
* Retrain with the guard in the loop on more seeds / longer (first attempt: no clear gain)
* One controller process per drone + adaptive partitioning to guarantee CPU budgets
* Use QNX SLM (System Launch and Monitor) instead of the self-written watchdog

## License
MIT – see `LICENSE`. swarm-sim is MIT licensed as well.
