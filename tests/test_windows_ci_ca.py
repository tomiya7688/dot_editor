import os
from pathlib import Path
import re
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]


# {
#   責務: [WindowsCiCaTests: Windows専用の対象fingerprintと誤実行防止を検証する]
#   フィールド: []
# }
class WindowsCiCaTests(unittest.TestCase):
    # {
    #   責務: [test_fingerprint_matches_python_audit: 除去対象と後続Python検査の対象を一致させる]
    #   処理: [1: 両入口の定数を読み取る, 2: 対象ストアとfingerprintの一致を照合する]
    #   引数: [self: テストの実行状態]
    #   戻り値: [なし。不一致ならテスト失敗]
    # }
    def test_fingerprint_matches_python_audit(self):
        # 証明書の主語名による広い削除へ変わらないよう、実DERのhashとの対応を維持する。
        script = (ROOT / "scripts/prepare_ci_windows_ca.ps1").read_text(encoding="utf-8")
        python = (ROOT / "scripts/python_trust.py").read_text(encoding="utf-8")
        fingerprint = re.search(r"\$AffectedFingerprint = '([0-9a-f]{64})'", script).group(1)
        self.assertIn(f'BAD_ROOT = "{fingerprint}"', python)
        self.assertIn("@('LocalMachine', 'CurrentUser')", script)
        self.assertIn("@('Root', 'CA')", script)
        self.assertIn("$Hasher.ComputeHash($Certificate.RawData)", script)
        self.assertIn("if ($Fingerprint -eq $AffectedFingerprint)", script)

    # {
    #   責務: [test_local_execution_stops_before_store_access: CIではない呼出しが証明書ストアに触れず停止する]
    #   処理: [1: CI識別変数を除いた子プロセスで実行する, 2: ガードの終了値と診断を確認する]
    #   引数: [self: テストの実行状態]
    #   戻り値: [なし。不一致ならテスト失敗。PowerShell未導入なら未実施を記録]
    # }
    def test_local_execution_stops_before_store_access(self):
        # 本体をローカルへ適用せず、構文とガードだけを実PowerShellで確認する。
        powershell = shutil.which("pwsh") or shutil.which("powershell")
        if powershell is None:
            self.skipTest("PowerShell is unavailable; actual repair remains a Windows CI check")
        environment = os.environ.copy()
        for name in ("GITHUB_ACTIONS", "RUNNER_ENVIRONMENT", "RUNNER_OS"):
            environment.pop(name, None)
        result = subprocess.run([powershell, "-NoProfile", "-File",
                                 str(ROOT / "scripts/prepare_ci_windows_ca.ps1")],
                                env=environment, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("requires a GitHub-hosted Windows runner", result.stderr)
        self.assertNotIn("Removed affected CA copies", result.stdout)
