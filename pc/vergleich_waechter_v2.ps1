# Waechter v2 (wind-kompensiert) auf echtem QNX, gleiche Seeds wie die v1-Laeufe.
# v1-Ergebnisse: out\vergleich_ki.csv (Seed 0), out\policy_netcov_seed1..3.csv
param([int]$Steps = 9000, [int[]]$Seeds = @(0, 1, 2, 3))
$py = "C:\Users\Admin\claude projekts\ml projekts\drohene schwarm (ML)\.venv\Scripts\python.exe"
$root = Join-Path $PSScriptRoot ".."
powershell -ExecutionPolicy Bypass -File (Join-Path $root "qnx\deploy.ps1") -Mode ki | Out-Null
foreach ($s in $Seeds) {
    Write-Output "=== Waechter v2, Seed $s ==="
    & $py (Join-Path $PSScriptRoot "qnx_bridge.py") --steps $Steps --seed $s --csv (Join-Path $root "out\waechter_v2_seed$s.csv") 2>&1 | Select-Object -Last 3
}
