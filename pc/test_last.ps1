# Stresstest mit dem echten Schwarm: Waehrend die Simulation im 10-Hz-Takt laeuft, frisst "hog"
# auf QNX 20 s lang die CPU. Einmal laufen controller/gateway mit normaler Prioritaet, einmal mit FIFO 50.
param([string]$Ip = (Get-Content (Join-Path $PSScriptRoot "..\vm_ip.txt") -Raw).Trim(), [int]$Steps = 300)
$py = "C:\Users\Admin\claude projekts\ml projekts\drohene schwarm (ML)\.venv\Scripts\python.exe"
$o = @("-i","C:\Users\Admin\qnxvm\qnx_key","-o","StrictHostKeyChecking=no","-o","UserKnownHostsFile=NUL",
       "-o","LogLevel=ERROR","-o","Ciphers=aes128-ctr","-o","MACs=hmac-sha2-256","-o","ConnectTimeout=20")
$bridge = Join-Path $PSScriptRoot "qnx_bridge.py"
foreach ($prio in @(0, 50)) {
    powershell -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "..\qnx\deploy.ps1") -Prio $prio | Out-Null
    $csv = Join-Path $PSScriptRoot "..\out\last_prio$prio.csv"
    $j = Start-Job { & $using:py $using:bridge --realtime --steps $using:Steps --timeout-ms 90 --csv $using:csv 2>&1 }
    Start-Sleep 5
    ssh @o "root@$Ip" "cd /tmp/rs && (nohup ./hog -t 1 -s 20 > /dev/null 2>&1 &)"
    Wait-Job $j | Out-Null
    Write-Output "=== controller/gateway Prioritaet: $(if ($prio -gt 0) {"FIFO $prio"} else {'normal'}) | hog 20 s Volllast ==="
    Receive-Job $j | Select-Object -Last 4 | Select-Object -First 3
    Start-Sleep 3
}
