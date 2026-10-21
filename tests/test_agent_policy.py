"""Check agent-policy validation for both valid and invalid inputs."""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from check_agent_policy import REQUIRED, check_pr_body, check_repository


# {
#   責務: [AgentPolicyTests: エージェントポリシーの回帰テストを保持する]
#   フィールド: [unittest.TestCaseの検証状態のみ]
# }
class AgentPolicyTests(unittest.TestCase):
    # {
    #   責務: [test_pr_evidence: PRの必要欄と検証証跡を検査する]
    #   処理: [
    #     1: 有効なPR説明が通過することを確認する
    #     2: 雛形のみのPR本文を拒否することを確認する
    #   ]
    #   引数: [self: テストケース]
    #   戻り値: [なし、不一致なら失敗]
    # }
    def test_pr_evidence(self):
        valid = ("## Issue\nCloses #123; tested the issue scope.\n"
                 "## Summary\nOne focused collaboration gate change.\n"
                 "## Validation\npython scripts/check_agent_policy.py passed.\n"
                 "## Risks\nNone for product data; only PR metadata validation.\n"
                 "## Handoff\nCodex branch issue-123, ready for human review.\n")
        self.assertEqual(check_pr_body(valid), [])
        self.assertTrue(check_pr_body("## Issue\n<!-- Closes #123 -->\n"))

    # {
    #   責務: [test_pr_rejects_duplicate_and_todo: 不正なPR本文を拒否する]
    #   処理: [
    #     1: 重複見出しと未記入の内容を作成する
    #     2: 両方の違反が検出されることを確認する
    #   ]
    #   引数: [self: テストケース]
    #   戻り値: [なし、不一致なら失敗]
    # }
    def test_pr_rejects_duplicate_and_todo(self):
        errors = check_pr_body("## Issue\nIssue #2 is tracked.\n"
                               "## Issue\nIssue #3 is tracked.\n"
                               "## Summary\nTODO placeholder text.\n")
        self.assertTrue(any("exactly one ## Issue" in item for item in errors))
        self.assertTrue(any("concrete report" in item for item in errors))

    # {
    #   責務: [test_context_limits: 短い入口とClaude参照の制約を検証する]
    #   処理: [
    #     1: 必須ファイルを持つ一時リポジトリを作る
    #     2: 正常条件と入口超過条件を比較する
    #     3: 別のClaude指示を加えた際の拒否を確認する
    #   ]
    #   引数: [self: テストケース]
    #   戻り値: [なし、不一致なら失敗]
    # }
    def test_context_limits(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in REQUIRED:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("shared policy\n", encoding="utf-8")
            (root / "CLAUDE.md").write_text("@AGENTS.md\n", encoding="utf-8")
            (root / "README.md").write_text("# User guide\n", encoding="utf-8")
            self.assertEqual(check_repository(root), [])
            (root / "AGENTS.md").write_text("A" * 2401, encoding="utf-8")
            self.assertTrue(any("exceeds" in item for item in check_repository(root)))
            (root / "CLAUDE.md").write_text("separate policy", encoding="utf-8")
            self.assertTrue(any("only @AGENTS.md" in item for item in check_repository(root)))

    # {
    #   責務: [test_broken_link: 参照切れのルール索引を拒否する]
    #   処理: [
    #     1: 一時リポジトリへ最小必須ファイルを作る
    #     2: 入口と開発者専用の文書にある不在の参照先を検出する
    #   ]
    #   引数: [self: テストケース]
    #   戻り値: [なし、不一致なら失敗]
    # }
    def test_broken_link(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in REQUIRED:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("shared policy\n", encoding="utf-8")
            (root / "CLAUDE.md").write_text("@AGENTS.md\n", encoding="utf-8")
            (root / "README.md").write_text("# User guide\n", encoding="utf-8")
            (root / "AGENTS.md").write_text("[missing](nothing.md)\n", encoding="utf-8")
            self.assertTrue(any("broken/outside" in item for item in check_repository(root)))
            (root / "AGENTS.md").write_text("shared policy\n", encoding="utf-8")
            (root / "docs" / "agents" / "development.md").write_text(
                "[bad](missing-internal.md)\n", encoding="utf-8"
            )
            self.assertTrue(any("broken/outside" in item for item in check_repository(root)))

    # {
    #   責務: [test_user_guide_isolated_from_agent_rules: 利用者向け案内への内部ルール混入を拒否する]
    #   処理: [
    #     1: 共有規約を備えた一時リポジトリを作る
    #     2: 通常の利用者向け案内は通過することを確認する
    #     3: AGENTSリンクやClaude向け手順を案内に入れると検出する
    #   ]
    #   引数: [self: テストケース]
    #   戻り値: [なし、検査結果が一致しない場合は失敗]
    # }
    def test_user_guide_isolated_from_agent_rules(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in REQUIRED:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("shared policy\n", encoding="utf-8")
            (root / "CLAUDE.md").write_text("@AGENTS.md\n", encoding="utf-8")
            guide = root / "README.md"
            guide.write_text("# 利用者向け\n\n起動と操作の説明\n", encoding="utf-8")
            self.assertEqual(check_repository(root), [])
            guide.write_text("# 利用者向け\n\n[開発規則](AGENTS.md)\n", encoding="utf-8")
            self.assertTrue(any("developer-only" in item for item in check_repository(root)))
            guide.write_text("# 利用者向け\n\nClaude CodeとCodexの共同開発\n", encoding="utf-8")
            self.assertTrue(any("developer-only" in item for item in check_repository(root)))
            guide.write_text("# 利用者向け\n\n起動と操作の説明\n", encoding="utf-8")
            api_doc = root / "docs" / "Command_API.md"
            api_doc.parent.mkdir(parents=True, exist_ok=True)
            api_doc.write_text("# API案内\n\n[内部規則](docs/agents/README.md)\n", encoding="utf-8")
            self.assertTrue(any("developer-only" in item for item in check_repository(root)))

    # {
    #   責務: [test_task_map_routes_resolve_to_source_and_tests: 調査ルートの実装・テスト参照切れを防ぐ]
    #   処理: [
    #     1: 最小限の共有規則を一時リポジトリへ作る
    #     2: 存在しない実装とテストの参照を検出する
    #     3: 対象ファイルを追加すると検査が通過することを確認する
    #   ]
    #   引数: [self: テストケース]
    #   戻り値: [なし、検査結果が一致しなければ失敗]
    # }
    def test_task_map_routes_resolve_to_source_and_tests(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in REQUIRED:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("shared policy\n", encoding="utf-8")
            (root / "CLAUDE.md").write_text("@AGENTS.md\n", encoding="utf-8")
            (root / "README.md").write_text("# User guide\n", encoding="utf-8")
            task_map = root / "docs" / "agents" / "task-map.md"
            task_map.write_text(
                "[source](../../src/module.py) and [tests](../../tests/test_module.py)\n",
                encoding="utf-8",
            )
            self.assertTrue(any("task-map.md: broken/outside" in error
                                for error in check_repository(root)))
            for relative in ("src/module.py", "tests/test_module.py"):
                destination = root / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_text("# placeholder\n", encoding="utf-8")
            self.assertEqual(check_repository(root), [])

