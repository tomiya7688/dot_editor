param(
    [Parameter(Mandatory = $true)]
    [string]$Directory,

    [ValidateRange(1, 3600)]
    [int]$TimeoutSeconds = 300
)

$ErrorActionPreference = 'Stop'

# Windows以外では子プロセスの起動前に対象外であることを伝える。
if (-not $IsWindows) {
    throw 'Windows is required for Authenticode signature verification.'
}

# ネイティブの署名APIが停止しても、呼び出し元で待機時間を制限する。
. (Join-Path $PSScriptRoot 'invoke_bounded_process.ps1')
$PowerShell = Join-Path $PSHOME 'pwsh.exe'
$Worker = Join-Path $PSScriptRoot 'verify_windows_signatures_worker.ps1'
$WorkerArguments = @('-NoProfile', '-NonInteractive', '-File', $Worker, '-Directory', $Directory, '-DedicatedProcess')
Invoke-BoundedProcess -FilePath $PowerShell -Arguments $WorkerArguments -TimeoutSeconds $TimeoutSeconds
