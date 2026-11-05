"""Package the release Rust CLI into a single-folder archive and re-run the E2E on the extracted copy."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from render_command_catalog import fetch_catalog, render_markdown, validate_catalog

EXECUTABLES = ("pixel-cli", "cli-anything-dot-editor")
SKILL = Path("skills") / "cli-anything-dot-editor" / "SKILL.md"
CARGO_TOML = ROOT / "rust" / "crates" / "hyper-dot-cli" / "Cargo.toml"


# {
#   責務: [cargo_version: CLIクレートの版をCargo.tomlから読む]
#   処理: [version = "..." の行を探して値を返す]
#   引数: []
#   戻り値: [版の文字列]
# }
def cargo_version() -> str:
    for line in CARGO_TOML.read_text(encoding="utf-8").splitlines():
        if line.startswith("version"):
            return line.split("=", 1)[1].strip().strip('"')
    raise SystemExit("version not found in Cargo.toml")


# {
#   責務: [archive_name: 配布アーカイブのフォルダ名と拡張子を決める]
#   処理: [名前を「hyper-dot-cli-<版>-<target>」とし、Windowsはzip、他はtar.gzにする]
#   引数: [version: 版, target: Rustのtarget, windows: Windows向けか]
#   戻り値: [(フォルダ名, アーカイブのファイル名)]
# }
def archive_name(version: str, target: str, windows: bool) -> tuple[str, str]:
    folder = f"hyper-dot-cli-{version}-{target}"
    return folder, folder + (".zip" if windows else ".tar.gz")


# {
#   責務: [readme_text: 同梱する短い案内を作る]
#   処理: [配置・起動・JSON出力・終了値・コマンド表の場所を短くまとめる]
#   引数: [version: 版, target: Rustのtarget]
#   戻り値: [README-CLI.mdの本文（LF改行）]
# }
def readme_text(version: str, target: str) -> str:
    return (
        f"# pixel-cli {version} ({target})\n\n"
        "ドット絵プロジェクトを、画面を使わずにシェルから作る・編集する・PNGへ書き出す実行ファイルです。"
        "Pythonは要りません。\n\n"
        "- 起動: `pixel-cli`（同じ内容の別名 `cli-anything-dot-editor`）を別プロセスとして呼び出します。\n"
        "- 例: `pixel-cli --json -p art.json project new --size 16`\n"
        "- 結果は標準出力、説明とエラーは標準エラーです。終了値は 0=成功、1=実行時の失敗、2=使い方の誤りです。\n"
        "- 全コマンドの一覧は `docs/cli/rust/COMMANDS.md`（機械可読版は `commands.json`、"
        "`pixel-cli --commands-json` でも取得できます）。\n"
        "- 使い方の詳細は `skills/cli-anything-dot-editor/SKILL.md` にあります。\n"
    )


# {
#   責務: [stage_files: 実行ファイルと同梱資料を配布フォルダへ集める]
#   処理: [
#     1: 2つの実行ファイル、SKILL.md、LICENSE、案内を並べる
#     2: 既存のフォルダがあれば作り直す
#   ]
#   引数: [build_dir: ビルド出力フォルダ, folder: 作る配布フォルダ, version: 版, target: Rustのtarget, suffix: 実行ファイルの拡張子]
#   戻り値: [なし。フォルダに集める]
# }
def stage_files(build_dir: Path, folder: Path, version: str, target: str, suffix: str) -> None:
    if folder.exists():
        shutil.rmtree(folder)
    (folder / SKILL.parent).mkdir(parents=True)
    for name in EXECUTABLES:
        source = build_dir / f"{name}{suffix}"
        if not source.is_file():
            raise SystemExit(f"missing executable: {source}")
        shutil.copy2(source, folder / source.name)
    shutil.copy2(ROOT / SKILL, folder / SKILL)
    shutil.copy2(ROOT / "LICENSE", folder / "LICENSE")
    (folder / "README-CLI.md").write_bytes(readme_text(version, target).encode("utf-8"))


# {
#   責務: [add_catalog: 配布フォルダの実行ファイル自身からコマンド表を作って同梱する]
#   処理: [
#     1: 同梱する実行ファイルに--commands-jsonを実行させて検証する
#     2: COMMANDS.mdとcommands.jsonをdocs/cli/rustへ書く
#   ]
#   引数: [folder: 配布フォルダ, suffix: 実行ファイルの拡張子]
#   戻り値: [カタログのdict]
# }
def add_catalog(folder: Path, suffix: str) -> dict:
    catalog = fetch_catalog(str(folder / f"pixel-cli{suffix}"))
    validate_catalog(catalog)
    target = folder / "docs" / "cli" / "rust"
    target.mkdir(parents=True)
    (target / "COMMANDS.md").write_bytes(render_markdown(catalog).encode("utf-8"))
    (target / "commands.json").write_bytes(
        (json.dumps(catalog, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    )
    return catalog


# {
#   責務: [is_executable_name: 実行権限を付けるファイル名か判定する]
#   処理: [拡張子を除いた名前が2つの実行ファイル名のどちらかか調べる]
#   引数: [name: ファイル名]
#   戻り値: [実行ファイルなら真]
# }
def is_executable_name(name: str) -> bool:
    return name.removesuffix(".exe") in EXECUTABLES


# {
#   責務: [make_archive: 配布フォルダから、同じ入力なら同じ内容のアーカイブを作る]
#   処理: [
#     1: ファイルを名前順に並べ、時刻・所有者を固定する
#     2: Windows向けはzip、他は実行権限を保持したtar.gzにする
#   ]
#   引数: [folder: 配布フォルダ, archive: 出力先のパス, windows: Windows向けか]
#   戻り値: [なし。アーカイブを書く]
# }
def make_archive(folder: Path, archive: Path, windows: bool) -> None:
    files = sorted(path for path in folder.rglob("*") if path.is_file())
    if windows:
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
            for path in files:
                info = zipfile.ZipInfo(f"{folder.name}/{path.relative_to(folder).as_posix()}")
                info.date_time = (1980, 1, 1, 0, 0, 0)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o644 << 16
                bundle.writestr(info, path.read_bytes())
        return
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as bundle:
        for path in files:
            info = tarfile.TarInfo(f"{folder.name}/{path.relative_to(folder).as_posix()}")
            data = path.read_bytes()
            info.size = len(data)
            info.mtime = 0
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            info.mode = 0o755 if is_executable_name(path.name) else 0o644
            bundle.addfile(info, io.BytesIO(data))
    with archive.open("wb") as handle:
        with gzip.GzipFile(filename="", fileobj=handle, mode="wb", mtime=0) as compressed:
            compressed.write(buffer.getvalue())


# {
#   責務: [extract_archive: アーカイブを新しい空のフォルダへ展開する]
#   処理: [形式に応じて展開し、展開先の外へ出るパスを拒否する]
#   引数: [archive: アーカイブ, destination: 展開先（存在しない・空のフォルダ）]
#   戻り値: [なし。展開する]
# }
def extract_archive(archive: Path, destination: Path) -> None:
    destination.mkdir(parents=True)
    if archive.suffix == ".zip":
        with zipfile.ZipFile(archive) as bundle:
            for name in bundle.namelist():
                if Path(name).is_absolute() or ".." in Path(name).parts:
                    raise SystemExit(f"unsafe path in archive: {name}")
            bundle.extractall(destination)
        return
    with tarfile.open(archive, "r:gz") as bundle:
        bundle.extractall(destination, filter="data")


# {
#   責務: [sha256_of: ファイルのSHA-256を返す]
#   処理: [全バイトを読んでハッシュを求める]
#   引数: [path: 対象のファイル]
#   戻り値: [小文字16進の文字列]
# }
def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# {
#   責務: [check_version: 実行ファイルの--versionがCargo.tomlの版と一致するか確認する]
#   処理: [同梱する実行ファイルを実行して出力の末尾の語を比べる]
#   引数: [executable: 実行ファイル, version: 期待する版]
#   戻り値: [なし。不一致なら例外]
# }
def check_version(executable: Path, version: str) -> None:
    run = subprocess.run(
        [str(executable), "--version"], capture_output=True, text=True, check=False, timeout=60
    )
    if run.returncode != 0 or run.stdout.split()[-1:] != [version]:
        raise SystemExit(f"{executable.name} --version is {run.stdout!r}, expected {version}")


# {
#   責務: [clean_environment: Pythonも検索パスも使わない最小の環境変数を作る]
#   処理: [PATHを空にし、Windowsの起動に必要なSystemRootだけを引き継ぐ]
#   引数: []
#   戻り値: [環境変数の辞書]
# }
def clean_environment() -> dict[str, str]:
    environment = {"PATH": ""}
    for name in ("SystemRoot", "SYSTEMROOT"):
        if name in os.environ:
            environment[name] = os.environ[name]
    return environment


# {
#   責務: [check_bundled_catalog: 展開した配布物の表が、同梱した実行ファイル自身の出力と一致するか確認する]
#   処理: [
#     1: 任意の作業フォルダから、PATHを空にして実行ファイルに--commands-jsonを実行させる
#     2: 同梱のcommands.jsonとCOMMANDS.mdが、その出力から作り直した内容と同じかを比べる
#     3: --helpもPythonなしで実行できることを確認する
#   ]
#   引数: [unpacked: 展開した配布フォルダ, suffix: 実行ファイルの拡張子]
#   戻り値: [なし、不一致や欠落なら例外]
# }
def check_bundled_catalog(unpacked: Path, suffix: str) -> None:
    executable = unpacked / f"pixel-cli{suffix}"
    with tempfile.TemporaryDirectory() as elsewhere:
        shown = subprocess.run(
            [str(executable), "--commands-json"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            cwd=elsewhere,
            env=clean_environment(),
            check=False,
            timeout=60,
        )
        helped = subprocess.run(
            [str(executable), "--help"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            cwd=elsewhere,
            env=clean_environment(),
            check=False,
            timeout=60,
        )
    if shown.returncode != 0 or shown.stderr or helped.returncode != 0:
        raise SystemExit("the extracted executable cannot print its catalog or help without Python")
    live = json.loads(shown.stdout)
    bundled_dir = unpacked / "docs" / "cli" / "rust"
    bundled = json.loads((bundled_dir / "commands.json").read_text(encoding="utf-8"))
    if bundled != live:
        raise SystemExit("the bundled commands.json differs from the executable's own catalog")
    if (bundled_dir / "COMMANDS.md").read_bytes() != render_markdown(live).encode("utf-8"):
        raise SystemExit("the bundled COMMANDS.md differs from a fresh render")


# {
#   責務: [main: 配布フォルダの作成・アーカイブ化・展開後のE2Eを行い、大きさとSHA-256を記録する]
#   処理: [
#     1: 版を照合し、フォルダを作ってコマンド表を同梱する
#     2: アーカイブを作り、新しい空のフォルダへ展開する
#     3: 展開した実行ファイルと同梱のSKILL.mdで別プロセスのE2Eを実行する
#     4: 名前・大きさ・SHA-256を表示し、GitHubのジョブ要約があれば追記する
#   ]
#   引数: [argv: CLI引数、Noneならsys.argvを使用する]
#   戻り値: [正常0]
# }
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", required=True)
    parser.add_argument("--build-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    windows = "windows" in args.target
    suffix = ".exe" if windows else ""
    version = cargo_version()
    for executable in EXECUTABLES:
        check_version(args.build_dir / f"{executable}{suffix}", version)
    name, archive_file = archive_name(version, args.target, windows)
    args.out.mkdir(parents=True, exist_ok=True)
    folder = args.out / "stage" / name
    stage_files(args.build_dir, folder, version, args.target, suffix)
    add_catalog(folder, suffix)
    archive = args.out / archive_file
    make_archive(folder, archive, windows)
    extracted = args.out / "extracted"
    if extracted.exists():
        shutil.rmtree(extracted)
    extract_archive(archive, extracted)
    unpacked = extracted / name
    check_bundled_catalog(unpacked, suffix)
    run = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "e2e_rust_cli.py"),
            str(unpacked),
            "--skill",
            str(unpacked / SKILL),
        ],
        check=False,
    )
    if run.returncode != 0:
        raise SystemExit("the end-to-end check of the extracted archive failed")
    sizes = {path.name: path.stat().st_size for path in (unpacked / f"pixel-cli{suffix}",)}
    line = (
        f"{archive_file}  size={archive.stat().st_size}  "
        f"pixel-cli={sizes[f'pixel-cli{suffix}']}  sha256={sha256_of(archive)}"
    )
    print(line)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as handle:
            handle.write(f"- `{line}`\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
