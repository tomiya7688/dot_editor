"""Exercise the read-only Windows distribution signature inspection."""

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "verify_windows_signatures.ps1"


# {
#   責務: [WindowsSignatureTests: 署名検査の実行と失敗条件を確認する]
#   フィールド: [なし]
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
                "DOT_EDITOR_SIGNATURE_SCRIPT": str(SCRIPT),
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
    #   責務: [test_signed_system_file: 署名付きの実ファイルを検査する]
    #   処理: [1: Windows標準ファイルを検査用に複製する, 2: 署名と改変後の失敗を検査する]
    #   引数: [self: テストインスタンス]
    #   戻り値: [なし。テスト環境で署名情報を利用できない場合はskip]
    # }
    def test_signed_system_file(self):
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
        result = self.run_verifier()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("checked timestamp presence", result.stdout)
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
