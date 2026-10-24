import hashlib
import importlib.util
from pathlib import Path
import re
import ssl
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("python_trust", ROOT / "scripts/python_trust.py")
trust = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(trust)


# {
#   責務: [PythonTrustTests: trust更新の順序・境界・失敗時の停止を検証する]
#   フィールド: []
# }
class PythonTrustTests(unittest.TestCase):
    # {
    #   責務: [test_version_boundaries: 不足版・不明版と安定版の最低条件を区別する]
    #   処理: [1: 最低版付近と未導入・プレリリースを比較する]
    #   引数: [self: テストの実行状態]
    #   戻り値: [なし。不一致ならテスト失敗]
    # }
    def test_version_boundaries(self):
        # 未確認の版形式を更新済みと数えない。
        for version in (None, "26.2.1", "26.2", "26.2.2rc1", "unknown"):
            self.assertFalse(trust.meets_minimum(version, (26, 2, 2)))
        for version in ("26.2.2", "26.3", "27.0"):
            self.assertTrue(trust.meets_minimum(version, (26, 2, 2)))
        self.assertRegex(trust.BAD_ROOT, r"^[0-9a-f]{64}$")

    # {
    #   責務: [test_bundle_checks_der_not_labels: ラベルがなくてもDER本体で対象rootを検出する]
    #   処理: [1: 小さなPEMを検査する, 2: 同じDERを拒否対象にして失敗を確認する]
    #   引数: [self: テストの実行状態]
    #   戻り値: [なし。不一致ならテスト失敗]
    # }
    def test_bundle_checks_der_not_labels(self):
        # 公開CAの実PEMを使い、検出対象のhashだけをテスト内で差し替える。
        bundled = importlib.import_module("pip._vendor.certifi")
        pem = re.search(r"-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----",
                        Path(bundled.where()).read_text(encoding="ascii"), re.S).group()
        fingerprint = hashlib.sha256(ssl.PEM_cert_to_DER_cert(pem)).hexdigest()
        with tempfile.TemporaryDirectory() as directory:
            bundle = Path(directory) / "ca.pem"
            bundle.write_text(pem, encoding="ascii")
            self.assertEqual(trust.inspect_ca_bundle(bundle)["certificates"], 1)
            with patch.object(trust, "BAD_ROOT", fingerprint):
                with self.assertRaisesRegex(ValueError, "Affected emSign root"):
                    trust.inspect_ca_bundle(bundle)
            bundle.write_text("no certificates", encoding="ascii")
            with self.assertRaisesRegex(ValueError, "no PEM"):
                trust.inspect_ca_bundle(bundle)
            bundle.write_text("-----BEGIN CERTIFICATE-----\nYWJj\n-----END CERTIFICATE-----\n",
                              encoding="ascii")
            with self.assertRaises(ssl.SSLError):
                trust.inspect_ca_bundle(bundle)
            bundle.write_text(pem + "\n-----BEGIN TRUSTED CERTIFICATE-----\nYWJj\n"
                              "-----END TRUSTED CERTIFICATE-----\n", encoding="ascii")
            with self.assertRaisesRegex(ValueError, "Unsupported PEM label"):
                trust.inspect_ca_bundle(bundle)

    # {
    #   責務: [test_default_capath_checks_unloaded_files: 既定Contextに未読込のhash名証明書も検査する]
    #   処理: [1: 既定capathを一時領域へ差し替える, 2: hash名だけの検査と失敗伝播を確認する]
    #   引数: [self: テストの実行状態]
    #   戻り値: [なし。不一致ならテスト失敗]
    # }
    def test_default_capath_checks_unloaded_files(self):
        # 実OSの証明書を変更せず、遅延読込と無関係なファイル・CRLを区別する。
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            for name in ("1234abcd.0", "1234abcd.1", "ignored.pem", "1234abcd.r0"):
                (path / name).touch()
            paths = ssl.get_default_verify_paths()._replace(openssl_capath=directory)
            with patch.dict(trust.os.environ, {}, clear=True), \
                 patch.object(trust.ssl, "get_default_verify_paths", return_value=paths), \
                 patch.object(trust.ssl, "create_default_context") as context, \
                 patch.object(trust, "inspect_ca_bundle", return_value={"certificates": 1}) as inspect:
                context.return_value.get_ca_certs.return_value = []
                report = trust.inspect_default_roots()
                self.assertEqual(report["loaded_certificates"], 0)
                self.assertEqual(report["ca_directories"][0]["certificates"], 2)
                self.assertEqual({call.args[0].name for call in inspect.call_args_list},
                                 {"1234abcd.0", "1234abcd.1"})
                inspect.side_effect = ValueError("Affected emSign root")
                with self.assertRaisesRegex(ValueError, "Affected emSign root"):
                    trust.inspect_default_roots()

    # {
    #   責務: [test_pip_upgrade_precedes_other_network_access: 旧pip更新と検証がcertifi取得より先であることを確認する]
    #   処理: [1: 呼出順を記録しhash付き更新・検査・取得・再監査の順を照合する]
    #   引数: [self: テストの実行状態]
    #   戻り値: [なし。不一致ならテスト失敗]
    # }
    def test_pip_upgrade_precedes_other_network_access(self):
        # ネットワークやインストールを実行せず、順序の契約を確認する。
        calls = []
        with patch.object(trust, "installed_version", return_value="26.2.1"), \
             patch.object(trust, "install_requirement", side_effect=lambda value: calls.append(value)), \
             patch.object(trust, "inspect_pip_bundle", side_effect=lambda: calls.append("pip-check")), \
             patch.object(trust, "inspect_default_roots", side_effect=lambda: calls.append("os-check")), \
             patch.object(trust, "inspect_ca_overrides", side_effect=lambda: calls.append("overrides")), \
             patch.object(trust, "audit_environment", side_effect=lambda: calls.append("audit")):
            trust.bootstrap_environment()
        self.assertEqual(calls, [trust.PIP_WHEEL, "pip-check", "os-check", "overrides",
                                 "certifi>=2026.10.19", "audit"])
        self.assertEqual(trust.PIP_WHEEL.rsplit("#sha256=", 1)[1],
                         "fd7f4dfa8190e014013b9f08f3e973f4e4c26ffd179a204895533a7254813a70")

    # {
    #   責務: [test_failed_pip_validation_stops_installation: pip検証失敗後に追加パッケージを取得しないことを確認する]
    #   処理: [1: 更新済みpipの検証を失敗させ取得が呼ばれないことを確認する]
    #   引数: [self: テストの実行状態]
    #   戻り値: [なし。不一致ならテスト失敗]
    # }
    def test_failed_pip_validation_stops_installation(self):
        # 新しいpipを古い固定wheelへ戻す処理も発生させない。
        with patch.object(trust, "installed_version", return_value="27.0"), \
             patch.object(trust, "inspect_pip_bundle", side_effect=ValueError("unsafe")), \
             patch.object(trust, "install_requirement") as install:
            with self.assertRaises(ValueError):
                trust.bootstrap_environment()
            install.assert_not_called()

    # {
    #   責務: [test_newer_pip_is_preserved_on_success: 新しい安定版pipを再導入せずcertifi取得と監査を完了する]
    #   処理: [1: 新しいpipの正常経路を実行する, 2: certifiだけの取得と最終結果を確認する]
    #   引数: [self: テストの実行状態]
    #   戻り値: [なし。不一致ならテスト失敗]
    # }
    def test_newer_pip_is_preserved_on_success(self):
        # pipを戻さないことと、必要なcertifi更新を省かないことを同時に確認する。
        with patch.object(trust, "installed_version", return_value="27.0"), \
             patch.object(trust, "inspect_pip_bundle"), \
             patch.object(trust, "inspect_default_roots"), \
             patch.object(trust, "inspect_ca_overrides"), \
             patch.object(trust, "install_requirement") as install, \
             patch.object(trust, "audit_environment", return_value={"verified": True}) as audit:
            self.assertEqual(trust.bootstrap_environment(), {"verified": True})
            install.assert_called_once_with("certifi>=2026.10.19")
            audit.assert_called_once_with()

    # {
    #   責務: [test_old_pip_stops_at_each_failed_gate: 旧pip更新後に検査が失敗したらcertifiを取得しない]
    #   処理: [1: 各検査を個別に失敗させる, 2: 取得がpipの固定wheelだけであることを確認する]
    #   引数: [self: テストの実行状態]
    #   戻り値: [なし。不一致ならテスト失敗]
    # }
    def test_old_pip_stops_at_each_failed_gate(self):
        # 各ゲートの失敗を独立させ、ネットワークにも実際の証明書にも依存させない。
        for failed_gate in ("inspect_pip_bundle", "inspect_default_roots", "inspect_ca_overrides"):
            with self.subTest(gate=failed_gate), \
                 patch.object(trust, "installed_version", return_value="26.2.1"), \
                 patch.object(trust, "inspect_pip_bundle"), \
                 patch.object(trust, "inspect_default_roots"), \
                 patch.object(trust, "inspect_ca_overrides"), \
                 patch.object(trust, failed_gate, side_effect=ValueError("unsafe")), \
                 patch.object(trust, "install_requirement") as install:
                with self.assertRaisesRegex(ValueError, "unsafe"):
                    trust.bootstrap_environment()
                install.assert_called_once_with(trust.PIP_WHEEL)

    # {
    #   責務: [test_check_mode_never_installs: 読み取り専用検査が更新を行わないことを確認する]
    #   処理: [1: CLIを検査モードで実行しbootstrapが呼ばれないことを確認する]
    #   引数: [self: テストの実行状態]
    #   戻り値: [なし。不一致ならテスト失敗]
    # }
    def test_check_mode_never_installs(self):
        # 検査モードの成功時も失敗時もインストールは行わない。
        with patch.object(trust, "bootstrap_environment") as bootstrap, \
             patch.object(trust, "audit_environment", return_value={}):
            self.assertEqual(trust.main(["--check"]), 0)
            bootstrap.assert_not_called()
        with patch.object(trust, "audit_environment", side_effect=ValueError("unsafe")):
            self.assertEqual(trust.main(["--check"]), 2)

    # {
    #   責務: [test_install_uses_same_python_and_secure_flags: 取得先と実行Pythonと失敗伝播を検証する]
    #   処理: [1: subprocess引数を確認する, 2: 取得失敗を呼出元へ伝えることを確認する]
    #   引数: [self: テストの実行状態]
    #   戻り値: [なし。不一致ならテスト失敗]
    # }
    def test_install_uses_same_python_and_secure_flags(self):
        # シェル経由や別のpip、TLS検証無効化へ変わらないようにする。
        with patch.object(trust.subprocess, "run") as run:
            trust.install_requirement(trust.PIP_WHEEL)
            command = run.call_args.args[0]
            self.assertEqual(command[:3], [sys.executable, "-m", "pip"])
            for flag in ("--isolated", "--no-cache-dir", "--no-deps", "--only-binary=:all:"):
                self.assertIn(flag, command)
            self.assertNotIn("--trusted-host", command)
            self.assertEqual(run.call_args.kwargs, {"check": True, "timeout": 300})
        with patch.object(trust.subprocess, "run", side_effect=subprocess.CalledProcessError(1, "pip")):
            with self.assertRaises(subprocess.CalledProcessError):
                trust.install_requirement(trust.PIP_WHEEL)

    # {
    #   責務: [test_ca_overrides_are_not_silently_ignored: 追加CAファイルの検査と未検証ディレクトリの拒否を確認する]
    #   処理: [1: 有効な追加CA指定を検査へ渡す, 2: ディレクトリ指定を拒否する]
    #   引数: [self: テストの実行状態]
    #   戻り値: [なし。不一致ならテスト失敗]
    # }
    def test_ca_overrides_are_not_silently_ignored(self):
        # 利用者の実際の環境変数やCAファイルはテストから変更しない。
        with patch.dict(trust.os.environ, {"REQUESTS_CA_BUNDLE": "extra.pem"}, clear=True), \
             patch.object(trust, "inspect_ca_bundle", return_value={}) as inspect:
            self.assertEqual(trust.inspect_ca_overrides(), {"REQUESTS_CA_BUNDLE": {}})
            inspect.assert_called_once_with("extra.pem")
        with patch.dict(trust.os.environ, {"SSL_CERT_DIR": "unknown"}, clear=True):
            with self.assertRaisesRegex(ValueError, "separate trust audit"):
                trust.inspect_ca_overrides()

    # {
    #   責務: [test_outdated_optional_packages_fail_without_implicit_install: 導入済み任意ツールの不足版を黙認しないことを確認する]
    #   処理: [1: uvが古い環境で読み取り専用監査を失敗させる]
    #   引数: [self: テストの実行状態]
    #   戻り値: [なし。不一致ならテスト失敗]
    # }
    def test_outdated_optional_packages_fail_without_implicit_install(self):
        # 使っていないツールを導入せず、使っている古いツールは別途更新を要求する。
        versions = {"pip": "26.2.2", "certifi": "2026.10.19", "uv": "0.13.3", "sigstore": None}
        with patch.object(trust, "installed_version", side_effect=versions.get), \
             patch.object(trust, "install_requirement") as install:
            with self.assertRaisesRegex(ValueError, "uv must be"):
                trust.audit_environment()
            install.assert_not_called()

    # {
    #   責務: [test_setup_and_ci_keep_the_security_gate: セットアップ・CIの検査経路と暫定公開停止を維持する]
    #   処理: [1: 各入口が共通スクリプトを呼ぶことを確認する, 2: 未署名uploadの復活を検出する]
    #   引数: [self: テストの実行状態]
    #   戻り値: [なし。不一致ならテスト失敗]
    # }
    def test_setup_and_ci_keep_the_security_gate(self):
        # #55で署名gateを実装する際は、この暫定公開停止の期待値も見直す。
        workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertEqual(workflow.count("run: python scripts/python_trust.py"), 1)
        self.assertEqual(workflow.count("python scripts/python_trust.py --check"), 2)
        self.assertIn("run: ./scripts/build_windows.ps1", workflow)
        self.assertIn("python -m unittest discover -s tests", workflow)
        self.assertNotIn("actions/upload-artifact", workflow)
        for name in ("setup_environment.ps1", "build_windows.ps1"):
            content = (ROOT / "scripts" / name).read_text(encoding="utf-8")
            self.assertIn('"python_trust.py"', content)
            self.assertIn("--check", content)
        self.assertIn("python scripts/python_trust.py", (ROOT / "README.md").read_text(encoding="utf-8"))
