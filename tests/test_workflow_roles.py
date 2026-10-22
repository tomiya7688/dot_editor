import re
import unittest
from pathlib import Path
from urllib.parse import unquote


# {
#   責務: [WorkflowRoleTests: 担当別手順の入口と役割識別子の取り違えを検出する]
#   フィールド: []
# }
class WorkflowRoleTests(unittest.TestCase):
    # {
    #   責務: [test_agent_entrypoints_route_to_role_dispatcher: 両エージェントの入口が担当選択へ到達することを確認する]
    #   処理: [1: 共通入口への参照とClaudeの取り込み指定を照合する]
    #   引数: [self: テストの実行状態]
    #   戻り値: [なし。不一致ならテスト失敗]
    # }
    def test_agent_entrypoints_route_to_role_dispatcher(self):
        # ツールごとに別の役割を割り当てず、同じ正本へ案内する。
        root = Path(__file__).resolve().parents[1]
        entrypoint = (root / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("doc/ワークフロー/ワークフロー.md", entrypoint)
        self.assertIn("implementer", entrypoint)
        self.assertIn("repository-reviewer", entrypoint)
        self.assertEqual((root / "CLAUDE.md").read_text(encoding="utf-8").strip(), "@AGENTS.md")

    # {
    #   責務: [test_dispatcher_links_both_role_workflows: 担当選択の正本から両方の手順へ進めることを確認する]
    #   処理: [1: 両担当の識別子とリンクを検査する]
    #   引数: [self: テストの実行状態]
    #   戻り値: [なし。不一致ならテスト失敗]
    # }
    def test_dispatcher_links_both_role_workflows(self):
        # 担当者が入口を読んでも手順を選べない欠落を検出する。
        root = Path(__file__).resolve().parents[1]
        dispatcher = (root / "doc/ワークフロー/ワークフロー.md").read_text(encoding="utf-8")
        for role, filename in (("implementer", "実装担当.md"),
                               ("repository-reviewer", "全体レビュアー.md")):
            with self.subTest(role=role):
                self.assertIn(role, dispatcher)
                self.assertIn(f"]({filename})", dispatcher)

    # {
    #   責務: [test_role_files_have_distinct_identifiers: 手順ファイルの担当識別子が逆転・重複していないことを確認する]
    #   処理: [1: 各ファイルの識別子を期待する担当と照合する]
    #   引数: [self: テストの実行状態]
    #   戻り値: [なし。不一致ならテスト失敗]
    # }
    def test_role_files_have_distinct_identifiers(self):
        # 文意の正しさは自己レビューし、ここでは機械的に確認できる対応を守る。
        root = Path(__file__).resolve().parents[1]
        for role, filename in (("implementer", "実装担当.md"),
                               ("repository-reviewer", "全体レビュアー.md")):
            text = (root / "doc/ワークフロー" / filename).read_text(encoding="utf-8")
            with self.subTest(role=role):
                self.assertEqual(re.findall(r"<!-- workflow-role: ([a-z-]+) -->", text), [role])

    # {
    #   責務: [test_local_workflow_links_resolve: 手順内のローカル文書リンクが実在することを確認する]
    #   処理: [1: 入口と担当手順のローカルリンクを解決し存在を検査する]
    #   引数: [self: テストの実行状態]
    #   戻り値: [なし。リンク切れならテスト失敗]
    # }
    def test_local_workflow_links_resolve(self):
        # 外部URLの通信可否やMarkdown全仕様の検査とは区別する。
        root = Path(__file__).resolve().parents[1]
        documents = [root / "AGENTS.md", *sorted((root / "doc/ワークフロー").glob("*.md"))]
        for document in documents:
            text = document.read_text(encoding="utf-8")
            for target in re.findall(r"\]\(([^)]+)\)", text):
                if "://" in target or target.startswith("#"):
                    continue
                with self.subTest(document=document.name, target=target):
                    self.assertTrue((document.parent / unquote(target.split("#", 1)[0])).is_file())
