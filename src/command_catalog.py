"""Command catalog (schema v1) of the Python CLI, introspected from its argparse parser."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
from pathlib import Path
import sys
from typing import Any

from pixel_cli import build_parser

PACKAGE_NAME = "hyper-dot-editor"
ENTRYPOINT = "python -m pixel_cli"

# 日本語の説明は、argparseにない補助情報としてここ1か所に置く。コマンドや引数との過不足はテストで検査する。
SUMMARY_JA = {
    "new": "新しいプロジェクトを作る",
    "palette": "プロジェクトを開いたまま、1行ずつ対話的に編集する",
    "edit": "プロジェクトを編集する。1回の起動で行える順序は固定",
    "inspect": "プロジェクトの状態をJSONで読む（変更しない）",
    "export": "見えている層を重ねてPNGに書き出す",
}
EFFECT = {
    "new": "create",
    "palette": "interactive",
    "edit": "edit",
    "inspect": "read",
    "export": "export",
}
SIDE_EFFECTS = {
    "new": ["creates_project"],
    "palette": ["interactive_session", "writes_project"],
    "edit": ["writes_project", "discards_detail"],
    "inspect": [],
    "export": ["writes_output"],
}
OPTION_JA = {
    "--size": "1辺のセル数（正方形）",
    "--resolution": "横と縦のセル数（WIDTH HEIGHT）",
    "--layered": "レイヤー付きのプロジェクトとして作る",
    "--output": "書き出し先のファイル",
    "--project": "対象のプロジェクトファイル",
    "--upscale": "解像度を2倍にする",
    "--split": "セルを4分割する（X Y）",
    "--split-region": "長方形の範囲を分割する（X Y WIDTH HEIGHT）",
    "--paint": "セルを塗る（X Y COLOR）",
    "--paint-child": "子セルを塗る（X Y CHILD_X CHILD_Y COLOR）",
    "--fill": "つながった範囲を塗りつぶす（X Y COLOR）",
    "--erase": "セルを透明にする（X Y）",
    "--erase-child": "子セルを透明にする（X Y CHILD_X CHILD_Y）",
    "--collapse": "分割したセルを折りたたむ。細部は既定で保持される（X Y）",
    "--discard-detail": "保持している細部を捨てる（セルのX Yか、範囲のX Y WIDTH HEIGHT）",
    "--detail-policy": "解像度変更や編集で細部を保持するか捨てるか",
    "--import-image": "画像ファイルを読み込む",
    "--add-layer": "名前を指定してレイヤーを足す",
    "--select-layer": "編集するレイヤーを選ぶ",
    "--rename-layer": "選択中のレイヤーの名前を変える",
    "--move-layer": "選択中のレイヤーの重なり順を1つ動かす",
    "--layer-visibility": "選択中のレイヤーを表示または非表示にする",
    "--remove-layer": "選択中のレイヤーを消す",
    "--sample": "セルの色を読む（X Y）",
    "--child": "保持している子セルを読む（CHILD_X CHILD_Y）",
    "--layer": "このレイヤーを読む（既定は保存済みの選択中の層）",
}
EXAMPLES = {
    "new": (["new", "--size", "16", "--output", "art.json"], "16x16の新しいプロジェクトを作る"),
    "palette": (["palette", "--project", "art.json"], "対話的な編集を始める"),
    "edit": (
        ["edit", "--project", "art.json", "--paint", "3", "4", "#FF8800"],
        "セルを橙色に塗る",
    ),
    "inspect": (["inspect", "--project", "art.json"], "プロジェクトの状態を見る"),
    "export": (
        ["export", "--project", "art.json", "--output", "art.png", "--size", "64"],
        "64x64のPNGに書き出す",
    ),
}


# {
#   責務: [cli_version: インストール済みパッケージの版を返す]
#   処理: [
#     1: パッケージのメタデータから版を読む
#     2: ソースから直接実行された場合は、pyproject.tomlの記述を使う
#   ]
#   引数: []
#   戻り値: [版の文字列]
# }
def cli_version() -> str:
    try:
        return importlib.metadata.version(PACKAGE_NAME)
    except importlib.metadata.PackageNotFoundError:
        text = (Path(__file__).resolve().parents[1] / "pyproject.toml").read_text(encoding="utf-8")
        for line in text.splitlines():
            if line.startswith("version"):
                return line.split("=", 1)[1].strip().strip('"')
        return "unknown"


# {
#   責務: [value_counts: argparseのnargsから値の最少・最多の個数を求める]
#   処理: [
#     1: 値を取らない動作は0、省略は1、整数はその個数、記号は意味に従う
#   ]
#   引数: [action: argparseの動作]
#   戻り値: [(最少, 最多)。最多が無制限ならNone]
# }
def value_counts(action: argparse.Action) -> tuple[int, int | None]:
    if action.nargs == 0:
        return 0, 0
    if action.nargs is None:
        return 1, 1
    if action.nargs == "+":
        return 1, None
    if action.nargs == "?":
        return 0, 1
    if action.nargs == "*":
        return 0, None
    return int(action.nargs), int(action.nargs)


# {
#   責務: [option_kind: 動作から値の種類を決める]
#   処理: [
#     1: 値を取らないものは真偽値、選択肢つきはchoice、型が整数ならinteger、Pathならpath、他はstring
#   ]
#   引数: [action: argparseの動作]
#   戻り値: [種類の名前]
# }
def option_kind(action: argparse.Action) -> str:
    if action.nargs == 0:
        return "boolean"
    if action.choices:
        return "choice"
    if action.type is int:
        return "integer"
    if action.type is Path:
        return "path"
    return "string"


# {
#   責務: [option_entry: argparseのオプション1つをカタログの項目にする]
#   処理: [
#     1: 長い名前と短い別名、値の個数、種類、必須、説明を集める
#     2: 日本語の説明が登録されていなければ失敗させる
#     3: 選択肢・既定値・値の表示名があれば加える
#   ]
#   引数: [action: argparseの動作]
#   戻り値: [オプションのdict]
# }
def option_entry(action: argparse.Action) -> dict[str, Any]:
    longs = [name for name in action.option_strings if name.startswith("--")]
    shorts = [name for name in action.option_strings if not name.startswith("--")]
    name = longs[0]
    if name not in OPTION_JA:
        raise SystemExit(f"no Japanese description for {name}")
    minimum, maximum = value_counts(action)
    entry: dict[str, Any] = {
        "name": name,
        "aliases": shorts + longs[1:],
        "kind": option_kind(action),
        "min_values": minimum,
        "max_values": maximum,
        "required": bool(action.required),
        "description_ja": OPTION_JA[name],
    }
    if action.choices:
        entry["choices"] = list(action.choices)
    if action.metavar is not None:
        entry["metavars"] = (
            list(action.metavar) if isinstance(action.metavar, tuple) else [action.metavar]
        )
    if isinstance(action.default, (str, int, float, bool)) and action.nargs != 0:
        entry["default"] = action.default
    return entry


# {
#   責務: [usage_of: 実行ファイル名に依存しない書式の1行を作る]
#   処理: [
#     1: argparseの書式からプログラム名を除き、サブコマンド名から始まる形にする
#   ]
#   引数: [name: サブコマンド名, parser: そのパーサー]
#   戻り値: [書式の文字列]
# }
def usage_of(name: str, parser: argparse.ArgumentParser) -> str:
    text = " ".join(parser.format_usage().split()).removeprefix("usage: ")
    return text[text.index(f" {name} ") + 1 :] if f" {name} " in text else name


# {
#   責務: [command_entry: argparseのサブコマンド1つをカタログの項目にする]
#   処理: [
#     1: ヘルプ以外の動作をオプションとして集める
#     2: 日本語の説明・種類・副作用・使用例が登録されていなければ失敗させる
#   ]
#   引数: [name: サブコマンド名, parser: そのパーサー]
#   戻り値: [コマンドのdict]
# }
def command_entry(name: str, parser: argparse.ArgumentParser) -> dict[str, Any]:
    if name not in SUMMARY_JA:
        raise SystemExit(f"no Japanese documentation for command {name}")
    options = [
        option_entry(action)
        for action in parser._actions
        if action.option_strings and not isinstance(action, argparse._HelpAction)
    ]
    example, example_ja = EXAMPLES[name]
    return {
        "id": name,
        "path": [name],
        "usage": usage_of(name, parser),
        "summary": (parser.description or parser.prog),
        "summary_ja": SUMMARY_JA[name],
        "effect": EFFECT[name],
        "requires_project": name != "new",
        "positionals": [],
        "options": options,
        "side_effects": SIDE_EFFECTS[name],
        "examples": [
            {"argv": ["python", "-m", "pixel_cli", *example], "description_ja": example_ja}
        ],
    }


# {
#   責務: [build_catalog: Python CLIのパーサー全体をカタログ（schema v1）にする]
#   処理: [
#     1: パーサーの全サブコマンドを定義順に集める
#     2: 実装の種類・版・入口を記し、共通オプションは空にする
#   ]
#   引数: []
#   戻り値: [カタログのdict]
# }
def build_catalog() -> dict[str, Any]:
    parser = build_parser()
    subparsers = next(
        action for action in parser._actions if isinstance(action, argparse._SubParsersAction)
    )
    commands = [command_entry(name, sub) for name, sub in subparsers.choices.items()]
    return {
        "schema_version": 1,
        "cli_implementation": "python",
        "cli_version": cli_version(),
        "entrypoint": ENTRYPOINT,
        "global_options": [],
        "commands": commands,
    }


# {
#   責務: [main: カタログを「JSON1個とLF」で標準出力へ出す]
#   処理: [カタログを整形したJSONにして末尾にLFを付けて表示する]
#   引数: []
#   戻り値: [正常0]
# }
def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", newline="\n")
    sys.stdout.write(
        json.dumps(build_catalog(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
