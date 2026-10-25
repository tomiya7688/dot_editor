"""Distrust the affected root only on an ephemeral GitHub-hosted Ubuntu runner."""
import hashlib
import os
from pathlib import Path
import re
import ssl
import subprocess
import sys
import tempfile

from python_trust import BAD_ROOT


# {
#   責務: [plan_distrust: UbuntuのCA選択設定から対象rootだけを無効化する計画を作る]
#   処理: [1: 有効な証明書のパスと実DERを確認する, 2: 一致する行だけを無効化する]
#   引数: [configuration: 現在の設定本文, certificate_directory: 配布元の証明書ディレクトリ]
#   戻り値: [更新本文と無効化する相対パス一覧。範囲外・不正PEMは例外]
# }
def plan_distrust(configuration, certificate_directory):
    # 名前だけで証明書を削除せず、設定で選ばれた実DERのfingerprintを照合する。
    directory = Path(certificate_directory).resolve()
    updated = []
    disabled = []
    for line in configuration.splitlines(keepends=True):
        name = line.strip()
        if name and line.rstrip("\r\n") != name:
            raise ValueError(f"Whitespace around CA selection is unsupported: {name}")
        if name and not name.startswith(("#", "!")):
            certificate_path = (directory / name).resolve()
            if not certificate_path.is_relative_to(directory):
                raise ValueError(f"CA path is outside the distribution directory: {name}")
            content = certificate_path.read_bytes()
            certificates = re.findall(rb"-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----",
                                      content, re.S)
            if len(certificates) != 1:
                raise ValueError(f"Expected one PEM certificate: {certificate_path}")
            # Ubuntuの仕様は1ファイル1証明書。比較前にOpenSSLで構造も検証する。
            certificate = certificates[0].decode("ascii")
            ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT).load_verify_locations(cadata=certificate)
            fingerprint = hashlib.sha256(ssl.PEM_cert_to_DER_cert(certificate)).hexdigest()
            if fingerprint == BAD_ROOT:
                line = "!" + line
                disabled.append(name)
        updated.append(line)
    return "".join(updated), disabled


# {
#   責務: [replace_configuration: 確定したCA選択設定を同じディレクトリで原子的に置き換える]
#   処理: [1: 一時ファイルへ設定を書き同期する, 2: 元の権限を維持して置き換える]
#   引数: [configuration_path: 既存設定の固定パス, content: 検証済みの更新本文]
#   戻り値: [なし。書込失敗時は例外]
# }
def replace_configuration(configuration_path, content):
    # 書込途中の設定をupdate-ca-certificatesへ渡さない。失敗時は一時ファイルだけ除去する。
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="",
                                         dir=configuration_path.parent, delete=False) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(content)
            temporary.flush()
            os.fsync(temporary.fileno())
        temporary_path.chmod(configuration_path.stat().st_mode & 0o777)
        # 使い捨てrunnerの終了後は再利用しないため、電源断後の永続性は保証しない。
        os.replace(temporary_path, configuration_path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


# {
#   責務: [main: GitHub-hosted Linuxだけで対象rootのOS信頼を無効化して再生成する]
#   処理: [1: 実行環境と権限を制限する, 2: 設定を更新してCA bundleを再生成する]
#   引数: []
#   戻り値: [成功0、対象外環境・更新失敗2]
# }
def main():
    # 利用者PC・self-hosted runnerを自動変更しない。環境名は認証境界ではなく誤実行防止。
    expected = {"GITHUB_ACTIONS": "true", "RUNNER_ENVIRONMENT": "github-hosted", "RUNNER_OS": "Linux"}
    if (sys.platform != "linux" or any(os.environ.get(key) != value for key, value in expected.items())
            or os.geteuid() != 0):
        print("CA repair requires a root GitHub-hosted Linux runner", file=sys.stderr)
        return 2
    try:
        configuration_path = Path("/etc/ca-certificates.conf")
        if configuration_path.is_symlink():
            raise ValueError("CI CA configuration must not be a symlink")
        original = configuration_path.read_text(encoding="utf-8")
        updated, disabled = plan_distrust(original, Path("/usr/share/ca-certificates"))
        if disabled:
            replace_configuration(configuration_path, updated)
        # 既に無効化済みでも古いbundleやhashリンクを残さず、毎回再生成する。
        subprocess.run(["/usr/sbin/update-ca-certificates", "--fresh"], check=True, timeout=120)
        print(f"Disabled affected CA entries: {disabled}")
        return 0
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(f"CI CA preparation failed: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
