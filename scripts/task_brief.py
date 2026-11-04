"""Print the design documents and must-read rules for one Issue, instead of re-deriving them."""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "docs" / "design" / "README.md"
# 毎回読む規則。落とさないよう、ここを正本とし、実装開始時に必ず表示する。
MUST_READ = (
    "E:/projects/REVIEW_OPERATIONS.md を開く（開始時と完了報告前）",
    "worktreeはE:/projects/worktrees/<topic>/dot_editor に作る（Cドライブ禁止）",
    "実装前に doc/ワークフロー/実装前チェック.md を満たす（設計書→テスト→実装）",
    "ソースの場所は python scripts/hotspots.py <file> で索引を出す（全文を読まない）",
    "整形: python scripts/format_python.py / cargo fmt --all。宣言コメントを付ける",
    "PR本文は python scripts/pr_body.py で生成する（5見出し・LF）",
    "6者レビュー＋PRでCodeRabbit。省略は証跡つき。GUIは起動しない",
)


# {
#   責務: [issue_numbers: 一覧の1行が指すIssue番号を取り出す]
#   処理: [
#     1: 「#26 〜 #30」のような範囲を展開する
#     2: 単独の番号を集める
#   ]
#   引数: [cell: 設計書一覧のIssue列の文字列]
#   戻り値: [Issue番号の集合]
# }
def issue_numbers(cell: str) -> set[int]:
    numbers = {int(item) for item in re.findall(r"#(\d+)", cell)}
    for low, high in re.findall(r"#(\d+)\s*[〜~-]\s*#(\d+)", cell):
        numbers.update(range(int(low), int(high) + 1))
    return numbers


# {
#   責務: [find_designs: Issue番号に対応する設計書の行を一覧から探す]
#   処理: [
#     1: 一覧の表の行を読む
#     2: Issue列に番号を含む行の設計書列と状態を返す
#   ]
#   引数: [issue: Issue番号, listing: 一覧の本文]
#   戻り値: [(設計書列, 状態)のリスト]
# }
def find_designs(issue: int, listing: str) -> list[tuple[str, str]]:
    rows = []
    for line in listing.splitlines():
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) >= 4 and issue in issue_numbers(cells[0]):
            rows.append((cells[2], cells[3]))
    return rows


# {
#   責務: [main: Issueの設計書と必読ルールを表示する]
#   処理: [
#     1: 一覧から該当する設計書を探す
#     2: なければ「先に設計書を書く」と案内する
#     3: 必読ルールを表示する
#   ]
#   引数: [argv: CLI引数、Noneならsys.argvを使用する]
#   戻り値: [設計書が見つかれば0、なければ1]
# }
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("issue", type=int)
    args = parser.parse_args(argv)
    rows = find_designs(args.issue, INDEX.read_text(encoding="utf-8"))
    if rows:
        for design, status in rows:
            print(f"設計書: {design} [{status}]")
    else:
        print(
            f"設計書なし: #{args.issue} は先に doc/ワークフロー/設計書.md に従って書く",
            file=sys.stderr,
        )
    print("必読ルール:")
    for rule in MUST_READ:
        print(f"- {rule}")
    return 0 if rows else 1


if __name__ == "__main__":
    raise SystemExit(main())
