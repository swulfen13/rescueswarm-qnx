#!/bin/sh
# Laeuft AUF QNX (in /tmp/rs). Stresstest fuer einen 100-Hz-Regeltakt (wie eine Flugsteuerung).
SEK=${1:-10}
cd /tmp/rs
N=$(pidin info | grep -c '^Processor')
[ "$N" -lt 1 ] && N=1
echo "CPUs in der VM: $N"
echo "--- A: keine Last, normale Prioritaet"
./rtbench -f 100 -s $SEK
echo "--- B: Volllast (hog, $N Threads), Regeltakt mit NORMALER Prioritaet"
./hog -t $N -s $((SEK + 2)) > /dev/null &
sleep 1
./rtbench -f 100 -s $SEK
wait
echo "--- C: Volllast (hog, $N Threads), Regeltakt mit ECHTZEIT-Prioritaet FIFO 50"
./hog -t $N -s $((SEK + 2)) > /dev/null &
sleep 1
./rtbench -f 100 -s $SEK -r 50
wait
echo "--- fertig"
