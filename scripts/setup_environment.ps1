param(
    [switch]$SkipInstall
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Venv = Join-Path $Root "dot_editor"
$Python = Join-Path $Venv "Scripts\python.exe"
$BasePython = "I:\program_files\ide\python\python.exe"

if (-not (Test-Path -LiteralPath $Python)) {
    if (-not (Test-Path -LiteralPath $BasePython)) {
        $BasePython = (Get-Command py -ErrorAction SilentlyContinue).Source
        if (-not $BasePython) {
            throw "Python 3 is required to create the development environment."
        }
        & $BasePython -3 -m venv $Venv
    } else {
        & $BasePython -m venv $Venv
    }
}

if (-not $SkipInstall) {
    & $Python -m pip install --upgrade pip
    & $Python -m pip install Pillow
}

& $Python $PSScriptRoot\evaluate.py
