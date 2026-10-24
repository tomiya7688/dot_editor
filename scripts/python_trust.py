"""Run in a fresh Python process to bootstrap or inspect this interpreter's trust bundles."""
import argparse
import hashlib
import importlib
from importlib import metadata
import json
import os
from pathlib import Path
import re
import ssl
import subprocess
import sys

# Python公式告知のwheelとSHA-256。旧pipの信頼ストアだけに更新の真正性を依存させない。
PIP_WHEEL = (
    "pip @ https://files.pythonhosted.org/packages/3f/06/"
    "3e4420302363fbb71be3c7f35ce042f54bfca330e3e66b3a2e3c4cca579f/"
    "pip-26.2.2-py3-none-any.whl#sha256="
    "fd7f4dfa8190e014013b9f08f3e973f4e4c26ffd179a204895533a7254813a70"
)
BAD_ROOT = "86a1ecba089c4a8d3bbe2734c612ba341d813e043cf9e8a862cd5c57a36bbe6b"
MINIMUMS = {"pip": (26, 2, 2), "certifi": (2026, 10, 19),
            "uv": (0, 13, 4), "sigstore": (4, 5, 1)}


# {
#   責務: [installed_version: このPython環境の配布パッケージ版を取得する]
#   処理: [1: metadataを読み未導入の場合だけNoneを返す]
#   引数: [name: 配布パッケージ名]
#   戻り値: [版文字列または未導入を表すNone]
# }
def installed_version(name):
    # pipをimportせず版を読み、更新前の同梱モジュールをプロセスに残さない。
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return None


# {
#   責務: [meets_minimum: 安定版の数値バージョンが最低条件を満たすか判定する]
#   処理: [1: 未導入・不明な版形式を拒否し数値部分を比較する]
#   引数: [version: 取得した版文字列またはNone, minimum: 最低版の整数列]
#   戻り値: [最低条件を満たす場合True]
# }
def meets_minimum(version, minimum):
    # 未確認の開発版・プレリリースを安全な安定版として自動承認しない。
    return bool(version and re.fullmatch(r"\d+(?:\.\d+){1,3}", version)
                and tuple(map(int, version.split("."))) >= minimum)


# {
#   責務: [inspect_ca_bundle: 実PEMの証明書を解析して対象rootが含まれないことを検査する]
#   処理: [1: PEMをDERへ変換しfingerprintを検査する, 2: 実パス・件数・ファイルhashを返す]
#   引数: [path: 実際に参照するCA bundleのパス]
#   戻り値: [検査結果の辞書。不正PEM・空・対象root混入時は例外]
# }
def inspect_ca_bundle(path):
    # ラベルや版番号だけでなく、証明書本体のSHA-256で対象rootを識別する。
    path = Path(path)
    content = path.read_bytes()
    certificates = re.findall(r"-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----",
                              content.decode("ascii"), re.S)
    if not certificates:
        raise ValueError(f"CA bundle has no PEM certificates: {path}")
    # base64だけの偽PEMを証明書として数えず、OpenSSLにも構造を検証させる。
    ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT).load_verify_locations(cadata=content.decode("ascii"))
    for certificate in certificates:
        if hashlib.sha256(ssl.PEM_cert_to_DER_cert(certificate)).hexdigest() == BAD_ROOT:
            raise ValueError(f"Affected emSign root remains in {path}")
    return {"path": str(path.resolve()), "certificates": len(certificates),
            "sha256": hashlib.sha256(content).hexdigest()}


# {
#   責務: [inspect_pip_bundle: 更新後のpipが同梱するcertifiと実bundleを検査する]
#   処理: [1: 同梱版の最低条件を確認する, 2: 実bundleを検査する]
#   引数: []
#   戻り値: [同梱版と実bundleの記録。不足・対象root混入時は例外]
# }
def inspect_pip_bundle():
    # 単体certifiを更新してもpip同梱版は置き換わらないため別に確認する。
    bundled = importlib.import_module("pip._vendor.certifi")
    if not meets_minimum(bundled.__version__, MINIMUMS["certifi"]):
        raise ValueError("pip vendored certifi must be >= 2026.10.19")
    return {"version": bundled.__version__, **inspect_ca_bundle(bundled.where())}


# {
#   責務: [inspect_default_roots: Python既定SSLContextに対象rootがないことを検査する]
#   処理: [1: 既定の証明書集合を読みfingerprintを比較する]
#   引数: []
#   戻り値: [読み込んだ件数。対象root混入時は例外]
# }
def inspect_default_roots():
    # OSを変更せず、このContextに読み込まれた集合だけを検査する。
    roots = ssl.create_default_context().get_ca_certs(binary_form=True)
    if any(hashlib.sha256(root).hexdigest() == BAD_ROOT for root in roots):
        raise ValueError("Affected emSign root remains in Python default SSLContext")
    return len(roots)


# {
#   責務: [inspect_ca_overrides: 有効なCA環境変数の追加信頼bundleを検査する]
#   処理: [1: 遅延読込のCAディレクトリ指定を拒否する, 2: 追加CAファイルを検査する]
#   引数: []
#   戻り値: [変数名と実bundleの記録。未検証ディレクトリ・不正bundleは例外]
# }
def inspect_ca_overrides():
    # SSL_CERT_DIRは遅延読込されるため、既定Contextの列挙だけで安全と判定しない。
    if os.environ.get("SSL_CERT_DIR"):
        raise ValueError("SSL_CERT_DIR requires a separate trust audit; unset it after verification")
    names = ("SSL_CERT_FILE", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE", "PIP_CERT")
    return {name: inspect_ca_bundle(os.environ[name]) for name in names if os.environ.get(name)}


# {
#   責務: [audit_environment: このPythonの版と実際の信頼bundleを読み取り専用で検証する]
#   処理: [1: 必須版と導入済み任意パッケージ版を検査する, 2: 実bundleと既定Contextを記録する]
#   引数: []
#   戻り値: [JSON化できる結果。不足・検査失敗時は例外]
# }
def audit_environment():
    # uvとsigstoreは未導入なら追加せず、導入済みの場合だけ最低版を要求する。
    versions = {name: installed_version(name) for name in MINIMUMS}
    for name, version in versions.items():
        if version is None and name in ("uv", "sigstore"):
            continue
        if not meets_minimum(version, MINIMUMS[name]):
            raise ValueError(f"{name} must be >= {'.'.join(map(str, MINIMUMS[name]))}")
    certifi = importlib.import_module("certifi")
    return {"python": sys.executable, "versions": versions,
            "pip_bundle": inspect_pip_bundle(), "certifi_bundle": inspect_ca_bundle(certifi.where()),
            "default_context_certificates": inspect_default_roots(), "ca_overrides": inspect_ca_overrides()}


# {
#   責務: [install_requirement: 同じPythonのpipで公開PyPIから指定パッケージを取得する]
#   処理: [1: TLS検証とwheel hashを維持して隔離設定・キャッシュ不使用でpipを実行する]
#   引数: [requirement: 固定URLまたは最低版を含む要件]
#   戻り値: [なし。取得・インストール失敗時は例外]
# }
def install_requirement(requirement):
    # shellや外部のpipを使わず、更新対象のPython自身で実行する。
    subprocess.run([sys.executable, "-m", "pip", "--isolated", "--disable-pip-version-check",
                    "--no-cache-dir", "install", "--upgrade", "--no-deps", "--only-binary=:all:",
                    "--index-url", "https://pypi.org/simple", requirement], check=True, timeout=300)


# {
#   責務: [bootstrap_environment: venv作成直後のpipから安全な版へ更新して検証する]
#   処理: [1: 必要ならhash固定wheelでpipを更新する, 2: pipと既定Contextを検査する,
#          3: 単体certifiを更新して全体を再検証する]
#   引数: []
#   戻り値: [検証結果。途中失敗時は後続処理を実行せず例外]
# }
def bootstrap_environment():
    # 新しい安定版pipを固定版へダウングレードしない。
    if not meets_minimum(installed_version("pip"), MINIMUMS["pip"]):
        install_requirement(PIP_WHEEL)
    inspect_pip_bundle()
    inspect_default_roots()
    inspect_ca_overrides()
    install_requirement("certifi>=2026.10.19")
    return audit_environment()


# {
#   責務: [main: 更新または読み取り専用検査を選択し結果と終了値を返す]
#   処理: [1: 引数を解析する, 2: 指定の処理を実行し成功JSONまたは失敗診断を出力する]
#   引数: [argv: CLI引数列。Noneならプロセスの引数]
#   戻り値: [成功0、検証・更新失敗2]
# }
def main(argv=None):
    # --checkは依存の再取得やファイル変更を行わない。
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="inspect only; do not install packages")
    arguments = parser.parse_args(argv)
    try:
        report = audit_environment() if arguments.check else bootstrap_environment()
        print(json.dumps(report, ensure_ascii=False))
        return 0
    except (OSError, ValueError, ImportError, subprocess.SubprocessError) as error:
        print(f"Python trust verification failed: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
