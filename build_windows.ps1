$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$env:PYTHONUTF8 = '1'
$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'Run install.cmd first.' }
& $python -m pip install -r requirements-build.txt
if ($LASTEXITCODE -ne 0) { throw 'Build dependencies failed to install.' }
& $python -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) { throw 'Tests failed.' }
& $python -m PyInstaller --noconfirm PatrolSummary.spec
if ($LASTEXITCODE -ne 0) { throw 'Packaging failed.' }
& $python collect_licenses.py (Join-Path $PSScriptRoot 'dist\PatrolSummary\THIRD_PARTY_LICENSES')
if ($LASTEXITCODE -ne 0) { throw 'License collection failed.' }
Copy-Item -LiteralPath README.md -Destination 'dist\PatrolSummary\README.md'
Write-Host 'Ready: dist\PatrolSummary\PatrolSummary.exe'
