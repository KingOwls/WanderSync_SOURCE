$ErrorActionPreference = "Continue"
$Root = (Resolve-Path "$PSScriptRoot\..").Path
$Reports = Join-Path $Root "security\reports"
New-Item -ItemType Directory -Force -Path $Reports | Out-Null
if (-not (Get-Command pip-audit -ErrorAction SilentlyContinue)) {
  Write-Error "pip-audit no está instalado. Ejecute: python -m pip install pip-audit"
  exit 2
}
pip-audit -r (Join-Path $Root "backend\requirements.txt") 2>&1 | Tee-Object (Join-Path $Reports "backend-pip-audit.txt")
$backend = $LASTEXITCODE
pip-audit -r (Join-Path $Root "ingestion\requirements.txt") 2>&1 | Tee-Object (Join-Path $Reports "ingestion-pip-audit.txt")
$ingestion = $LASTEXITCODE
Push-Location (Join-Path $Root "frontend")
if (-not (Test-Path "package-lock.json")) {
  Write-Host "package-lock.json missing; generating lockfile for reproducible npm audit..."
  npm install --package-lock-only --ignore-scripts
  if ($LASTEXITCODE -ne 0) { Pop-Location; exit 3 }
}
npm audit --json | Out-File -Encoding utf8 (Join-Path $Reports "frontend-npm-audit.json")
$npm = $LASTEXITCODE
Pop-Location
Write-Host "Reports saved under security/reports (backend=$backend ingestion=$ingestion npm=$npm)"
if ($backend -ne 0 -or $ingestion -ne 0 -or $npm -ne 0) { exit 1 }
