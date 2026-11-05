"""Open built wheel and sdist files and check the bundled command reference against a fresh render."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import tarfile
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from command_catalog import build_catalog
from render_command_catalog import render_markdown

PACKAGE = "hyper_dot_editor_help"
NAMES = ("COMMANDS.md", "commands.json")


# {
#   責務: [expected_files: 今のソースから作り直した、あるべき資料の中身を返す]
#   処理: [カタログを作り直し、COMMANDS.mdとcommands.jsonの本文を作る]
#   引数: []
#   戻り値: [ファイル名から本文（バイト列）への辞書]
# }
def expected_files() -> dict[str, bytes]:
    catalog = build_catalog()
    return {
        "COMMANDS.md": render_markdown(catalog).encode("utf-8"),
        "commands.json": (
            json.dumps(catalog, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8"),
    }


# {
#   責務: [check_wheel: wheelの中の資料が、あるべき中身と一致することを確認する]
#   処理: [wheelを開き、パッケージ内の2ファイルを読んで比べる]
#   引数: [wheel: wheelファイル, expected: あるべき中身]
#   戻り値: [なし、欠落や不一致なら例外]
# }
def check_wheel(wheel: Path, expected: dict[str, bytes]) -> None:
    with zipfile.ZipFile(wheel) as bundle:
        for name in NAMES:
            member = f"{PACKAGE}/{name}"
            if member not in bundle.namelist():
                raise SystemExit(f"{wheel.name}: missing {member}")
            if bundle.read(member) != expected[name]:
                raise SystemExit(f"{wheel.name}: {member} is stale or different")


# {
#   責務: [check_sdist: sdistの中の資料が、あるべき中身と一致することを確認する]
#   処理: [tar.gzを開き、トップフォルダ配下のsrc内の2ファイルを読んで比べる]
#   引数: [sdist: sdistファイル, expected: あるべき中身]
#   戻り値: [なし、欠落や不一致なら例外]
# }
def check_sdist(sdist: Path, expected: dict[str, bytes]) -> None:
    with tarfile.open(sdist, "r:gz") as bundle:
        names = {member.name: member for member in bundle.getmembers()}
        for name in NAMES:
            matches = [key for key in names if key.endswith(f"/src/{PACKAGE}/{name}")]
            if len(matches) != 1:
                raise SystemExit(
                    f"{sdist.name}: expected one src/{PACKAGE}/{name}, found {matches}"
                )
            extracted = bundle.extractfile(names[matches[0]])
            if extracted is None or extracted.read() != expected[name]:
                raise SystemExit(f"{sdist.name}: {name} is stale or different")


# {
#   責務: [main: 指定フォルダのwheelとsdistを開いて、資料の同梱と一致を確認する]
#   処理: [
#     1: フォルダ内にwheelとsdistが1つずつあることを確認する
#     2: 両方の中の資料を、今のソースから作った中身と比べる
#   ]
#   引数: [argv: CLI引数、Noneならsys.argvを使用する]
#   戻り値: [正常0]
# }
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path)
    args = parser.parse_args(argv)
    wheels = sorted(args.folder.glob("*.whl"))
    sdists = sorted(args.folder.glob("*.tar.gz"))
    if len(wheels) != 1 or len(sdists) != 1:
        raise SystemExit(f"need exactly one wheel and one sdist in {args.folder}")
    expected = expected_files()
    check_wheel(wheels[0], expected)
    check_sdist(sdists[0], expected)
    print(
        f"[package-catalog] {wheels[0].name} and {sdists[0].name} carry the current command reference"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
