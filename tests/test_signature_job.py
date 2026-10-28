"""Check that the dedicated signature worker does not leave its child running."""

import ctypes
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

WORKER = Path(__file__).resolve().parents[1] / "scripts" / "verify_windows_signatures_worker.ps1"


# {
#   責務: [SignatureJobTests: 専用ワーカー終了時の子プロセス終了を確認する]
#   フィールド: [なし]
# }
@unittest.skipUnless(sys.platform == "win32", "Windows job objects are required")
class SignatureJobTests(unittest.TestCase):
    # {
    #   責務: [check_worker_stops_child: ワーカー終了後の子プロセス終了を検証する]
    #   処理: [1: 模擬署名APIから子を起動する, 2: 指定した方法でワーカーを終了し子の終了を確認する]
    #   引数: [self: テストインスタンス, terminate: ワーカーを強制終了するか]
    #   戻り値: [なし]
    # }
    def check_worker_stops_child(self, terminate):
        # 自動削除する専用領域だけにPIDと同期用ファイルを置く。
        with tempfile.TemporaryDirectory(dir=os.environ.get("DOT_EDITOR_TEST_TEMP")) as temporary:
            directory = Path(temporary)
            (directory / "fixture.exe").write_bytes(b"fixture")
            pid_file = directory / "child.pid"
            release_file = directory / "release"
            child_code = (
                "import os,pathlib,time; p=pathlib.Path(os.environ['DOT_EDITOR_JOB_PID']); "
                "q=p.with_suffix('.pending'); q.write_text(str(os.getpid())); q.replace(p); "
                "time.sleep(90)"
            )
            # 外部プロセスを起動する署名APIを模擬し、テスト側が終了確認用ハンドルを開くまで待つ。
            command = (
                "function Get-AuthenticodeSignature { param($LiteralPath) "
                "$s=[Diagnostics.ProcessStartInfo]::new(); $s.FileName=$env:DOT_EDITOR_JOB_PYTHON; "
                "$s.UseShellExecute=$false; [void]$s.ArgumentList.Add('-c'); "
                "[void]$s.ArgumentList.Add($env:DOT_EDITOR_JOB_CODE); "
                "[void][Diagnostics.Process]::Start($s); "
                "for($i=0; $i -lt 1200 -and -not (Test-Path -LiteralPath $env:DOT_EDITOR_JOB_RELEASE); $i++) "
                "{ Start-Sleep -Milliseconds 50 }; "
                "if(-not (Test-Path -LiteralPath $env:DOT_EDITOR_JOB_RELEASE)) { throw 'release timeout' }; "
                "[pscustomobject]@{Status='Valid';SignerCertificate=1;TimeStamperCertificate=1} }; "
                "& $env:DOT_EDITOR_JOB_WORKER -Directory $env:DOT_EDITOR_JOB_DIRECTORY -DedicatedProcess"
            )
            process = subprocess.Popen(
                ["pwsh", "-NoProfile", "-NonInteractive", "-Command", command],
                env={
                    **os.environ,
                    "DOT_EDITOR_JOB_WORKER": str(WORKER),
                    "DOT_EDITOR_JOB_DIRECTORY": str(directory),
                    "DOT_EDITOR_JOB_PYTHON": sys.executable,
                    "DOT_EDITOR_JOB_CODE": child_code,
                    "DOT_EDITOR_JOB_PID": str(pid_file),
                    "DOT_EDITOR_JOB_RELEASE": str(release_file),
                },
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            # PIDの再利用を避けるため、子が動いている間に照会用ハンドルを保持する。
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
            kernel32.OpenProcess.restype = ctypes.c_void_p
            kernel32.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
            kernel32.WaitForSingleObject.restype = ctypes.c_uint32
            kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
            kernel32.CloseHandle.restype = ctypes.c_int
            handle = None
            try:
                deadline = time.monotonic() + 90
                while (
                    not pid_file.is_file()
                    and process.poll() is None
                    and time.monotonic() < deadline
                ):
                    time.sleep(0.1)
                self.assertTrue(pid_file.is_file(), "Child did not start")
                handle = kernel32.OpenProcess(0x00100000, False, int(pid_file.read_text("ascii")))
                self.assertTrue(handle, f"Could not inspect child: {ctypes.get_last_error()}")
                # 通常終了と強制終了のどちらでもJobの最後のハンドルが閉じる。
                if terminate:
                    process.kill()
                else:
                    release_file.touch()
                stdout, stderr = process.communicate(timeout=90)
                if terminate:
                    self.assertNotEqual(process.returncode, 0, stdout)
                else:
                    self.assertEqual(process.returncode, 0, stderr)
                    self.assertIn("checked timestamp presence", stdout)
                self.assertEqual(kernel32.WaitForSingleObject(handle, 5000), 0)
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=5)
                if process.stdout is not None:
                    process.stdout.close()
                if process.stderr is not None:
                    process.stderr.close()
                if handle:
                    kernel32.CloseHandle(handle)

    # {
    #   責務: [test_worker_exit_stops_child: 正常終了時に子を残さない]
    #   処理: [1: ワーカーを正常終了させ, 2: 子の終了を確認する]
    #   引数: [self: テストインスタンス]
    #   戻り値: [なし]
    # }
    def test_worker_exit_stops_child(self):
        # 署名成功で終了する場合も、ワーカーの子は残らない。
        self.check_worker_stops_child(False)

    # {
    #   責務: [test_worker_termination_stops_child: 強制終了時に子を残さない]
    #   処理: [1: ワーカーを強制終了させ, 2: 子の終了を確認する]
    #   引数: [self: テストインスタンス]
    #   戻り値: [なし]
    # }
    def test_worker_termination_stops_child(self):
        # ワーカーを強制終了した場合も、Jobが子を停止する。
        self.check_worker_stops_child(True)
