param(
    [Parameter(Mandatory = $true)]
    [string]$Directory
)

$ErrorActionPreference = 'Stop'

# この検査は署名とタイムスタンプの存在確認であり、RFC 3161や発行元の固定を保証しない。
if (-not $IsWindows) {
    throw 'Windows Authenticode verification requires PowerShell 7 on Windows.'
}

$Root = Get-Item -LiteralPath $Directory -Force
if (-not $Root.PSIsContainer -or $Root.Attributes -band [IO.FileAttributes]::ReparsePoint) {
    throw 'The distribution directory must be a real directory, not a link.'
}

# リンク先をたどると別のディレクトリのファイルを検査対象にしてしまう。
$Entries = @(Get-ChildItem -LiteralPath $Root.FullName -Recurse -Force)
$Links = @($Entries | Where-Object { $_.Attributes -band [IO.FileAttributes]::ReparsePoint })
if ($Links.Count -ne 0) {
    throw 'Distribution entries must not contain symbolic links or junctions.'
}
$Executables = @($Entries | Where-Object { -not $_.PSIsContainer -and $_.Extension -in '.exe', '.dll', '.pyd' })
if ($Executables.Count -eq 0) {
    throw 'No executable files were found in the distribution directory.'
}

# 失敗ファイルをすべて表示し、どれか一つでも不正なら配布可能としない。
$FailureCount = 0
foreach ($Executable in $Executables) {
    $Signature = Get-AuthenticodeSignature -LiteralPath $Executable.FullName
    if ($Signature.Status -ne 'Valid' -or $null -eq $Signature.SignerCertificate -or
        $null -eq $Signature.TimeStamperCertificate) {
        $FailureCount++
        Write-Error -Message "Invalid signature or missing timestamp: $($Executable.FullName) ($($Signature.Status))" -ErrorAction Continue
    }
}
if ($FailureCount -ne 0) {
    throw "Windows signature verification failed for $FailureCount file(s)."
}
Write-Output "Validated Windows signatures and checked timestamp presence for $($Executables.Count) file(s); publishers are not pinned."
