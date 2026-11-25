# Stresstest: Wie puenktlich bleibt ein Regeltakt auf QNX, wenn ein Stoerprozess die CPU voll belegt?
# Voraussetzung: qnx\deploy.ps1 wurde ausgefuehrt (rtbench + hog liegen in /tmp/rs).
# Der Test laeuft auf QNX im Hintergrund (unter Volllast kann die SSH-Sitzung selbst haengen) und
# schreibt nach /tmp/rs/echtzeit.txt; danach wird das Ergebnis abgeholt.
param([string]$Ip = (Get-Content (Join-Path $PSScriptRoot "..\vm_ip.txt") -Raw).Trim(), [int]$Sek = 10)
$o = @("-i","C:\Users\Admin\qnxvm\qnx_key","-o","StrictHostKeyChecking=no","-o","UserKnownHostsFile=NUL",
       "-o","LogLevel=ERROR","-o","Ciphers=aes128-ctr","-o","MACs=hmac-sha2-256","-o","ConnectTimeout=10")
$sh = Join-Path $PSScriptRoot "..\qnx\test_echtzeit.sh"
$tmp = Join-Path $env:TEMP "test_echtzeit.sh"
(Get-Content $sh -Raw).Replace("`r", "") | Set-Content -NoNewline -Encoding ascii $tmp
scp @o $tmp "root@${Ip}:/tmp/rs/test_echtzeit.sh"
ssh @o "root@$Ip" "cd /tmp/rs && rm -f echtzeit.txt && (nohup sh test_echtzeit.sh $Sek > echtzeit.txt 2>&1 &)"
Start-Sleep ($Sek * 5 + 15)
ssh @o "root@$Ip" "cat /tmp/rs/echtzeit.txt"
