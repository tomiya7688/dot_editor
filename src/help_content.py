"""Offline help text for the GUI (Tk-free, read-only, built from this package's own definitions)."""

from __future__ import annotations

import sys
from typing import Any


# {
#   責務: [basic_text: 基本操作の案内文を作る]
#   処理: [新規・描画・レイヤー・保存・PNG出力の流れを短く書く]
#   引数: []
#   戻り値: [表示用の文章]
# }
def basic_text() -> str:
    return (
        "基本操作\n\n"
        "1. 色を選びます（右のパレット、または「色 (C)」メニュー）。\n"
        "2. ブラシで、キャンバスをクリックまたはドラッグして塗ります。"
        "消しゴム・スポイト・塗りつぶしは「描画 (T)」メニューか右のボタンで選びます。\n"
        "3. 「レイヤー (L)」で層を足したり、表示・非表示や順序を変えたりできます。\n"
        "4. 「ファイル (F)」の「プロジェクトを保存」で作品を保存し、「PNGを保存」で画像に書き出します。\n"
        "5. 間違えたら Ctrl+Z で元に戻し、Ctrl+Y でやり直します。\n\n"
        "解像度を変えても、描いた細部は既定で保持されます。"
        "細部を捨てたいときだけ「表示 (V)」の「細部を破棄」を選びます。\n"
        "「作品をリセット」は確認のあと、全レイヤーと履歴を消します。元に戻せません。\n"
    )


# {
#   責務: [keyboard_text: キーボード操作の案内文を、キー割当表から作る]
#   処理: [割当表の各行を「キー: 動作」に並べ、メニューの開き方を添える]
#   引数: [bindings: (キー, 動作)の並び]
#   戻り値: [表示用の文章]
# }
def keyboard_text(bindings: tuple[tuple[str, str], ...]) -> str:
    lines = ["キーボード操作", ""]
    lines += [f"{key}: {action}" for key, action in bindings]
    lines += [
        "",
        "メニューは Alt を押してから、表示中の括弧付き英字（例: Alt→T で描画）で開きます。",
        "メニューの中は上下左右、Enterで実行、Escで戻ります。",
    ]
    return "\n".join(lines) + "\n"


# {
#   責務: [commands_text: コマンド行ツールの一覧を、カタログから読みやすい文章にする]
#   処理: [
#     1: 実装の種類と版を先頭に書く
#     2: 各コマンドの説明・書式・オプションの説明・副作用を並べる
#   ]
#   引数: [catalog: schema v1のカタログ]
#   戻り値: [表示用の文章]
# }
def commands_text(catalog: dict[str, Any]) -> str:
    lines = [
        "CLIコマンド表",
        f"実装: {catalog['cli_implementation']}　版: {catalog['cli_version']}　"
        f"入口: {catalog['entrypoint']}",
        "",
    ]
    for command in catalog["commands"]:
        lines += [
            f"■ {' '.join(command['path'])} — {command['summary_ja']}",
            f"  書式: {command['usage']}",
        ]
        for option in command["options"]:
            need = "（必須）" if option["required"] else ""
            lines.append(f"    {option['name']}{need}: {option['description_ja']}")
        if command["side_effects"]:
            lines.append("  副作用: " + "、".join(command["side_effects"]))
        for example in command["examples"]:
            lines.append("  例: " + " ".join(example["argv"]))
        lines.append("")
    return "\n".join(lines)


# {
#   責務: [about_text: バージョン情報の文章を作る]
#   処理: [版・実装・Pythonの版を書く。署名や作者名は含めない]
#   引数: [version: 版の文字列]
#   戻り値: [表示用の文章]
# }
def about_text(version: str) -> str:
    return (
        "Hyper Dot Editor\n"
        f"版: {version}\n"
        f"実行環境: Python {sys.version_info.major}.{sys.version_info.minor}\n"
        "このヘルプは、この版に含まれる定義から作っています。ネットワークには接続しません。\n"
    )


# {
#   責務: [load_commands_text: この版のCLIの定義からコマンド表の文章を作る]
#   処理: [
#     1: 同じ配布物のcommand_catalogで表を作る
#     2: 作れなければ理由を示す文章を返し、他の資料で代用しない
#   ]
#   引数: []
#   戻り値: [表示用の文章]
# }
def load_commands_text() -> str:
    try:
        from command_catalog import build_catalog

        return commands_text(build_catalog())
    except (ImportError, SystemExit) as error:
        return (
            "この版のヘルプを表示できません。\n"
            f"理由: {error}\n"
            "コマンドラインから `DotEditorCLI.exe --help` で一覧を確認してください。\n"
        )
