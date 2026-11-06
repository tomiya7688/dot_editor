"""Generate a policy-compliant PR body (five sections, LF line endings) from short arguments."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_agent_policy import check_pr_body

FOOTER = "🤖 Generated with [Claude Code](https://claude.com/claude-code)"


# {
#   責務: [build_body: 5つの見出しを持つPR本文を組み立てる]
#   処理: [
#     1: Issue・概要・検証・リスク・引き継ぎを見出しつきで並べる
#     2: 末尾に生成表記を付ける
#   ]
#   引数: [issue: Issue記述, summary: 概要, validation: 検証結果, risks: リスク, handoff: 引き継ぎ]
#   戻り値: [LF改行のPR本文]
# }
def build_body(issue: str, summary: str, validation: str, risks: str, handoff: str) -> str:
    sections = (
        ("Issue", issue),
        ("Summary", summary),
        ("Validation", validation),
        ("Risks", risks),
        ("Handoff", handoff),
    )
    parts = [f"## {name}\n{text.strip()}\n" for name, text in sections]
    return "\n".join(parts) + f"\n{FOOTER}\n"


# {
#   責務: [main: PR本文を生成して検査し、ファイルへ書く]
#   処理: [
#     1: 引数から本文を組み立てる
#     2: Agent policyと同じ検査を通す
#     3: LF改行・BOMなしで書き出す
#   ]
#   引数: [argv: CLI引数、Noneならsys.argvを使用する]
#   戻り値: [正常0、検査に通らなければ1]
# }
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("issue", "summary", "validation", "risks", "handoff"):
        parser.add_argument(f"--{name}", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    body = build_body(args.issue, args.summary, args.validation, args.risks, args.handoff)
    problems = check_pr_body(body)
    for problem in problems:
        print(f"[pr-body] {problem}", file=sys.stderr)
    if problems:
        return 1
    args.out.write_bytes(body.encode("utf-8"))
    print(f"[pr-body] wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
