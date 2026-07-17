$ErrorActionPreference = "Stop"

$RestoreProjectRoot = Split-Path -Parent $PSScriptRoot
$RestoreVenvPython = Join-Path $RestoreProjectRoot ".venv\Scripts\python.exe"

if (Test-Path -LiteralPath $RestoreVenvPython) {
    $RestorePython = $RestoreVenvPython
}
else {
    $RestorePython = (Get-Command python -ErrorAction Stop).Source
}

& $RestorePython (Join-Path $RestoreProjectRoot "run_app.py")
exit $LASTEXITCODE
