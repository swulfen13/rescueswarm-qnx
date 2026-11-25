# Kopiert alle QNX-Programme + policy.bin in die VM und startet den watchdog,
# der controller und gateway startet und bei Absturz sofort neu startet.
#   .\deploy.ps1                  -> KI-Policy + Sicherheitswaechter, Echtzeit-Prioritaet 50
#   .\deploy.ps1 -Mode ki-ohne    -> KI-Policy OHNE Waechter (Vergleich)
#   .\deploy.ps1 -Mode regeln     -> einfache Regeln + Waechter
#   .\deploy.ps1 -Prio 0          -> ohne Echtzeit-Prioritaet (Vergleich Stresstest)
# Log auf QNX: /tmp/rs/watchdog.log
param([string]$Ip = (Get-Content (Join-Path $PSScriptRoot "..\vm_ip.txt") -Raw).Trim(), [ValidateSet("ki","ki-ohne","regeln")][string]$Mode = "ki", [int]$Prio = 50)
$o = @("-i","C:\Users\Admin\qnxvm\qnx_key","-o","StrictHostKeyChecking=no","-o","UserKnownHostsFile=NUL",
       "-o","LogLevel=ERROR","-o","Ciphers=aes128-ctr","-o","MACs=hmac-sha2-256")
$bin = Join-Path $PSScriptRoot "bin"
$a = @{ "ki" = "-p policy.bin"; "ki-ohne" = "-p policy.bin -n"; "regeln" = "" }[$Mode]
if ($Prio -gt 0) { $a = "$a -r $Prio" }
ssh @o "root@$Ip" "slay -f watchdog 2>/dev/null; slay -f controller 2>/dev/null; slay -f gateway 2>/dev/null; sleep 1; mkdir -p /tmp/rs; cd /tmp/rs; rm -f watchdog controller gateway rtbench hog"
scp @o "$bin\watchdog" "$bin\controller" "$bin\gateway" "$bin\rtbench" "$bin\hog" (Join-Path $PSScriptRoot "policy.bin") "root@${Ip}:/tmp/rs/"
ssh @o "root@$Ip" "cd /tmp/rs && chmod +x watchdog controller gateway rtbench hog && (nohup ./watchdog $a > watchdog.log 2>&1 &) && sleep 2 && cat watchdog.log"
