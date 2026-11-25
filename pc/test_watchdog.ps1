# Absturztest im Echtzeit-Takt (10 Hz): controller 2x und gateway 1x abschiessen, watchdog startet neu.
param([string]$Ip = (Get-Content (Join-Path $PSScriptRoot "..\vm_ip.txt") -Raw).Trim(), [int]$Steps = 600)
$py = "C:\Users\Admin\claude projekts\ml projekts\drohene schwarm (ML)\.venv\Scripts\python.exe"
$o = @("-i","C:\Users\Admin\qnxvm\qnx_key","-o","StrictHostKeyChecking=no","-o","UserKnownHostsFile=NUL",
       "-o","LogLevel=ERROR","-o","Ciphers=aes128-ctr","-o","MACs=hmac-sha2-256")
$csv = Join-Path $PSScriptRoot "..\out\watchdog_test.csv"
$bridge = Join-Path $PSScriptRoot "qnx_bridge.py"
$j = Start-Job { & $using:py $using:bridge --realtime --steps $using:Steps --csv $using:csv 2>&1 }
Start-Sleep 10; ssh @o "root@$Ip" "slay -f controller"; Write-Output "[10 s] controller abgeschossen"
Start-Sleep 15; ssh @o "root@$Ip" "slay -s SIGSEGV -f controller"; Write-Output "[25 s] controller mit SIGSEGV (simulierter Absturz)"
Start-Sleep 15; ssh @o "root@$Ip" "slay -f gateway"; Write-Output "[40 s] gateway abgeschossen"
Wait-Job $j | Out-Null
Receive-Job $j | Select-Object -Last 5
Write-Output "--- watchdog.log ---"
ssh @o "root@$Ip" "grep -e beendet -e wieder /tmp/rs/watchdog.log"
