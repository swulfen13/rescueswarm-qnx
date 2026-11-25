# RescueSwarm – Video-Skript (Sprechertext, englisch, ~2:45)

Stimme: ElevenLabs (ruhig, klar, männlich oder weiblich – Paul entscheidet). Jede Szene = ein Audio-Stück.
Bild: in Klammern. Zahlen alle gemessen auf QNX 8.0 in der VM.

## 1 · Problem (≈18 s)
(Titel „RescueSwarm“, dann dunkle Karte mit erlöschenden Funkmasten)
When an earthquake or a flood hits, the first thing to fail is often communication. Cell towers go down, and rescue teams lose contact exactly when they need it most. RescueSwarm sends a drone swarm to build an emergency network – and runs its brain on QNX.

## 2 · Architecture (≈21 s)
(Architektur-Grafik: PC-Simulation ↔ UDP ↔ QNX: gateway, controller mit KI + Wächter, watchdog)
The swarm is flown by a multi-agent reinforcement-learning policy – a hundred and twenty thousand weights, ported to plain C, running on QNX eight. A gateway talks to the simulation over UDP and to the controller through QNX message passing. A watchdog supervises both. And between the AI and the drones sits a deterministic safety guard.

## 3 · Live (≈19 s)
(Live-Ansicht Katastrophengebiet)
Here it is, live. Every hundred milliseconds the state of the swarm goes to QNX, and the AI plus the guard decide for every drone in about one millisecond. In this disaster zone a single uplink is the bottleneck – the swarm keeps every site online and the uplink fully used.

## 4 · Stress test 1 – batteries (≈21 s)
(Diagramm: Drohnen in der Luft über 15 min, ohne vs. mit Wächter)
Stress test one: batteries. The AI alone drains the whole swarm at once – within twelve minutes, every drone is down. With the QNX guard, drones go to charge in time, never more than thirty percent at once, wind-compensated. After fifteen minutes, sixteen of sixteen are still flying.

## 5 · Stress test 2 – crash (≈16 s)
(Live-Ansicht, controller wird abgeschossen, rotes Banner)
Stress test two: we kill the controller in mid-flight. The gateway notices, tells the swarm to hold position, and the watchdog restarts the controller in under two milliseconds. The swarm loses a single control step.

## 6 · Stress test 3 – CPU load (≈16 s)
(Balken: normale Priorität vs. SCHED_FIFO)
Stress test three: a runaway process eats the CPU. At normal priority, the control loop runs up to three quarters of a second late. With QNX real-time priority, the swarm's round trip stays under two milliseconds.

## 7 · City (≈24 s)
(Live-Ansicht Stadt mit Funkketten, dann Balken 46 → 62 %)
Scenario two: a city, four by four kilometres, with three surviving network nodes. Drones can only reach each other over about a kilometre, so they have to form relay chains. With a city-trained AI and a second QNX rule – the link guard, which brings lost drones back into the network – the swarm serves a third more demand.

## 8 · Close (≈14 s)
(Schluss-Karte mit Repo-Link)
Everything you saw runs on QNX eight in a virtual machine – the drones are simulated, the numbers are measured. The AI flies; QNX keeps it safe. RescueSwarm – open source on GitHub.
