param([switch]$SkipInstall)
$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $ProjectRoot ".venv/Scripts/python.exe"
if (-not (Test-Path -LiteralPath $Python)) { throw "Run scripts/setup_environment.ps1 first." }
Push-Location $ProjectRoot
try {
    # 新規venvでも、依存取得より先にpip自身の信頼ストアを更新する。
    $TrustArguments = @()
    if ($SkipInstall) { $TrustArguments = @("--check") }
    & $Python (Join-Path $PSScriptRoot "python_trust.py") @TrustArguments
    if ($LASTEXITCODE -ne 0) { throw "Python trust verification failed." }
    if (-not $SkipInstall) {
        & $Python -m pip install -e . -r requirements-build.txt
        if ($LASTEXITCODE -ne 0) { throw "Build dependency installation failed." }
        # 依存解決が信頼パッケージを置き換えていないことをビルド直前にも確認する。
        & $Python (Join-Path $PSScriptRoot "python_trust.py") --check
        if ($LASTEXITCODE -ne 0) { throw "Python trust verification failed after installation." }
    }
    & $Python -m build
    if ($LASTEXITCODE -ne 0) { throw "Python package build failed." }
    foreach ($Target in @(@("DotEditor", "--windowed", "src/dot_editor.py"), @("DotEditorCLI", "--console", "src/pixel_cli.py"))) {
        & $Python -m PyInstaller --noconfirm --clean --onedir --name $Target[0] $Target[1] --paths src --distpath dist/windows --workpath build/pyinstaller --specpath build/spec $Target[2]
        if ($LASTEXITCODE -ne 0) { throw "Executable build failed: $($Target[0])" }
    }
    Copy-Item -LiteralPath LICENSE,README.md -Destination dist/windows
    & $Python -m pip list --format=freeze | Out-File -LiteralPath dist/windows/build-dependencies.txt -Encoding utf8
    if ($LASTEXITCODE -ne 0) { throw "Dependency manifest failed." }
    & $Python scripts/distribution_notices.py dist/windows
    if ($LASTEXITCODE -ne 0) { throw "Dependency license collection failed." }
    & $Python scripts/smoke_distribution.py dist/windows
    if ($LASTEXITCODE -ne 0) { throw "Distribution smoke test failed." }
    Compress-Archive -Path dist/windows/* -DestinationPath dist/HyperDotEditor-windows-x64.zip -Force
    Get-FileHash -LiteralPath dist/HyperDotEditor-windows-x64.zip -Algorithm SHA256
} finally {
    Pop-Location
}
