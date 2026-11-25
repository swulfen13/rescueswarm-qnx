#!/bin/bash
# Baut (falls noetig) und startet die QNX-8.0-VM in VirtualBox (ohne Fenster).
# Die VM liegt unter C:\Users\Admin\qnxvm, weil mkqnximage keine Leerzeichen im Pfad verkraftet.
# SSH als root mit dem Schluessel C:\Users\Admin\qnxvm\qnx_key
# Die IP wird nach vm_ip.txt geschrieben (alle Skripte lesen sie dort).
HERE="$(pwd)"
VMDIR="C:/Users/Admin/qnxvm"
mkdir -p "$VMDIR" && cd "$VMDIR" || exit 1
mkqnximage --type=vbox --ssh-ident="$VMDIR/qnx_key.pub" --run=-h "$@"
echo "--- IP der VM:"
mkqnximage --getip | tee "$HERE/vm_ip.txt"
