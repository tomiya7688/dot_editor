"""Exercise the read-only Windows distribution signature inspection."""

import ctypes
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

from tests.signature_job_guard import SignatureTestJob

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "verify_windows_signatures.ps1"
WORKER = ROOT / "scripts" / "verify_windows_signatures_worker.ps1"
BOUNDED_PROCESS = ROOT / "scripts" / "invoke_bounded_process.ps1"
SIGNATURE_JOB = ROOT / "scripts" / "enter_signature_job.ps1"


# {
#   責務: [WindowsSignatureTests: 署名検査の実行と失敗条件を確認する]
#   フィールド: [temporary: 自動削除する一時領域, directory: 検査対象ディレクトリ]
# }
@unittest.skipUnless(sys.platform == "win32", "Authenticode is available on Windows only")
class WindowsSignatureTests(unittest.TestCase):
    # {
    #   責務: [setUp: 検査する一時配布ディレクトリを準備する]
    #   処理: [1: 指定された一時領域の下に作業領域を作る, 2: 自動削除を登録する]
    #   引数: [self: テストインスタンス]
    #   戻り値: [なし]
    # }
    def setUp(self):
        # 開発者環境ではEドライブの専用領域を渡し、Cドライブへ作業物を置かない。
        self.temporary = tempfile.TemporaryDirectory(dir=os.environ.get("DOT_EDITOR_TEST_TEMP"))
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)

    # {
    #   責務: [run_verifier: 子PowerShellで配布物の検査を実行する]
    #   処理: [1: 検査対象を引数として渡す, 2: 終了値と診断を返す]
    #   引数: [self: テストインスタンス]
    #   戻り値: [終了値と標準出力・標準エラー]
    # }
    def run_verifier(self):
        # 対象名をシェル文字列に連結せず、引数としてそのまま渡す。
        return subprocess.run(
            ["pwsh", "-NoProfile", "-NonInteractive", "-File", str(SCRIPT), str(self.directory)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )

    # {
    #   責務: [test_unsigned_file_fails: 未署名の実行ファイルを拒否する]
    #   処理: [1: 異なる拡張子と階層に未署名ファイルを置く, 2: 全件の検査失敗を確認する]
    #   引数: [self: テストインスタンス]
    #   戻り値: [なし]
    # }
    def test_unsigned_file_fails(self):
        # 署名APIを模擬せず、本物のWindows署名検査で拒否を確認する。
        (self.directory / "unsigned.exe").write_bytes(b"not a signed executable")
        nested = self.directory / "nested"
        nested.mkdir()
        (nested / "unsigned.PYD").write_bytes(b"not a signed executable")
        (nested / "unsigned.DLL").write_bytes(b"not a signed executable")
        result = self.run_verifier()
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("Invalid signature", result.stderr)
        self.assertNotIn("distribution is not authorized", result.stdout)
        for name in ("unsigned.exe", "unsigned.PYD", "unsigned.DLL"):
            self.assertIn(name, result.stderr)

    # {
    #   責務: [test_empty_directory_fails: 検査対象なしを成功扱いしない]
    #   処理: [1: 空ディレクトリを渡す, 2: 非0と理由を確認する]
    #   引数: [self: テストインスタンス]
    #   戻り値: [なし]
    # }
    def test_empty_directory_fails(self):
        # 拡張子の判定漏れや誤ったディレクトリ指定を黙って通さない。
        result = self.run_verifier()
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("No executable files", result.stderr)

    # {
    #   責務: [test_link_is_rejected: 配布物内のリンクをたどらず拒否する]
    #   処理: [1: 一時領域内にリンクを作る, 2: 非0と理由を確認する]
    #   引数: [self: テストインスタンス]
    #   戻り値: [なし。リンク作成権限がない場合はskip]
    # }
    def test_link_is_rejected(self):
        # 開発者モードなどの権限がないWindowsでは、権限変更せずskipを記録する。
        target = self.directory / "original.txt"
        target.write_text("fixture", encoding="utf-8")
        try:
            (self.directory / "linked.txt").symlink_to(target)
        except OSError as error:
            self.skipTest(f"Cannot create test symlink: {error}")
        result = self.run_verifier()
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("must not contain symbolic links", result.stderr)

    # {
    #   責務: [test_ancestor_junction_is_rejected: 起点の祖先にあるジャンクションを拒否する]
    #   処理: [1: 一時領域内にジャンクションを作る, 2: その下の起点が拒否されることを確認する]
    #   引数: [self: テストインスタンス]
    #   戻り値: [なし]
    # }
    def test_ancestor_junction_is_rejected(self):
        # 対象とリンクの両方を一時領域に限定し、終了時はリンクだけを削除する。
        special_directory = self.directory / "space & special"
        special_directory.mkdir()
        target = special_directory / "real"
        (target / "nested").mkdir(parents=True)
        junction = special_directory / "junction"
        created = subprocess.run(
            f'cmd /d /s /c "mklink /J "{junction}" "{target}""',
            capture_output=True,
            timeout=30,
        )
        self.assertEqual(created.returncode, 0, created.stderr.decode(errors="replace"))
        try:
            result = subprocess.run(
                [
                    "pwsh",
                    "-NoProfile",
                    "-NonInteractive",
                    "-File",
                    str(WORKER),
                    str(junction / "nested"),
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=60,
            )
            self.assertNotEqual(result.returncode, 0, result.stdout)
            self.assertIn("ancestors must not contain reparse points", result.stderr)
        finally:
            junction.rmdir()

    # {
    #   責務: [test_missing_timestamp_fails: 証明書がない署名を拒否する]
    #   処理: [1: 署名APIの戻り値だけを模擬する, 2: タイムスタンプ欠落の非0を確認する]
    #   引数: [self: テストインスタンス]
    #   戻り値: [なし]
    # }
    def test_missing_timestamp_fails(self):
        # 検査APIを模擬し、証明書を発行したり信頼ストアを書き換えたりしない。
        (self.directory / "missing_timestamp.exe").write_bytes(b"fixture")
        command = (
            "function Get-AuthenticodeSignature { param($LiteralPath) "
            "[pscustomobject]@{Status='Valid';SignerCertificate=1;TimeStamperCertificate=$null} }; "
            "& $env:DOT_EDITOR_SIGNATURE_SCRIPT $env:DOT_EDITOR_SIGNATURE_DIRECTORY"
        )
        result = subprocess.run(
            ["pwsh", "-NoProfile", "-NonInteractive", "-Command", command],
            env={
                **os.environ,
                "DOT_EDITOR_SIGNATURE_SCRIPT": str(WORKER),
                "DOT_EDITOR_SIGNATURE_DIRECTORY": str(self.directory),
            },
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("Invalid signature or missing timestamp", result.stderr)
        self.assertIn("(Valid)", result.stderr)

    # {
    #   責務: [test_changed_executables_fail: 検査中の実行ファイルの追加・削除・変更を拒否する]
    #   処理: [1: 署名APIの模擬中に変更を試す, 2: ロックまたは再走査での失敗を確認する]
    #   引数: [self: テストインスタンス]
    #   戻り値: [なし]
    # }
    def test_changed_executables_fail(self):
        # 署名APIの呼出し中に変更を起こし、時間依存の競合テストを避ける。
        for change in ("add", "modify", "remove", "replace"):
            with self.subTest(change=change):
                directory = self.directory / change
                directory.mkdir()
                (directory / "original.exe").write_bytes(b"original")
                if change in ("remove", "replace"):
                    (directory / "other.dll").write_bytes(b"other")
                command = (
                    "function Get-AuthenticodeSignature { param($LiteralPath) try { "
                    "if ($env:DOT_EDITOR_CHANGE -eq 'add') { "
                    "[IO.File]::WriteAllText((Join-Path $env:DOT_EDITOR_SIGNATURE_DIRECTORY 'added.dll'),'new') "
                    "} elseif ($env:DOT_EDITOR_CHANGE -eq 'remove') { "
                    "[IO.File]::Delete((Join-Path $env:DOT_EDITOR_SIGNATURE_DIRECTORY 'other.dll')) "
                    "} elseif ($env:DOT_EDITOR_CHANGE -eq 'replace') { "
                    "[IO.File]::Delete((Join-Path $env:DOT_EDITOR_SIGNATURE_DIRECTORY 'other.dll')); "
                    "[IO.File]::WriteAllText((Join-Path $env:DOT_EDITOR_SIGNATURE_DIRECTORY 'new.dll'),'new') "
                    "} else { [IO.File]::WriteAllText($LiteralPath,'modified') } "
                    "} catch { throw 'fixture mutation blocked' }; "
                    "[pscustomobject]@{Status='Valid';SignerCertificate=1;TimeStamperCertificate=1} }; "
                    "& $env:DOT_EDITOR_SIGNATURE_SCRIPT $env:DOT_EDITOR_SIGNATURE_DIRECTORY"
                )
                result = subprocess.run(
                    ["pwsh", "-NoProfile", "-NonInteractive", "-Command", command],
                    env={
                        **os.environ,
                        "DOT_EDITOR_SIGNATURE_SCRIPT": str(WORKER),
                        "DOT_EDITOR_SIGNATURE_DIRECTORY": str(directory),
                        "DOT_EDITOR_CHANGE": change,
                    },
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=60,
                )
                self.assertNotEqual(result.returncode, 0, result.stdout)
                if change == "add":
                    self.assertIn(
                        "Executable files changed during signature verification", result.stderr
                    )
                    self.assertIn("added.dll", result.stderr)
                else:
                    self.assertIn("fixture mutation blocked", result.stderr)
                    self.assertEqual((directory / "original.exe").read_bytes(), b"original")
                    if change in ("remove", "replace"):
                        self.assertEqual((directory / "other.dll").read_bytes(), b"other")

    # {
    #   責務: [test_hash_failure_identifies_file: 内容を読めない実行ファイルの名前を報告する]
    #   処理: [1: ハッシュ取得エラーを模擬する, 2: 失敗と対象パスを確認する]
    #   引数: [self: テストインスタンス]
    #   戻り値: [なし]
    # }
    def test_hash_failure_identifies_file(self):
        # 読取拒否を模擬し、ACLや他の利用者データを変更しない。
        (self.directory / "locked.exe").write_bytes(b"fixture")
        command = (
            "function Get-FileHash { param($LiteralPath,$Algorithm) throw 'fixture read error' }; "
            "& $env:DOT_EDITOR_SIGNATURE_SCRIPT $env:DOT_EDITOR_SIGNATURE_DIRECTORY"
        )
        result = subprocess.run(
            ["pwsh", "-NoProfile", "-NonInteractive", "-Command", command],
            env={
                **os.environ,
                "DOT_EDITOR_SIGNATURE_SCRIPT": str(WORKER),
                "DOT_EDITOR_SIGNATURE_DIRECTORY": str(self.directory),
            },
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("Unable to hash executable", result.stderr)
        self.assertIn("locked.exe", result.stderr)
        self.assertIn("fixture read error", result.stderr)

    # {
    #   責務: [test_transient_overwrite_is_blocked: 署名検査中の一時的な上書きを拒否する]
    #   処理: [1: 模擬署名APIから上書きと復元を試す, 2: ロックによる拒否を確認する]
    #   引数: [self: テストインスタンス]
    #   戻り値: [なし]
    # }
    def test_transient_overwrite_is_blocked(self):
        # 検査前後のハッシュが同じでも、署名中の書き換えを防げることを確認する。
        executable = self.directory / "original.exe"
        executable.write_bytes(b"original")
        marker = self.directory / "mutation-result.txt"
        command = (
            "function Get-AuthenticodeSignature { param($LiteralPath) "
            "try { [IO.File]::WriteAllText($LiteralPath,'modified'); "
            "[IO.File]::WriteAllText($LiteralPath,'original'); $result='allowed' } "
            "catch { if ($_.Exception -isnot [IO.IOException] -and "
            "$_.Exception.InnerException -isnot [IO.IOException]) { throw }; $result='blocked' }; "
            "[IO.File]::WriteAllText($env:DOT_EDITOR_MUTATION_MARKER,$result); "
            "[pscustomobject]@{Status='Valid';SignerCertificate=1;TimeStamperCertificate=1} }; "
            "& $env:DOT_EDITOR_SIGNATURE_SCRIPT $env:DOT_EDITOR_SIGNATURE_DIRECTORY"
        )
        result = subprocess.run(
            ["pwsh", "-NoProfile", "-NonInteractive", "-Command", command],
            env={
                **os.environ,
                "DOT_EDITOR_SIGNATURE_SCRIPT": str(WORKER),
                "DOT_EDITOR_SIGNATURE_DIRECTORY": str(self.directory),
                "DOT_EDITOR_MUTATION_MARKER": str(marker),
            },
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(marker.read_text(encoding="utf-8"), "blocked")
        self.assertEqual(executable.read_bytes(), b"original")

    # {
    #   責務: [test_existing_writer_prevents_verification: 既存の書込ハンドルがある対象を拒否する]
    #   処理: [1: 書込ハンドルを保持する, 2: 検査の失敗と同一プロセス内での解放を確認する]
    #   引数: [self: テストインスタンス]
    #   戻り値: [なし]
    # }
    def test_existing_writer_prevents_verification(self):
        # 書込可能な既存ハンドルとの競合を起こし、対象ファイルだけを検査する。
        executable = self.directory / "busy.exe"
        executable.write_bytes(b"fixture")
        other = self.directory / "a-other.exe"
        other.write_bytes(b"fixture")
        command = (
            "function Get-FileHash { param($LiteralPath,$Algorithm) [pscustomobject]@{Hash='fixture'} }; "
            "$held=[IO.File]::Open($env:DOT_EDITOR_BUSY_FILE,'Open','Write','ReadWrite'); "
            "try { try { & $env:DOT_EDITOR_SIGNATURE_SCRIPT $env:DOT_EDITOR_SIGNATURE_DIRECTORY } "
            "catch { $failure=$_.Exception.Message }; "
            "[IO.File]::WriteAllText($env:DOT_EDITOR_OTHER_FILE,'released'); "
            "if ($failure) { throw $failure } } finally { $held.Dispose() }"
        )
        result = subprocess.run(
            ["pwsh", "-NoProfile", "-NonInteractive", "-Command", command],
            env={
                **os.environ,
                "DOT_EDITOR_SIGNATURE_SCRIPT": str(WORKER),
                "DOT_EDITOR_SIGNATURE_DIRECTORY": str(self.directory),
                "DOT_EDITOR_BUSY_FILE": str(executable),
                "DOT_EDITOR_OTHER_FILE": str(other),
            },
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("Unable to lock executable", result.stderr)
        self.assertNotIn("distribution is not authorized", result.stdout)
        self.assertIn("busy.exe", result.stderr)
        self.assertIn("after acquiring 1 lock(s)", result.stderr)
        self.assertEqual(other.read_text(encoding="utf-8"), "released")
        executable.write_bytes(b"after")

    # {
    #   責務: [test_real_existing_writer_fails: 実際の書込中ファイルを拒否する]
    #   処理: [1: 書込可能なハンドルを保持する, 2: 競合失敗と解放後の署名検査到達を確認する]
    #   引数: [self: テストインスタンス]
    #   戻り値: [なし]
    # }
    def test_real_existing_writer_fails(self):
        # 読取共有の競合を、ハッシュAPIを模擬せず同一の一時ファイルで確認する。
        executable = self.directory / "busy-real.exe"
        executable.write_bytes(b"fixture")
        with executable.open("r+b"):
            result = subprocess.run(
                [
                    "pwsh",
                    "-NoProfile",
                    "-NonInteractive",
                    "-File",
                    str(WORKER),
                    str(self.directory),
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=60,
            )
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertTrue(
            "Unable to hash executable" in result.stderr
            or "Unable to lock executable" in result.stderr,
            result.stderr,
        )
        self.assertIn("busy-real.exe", result.stderr)
        self.assertNotIn("distribution is not authorized", result.stdout)
        # 同じ未署名ファイルでハンドルを閉じると、競合ではなく署名不正になる。
        released = subprocess.run(
            ["pwsh", "-NoProfile", "-NonInteractive", "-File", str(WORKER), str(self.directory)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
        self.assertNotEqual(released.returncode, 0, released.stdout)
        self.assertIn("Invalid signature", released.stderr)
        self.assertNotIn("Unable to hash executable", released.stderr)
        self.assertNotIn("Unable to lock executable", released.stderr)

    # {
    #   責務: [test_hung_process_is_terminated: 応答しない検査を期限切れで失敗させる]
    #   処理: [1: PIDを記録する子プロセスを起動する, 2: 上限超過後の子プロセス終了を確認する]
    #   引数: [self: テストインスタンス]
    #   戻り値: [なし]
    # }
    def test_hung_process_is_terminated(self):
        # 一時領域へPIDを記録させ、実際に起動した子プロセスだけを確認する。
        pid_file = self.directory / "child.pid"
        child_code = (
            "import os, pathlib, time; "
            "target = pathlib.Path(os.environ['DOT_EDITOR_CHILD_PID']); "
            "pending = target.with_suffix('.pending'); "
            "pending.write_text(str(os.getpid())); pending.replace(target); "
            "time.sleep(90)"
        )
        command = (
            ". $env:DOT_EDITOR_BOUNDED_PROCESS; "
            "Invoke-BoundedProcess -FilePath $env:DOT_EDITOR_CHILD_PYTHON "
            "-Arguments @('-c', $env:DOT_EDITOR_CHILD_CODE) -TimeoutSeconds 30"
        )
        process = subprocess.Popen(
            ["pwsh", "-NoProfile", "-NonInteractive", "-Command", command],
            env={
                **os.environ,
                "DOT_EDITOR_BOUNDED_PROCESS": str(BOUNDED_PROCESS),
                "DOT_EDITOR_CHILD_PYTHON": sys.executable,
                "DOT_EDITOR_CHILD_CODE": child_code,
                "DOT_EDITOR_CHILD_PID": str(pid_file),
            },
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        # 対象が生きている間にハンドルを取得し、PID再利用による誤判定を防ぐ。
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
        kernel32.OpenProcess.restype = ctypes.c_void_p
        kernel32.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        kernel32.WaitForSingleObject.restype = ctypes.c_uint32
        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        kernel32.CloseHandle.restype = ctypes.c_int
        process_handle = None
        try:
            deadline = time.monotonic() + 90
            while not pid_file.is_file() and process.poll() is None and time.monotonic() < deadline:
                time.sleep(0.1)
            self.assertTrue(pid_file.is_file(), "Child did not start before the timeout")
            child_pid = int(pid_file.read_text(encoding="ascii"))
            # SYNCHRONIZE権限だけで終了状態を照会し、子プロセスを変更しない。
            process_handle = kernel32.OpenProcess(0x00100000, False, child_pid)
            self.assertTrue(process_handle, f"Could not inspect child: {ctypes.get_last_error()}")
            stdout, stderr = process.communicate(timeout=120)
            self.assertNotEqual(process.returncode, 0, stdout)
            self.assertIn("timed out after 30 second", stderr)
            self.assertEqual(kernel32.WaitForSingleObject(process_handle, 0), 0)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)
            if process.stdout is not None:
                process.stdout.close()
            if process.stderr is not None:
                process.stderr.close()
            if process_handle:
                kernel32.CloseHandle(process_handle)

    # {
    #   責務: [assert_worker_lock_held: 試験用ワーカーが排他的にファイルを保持することを確認する]
    #   処理: [1: Windows APIでファイルを開く, 2: 共有違反で拒否されることを確認する]
    #   引数: [self: テストインスタンス, path: ロック対象]
    #   戻り値: [なし]
    # }
    def assert_worker_lock_held(self, path):
        # CRTが隠すWindowsエラーを直接取得し、権限不足との混同を避ける。
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateFileW.argtypes = [
            ctypes.c_wchar_p,
            ctypes.c_uint32,
            ctypes.c_uint32,
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.c_uint32,
            ctypes.c_void_p,
        ]
        kernel32.CreateFileW.restype = ctypes.c_void_p
        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        handle = kernel32.CreateFileW(str(path), 0x80000000, 7, None, 3, 0, None)
        if handle != ctypes.c_void_p(-1).value:
            kernel32.CloseHandle(handle)
            self.fail("Worker lock was not held")
        self.assertEqual(ctypes.get_last_error(), 32, "Expected a Windows sharing violation")

    # {
    #   責務: [assert_worker_lock_released: 試験用ワーカーの排他ロック解放を確認する]
    #   処理: [1: 期限付きでファイルを開く, 2: 期限を超えたら失敗する]
    #   引数: [self: テストインスタンス, path: ロック対象]
    #   戻り値: [なし]
    # }
    def assert_worker_lock_released(self, path):
        # OSのハンドル解放が完了するまで短時間だけ待つ。
        deadline = time.monotonic() + 5
        while True:
            try:
                with path.open("rb"):
                    return
            except PermissionError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(0.05)

    # {
    #   責務: [check_public_worker_cleanup: 公開入口のワーカー終了を検証する]
    #   処理: [1: 試験用Jobの中で公開入口を実行する, 2: 指定した終了方法でワーカーの停止を確認する]
    #   引数: [self: テストインスタンス, abort_before_publish: 準備完了通知前にJobを終了するか, skip_inner_job: 対象Jobの設定を省いて保護用Jobを検証するか]
    #   戻り値: [なし]
    # }
    def check_public_worker_cleanup(
        self, abort_before_publish, skip_inner_job=False, suppress_ready=False, ready_timeout=80
    ):
        # 入口の相対パス解決を保ちつつ、ワーカーだけを一時領域の試験用処理に置き換える。
        scripts = self.directory / "scripts"
        scripts.mkdir()
        distribution = self.directory / "distribution"
        distribution.mkdir()
        shutil.copyfile(SCRIPT, scripts / SCRIPT.name)
        shutil.copyfile(BOUNDED_PROCESS, scripts / BOUNDED_PROCESS.name)
        shutil.copyfile(SIGNATURE_JOB, scripts / SIGNATURE_JOB.name)
        lock_file = self.directory / "worker.lock"
        ready_file = self.directory / "worker.ready"
        published_file = self.directory / "worker.published"
        # 排他利用前に読み取れることを確認し、権限不足と区別する。
        lock_file.write_bytes(b"fixture")
        self.assertEqual(lock_file.read_bytes(), b"fixture")
        (scripts / WORKER.name).write_text(
            "param($Directory, [switch]$DedicatedProcess)\n"
            "$lock = [IO.File]::Open($env:DOT_EDITOR_WORKER_LOCK, 'Open', 'ReadWrite', 'None')\n"
            "try {\n"
            "  if ($env:DOT_EDITOR_SUPPRESS_READY -ne '1') { [IO.File]::WriteAllText($env:DOT_EDITOR_WORKER_READY, 'ready') }\n"
            "  if ($env:DOT_EDITOR_ABORT_BEFORE_PUBLISH -eq '1') { Start-Sleep -Seconds 150 }\n"
            "  [IO.File]::WriteAllText($env:DOT_EDITOR_WORKER_PUBLISHED, 'ready')\n"
            "  Start-Sleep -Seconds 150\n"
            "} finally { $lock.Dispose() }\n",
            encoding="utf-8",
        )
        # 試験用Jobを先に作り、その配下で入口とワーカーを起動する。
        wrapper = scripts / "test_wrapper.ps1"
        entry_done = self.directory / "entry.done"
        release_wrapper = self.directory / "wrapper.release"
        start_wrapper = self.directory / "wrapper.start"
        wrapper.write_text(
            "$gate = [Diagnostics.Stopwatch]::StartNew()\n"
            "while (-not [IO.File]::Exists($env:DOT_EDITOR_WRAPPER_START) -and $gate.Elapsed.TotalSeconds -lt 120) { Start-Sleep -Milliseconds 100 }\n"
            "if (-not [IO.File]::Exists($env:DOT_EDITOR_WRAPPER_START)) { throw 'Test job assignment was not confirmed' }\n"
            ". (Join-Path $PSScriptRoot 'enter_signature_job.ps1')\n"
            "if ($env:DOT_EDITOR_SKIP_INNER_JOB -ne '1') { Enter-SignatureJob }\n"
            "& (Join-Path $PSHOME 'pwsh.exe') -NoProfile -NonInteractive -File "
            "(Join-Path $PSScriptRoot 'verify_windows_signatures.ps1') "
            "-Directory $env:DOT_EDITOR_TEST_DIRECTORY -TimeoutSeconds 90\n"
            "$result = $LASTEXITCODE\n"
            "$pendingResult = $env:DOT_EDITOR_ENTRY_DONE + '.pending'\n"
            "[IO.File]::WriteAllText($pendingResult, [string]$result)\n"
            "[IO.File]::Move($pendingResult, $env:DOT_EDITOR_ENTRY_DONE)\n"
            "$watch = [Diagnostics.Stopwatch]::StartNew()\n"
            "while (-not [IO.File]::Exists($env:DOT_EDITOR_WRAPPER_RELEASE) -and $watch.Elapsed.TotalSeconds -lt 150) { Start-Sleep -Milliseconds 100 }\n"
            "exit $result\n",
            encoding="utf-8",
        )
        # 保護用Jobはテスト対象のJobとは別に保持し、割当完了までラッパーを待機させる。
        guard = SignatureTestJob()
        try:
            process = subprocess.Popen(
                [
                    "pwsh",
                    "-NoProfile",
                    "-NonInteractive",
                    "-File",
                    str(wrapper),
                ],
                env={
                    **os.environ,
                    "DOT_EDITOR_WORKER_LOCK": str(lock_file),
                    "DOT_EDITOR_WORKER_READY": str(ready_file),
                    "DOT_EDITOR_WORKER_PUBLISHED": str(published_file),
                    "DOT_EDITOR_TEST_DIRECTORY": str(distribution),
                    "DOT_EDITOR_ABORT_BEFORE_PUBLISH": "1" if abort_before_publish else "0",
                    "DOT_EDITOR_SUPPRESS_READY": "1" if suppress_ready else "0",
                    "DOT_EDITOR_SKIP_INNER_JOB": "1" if skip_inner_job else "0",
                    "DOT_EDITOR_ENTRY_DONE": str(entry_done),
                    "DOT_EDITOR_WRAPPER_RELEASE": str(release_wrapper),
                    "DOT_EDITOR_WRAPPER_START": str(start_wrapper),
                },
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        except BaseException as process_start_error:
            try:
                guard.close()
            except OSError as cleanup_error:
                raise process_start_error from cleanup_error
            raise
        # 試験用ワーカーが独占するファイルを用い、PIDやプロセスハンドルの移送を不要にする。
        try:
            # 子プロセスを起動する前に保護用Jobへ所属させる。
            # WindowsのCPythonが保持する起動時ハンドルを使い、PID再取得を避ける。
            try:
                guard.assign(process._handle)
            except OSError as assignment_error:
                # 所属前のラッパーは保護Jobでは回収できないため、直接終了して待つ。
                try:
                    process.kill()
                    process.wait(timeout=5)
                except (OSError, subprocess.TimeoutExpired) as cleanup_error:
                    raise cleanup_error from assignment_error
                raise
            start_wrapper.touch()
            deadline = time.monotonic() + ready_timeout
            expected_ready = ready_file if abort_before_publish else published_file
            while (
                not expected_ready.is_file()
                and process.poll() is None
                and time.monotonic() < deadline
            ):
                time.sleep(0.05)
            if not expected_ready.is_file():
                if process.poll() is None:
                    process.kill()
                stdout, stderr = process.communicate(timeout=5)
                self.fail(f"Worker did not become ready: {stdout}\n{stderr}")
            self.assert_worker_lock_held(lock_file)
            if abort_before_publish:
                # 準備完了通知の前にJob保持者を終了し、子孫停止を確認する。
                process.kill()
                if skip_inner_job:
                    # 対象Jobがない場合は独立した保護用Jobで子孫を回収する。
                    guard.close()
            else:
                # Jobを開いたまま入口の終了とワーカーの停止を別々に確認する。
                entry_deadline = time.monotonic() + 120
                while (
                    not entry_done.is_file()
                    and process.poll() is None
                    and time.monotonic() < entry_deadline
                ):
                    time.sleep(0.1)
                self.assertTrue(entry_done.is_file(), "Entry did not finish before the timeout")
                self.assertNotEqual(int(entry_done.read_text("ascii")), 0)
                self.assert_worker_lock_released(lock_file)
                release_wrapper.touch()
            stdout, stderr = process.communicate(timeout=120)
            self.assertNotEqual(process.returncode, 0, stdout)
            if not abort_before_publish:
                self.assertIn("timed out after 90 second", stderr)
            self.assert_worker_lock_released(lock_file)
        finally:
            active_error = sys.exc_info()[1]
            cleanup_errors = []
            try:
                if process.poll() is None:
                    release_wrapper.touch()
                    # 通常の期限切れ処理に子を停止させる機会を与える。
                    try:
                        process.wait(timeout=95)
                    except subprocess.TimeoutExpired:
                        try:
                            process.kill()
                            process.wait(timeout=5)
                        except (OSError, subprocess.TimeoutExpired) as cleanup_error:
                            cleanup_errors.append(cleanup_error)
            except OSError as cleanup_error:
                cleanup_errors.append(cleanup_error)
            finally:
                try:
                    # 対象Jobが壊れていても独立したJobで残った子孫を回収する。
                    try:
                        guard.close()
                    except OSError as cleanup_error:
                        cleanup_errors.append(cleanup_error)
                    finally:
                        if process.stdout is not None:
                            try:
                                process.stdout.close()
                            except OSError as cleanup_error:
                                cleanup_errors.append(cleanup_error)
                        if process.stderr is not None:
                            try:
                                process.stderr.close()
                            except OSError as cleanup_error:
                                cleanup_errors.append(cleanup_error)
                finally:
                    try:
                        self.assert_worker_lock_released(lock_file)
                    except AssertionError as cleanup_error:
                        cleanup_errors.append(cleanup_error)
            if active_error is not None:
                if cleanup_errors:
                    raise active_error from cleanup_errors[0]
                raise active_error
            if cleanup_errors:
                raise cleanup_errors[0]

    # {
    #   責務: [test_public_timeout_stops_worker: 公開入口の期限切れでワーカーを停止する]
    #   処理: [1: 応答しないワーカーを起動する, 2: 期限切れと停止を確認する]
    #   引数: [self: テストインスタンス]
    #   戻り値: [なし]
    # }
    def test_public_timeout_stops_worker(self):
        # 実際の公開入口に期限を渡す。
        self.check_public_worker_cleanup(False)

    # {
    #   責務: [test_outer_job_stops_hung_worker: 試験用Jobの終了で待機中のワーカーを回収する]
    #   処理: [1: 試験用ワーカーを待機させる, 2: Job保持者の終了とワーカーの停止を確認する]
    #   引数: [self: テストインスタンス]
    #   戻り値: [なし]
    # }
    def test_outer_job_stops_hung_worker(self):
        # 排他的ロックの解放により、試験用ワーカーの停止を確認する。
        self.check_public_worker_cleanup(True)

    # {
    #   責務: [test_guard_stops_worker_without_inner_job: 対象Jobがない場合も試験用の保護が子孫を回収する]
    #   処理: [1: 対象Jobを省略してワーカーを待機させる, 2: 保護用Jobを閉じて停止を確認する]
    #   引数: [self: テストインスタンス]
    #   戻り値: [なし]
    # }
    def test_guard_stops_worker_without_inner_job(self):
        # 対象Jobを使わない失敗経路で保護用Jobを検証する。
        self.check_public_worker_cleanup(True, skip_inner_job=True)

    # {
    #   責務: [test_missing_ready_stops_worker: 準備通知がない場合に入口を停止する]
    #   処理: [1: 通知を抑止して入口を起動する, 2: 期限後の停止とロック解放を確認する]
    #   引数: [self: テストインスタンス]
    #   戻り値: [なし]
    # }
    def test_missing_ready_stops_worker(self):
        # 短い試験用期限で準備未完了の回収経路を通す。
        with self.assertRaisesRegex(AssertionError, "Worker did not become ready"):
            self.check_public_worker_cleanup(True, suppress_ready=True, ready_timeout=1)

    # {
    #   責務: [test_guard_assignment_failure_stops_wrapper: Job割当失敗を呼び出し元に伝える]
    #   処理: [1: Job割当を失敗させる, 2: 例外を確認する]
    #   引数: [self: テストインスタンス]
    #   戻り値: [なし]
    # }
    def test_guard_assignment_failure_stops_wrapper(self):
        # ゲート解放前の失敗を注入し、割当に失敗したまま子を起動しない。
        original_wait = subprocess.Popen.wait
        original_kill = subprocess.Popen.kill
        with (
            mock.patch.object(SignatureTestJob, "assign", side_effect=OSError("assignment failed")),
            mock.patch.object(
                subprocess.Popen, "wait", autospec=True, side_effect=original_wait
            ) as wait,
            mock.patch.object(
                subprocess.Popen, "kill", autospec=True, side_effect=original_kill
            ) as kill,
        ):
            with self.assertRaisesRegex(OSError, "assignment failed"):
                self.check_public_worker_cleanup(True)
        # ラッパーの終了と子の起動ゲートが未開放であることを確認する。
        self.assertTrue(kill.called, "Wrapper termination was not requested")
        self.assertTrue(wait.called, "Wrapper termination was not awaited")
        self.assertIsNotNone(wait.call_args.args[0].poll())
        self.assertFalse((self.directory / "wrapper.start").exists())
        self.assertFalse((self.directory / "worker.ready").exists())

    # {
    #   責務: [copy_signed_system_file: 署名付きの実ファイルを検査用に複製する]
    #   処理: [1: Windows標準ファイルの署名を確認する, 2: 一時領域に複製する]
    #   引数: [self: テストインスタンス]
    #   戻り値: [複製先のパス。署名情報を利用できない場合はskip]
    # }
    def copy_signed_system_file(self):
        # Windows提供バイナリは既存の署名を利用し、証明書を生成・信頼登録しない。
        system_file = Path(os.environ["SystemRoot"]) / "System32" / "notepad.exe"
        probe = subprocess.run(
            [
                "pwsh",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                "$s = Get-AuthenticodeSignature -LiteralPath $env:DOT_EDITOR_SIGNED_SAMPLE; "
                "if ($s.Status -eq 'Valid' -and $null -ne $s.TimeStamperCertificate) "
                "{ exit 0 } else { exit 3 }",
            ],
            env={**os.environ, "DOT_EDITOR_SIGNED_SAMPLE": str(system_file)},
            capture_output=True,
            timeout=60,
        )
        if probe.returncode:
            if os.environ.get("DOT_EDITOR_REQUIRE_SIGNED_SAMPLE") == "1":
                self.fail("The required system file has no verifiable signature and timestamp")
            self.skipTest("The system file has no verifiable signature and timestamp")
        sample = self.directory / "signed.exe"
        shutil.copyfile(system_file, sample)
        return sample

    # {
    #   責務: [test_signed_system_file: 署名付きの実ファイルを受け入れる]
    #   処理: [1: 署名済みの標準ファイルを複製する, 2: 検査成功を確認する]
    #   引数: [self: テストインスタンス]
    #   戻り値: [なし。署名情報を利用できない場合はskip]
    # }
    def test_signed_system_file(self):
        # 有効な署名とタイムスタンプを持つ実ファイルを受け入れる。
        self.copy_signed_system_file()
        result = self.run_verifier()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("checked timestamp presence", result.stdout)
        self.assertIn("EXE/DLL/PYD", result.stdout)
        self.assertIn("distribution is not authorized", result.stdout)

    # {
    #   責務: [test_tampered_system_file: 署名済みファイルの改変を拒否する]
    #   処理: [1: 署名済みの標準ファイルを複製する, 2: 内容を改変して検査失敗を確認する]
    #   引数: [self: テストインスタンス]
    #   戻り値: [なし。署名情報を利用できない場合はskip]
    # }
    def test_tampered_system_file(self):
        sample = self.copy_signed_system_file()
        # 署名付きファイルの改変を検出し、コピーしたファイルだけを変更する。
        with sample.open("r+b") as stream:
            stream.seek(0x30)
            original = stream.read(1)
            stream.seek(0x30)
            stream.write(bytes([original[0] ^ 1]))
        tampered = self.run_verifier()
        self.assertNotEqual(tampered.returncode, 0, tampered.stdout)
        self.assertIn("Invalid signature", tampered.stderr)

    # {
    #   責務: [run_pinned: 想定発行元を指定して子PowerShellで検査を実行する]
    #   処理: [1: -ExpectedPublisherを引数として渡す, 2: 負荷の高い環境でも待てる上限で実行する]
    #   引数: [self: テストインスタンス, publisher: 想定する署名者名]
    #   戻り値: [終了値と標準出力・標準エラー]
    # }
    def run_pinned(self, publisher):
        return subprocess.run(
            [
                "pwsh",
                "-NoProfile",
                "-NonInteractive",
                "-File",
                str(SCRIPT),
                str(self.directory),
                "-ExpectedPublisher",
                publisher,
                "-TimeoutSeconds",
                "300",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=330,
        )

    # {
    #   責務: [signer_name: 署名済みファイルの署名者名(CN)を実際に取得する]
    #   処理: [1: 子PowerShellで署名者証明書の名前を読む, 2: 空なら失敗にする]
    #   引数: [self: テストインスタンス, sample: 署名済みファイル]
    #   戻り値: [署名者名]
    # }
    def signer_name(self, sample):
        done = subprocess.run(
            [
                "pwsh",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                "(Get-AuthenticodeSignature -LiteralPath $env:DOT_EDITOR_SIGNED_SAMPLE)"
                ".SignerCertificate.GetNameInfo('SimpleName', $false)",
            ],
            env={**os.environ, "DOT_EDITOR_SIGNED_SAMPLE": str(sample)},
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
        )
        name = done.stdout.strip()
        self.assertTrue(name, done.stderr)
        return name

    # {
    #   責務: [test_expected_publisher_matches: 想定発行元が一致すれば受け入れ、不一致や部分一致は拒否する]
    #   処理: [
    #     1: 署名済みの標準ファイルと実際の署名者名を取得する
    #     2: 完全一致なら成功、別名・大文字小文字違い・部分一致なら失敗を確認する
    #   ]
    #   引数: [self: テストインスタンス]
    #   戻り値: [なし。署名情報を利用できない場合はskip]
    # }
    def test_expected_publisher_matches(self):
        sample = self.copy_signed_system_file()
        name = self.signer_name(sample)
        accepted = self.run_pinned(name)
        self.assertEqual(accepted.returncode, 0, accepted.stderr)
        self.assertIn(f"every publisher matched '{name}'", accepted.stdout)
        for wrong in ("Tomiya7688", name.upper() if name.upper() != name else name.lower(), name[:-1]):
            rejected = self.run_pinned(wrong)
            self.assertNotEqual(rejected.returncode, 0, wrong)
            self.assertIn("Unexpected publisher", rejected.stderr)


if __name__ == "__main__":
    unittest.main()
