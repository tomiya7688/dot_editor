"""Print a compact symbol index (name:line) of a source file, so it need not be read in full."""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys

PATTERNS = {
    ".py": re.compile(r"^\s*(?:async\s+)?(?:def|class)\s+(\w+)"),
    ".rs": re.compile(r"^\s*(?:pub(?:\([^)]*\))?\s+)?(?:fn|struct|enum|trait|impl)\s+(\w+)"),
}


# {
#   責務: [index_symbols: ファイル内の関数・型の名前と行番号を一覧にする]
#   処理: [
#     1: 拡張子に合う正規表現を選ぶ
#     2: 各行を走査し、名前と行番号を集める
#   ]
#   引数: [path: 対象ファイル, pattern: 名前を取り出す正規表現]
#   戻り値: [(行番号, 名前)のリスト]
# }
def index_symbols(path: Path, pattern: re.Pattern[str]) -> list[tuple[int, str]]:
    found = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        match = pattern.match(line)
        if match:
            found.append((number, match.group(1)))
    return found


# {
#   責務: [main: 指定ファイルの記号索引を表示する]
#   処理: [
#     1: 引数のファイルごとに索引を作る
#     2: --grep指定があれば名前で絞り込む
#     3: 1行にまとめて表示する
#   ]
#   引数: [argv: CLI引数、Noneならsys.argvを使用する]
#   戻り値: [正常0、対応しない拡張子や不在ファイルは2]
# }
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument("--grep", help="名前に含まれる語で絞り込む")
    args = parser.parse_args(argv)
    for path in args.files:
        pattern = PATTERNS.get(path.suffix)
        if pattern is None or not path.is_file():
            print(f"[hotspots] unsupported or missing: {path}", file=sys.stderr)
            return 2
        symbols = index_symbols(path, pattern)
        if args.grep:
            symbols = [item for item in symbols if args.grep in item[1]]
        print(f"{path} ({len(symbols)}): " + " ".join(f"{name}:{line}" for line, name in symbols))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
