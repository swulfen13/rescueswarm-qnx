# Vergleich auf echtem QNX: KI mit Sicherheitswaechter vs. KI ohne Waechter (gleicher Seed).
param([int]$Steps = 9000)
$py = "C:\Users\Admin\claude projekts\ml projekts\drohene schwarm (ML)\.venv\Scripts\python.exe"
$qnx = Join-Path $PSScriptRoot "..\qnx\deploy.ps1"
foreach ($m in @("ki-ohne", "ki")) {
    powershell -ExecutionPolicy Bypass -File $qnx -Mode $m | Out-Null
    Write-Output "=== Modus: $m ==="
    & $py (Join-Path $PSScriptRoot "qnx_bridge.py") --steps $Steps --csv (Join-Path $PSScriptRoot "..\out\vergleich_$m.csv") 2>&1 | Select-Object -Last 4
}
