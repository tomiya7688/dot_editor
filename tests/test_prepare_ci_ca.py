import hashlib
import importlib.util
from pathlib import Path
import re
import ssl
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("prepare_ci_ca", ROOT / "scripts/prepare_ci_ca.py")
repair = importlib.util.module_from_spec(SPEC)
# scriptsはCLI実行時のimport元。テスト読込でも同じ共有定数を渡す。
TRUST_SPEC = importlib.util.spec_from_file_location("python_trust", ROOT / "scripts/python_trust.py")
trust = importlib.util.module_from_spec(TRUST_SPEC)
TRUST_SPEC.loader.exec_module(trust)
with patch.dict("sys.modules", {"python_trust": trust}):
    SPEC.loader.exec_module(repair)


# {
#   責務: [PrepareCiCaTests: 対象fingerprint限定の無効化とローカル誤実行防止を検証する]
#   フィールド: []
# }
class PrepareCiCaTests(unittest.TestCase):
    # {
    #   責務: [test_only_matching_root_is_disabled: 対象DERだけを無効化しコメントと無関係な選択を保つ]
    #   処理: [1: 一時領域へ公開CAを置く, 2: 一致・不一致と繰返しの計画を照合する]
    #   引数: [self: テストの実行状態]
    #   戻り値: [なし。不一致ならテスト失敗]
    # }
    def test_only_matching_root_is_disabled(self):
        # 安全な公開CAを一時的な拒否対象とし、OSの設定は変更しない。
        import pip._vendor.certifi
        pem = re.search(r"-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----",
                        Path(pip._vendor.certifi.where()).read_text(encoding="ascii"), re.S).group()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / "root.crt").write_text(pem, encoding="ascii")
            # Ubuntuの選択設定には非ASCIIの証明書名もある。PEM外の注釈も内容と区別する。
            (path / "ルート.crt").write_text("# 公開CA\n" + pem, encoding="utf-8")
            self.assertEqual(repair.plan_distrust("ルート.crt\n", path), ("ルート.crt\n", []))
            original = "# comment\n!old.crt\n\nroot.crt\n"
            self.assertEqual(repair.plan_distrust(original, path), (original, []))
            fingerprint = hashlib.sha256(ssl.PEM_cert_to_DER_cert(pem)).hexdigest()
            with patch.object(repair, "BAD_ROOT", fingerprint):
                updated, disabled = repair.plan_distrust(original, path)
                self.assertEqual(updated, "# comment\n!old.crt\n\n!root.crt\n")
                self.assertEqual(disabled, ["root.crt"])
                self.assertEqual(repair.plan_distrust(updated, path), (updated, []))
                self.assertEqual(repair.plan_distrust("ルート.crt\n", path), ("!ルート.crt\n", ["ルート.crt"]))
            with self.assertRaisesRegex(ValueError, "outside"):
                repair.plan_distrust("../escape.crt\n", path)
            with self.assertRaises(FileNotFoundError):
                repair.plan_distrust("missing.crt\n", path)
            for selection in (" root.crt\n", "root.crt \n", " # comment\n", " !root.crt\n"):
                with self.subTest(selection=selection), self.assertRaisesRegex(ValueError, "Whitespace"):
                    repair.plan_distrust(selection, path)
            (path / "root.crt").write_text("invalid", encoding="ascii")
            with self.assertRaisesRegex(ValueError, "one PEM"):
                repair.plan_distrust(original, path)

    # {
    #   責務: [test_local_environment_is_rejected_before_any_write: 通常環境からの呼出しはOSを読み書きしない]
    #   処理: [1: 環境ガードを失敗させる, 2: 設定読取と外部コマンドがないことを確認する]
    #   引数: [self: テストの実行状態]
    #   戻り値: [なし。不一致ならテスト失敗]
    # }
    def test_local_environment_is_rejected_before_any_write(self):
        # 実OSがLinuxの場合でもGitHubの環境を持たなければ拒否する。
        with patch.dict(repair.os.environ, {}, clear=True), \
             patch.object(repair.Path, "read_text") as read, \
             patch.object(repair.subprocess, "run") as run:
            self.assertEqual(repair.main(), 2)
            read.assert_not_called()
            run.assert_not_called()

    # {
    #   責務: [test_ci_regeneration_failure_stops_the_step: CIの再生成失敗を成功扱いせず後続を止める]
    #   処理: [1: runnerの環境だけを模擬する, 2: 再生成コマンドと失敗終了値を確認する]
    #   引数: [self: テストの実行状態]
    #   戻り値: [なし。不一致ならテスト失敗]
    # }
    def test_ci_regeneration_failure_stops_the_step(self):
        # root権限・OSファイル操作・外部コマンドはすべてmockで置き換える。
        environment = {"GITHUB_ACTIONS": "true", "RUNNER_ENVIRONMENT": "github-hosted", "RUNNER_OS": "Linux"}
        with patch.dict(repair.os.environ, environment, clear=True), \
             patch.object(repair.sys, "platform", "linux"), \
             patch.object(repair.os, "geteuid", return_value=0, create=True), \
             patch.object(repair.Path, "read_text", return_value="original"), \
             patch.object(repair.Path, "is_symlink", return_value=False), \
             patch.object(repair, "plan_distrust", return_value=("updated", ["root.crt"])) as plan, \
             patch.object(repair, "replace_configuration") as replace, \
             patch.object(repair.subprocess, "run", side_effect=OSError("failed")) as run:
            self.assertEqual(repair.main(), 2)
            plan.assert_called_once_with("original", Path("/usr/share/ca-certificates"))
            replace.assert_called_once_with(Path("/etc/ca-certificates.conf"), "updated")
            run.assert_called_once_with(["/usr/sbin/update-ca-certificates", "--fresh"],
                                        check=True, timeout=120)

    # {
    #   責務: [test_ci_success_refreshes_even_without_changes: 未変更でも再生成しsymlink設定は更新前に拒否する]
    #   処理: [1: rootの正常なrunner環境を模擬する, 2: 再生成の成功とsymlink時の無操作を確認する]
    #   引数: [self: テストの実行状態]
    #   戻り値: [なし。不一致ならテスト失敗]
    # }
    def test_ci_success_refreshes_even_without_changes(self):
        # 実FSの構成に依存させず、同じガードを経る主経路を検証する。
        environment = {"GITHUB_ACTIONS": "true", "RUNNER_ENVIRONMENT": "github-hosted", "RUNNER_OS": "Linux"}
        with patch.dict(repair.os.environ, environment, clear=True), \
             patch.object(repair.sys, "platform", "linux"), \
             patch.object(repair.os, "geteuid", return_value=0, create=True), \
             patch.object(repair.Path, "read_text", return_value="original") as read, \
             patch.object(repair.Path, "is_symlink", return_value=False) as symlink, \
             patch.object(repair, "plan_distrust", return_value=("original", [])) as plan, \
             patch.object(repair, "replace_configuration") as replace, \
             patch.object(repair.subprocess, "run") as run:
            self.assertEqual(repair.main(), 0)
            plan.assert_called_once_with("original", Path("/usr/share/ca-certificates"))
            replace.assert_not_called()
            run.assert_called_once_with(["/usr/sbin/update-ca-certificates", "--fresh"],
                                        check=True, timeout=120)
            read.reset_mock()
            run.reset_mock()
            symlink.return_value = True
            self.assertEqual(repair.main(), 2)
            read.assert_not_called()
            run.assert_not_called()

    # {
    #   責務: [test_configuration_replacement_is_atomic: 原子的置換に失敗した場合も既存設定を残す]
    #   処理: [1: 一時設定を正常更新する, 2: 置換失敗時の元設定と一時ファイル除去を確認する]
    #   引数: [self: テストの実行状態]
    #   戻り値: [なし。不一致ならテスト失敗]
    # }
    def test_configuration_replacement_is_atomic(self):
        # 専用の一時ディレクトリ以外は読み書きしない。
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ca.conf"
            path.write_text("old\n", encoding="ascii")
            repair.replace_configuration(path, "新しい設定\n")
            self.assertEqual(path.read_text(encoding="utf-8"), "新しい設定\n")
            with patch.object(repair.os, "replace", side_effect=OSError("denied")):
                with self.assertRaises(OSError):
                    repair.replace_configuration(path, "unfinished\n")
            self.assertEqual(path.read_text(encoding="utf-8"), "新しい設定\n")
            self.assertEqual(list(Path(directory).iterdir()), [path])
