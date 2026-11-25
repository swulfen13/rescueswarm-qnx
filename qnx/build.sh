#!/bin/bash
# Baut die QNX-Programme fuer x86_64 (VirtualBox-VM). Aufruf ueber qnx.bat.
set -e
cd "$(dirname "$0")"
mkdir -p bin
qcc -Vgcc_ntox86_64 -O2 -Wall -o bin/controller controller.c policy.c -lm && echo "gebaut: bin/controller"
qcc -Vgcc_ntox86_64 -O2 -Wall -o bin/gateway gateway.c -lsocket && echo "gebaut: bin/gateway"
for p in watchdog rtbench hog; do
    qcc -Vgcc_ntox86_64 -O2 -Wall -o bin/$p $p.c && echo "gebaut: bin/$p"
done
