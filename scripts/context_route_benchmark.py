"""Measure task-route file coverage and candidate text sizes, not model tokens.

Like ObaPick's fixed-fixture benchmark, compare the same eligible file pool against
the linked files for three representative tasks. No Claude/Codex invocation occurs.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
TASKS = (
    {
        "id": "rust-project-json",
        "route": "Rust project JSON",
        "required_evidence": (
            "rust/crates/hyper-dot-core/src/project_json_import.rs",
            "rust/crates/hyper-dot-core/tests/project_json_import.rs",
            "scripts/test_rust_json_compat.py",
            "tests/fixtures/project_json/legacy_refinement_v1.json",
            "tests/fixtures/project_json/transparent_rectangular_v2.json",
            "docs/Non_destructive_resolution.md",
        ),
    },
    {
        "id": "python-cli",
        "route": "Python CLI / Command API",
        "required_evidence": (
            "src/pixel_cli.py",
            "src/pixel_commands.py",
            "tests/test_pixel_cli.py",
            "tests/test_commands.py",
            "docs/Command_API.md",
            "docs/CUI_detail_operations.md",
        ),
    },
    {
        "id": "gui-keyboard",
        "route": "GUI keyboard or menus",
        "required_evidence": (
            "src/dot_editor.py",
            "tests/test_keyboard_focus_regions.py",
            "tests/test_menu_structure.py",
            "README.md",
        ),
    },
)
LINK = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


# {
#   責務: [eligible_paths: 広範囲に全文を読む比較条件の候補集合を作る]
#   処理: [
#     1: 既存の製品ソース・テスト・資料とJSON fixtureを列挙する
#     2: 出力物・仮想環境・エージェント専用文書を含めず相対パスを返す
#   ]
#   引数: [root: 検証対象のリポジトリ]
#   戻り値: [固定された対象範囲の相対ファイルパス]
# }
def eligible_paths(root: Path) -> list[str]:
    candidates = set()
    for directory, suffix in (
        ("src", ".py"),
        ("tests", ".py"),
        ("scripts", ".py"),
        ("rust/crates", ".rs"),
    ):
        area = root / directory
        if area.exists():
            candidates.update(path for path in area.rglob("*")
                              if path.is_file() and path.suffix == suffix)
    candidates.update(path for path in (root / "docs").glob("*.md") if path.is_file())
    candidates.update(path for path in (root / "tests/fixtures/project_json").glob("*.json")
                      if path.is_file())
    if (root / "README.md").is_file():
        candidates.add(root / "README.md")
    return sorted(path.relative_to(root).as_posix() for path in candidates)


# {
#   責務: [task_routes: タスク別案内表から候補とその役割を抽出する]
#   処理: [
#     1: 案内表の4列を読み、各列のMarkdownリンクだけを検出する
#     2: 参照がリポジトリ内の実在ファイルかを検査する
#     3: 同名経路や同一パスの重複を拒否して候補を返す
#   ]
#   引数: [root: 案内表のあるリポジトリ]
#   戻り値: [作業カテゴリをキーとしたソース・テスト・仕様の対応]
# }
def task_routes(root: Path) -> dict[str, dict[str, list[str]]]:
    root = root.resolve()
    map_path = root / "docs/agents/task-map.md"
    contents = map_path.read_text(encoding="utf-8")
    routes = {}
    for line in contents.splitlines():
        if not line.startswith("| "):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if not cells or cells[0] == "Change category" or cells[0].startswith("---"):
            continue
        if len(cells) != 4:
            raise ValueError(f"task-map row must have four cells: {line[:90]}")
        category = cells[0]
        if category in routes:
            raise ValueError(f"duplicate task-map category: {category}")
        roles = {}
        for role, cell in zip(("source", "test", "contract"), cells[1:]):
            paths = []
            for match in LINK.finditer(cell):
                raw_path = match.group(1).split("#", 1)[0]
                resolved = (map_path.parent / raw_path).resolve()
                if not resolved.is_relative_to(root) or not resolved.is_file():
                    raise ValueError(f"{category}: missing/outside linked file: {raw_path}")
                paths.append(resolved.relative_to(root).as_posix())
            if not paths:
                raise ValueError(f"{category}: missing {role} links")
            roles[role] = paths
        flattened = [path for values in roles.values() for path in values]
        if len(flattened) != len(set(flattened)):
            raise ValueError(f"{category}: repeated linked file")
        routes[category] = roles
    return routes


# {
#   責務: [measure_paths: 実在ファイル群を全文読み込み相当の文字・バイト量に換算する]
#   処理: [
#     1: 相対パスを正規化して作業場所外の参照を防止する
#     2: UTF-8テキストを読み、文字数と実バイト数を加算する
#   ]
#   引数: [root: リポジトリ、paths: 測定する相対パス]
#   戻り値: [ファイル数・文字数・UTF-8バイト数]
# }
def measure_paths(root: Path, paths: list[str]) -> dict[str, int]:
    root = root.resolve()
    chars = 0
    byte_count = 0
    for relative in paths:
        source = (root / relative).resolve()
        if not source.is_relative_to(root) or not source.is_file():
            raise ValueError(f"cannot measure nonexistent/outside path: {relative}")
        payload = source.read_bytes()
        chars += len(payload.decode("utf-8"))
        byte_count += len(payload)
    return {"files": len(paths), "characters": chars, "utf8_bytes": byte_count}


# {
#   責務: [build_report: 同じ三作業で広範囲読込と案内表経由の根拠保持を比較する]
#   処理: [
#     1: 比較対象と案内表を読み取り独立の必須根拠と照らす
#     2: 必須の実装・テスト・仕様が欠落した経路は失敗する
#     3: 文字量とバイト量を記録しモデル使用量は未計測と明示する
#   ]
#   引数: [root: 作業リポジトリ、tasks: 同一条件で確認する作業定義]
#   戻り値: [各作業と全体の候補読込量、必要根拠の確認結果]
# }
def build_report(root: Path, tasks: tuple[dict, ...] = TASKS) -> dict:
    broad = eligible_paths(root)
    broad_set = set(broad)
    if not broad:
        raise ValueError("no eligible files in comparison scope")
    routes = task_routes(root)
    broad_metrics = measure_paths(root, broad)
    samples = []
    for task in tasks:
        category = task["route"]
        if category not in routes:
            raise ValueError(f"missing task route: {category}")
        roles = routes[category]
        selected = [path for role in ("source", "test", "contract")
                    for path in roles[role]]
        required = set(task["required_evidence"])
        missing = sorted(required.difference(selected))
        if missing:
            raise ValueError(f"{task['id']}: missing required evidence: {missing}")
        outside_comparison = sorted(set(selected).difference(broad_set))
        if outside_comparison:
            raise ValueError(f"{task['id']}: selected paths outside baseline: {outside_comparison}")
        routed_metrics = measure_paths(root, selected)
        if routed_metrics["utf8_bytes"] >= broad_metrics["utf8_bytes"]:
            raise ValueError(f"{task['id']}: route offers no bounded full-file selection")
        samples.append({
            "id": task["id"],
            "route": category,
            "required_evidence": sorted(required),
            "selected_paths": selected,
            "required_evidence_complete": True,
            "baseline": broad_metrics,
            "routed": routed_metrics,
            "reduction_percent_of_candidate_bytes": round(
                (1 - routed_metrics["utf8_bytes"] / broad_metrics["utf8_bytes"]) * 100, 1
            ),
        })
    return {
        "schema_version": 1,
        "scope": "read-all eligible owned text vs read-all links in one task-map row",
        "measurement": "static full-file candidates, not observed agent behavior",
        "agent_executions": None,
        "model_input_tokens": None,
        "elapsed_seconds": None,
        "eligible_paths": broad,
        "tasks": samples,
        "aggregate": {
            "tasks": len(samples),
            "required_evidence_complete": all(
                sample["required_evidence_complete"] for sample in samples
            ),
            "baseline_candidate_bytes": broad_metrics["utf8_bytes"] * len(samples),
            "routed_candidate_bytes": sum(sample["routed"]["utf8_bytes"] for sample in samples),
        },
    }


# {
#   責務: [main: ルーティングの検証結果をCIとJSON利用者へ提供する]
#   処理: [
#     1: ファイル候補と必須根拠を検査して集計する
#     2: JSON指定時は生のメトリクスを出力する
#     3: CI指定時は短い結果を表示し違反時に終了値1を返す
#   ]
#   引数: [argv: 引数配列、省略時はコマンドラインを使用する]
#   戻り値: [成功0または違反1の終了コード]
# }
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    fmt = parser.add_mutually_exclusive_group()
    fmt.add_argument("--check", action="store_true", help="check evidence and print summary")
    fmt.add_argument("--json", action="store_true", help="emit reproducible machine-readable report")
    args = parser.parse_args(argv)
    try:
        report = build_report(ROOT)
    except (OSError, UnicodeError, ValueError) as error:
        print(f"[context-route] FAIL: {error}")
        return 1
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        for task in report["tasks"]:
            print(f"[context-route] {task['id']}: {task['routed']['files']} files, "
                  f"{task['routed']['utf8_bytes']} UTF-8 bytes; evidence complete")
        print("[context-route] OK: static candidates only; agent tokens/behavior NOT measured")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
