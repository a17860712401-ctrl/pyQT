$ErrorActionPreference = "Stop"

$RestoreProjectRoot = Split-Path -Parent $PSScriptRoot
$RestoreVenvPython = Join-Path $RestoreProjectRoot ".venv\Scripts\python.exe"

if (Test-Path -LiteralPath $RestoreVenvPython) {
    $RestorePython = $RestoreVenvPython
}
else {
    $RestorePython = (Get-Command python -ErrorAction Stop).Source
}

Push-Location $RestoreProjectRoot
try {
    & $RestorePython -m PyInstaller --clean --noconfirm "SpectrumRestore.spec"
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller 打包失败，退出码：$LASTEXITCODE"
    }
}
finally {
    Pop-Location
}
