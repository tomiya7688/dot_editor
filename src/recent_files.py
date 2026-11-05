"""Recently used project paths, kept in the user's settings folder (never in a project file)."""

from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile

MAX_RECENT = 8
FILE_NAME = "recent.json"


# {
#   責務: [config_directory: 最近使った作品の一覧を置く、利用者の設定フォルダを決める]
#   処理: [
#     1: 環境変数HYPER_DOT_EDITOR_CONFIG_DIRがあればそれを使う（テストや持ち運び用）
#     2: Windowsは%APPDATA%、それ以外はXDG_CONFIG_HOMEまたは~/.configの下のHyperDotEditorにする
#   ]
#   引数: []
#   戻り値: [設定フォルダのパス]
# }
def config_directory() -> Path:
    override = os.environ.get("HYPER_DOT_EDITOR_CONFIG_DIR")
    if override:
        return Path(override)
    if os.name == "nt":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "HyperDotEditor"


# {
#   責務: [load_recent: 最近使った作品のパスの一覧を読む]
#   処理: [
#     1: 設定ファイルが無い、壊れている、形式が違う場合は空の一覧にする
#     2: 文字列のパスだけを、新しい順に最大件数まで返す
#   ]
#   引数: []
#   戻り値: [パス文字列のリスト（新しい順）]
# }
def load_recent() -> list[str]:
    try:
        data = json.loads((config_directory() / FILE_NAME).read_text(encoding="utf-8"))
        paths = data["paths"]
    except (OSError, ValueError, KeyError, TypeError):
        return []
    if not isinstance(paths, list):
        return []
    return [path for path in paths if isinstance(path, str) and path][:MAX_RECENT]


# {
#   責務: [save_recent: 一覧を設定フォルダへ原子的に書く]
#   処理: [
#     1: 設定フォルダを作り、一時ファイルへ書いてから置き換える
#     2: 書けない場合は何もせず偽を返す（作品の保存や読込を妨げない）
#   ]
#   引数: [paths: 保存するパス文字列のリスト]
#   戻り値: [書けたら真]
# }
def save_recent(paths: list[str]) -> bool:
    directory = config_directory()
    try:
        directory.mkdir(parents=True, exist_ok=True)
        text = json.dumps({"version": 1, "paths": paths[:MAX_RECENT]}, ensure_ascii=False, indent=2)
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=directory, delete=False, suffix=".tmp"
        ) as handle:
            handle.write(text + "\n")
            temporary = Path(handle.name)
        os.replace(temporary, directory / FILE_NAME)
    except OSError:
        return False
    return True


# {
#   責務: [normalize: 同じ作品を同じ文字列にそろえる]
#   処理: [絶対パスにして、可能なら実体のパスに正規化する]
#   引数: [path: 作品のパス]
#   戻り値: [正規化したパス文字列]
# }
def normalize(path: str | Path) -> str:
    try:
        return str(Path(path).resolve())
    except OSError:
        return str(Path(path).absolute())


# {
#   責務: [remember: 作品を一覧の先頭へ加えて保存する]
#   処理: [同じ作品は重複させず、最大件数を超えた古いものを落とす]
#   引数: [path: 保存または開いた作品のパス]
#   戻り値: [更新後の一覧]
# }
def remember(path: str | Path) -> list[str]:
    target = normalize(path)
    paths = [target] + [item for item in load_recent() if normalize(item) != target]
    paths = paths[:MAX_RECENT]
    save_recent(paths)
    return paths


# {
#   責務: [forget: 開けなかった作品を一覧から外す（ファイル自体は決して削除しない）]
#   処理: [指定の作品を一覧から除いて保存する]
#   引数: [path: 一覧から外す作品のパス]
#   戻り値: [更新後の一覧]
# }
def forget(path: str | Path) -> list[str]:
    target = normalize(path)
    paths = [item for item in load_recent() if normalize(item) != target]
    save_recent(paths)
    return paths
