# Nimmt die Live-Ansicht fuers Video auf (1920x1080 JPEG-Bilder) – laeuft echt gegen QNX in der VM.
#   A disaster : Standard-Szenario, 1800 Takte, jedes 3. Bild
#   B crash    : Echtzeit 10 Hz, jedes Bild, nach 20 s wird der controller per slay abgeschossen
#   C city     : Stadt-Szenario mit Stadt-Policy, 2700 Takte, jedes 3. Bild
param([string[]]$Clips = @("disaster", "crash", "city"))
$py = "C:\Users\Admin\claude projekts\ml projekts\drohene schwarm (ML)\.venv\Scripts\python.exe"
$root = Join-Path $PSScriptRoot ".."
$bridge = Join-Path $root "pc\qnx_bridge.py"
$deploy = Join-Path $root "qnx\deploy.ps1"
$ip = (Get-Content (Join-Path $root "vm_ip.txt") -Raw).Trim()
$o = @("-i","C:\Users\Admin\qnxvm\qnx_key","-o","StrictHostKeyChecking=no","-o","UserKnownHostsFile=NUL",
       "-o","LogLevel=ERROR","-o","Ciphers=aes128-ctr","-o","MACs=hmac-sha2-256")
$env:RS_LIVE_VIDEO = "1"

if ($Clips -contains "disaster") {
    powershell -ExecutionPolicy Bypass -File $deploy | Out-Null
    $env:RS_LIVE_SAVE = Join-Path $PSScriptRoot "clips\disaster"; $env:RS_LIVE_EVERY = "3"
    & $py $bridge --steps 1800 --seed 0 --live 2>&1 | Select-Object -Last 2
}
if ($Clips -contains "crash") {
    powershell -ExecutionPolicy Bypass -File $deploy | Out-Null
    $env:RS_LIVE_SAVE = Join-Path $PSScriptRoot "clips\crash"; $env:RS_LIVE_EVERY = "1"
    $job = Start-Job -ScriptBlock { param($o, $ip) Start-Sleep 20; ssh @o "root@$ip" "slay -f controller" } -ArgumentList (,$o), $ip
    & $py $bridge --steps 450 --seed 0 --realtime --live 2>&1 | Select-Object -Last 3
    Receive-Job $job -Wait | Out-Null
    ssh @o "root@$ip" "grep -e beendet -e neu /tmp/rs/watchdog.log | tail -3"
}
if ($Clips -contains "city") {
    powershell -ExecutionPolicy Bypass -File $deploy -Policy policy_stadt.bin | Out-Null
    $env:RS_LIVE_SAVE = Join-Path $PSScriptRoot "clips\city"; $env:RS_LIVE_EVERY = "3"
    & $py $bridge --config (Join-Path $root "scenarios\stadt.yaml") --steps 2700 --seed 0 --live 2>&1 | Select-Object -Last 2
    powershell -ExecutionPolicy Bypass -File $deploy | Out-Null
}
