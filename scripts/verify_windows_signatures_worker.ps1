param(
    [Parameter(Mandatory = $true)]
    [string]$Directory,
    [switch]$DedicatedProcess
)

$ErrorActionPreference = 'Stop'

# この検査は署名とタイムスタンプの存在確認であり、RFC 3161や発行元の固定を保証しない。
if (-not $IsWindows) {
    throw 'Windows Authenticode verification requires PowerShell 7 on Windows.'
}

# 専用ワーカーだけをJobに所属させ、利用者の対話シェルには影響させない。
if ($DedicatedProcess) {
    . (Join-Path $PSScriptRoot 'enter_signature_job.ps1')
    Enter-SignatureJob
}

# {
#   責務: [Get-ExecutableSnapshot: 配布対象の実行ファイル一覧と内容ハッシュを取得する]
#   処理: [1: 起点とその祖先・配下のリンクを検査する, 2: 対象ファイルのSHA-256を収集する]
#   引数: [Path: 配布対象ディレクトリ]
#   戻り値: [パスとSHA-256の辞書。対象なしや不正な起点は例外]
# }
function Get-ExecutableSnapshot {
    param([Parameter(Mandatory = $true)][string]$Path)

    # 起点自身と配下の再解析ポイントを検査対象にしない。
    $Root = Get-Item -LiteralPath $Path -Force
    if (-not $Root.PSIsContainer -or $Root.Attributes -band [IO.FileAttributes]::ReparsePoint) {
        throw 'The distribution directory must be a real directory, not a link.'
    }
    # 起点そのものが実ディレクトリでも、祖先のジャンクションを経由し得る。
    $Ancestor = $Root.Parent
    while ($null -ne $Ancestor) {
        if ($Ancestor.Attributes -band [IO.FileAttributes]::ReparsePoint) {
            throw "Distribution directory ancestors must not contain reparse points: $($Ancestor.FullName)"
        }
        $Ancestor = $Ancestor.Parent
    }
    $Entries = @(Get-ChildItem -LiteralPath $Root.FullName -Recurse -Force)
    $Links = @($Entries | Where-Object { $_.Attributes -band [IO.FileAttributes]::ReparsePoint })
    if ($Links.Count -ne 0) {
        throw 'Distribution entries must not contain symbolic links or junctions.'
    }
    # 大文字小文字の違うパスも別対象として記録し、対象なしを成功にしない。
    $Executables = @($Entries | Where-Object { -not $_.PSIsContainer -and $_.Extension -in '.exe', '.dll', '.pyd' })
    if ($Executables.Count -eq 0) {
        throw 'No executable files were found in the distribution directory.'
    }
    $Snapshot = [Collections.Generic.Dictionary[string, string]]::new([StringComparer]::Ordinal)
    foreach ($Executable in $Executables) {
        # 排他ロックや削除でも成功にせず、検査できなかった対象を示す。
        try {
            $Hash = (Get-FileHash -LiteralPath $Executable.FullName -Algorithm SHA256).Hash
        }
        catch {
            throw "Unable to hash executable $($Executable.FullName): $($_.Exception.Message)"
        }
        $Snapshot.Add($Executable.FullName, $Hash)
    }
    return , $Snapshot
}

# {
#   責務: [Assert-ExecutableSnapshotMatches: 検査対象の一覧と内容の差を拒否する]
#   処理: [1: 削除と内容変更を確認する, 2: 追加を確認する]
#   引数: [Expected: 基準の辞書, Actual: 比較する辞書]
#   戻り値: [なし。一致しない場合は例外]
# }
function Assert-ExecutableSnapshotMatches {
    param(
        [Parameter(Mandatory = $true)][Collections.Generic.Dictionary[string, string]]$Expected,
        [Parameter(Mandatory = $true)][Collections.Generic.Dictionary[string, string]]$Actual
    )
    # パス数が同じ場合でも入れ替えを見逃さない。
    foreach ($Executable in $Expected.Keys) {
        if (-not $Actual.ContainsKey($Executable)) {
            throw "Executable files changed during signature verification: removed $Executable"
        }
        if ($Actual[$Executable] -cne $Expected[$Executable]) {
            throw "Executable files changed during signature verification: modified $Executable"
        }
    }
    foreach ($Executable in $Actual.Keys) {
        if (-not $Expected.ContainsKey($Executable)) {
            throw "Executable files changed during signature verification: added $Executable"
        }
    }
}

# 起点の列挙後に各ファイルを読取共有のみで開き、署名検査が終わるまで保持する。
$InitialSnapshot = Get-ExecutableSnapshot -Path $Directory
$ReadLocks = [Collections.Generic.List[IO.FileStream]]::new()
$VerificationFailure = $null
try {
    # ロック順をパスの序数順で固定し、取得失敗時の解放も再現可能にする。
    [string[]]$LockPaths = @($InitialSnapshot.Keys)
    [Array]::Sort($LockPaths, [StringComparer]::Ordinal)
    foreach ($Executable in $LockPaths) {
        try {
            $ReadLocks.Add([IO.File]::Open($Executable, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::Read))
        }
        catch {
            throw "Unable to lock executable $Executable after acquiring $($ReadLocks.Count) lock(s): $($_.Exception.Message)"
        }
    }
    # 最初の一覧取得からロック完了までの変更も成功にしない。
    $LockedSnapshot = Get-ExecutableSnapshot -Path $Directory
    Assert-ExecutableSnapshotMatches -Expected $InitialSnapshot -Actual $LockedSnapshot

    # 署名の不正は集計し、署名取得自体の例外は直ちに失敗させる。
    $FailureCount = 0
    foreach ($Executable in $LockPaths) {
        $Signature = Get-AuthenticodeSignature -LiteralPath $Executable
        if ($Signature.Status -ne 'Valid' -or $null -eq $Signature.SignerCertificate -or
            $null -eq $Signature.TimeStamperCertificate) {
            $FailureCount++
            Write-Error -Message "Invalid signature or missing timestamp: $Executable ($($Signature.Status))" -ErrorAction Continue
        }
    }
    if ($FailureCount -ne 0) {
        throw "Windows signature verification failed for $FailureCount file(s)."
    }
    # 新しいファイルの追加など、ロックで防げない変化を再走査で検出する。
    try {
        $FinalSnapshot = Get-ExecutableSnapshot -Path $Directory
    }
    catch {
        throw "Unable to recheck executable files after signature verification: $($_.Exception.Message)"
    }
    Assert-ExecutableSnapshotMatches -Expected $InitialSnapshot -Actual $FinalSnapshot
}
catch {
    # 解放にも失敗した場合に、元の検査エラーを失わない。
    $VerificationFailure = $_.Exception.Message
    throw
}
finally {
    # 解放に失敗したハンドルがあっても、残りのハンドルを解放する。
    $ReleaseErrors = [Collections.Generic.List[string]]::new()
    foreach ($ReadLock in $ReadLocks) {
        try {
            $ReadLock.Dispose()
        }
        catch {
            $ReleaseErrors.Add($_.Exception.Message)
        }
    }
    if ($ReleaseErrors.Count -ne 0) {
        if ($null -ne $VerificationFailure) {
            throw "Signature verification failed: $VerificationFailure; unable to release executable file locks: $($ReleaseErrors -join '; ')"
        }
        throw "Unable to release executable file locks: $($ReleaseErrors -join '; ')"
    }
}
# 全ハンドルの解放が成功して初めて、対象拡張子と診断の限界を通知する。
Write-Output "Validated Windows signatures and checked timestamp presence for $($InitialSnapshot.Count) EXE/DLL/PYD file(s); publishers are not pinned. Diagnostic only; distribution is not authorized."
