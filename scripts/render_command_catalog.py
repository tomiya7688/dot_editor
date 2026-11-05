"""Render COMMANDS.md from the command catalog printed by a real pixel-cli binary."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

REQUIRED_COMMAND_KEYS = (
    "id",
    "path",
    "usage",
    "summary",
    "summary_ja",
    "effect",
    "requires_project",
    "positionals",
    "options",
    "side_effects",
    "examples",
)


# {
#   責務: [catalog_command: コマンド表を出させる実行コマンドを決める]
#   処理: [
#     1: 「python」と書かれたときは、Python CLIのcommand_catalogモジュールを使う
#     2: それ以外は、Rustの実行ファイルへ--commands-jsonを渡す
#   ]
#   引数: [source: 実行ファイルのパス、または「python」]
#   戻り値: [実行するコマンドの語のリスト]
# }
def catalog_command(source: str) -> list[str]:
    if source == "python":
        return [sys.executable, "-m", "command_catalog"]
    return [source, "--commands-json"]


# {
#   責務: [fetch_catalog: 実際のCLIにコマンド表を出させてJSONとして読む]
#   処理: [
#     1: 決めた実行コマンドを実行する
#     2: 終了値0・標準エラーなし・JSON1個とLFであることを確認する
#   ]
#   引数: [source: 実行ファイルのパス、または「python」]
#   戻り値: [カタログのJSON値、条件に反すれば例外]
# }
def fetch_catalog(source: str) -> dict:
    run = subprocess.run(
        catalog_command(source),
        capture_output=True,
        text=True,
        encoding="utf-8",
        stdin=subprocess.DEVNULL,
        check=False,
    )
    if run.returncode != 0 or run.stderr:
        raise SystemExit(f"--commands-json failed ({run.returncode}): {run.stderr}")
    if not run.stdout.endswith("\n") or run.stdout.endswith("\n\n"):
        raise SystemExit("--commands-json must print one JSON value and one LF")
    return json.loads(run.stdout)


# {
#   責務: [validate_catalog: カタログがschema v1の必須項目と一意性を満たすか検査する]
#   処理: [
#     1: 版・実装種別・必須キーを確認する
#     2: コマンドIDの重複と、日本語説明の空を拒否する
#   ]
#   引数: [catalog: カタログのJSON値]
#   戻り値: [なし、違反があれば例外]
# }
def validate_catalog(catalog: dict) -> None:
    if catalog.get("schema_version") != 1:
        raise SystemExit("unsupported catalog schema_version")
    if catalog.get("cli_implementation") not in ("rust", "python"):
        raise SystemExit("unknown cli_implementation")
    seen = set()
    for command in catalog["commands"]:
        missing = [key for key in REQUIRED_COMMAND_KEYS if key not in command]
        if missing:
            raise SystemExit(f"{command.get('id')}: missing {missing}")
        if command["id"] in seen:
            raise SystemExit(f"duplicate command id {command['id']}")
        seen.add(command["id"])
        if not command["summary_ja"].strip():
            raise SystemExit(f"{command['id']}: empty Japanese summary")


# {
#   責務: [escape_cell: 表のセルを壊す文字を無害にする]
#   処理: [
#     1: 縦線とバッククォートをエスケープし、改行を空白にする
#   ]
#   引数: [text: セルに入れる文字列]
#   戻り値: [エスケープ済みの文字列]
# }
def escape_cell(text: str) -> str:
    return text.replace("\\", "\\\\").replace("|", "\\|").replace("`", "\\`").replace("\n", " ")


# {
#   責務: [quote_arg: 引数をシェル表示用に必要なときだけ二重引用符で囲む]
#   処理: [
#     1: 空白・記号を含む語を囲み、内部の二重引用符を退避する
#   ]
#   引数: [word: 引数の1語]
#   戻り値: [表示用の文字列]
# }
def quote_arg(word: str) -> str:
    if word and all(ch.isalnum() or ch in "-_./:=@%+,~" for ch in word):
        return word
    return '"' + word.replace("\\", "\\\\").replace('"', '\\"') + '"'


# {
#   責務: [render_options: オプションの表を作る]
#   処理: [
#     1: 名前・別名・値の個数・必須・説明を1行ずつ並べる
#   ]
#   引数: [options: オプションのリスト]
#   戻り値: [Markdownの行のリスト（空なら空）]
# }
def render_options(options: list) -> list[str]:
    if not options:
        return []
    lines = ["| オプション | 値の数 | 必須 | 説明 |", "| --- | --- | --- | --- |"]
    for option in options:
        names = ", ".join([option["name"], *option["aliases"]])
        count = option["min_values"] if option["min_values"] == option["max_values"] else "可変"
        lines.append(
            f"| `{names}` | {count} | {'はい' if option['required'] else 'いいえ'} "
            f"| {escape_cell(option['description_ja'])} |"
        )
    return lines


# {
#   責務: [render_markdown: カタログからCOMMANDS.mdの本文を作る]
#   処理: [
#     1: 先頭に実装の種類と版を書き、共通オプションの表を置く
#     2: コマンドごとに説明・書式・引数・オプション・副作用・使用例を書く
#     3: 生成時刻やパスを含めず、同じ入力から同じ出力にする
#   ]
#   引数: [catalog: 検証済みのカタログ]
#   戻り値: [LF改行のMarkdown文字列]
# }
def render_markdown(catalog: dict) -> str:
    lines = [
        f"# {catalog['entrypoint']} コマンド一覧",
        "",
        f"実装: {catalog['cli_implementation']}　版: {catalog['cli_version']}　"
        "このファイルは実行ファイル自身が出すコマンド表から自動生成されています。",
        "",
        "## 共通オプション",
        "",
        *render_options(catalog["global_options"]),
        "",
        "## コマンド",
        "",
    ]
    for command in catalog["commands"]:
        lines += [f"### `{' '.join(command['path'])}`", "", escape_cell(command["summary_ja"]), ""]
        lines += [f"書式: `{command['usage']}`", ""]
        if command["positionals"]:
            lines += ["| 引数 | 種類 | 説明 |", "| --- | --- | --- |"]
            for argument in command["positionals"]:
                kind = argument["kind"]
                if argument.get("choices"):
                    kind += "（" + " / ".join(argument["choices"]) + "）"
                lines.append(
                    f"| `{argument['name']}` | {kind} | {escape_cell(argument['description_ja'])} |"
                )
            lines.append("")
        option_lines = render_options(command["options"])
        if option_lines:
            lines += [*option_lines, ""]
        if command["side_effects"]:
            lines += ["副作用: " + "、".join(f"`{item}`" for item in command["side_effects"]), ""]
        for example in command["examples"]:
            shown = " ".join(quote_arg(word) for word in example["argv"])
            lines += [escape_cell(example["description_ja"]), "", "```text", shown, "```", ""]
    return "\n".join(lines).rstrip("\n") + "\n"


# {
#   責務: [main: 実行ファイルからコマンド表を取り、COMMANDS.mdとcommands.jsonを書く]
#   処理: [
#     1: カタログを取得して検証する
#     2: 同じ実行ファイルから2回生成して、バイト列が一致することを確認する
#     3: 出力先フォルダへUTF-8・LFで書き出す
#   ]
#   引数: [argv: CLI引数、Noneならsys.argvを使用する]
#   戻り値: [正常0]
# }
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", help="path to pixel-cli, or the word python")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    first = fetch_catalog(args.source)
    validate_catalog(first)
    second = fetch_catalog(args.source)
    markdown = render_markdown(first)
    if markdown != render_markdown(second) or first != second:
        raise SystemExit("catalog generation is not deterministic")
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "COMMANDS.md").write_bytes(markdown.encode("utf-8"))
    (args.out / "commands.json").write_bytes(
        (json.dumps(first, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    )
    print(f"[catalog] {len(first['commands'])} commands -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
