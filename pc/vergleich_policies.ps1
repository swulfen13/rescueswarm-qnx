# Vergleich auf echtem QNX: alte Policy (netcov_final) vs. nachtrainierte Policy (mit Waechter trainiert).
# Beide laufen mit Waechter, gleiche Seeds. Am Ende ist wieder die Policy aktiv, die in qnx\policy.bin liegt.
param([int]$Steps = 9000, [int[]]$Seeds = @(1, 2, 3), [string[]]$Policies = @("netcov", "guard"))
$py = "C:\Users\Admin\claude projekts\ml projekts\drohene schwarm (ML)\.venv\Scripts\python.exe"
$root = Join-Path $PSScriptRoot ".."
$deploy = Join-Path $root "qnx\deploy.ps1"
$aktiv = Join-Path $root "qnx\policy.bin"
$sicher = Join-Path $root "qnx\policy_aktiv_backup.bin"
Copy-Item $aktiv $sicher -Force
foreach ($p in $Policies) {
    Copy-Item (Join-Path $root "qnx\policy_$p.bin") $aktiv -Force
    powershell -ExecutionPolicy Bypass -File $deploy -Mode ki | Out-Null
    foreach ($s in $Seeds) {
        $csv = Join-Path $root "out\policy_${p}_seed$s.csv"
        Write-Output "=== Policy: $p, Seed $s ==="
        & $py (Join-Path $PSScriptRoot "qnx_bridge.py") --steps $Steps --seed $s --csv $csv 2>&1 | Select-Object -Last 3
    }
}
Copy-Item $sicher $aktiv -Force
Remove-Item $sicher
powershell -ExecutionPolicy Bypass -File $deploy -Mode ki | Out-Null
