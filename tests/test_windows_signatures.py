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

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "verify_windows_signatures.ps1"
WORKER = ROOT / "scripts" / "verify_windows_signatures_worker.ps1"
BOUNDED_PROCESS = ROOT / "scripts" / "invoke_bounded_process.ps1"


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
        target = self.directory / "real"
        (target / "nested").mkdir(parents=True)
        junction = self.directory / "junction"
        created = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(junction), str(target)],
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


if __name__ == "__main__":
    unittest.main()
