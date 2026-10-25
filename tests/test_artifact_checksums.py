import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("artifact_checksums", ROOT / "scripts/artifact_checksums.py")
checksums = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(checksums)


# {
#   責務: [ArtifactChecksumTests: 最終成果物の一覧・改変検知・原子的保存を検証する]
#   フィールド: [temporary: 専用一時領域, directory: 検査するdist, names: fixtureの成果物名]
# }
class ArtifactChecksumTests(unittest.TestCase):
    # {
    #   責務: [setUp: 各テスト専用の不透明な成果物fixtureを用意する]
    #   処理: [1: 一時領域を作成する, 2: 最終3成果物の名前と内容を保存する]
    #   引数: [self: テストの実行状態]
    #   戻り値: [なし]
    # }
    def setUp(self):
        # パッケージの実行検査とは分離し、ここではhashと一覧の契約だけを確認する。
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.names = ("hyper_dot_editor-0.1.0-py3-none-any.whl", "hyper_dot_editor-0.1.0.tar.gz",
                      "HyperDotEditor-windows-x64.zip")
        for name in self.names:
            (self.directory / name).write_bytes(name.encode("ascii"))

    # {
    #   責務: [test_manifest_is_deterministic_and_checked: 全3成果物を名前順に記録し再計算できる]
    #   処理: [1: manifestを生成する, 2: 正確なhashとLF終端と繰返し不変を確認する]
    #   引数: [self: テストの実行状態]
    #   戻り値: [なし。不一致ならテスト失敗]
    # }
    def test_manifest_is_deterministic_and_checked(self):
        # ディレクトリ順に依存せず、既存manifest自身を再帰的にhashしない。
        manifest = checksums.write_manifest(self.directory)
        expected = "".join(f"{hashlib.sha256(name.encode('ascii')).hexdigest()}  {name}\n"
                           for name in sorted(self.names)).encode("ascii")
        self.assertEqual(manifest.read_bytes(), expected)
        checksums.verify_manifest(self.directory)
        checksums.write_manifest(self.directory)
        self.assertEqual(manifest.read_bytes(), expected)

    # {
    #   責務: [test_modified_artifact_or_manifest_is_rejected: 成果物改変とmanifest改変を拒否する]
    #   処理: [1: 成果物を改変して失敗を確認する, 2: manifestの余分な行も拒否する]
    #   引数: [self: テストの実行状態]
    #   戻り値: [なし。不一致ならテスト失敗]
    # }
    def test_modified_artifact_or_manifest_is_rejected(self):
        # manifest内の任意パスを開かせるのではなく本文全体の一致を要求する。
        manifest = checksums.write_manifest(self.directory)
        (self.directory / self.names[0]).write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "does not match"):
            checksums.verify_manifest(self.directory)
        manifest.write_bytes(b"x" * 100000)
        with self.assertRaisesRegex(ValueError, "does not match"):
            checksums.verify_manifest(self.directory)
        checksums.write_manifest(self.directory)
        with manifest.open("ab") as stream:
            stream.write(b"0" * 64 + b"  ../outside\n")
        with self.assertRaisesRegex(ValueError, "does not match"):
            checksums.verify_manifest(self.directory)

    # {
    #   責務: [test_missing_duplicate_empty_and_unlisted_outputs_fail: 不完全・混在したdistを署名対象にしない]
    #   処理: [1: 空・欠落・別版追加・未知のファイルを個別に検査する]
    #   引数: [self: テストの実行状態]
    #   戻り値: [なし。不一致ならテスト失敗]
    # }
    def test_missing_duplicate_empty_and_unlisted_outputs_fail(self):
        # 検査のためだけの変更は各ケースで元へ戻す。
        target = self.directory / self.names[0]
        target.write_bytes(b"")
        with self.assertRaisesRegex(ValueError, "non-empty"):
            checksums.checksum_manifest(self.directory)
        target.unlink()
        with self.assertRaisesRegex(ValueError, "exactly one"):
            checksums.checksum_manifest(self.directory)
        target.write_bytes(b"wheel")
        extra = self.directory / "hyper_dot_editor-0.2.0-py3-none-any.whl"
        extra.write_bytes(b"old")
        with self.assertRaisesRegex(ValueError, "exactly one"):
            checksums.checksum_manifest(self.directory)
        extra.unlink()
        extra = self.directory / "unknown.zip"
        extra.write_bytes(b"unknown")
        with self.assertRaisesRegex(ValueError, "Unlisted"):
            checksums.checksum_manifest(self.directory)

    # {
    #   責務: [test_version_mismatch_is_rejected: wheelとsdistが別版なら拒否する]
    #   処理: [1: sdistだけ別版へ変更して検査を失敗させる]
    #   引数: [self: テストの実行状態]
    #   戻り値: [なし。不一致ならテスト失敗]
    # }
    def test_version_mismatch_is_rejected(self):
        # 各種別が1個ずつでも、異なる版の混在は受け入れない。
        (self.directory / self.names[1]).rename(self.directory / "hyper_dot_editor-0.2.0.tar.gz")
        with self.assertRaisesRegex(ValueError, "versions differ"):
            checksums.checksum_manifest(self.directory)

    # {
    #   責務: [test_write_failure_preserves_previous_manifest: 置換失敗で既存manifestを破壊しない]
    #   処理: [1: 置換だけを失敗させる, 2: 元本文維持と一時ファイル除去を確認する]
    #   引数: [self: テストの実行状態]
    #   戻り値: [なし。不一致ならテスト失敗]
    # }
    def test_write_failure_preserves_previous_manifest(self):
        # 他のファイルに触れず、このテストの一時領域内で失敗を注入する。
        manifest = self.directory / "SHA256SUMS"
        manifest.write_bytes(b"previous")
        with patch.object(checksums.os, "replace", side_effect=OSError("denied")):
            with self.assertRaises(OSError):
                checksums.write_manifest(self.directory)
        self.assertEqual(manifest.read_bytes(), b"previous")
        self.assertEqual({path.name for path in self.directory.iterdir()}, set(self.names) | {"SHA256SUMS"})

    # {
    #   責務: [test_check_mode_never_writes: CLIの読取専用検査と改変時の非0を確認する]
    #   処理: [1: 未作成状態を検査する, 2: 成功と改変失敗をインストール・保存なしで確認する]
    #   引数: [self: テストの実行状態]
    #   戻り値: [なし。不一致ならテスト失敗]
    # }
    def test_check_mode_never_writes(self):
        # --checkは不足ファイルを勝手に再生成しない。
        with patch.object(checksums, "write_manifest") as write:
            self.assertEqual(checksums.main([str(self.directory), "--check"]), 2)
            write.assert_not_called()
        self.assertEqual(checksums.main([str(self.directory)]), 0)
        self.assertEqual(checksums.main([str(self.directory), "--check"]), 0)
        (self.directory / self.names[2]).write_bytes(b"changed")
        self.assertEqual(checksums.main([str(self.directory), "--check"]), 2)

    # {
    #   責務: [test_symlinks_are_not_signature_subjects: 成果物とmanifestのリンクを署名対象にしない]
    #   処理: [1: 一時領域内だけを指すリンクを作る, 2: 読取・生成の両経路で拒否を確認する]
    #   引数: [self: テストの実行状態]
    #   戻り値: [なし。不一致なら失敗。リンク作成権限がなければ未実施を記録]
    # }
    def test_symlinks_are_not_signature_subjects(self):
        # OSの実ファイルを指さず、このfixtureの内部だけで境界を検査する。
        target = self.directory / self.names[0]
        payload = self.directory / "payload"
        target.rename(payload)
        try:
            target.symlink_to(payload)
        except OSError:
            self.skipTest("Creating symlinks is not permitted by this OS account")
        with self.assertRaisesRegex(ValueError, "symlink"):
            checksums.checksum_manifest(self.directory)
        target.unlink()
        payload.rename(target)
        manifest = self.directory / "SHA256SUMS"
        manifest.symlink_to(target)
        with self.assertRaisesRegex(ValueError, "symlink"):
            checksums.verify_manifest(self.directory)
        with self.assertRaisesRegex(ValueError, "symlink"):
            checksums.write_manifest(self.directory)

    # {
    #   責務: [test_ci_attests_and_verifies_all_final_subjects: 最終3成果物とmanifestの出所検証をCIへ結び付ける]
    #   処理: [1: 固定actionと対象4種を確認する, 2: source制約と公開停止を確認する]
    #   引数: [self: テストの実行状態]
    #   戻り値: [なし。不一致ならテスト失敗]
    # }
    def test_ci_attests_and_verifies_all_final_subjects(self):
        # 静的な契約だけでOIDCの実動作成功とは扱わず、push CIで別に確認する。
        workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertIn("actions/attest@1e69f48acb82d1966a394da916b4c1698aa569d6", workflow)
        for subject in ("dist/HyperDotEditor-windows-x64.zip", "dist/hyper_dot_editor-*.whl",
                        "dist/hyper_dot_editor-*.tar.gz", "dist/SHA256SUMS"):
            self.assertIn(subject, workflow)
        for flag in ("--signer-workflow", "--source-digest", "--source-ref", "--deny-self-hosted-runners"):
            self.assertIn(flag, workflow)
        self.assertNotIn("actions/upload-artifact", workflow)
        build = (ROOT / "scripts/build_windows.ps1").read_text(encoding="utf-8")
        self.assertIn("scripts/artifact_checksums.py dist", build)


if __name__ == "__main__":
    unittest.main()
