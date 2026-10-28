# {
#   責務: [Invoke-BoundedProcess: 指定プロセスを期限付きで実行し結果を伝える]
#   処理: [1: 出力を非同期に収集する, 2: 期限切れなら起動したプロセスの停止を試みる, 3: 結果を返す]
#   引数: [FilePath: 実行ファイル, Arguments: 引数配列, TimeoutSeconds: 待機上限秒]
#   戻り値: [なし。成功時はコンソールへ出力し、失敗または期限切れなら例外]
# }
function Invoke-BoundedProcess {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FilePath,

        [Parameter(Mandatory = $true)]
        [string[]]$Arguments,

        [Parameter(Mandatory = $true)]
        [ValidateRange(1, 3600)]
        [int]$TimeoutSeconds
    )

    # 引数をコマンド文字列に連結せず、パスの空白や特殊文字を保持する。
    $StartInfo = [System.Diagnostics.ProcessStartInfo]::new()
    $StartInfo.FileName = $FilePath
    $StartInfo.UseShellExecute = $false
    $StartInfo.RedirectStandardOutput = $true
    $StartInfo.RedirectStandardError = $true
    foreach ($Argument in $Arguments) {
        [void]$StartInfo.ArgumentList.Add($Argument)
    }
    $Process = [System.Diagnostics.Process]::new()
    $Process.StartInfo = $StartInfo
    $Stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
    try {
        if (-not $Process.Start()) {
            throw 'Could not start the signature verification process.'
        }
        # 両ストリームを並行して読み、パイプ満杯による相互待ちを避ける。
        $OutputTask = $Process.StandardOutput.ReadToEndAsync()
        $ErrorTask = $Process.StandardError.ReadToEndAsync()
        if (-not $Process.WaitForExit($TimeoutSeconds * 1000)) {
            # 終了と競合する場合でも、期限切れを成功扱いしない。
            try {
                $Process.Kill($true)
            }
            catch [System.InvalidOperationException] {
                # 期限切れの直後に終了した場合、停止済みなので失敗を維持する。
            }
            catch {
                # 停止要求自体が失敗した場合は、未停止の可能性を明示する。
                throw "Signature verification timed out; process termination failed: $($_.Exception.Message)"
            }
            # 停止要求後の待機も制限し、呼び出し元を無期限に止めない。
            if (-not $Process.WaitForExit(5000)) {
                throw "Signature verification timed out; process termination was not confirmed."
            }
            throw "Signature verification timed out after $TimeoutSeconds second(s)."
        }
        # 子孫が出力パイプを保持していても待機は制限する。子孫の寿命は呼び出し側が管理する。
        $RemainingMilliseconds = [Math]::Max(0, ($TimeoutSeconds * 1000) - $Stopwatch.ElapsedMilliseconds)
        if (-not [System.Threading.Tasks.Task]::WaitAll([System.Threading.Tasks.Task[]]@($OutputTask, $ErrorTask), [int]$RemainingMilliseconds)) {
            throw "Signature verification timed out while collecting process output."
        }
        $Output = $OutputTask.GetAwaiter().GetResult()
        $Errors = $ErrorTask.GetAwaiter().GetResult()
        if ($Process.ExitCode -ne 0) {
            # 失敗前に出力された診断を破棄しない。
            if ($Output) {
                [Console]::Out.Write($Output)
            }
            throw "Signature verification process failed (exit $($Process.ExitCode)): $Errors"
        }
        if ($Errors) {
            [Console]::Error.Write($Errors)
        }
        if ($Output) {
            [Console]::Out.Write($Output)
        }
    }
    finally {
        $Process.Dispose()
    }
}
