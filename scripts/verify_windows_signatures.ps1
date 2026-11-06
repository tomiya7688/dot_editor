param(
    [Parameter(Mandatory = $true)]
    [string]$Directory,

    [ValidateRange(1, 3600)]
    [int]$TimeoutSeconds = 300,

    # 指定すると、署名者証明書の名前(CN)がこの文字列と完全一致する場合だけ成功にする。
    [string]$ExpectedPublisher = ''
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
# 想定発行元は指定された場合だけ渡し、未指定なら従来どおり固定しない診断として動く。
if ($ExpectedPublisher -ne '') {
    $WorkerArguments += @('-ExpectedPublisher', $ExpectedPublisher)
}
Invoke-BoundedProcess -FilePath $PowerShell -Arguments $WorkerArguments -TimeoutSeconds $TimeoutSeconds
