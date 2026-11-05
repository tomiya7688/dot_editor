"""Pre-rendered command reference (COMMANDS.md and commands.json) bundled into the package."""

from importlib import resources


# {
#   責務: [read_text: 同梱された資料のファイルを読む]
#   処理: [パッケージの資料入口から指定の名前のファイルをUTF-8で読む]
#   引数: [name: 資料のファイル名（COMMANDS.mdまたはcommands.json）]
#   戻り値: [ファイルの文字列。同梱されていなければFileNotFoundError]
# }
def read_text(name: str) -> str:
    return resources.files(__package__).joinpath(name).read_text(encoding="utf-8")
