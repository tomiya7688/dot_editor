param(
    [switch]$SkipInstall
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Venv = Join-Path $Root ".venv"
$Python = Join-Path $Venv "Scripts\python.exe"

if (-not (Test-Path -LiteralPath $Python)) {
    $PyLauncher = Get-Command py -ErrorAction SilentlyContinue
    if ($PyLauncher) {
        & $PyLauncher.Source -3 -m venv $Venv
    } else {
        $BasePython = Get-Command python -ErrorAction SilentlyContinue
        if (-not $BasePython) {
            throw "Python 3.10 or later is required to create the development environment."
        }
        & $BasePython.Source -m venv $Venv
    }

    if ($LASTEXITCODE -ne 0) {
        throw "Failed to create the virtual environment."
    }
}

& $Python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 'Python 3.10 or later is required.')"
if ($LASTEXITCODE -ne 0) {
    throw "Python 3.10 or later is required."
}

if (-not $SkipInstall) {
    & $Python -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to upgrade pip."
    }

    & $Python -m pip install -r (Join-Path $Root "requirements.txt")
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to install project dependencies."
    }
}

& $Python (Join-Path $PSScriptRoot "evaluate.py")
if ($LASTEXITCODE -ne 0) {
    throw "Project evaluation failed."
}
