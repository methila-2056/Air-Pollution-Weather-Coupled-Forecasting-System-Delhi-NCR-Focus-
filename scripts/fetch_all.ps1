# Fetch all data sources and rebuild the featured dataset (PowerShell).

$ErrorActionPreference = "Stop"

$python = "python"
$steps = @(
    "scripts/download_weather.py",
    "scripts/download_pollution.py",
    "scripts/download_fire.py",
    "scripts/download_atmosphere.py",
    "scripts/build_dataset.py"
)

foreach ($step in $steps) {
    Write-Host "==> $step"
    & $python $step
    if ($LASTEXITCODE -ne 0) { throw "Step failed: $step" }
}

Write-Host "All data pipeline steps completed."