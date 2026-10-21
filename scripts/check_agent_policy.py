"""Check the small agent context, shared Claude entrypoint and PR evidence."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
MAX_BYTES = 2400
MAX_LINES = 55
REQUIRED = (
    "AGENTS.md", "CLAUDE.md", "コーディング規約.md",
    "doc/ワークフロー/ワークフロー.md", "docs/agents/README.md",
    "docs/agents/collaboration.md", "docs/agents/quality-gates.md",
    "docs/agents/development.md",
    ".github/pull_request_template.md",
)
SECTIONS = ("Issue", "Summary", "Validation", "Risks", "Handoff")
USER_DOCS = ("README.md",)
DEVELOPER_ONLY_REFERENCES = re.compile(
    r"AGENTS\.md|CLAUDE\.md|docs/agents/|doc/ワークフロー/|"
    r"コーディング規約\.md|Claude Code|Codex|共同開発|開発ワークフロー",
    re.IGNORECASE,
)


# {
#   責務: [check_repository: エージェント入口の上限と参照ファイルを検証する]
#   処理: [
#     1: 必須ファイルが存在するか調べる
#     2: AGENTS.mdのサイズとClaude用の単一参照を確認する
#     3: 索引の参照先と利用者向け文書への開発ルール混入を検査する
#   ]
#   引数: [root: 対象リポジトリのルートパス]
#   戻り値: [違反を表すメッセージのリスト]
# }
def check_repository(root: Path) -> list[str]:
    problems = []
    for name in REQUIRED:
        if not (root / name).is_file():
            problems.append(f"missing required file: {name}")
    entry = root / "AGENTS.md"
    if entry.is_file():
        data = entry.read_bytes()
        if len(data) > MAX_BYTES:
            problems.append(f"AGENTS.md exceeds {MAX_BYTES} UTF-8 bytes")
        if len(data.splitlines()) > MAX_LINES:
            problems.append(f"AGENTS.md exceeds {MAX_LINES} lines")
    claude = root / "CLAUDE.md"
    if claude.is_file() and claude.read_text(encoding="utf-8").strip() != "@AGENTS.md":
        problems.append("CLAUDE.md must contain only @AGENTS.md")
    for relative in ("AGENTS.md", "docs/agents/README.md"):
        path = root / relative
        if not path.is_file():
            continue
        # References to external websites are informational; local routes are verified.
        for target in re.findall(r"\[[^\]]+\]\(([^)]+)\)", path.read_text(encoding="utf-8")):
            if "://" in target or target.startswith("#"):
                continue
            destination = (path.parent / target.split("#", 1)[0]).resolve()
            if not destination.is_relative_to(root.resolve()) or not destination.exists():
                problems.append(f"{relative}: broken/outside local link: {target}")
    for relative in USER_DOCS:
        guide = root / relative
        if not guide.is_file():
            problems.append(f"missing user guide: {relative}")
            continue
        for match in DEVELOPER_ONLY_REFERENCES.finditer(guide.read_text(encoding="utf-8")):
            problems.append(
                f"{relative}: developer-only work rule/reference at char {match.start()}: "
                f"{match.group()}"
            )
    return problems


# {
#   責務: [check_pr_body: PR本文の検証記録と引き継ぎ情報を検査する]
#   処理: [
#     1: Markdownの雛形コメントを除いて見出しを検出する
#     2: 必須見出しの欠落、重複、未記入を調べる
#     3: Issue参照と検証結果の記載を確認する
#   ]
#   引数: [body: pull_requestイベントのPR本文]
#   戻り値: [不足項目と違反のメッセージ]
# }
def check_pr_body(body: str) -> list[str]:
    source = re.sub(r"<!--.*?-->", "", body, flags=re.DOTALL)
    headings = list(re.finditer(r"^## ([A-Za-z]+)[ \t]*$", source, flags=re.MULTILINE))
    problems = []
    for section in SECTIONS:
        found = [(index, heading) for index, heading in enumerate(headings)
                 if heading.group(1) == section]
        if len(found) != 1:
            problems.append(f"PR needs exactly one ## {section} section")
            continue
        index, heading = found[0]
        end = headings[index + 1].start() if index + 1 < len(headings) else len(source)
        content = source[heading.end():end].strip()
        if len(content) < 12 or re.search(r"\b(?:TODO|TBD|WIP|PLACEHOLDER)\b|未記入", content, re.IGNORECASE):
            problems.append(f"PR ## {section} needs a concrete report")
        if section == "Issue" and not re.search(r"(?<!\w)#\d+\b|/issues/\d+\b", content):
            problems.append("PR ## Issue needs a GitHub Issue reference")
        if section == "Validation" and not re.search(r"python|cargo|CI|build|pytest|unittest|未実施|not run", content, re.IGNORECASE):
            problems.append("PR ## Validation needs commands/results or not-run explanation")
    return problems


# {
#   責務: [main: 共有ルールと必要なPR証跡をコマンド行から検査する]
#   処理: [
#     1: PRイベントの任意パスを読み取る
#     2: 共有ファイルとPR本文の問題を収集する
#     3: 違反理由を表示して終了コードを返す
#   ]
#   引数: [argv: CLI引数、Noneならsys.argvを使用する]
#   戻り値: [正常0、違反1の終了コード]
# }
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pr-event", type=Path)
    args = parser.parse_args(argv)
    problems = check_repository(ROOT)
    if args.pr_event is not None:
        try:
            event = json.loads(args.pr_event.read_text(encoding="utf-8"))
            body = event["pull_request"].get("body") or ""
            problems.extend(check_pr_body(body))
        except (OSError, ValueError, KeyError, TypeError) as error:
            problems.append(f"cannot parse PR event: {error}")
    for problem in problems:
        print(f"[agent-policy] {problem}")
    if problems:
        return 1
    print("[agent-policy] OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
