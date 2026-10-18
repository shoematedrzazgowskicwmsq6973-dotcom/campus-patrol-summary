$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$env:PYTHONUTF8 = '1'
$venvPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $venvPython)) {
    $launcher = Get-Command py -ErrorAction SilentlyContinue
    if (-not $launcher) { throw 'Python launcher not found. Install Python 3.12 or 3.13 from python.org, with Tcl/Tk and the Python launcher enabled.' }
    $candidates = @('-3.12', '-3.13')
    $created = $false
    foreach ($version in $candidates) {
        try {
            $probe = & py $version -c 'import sys; print(sys.executable)' 2>$null
        } catch { continue }
        if ($LASTEXITCODE -eq 0) {
            & py $version -m venv (Join-Path $PSScriptRoot '.venv')
            if ($LASTEXITCODE -ne 0) { throw 'Could not create the local Python environment.' }
            $created = $true
            break
        }
    }
    if (-not $created) { throw 'Install Python 3.12 or 3.13 with Tcl/Tk support, then run this installer again.' }
}
Write-Host 'Installing local OCR components. Internet is needed for this installation only.'
$dependencyFile = Join-Path $PSScriptRoot 'requirements-lock.txt'
if (-not (Test-Path -LiteralPath $dependencyFile)) { $dependencyFile = Join-Path $PSScriptRoot 'requirements.txt' }
& $venvPython -m pip install --disable-pip-version-check -r $dependencyFile
if ($LASTEXITCODE -ne 0) { throw 'Installation failed. Check the network connection and run again.' }
& $venvPython (Join-Path $PSScriptRoot 'verify_install.py')
if ($LASTEXITCODE -ne 0) { throw 'Verification failed. See the error above.' }
Write-Host 'Ready. Open start.cmd to use the tool offline.' -ForegroundColor Green
