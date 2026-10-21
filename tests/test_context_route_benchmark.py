"""Regression tests for bounded ObaPick-style context-route candidates."""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from context_route_benchmark import ROOT, build_report, eligible_paths, task_routes


# {
#   責務: [ContextRouteBenchmarkTests: 案内の根拠保持と負例を実ファイル・一時fixtureで検証する]
#   フィールド: [root: 使い捨て作業場所、trial: fixtureの完了条件]
# }
class ContextRouteBenchmarkTests(unittest.TestCase):
    # {
    #   責務: [setUp: 既知のソース・テスト・仕様を持つ比較fixtureを用意する]
    #   処理: [
    #     1: 互いに独立した一時リポジトリを作る
    #     2: 照合すべき3種類の根拠と関係のないコードを配置する
    #     3: 今回の作業用ルートと必要根拠を設定する
    #   ]
    #   引数: [self: テストの状態を保持するインスタンス]
    #   戻り値: [なし、テストfixtureをインスタンスへ設定する]
    # }
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        documents = {
            "src/example.py": "def example():\n    return 'expected'\n",
            "src/unrelated.py": "def unrelated():\n    return 'not needed'\n",
            "tests/test_example.py": "assert True\n",
            "docs/contract.md": "# Example contract\n\nExpected behavior.\n",
            "README.md": "# User guide\n",
            "docs/agents/task-map.md": (
                "| Change category | Start with source | Matching tests/verification "
                "| Contract when needed |\n"
                "| --- | --- | --- | --- |\n"
                "| Example flow | [implementation](../../src/example.py) "
                "| [regression](../../tests/test_example.py) "
                "| [contract](../contract.md) |\n"
            ),
        }
        for relative, content in documents.items():
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        self.trial = ({
            "id": "example-task",
            "route": "Example flow",
            "required_evidence": (
                "src/example.py", "tests/test_example.py", "docs/contract.md"
            ),
        },)

    # {
    #   責務: [test_complete_evidence_and_bounded_candidates: 必須根拠を残した絞り込みを検査する]
    #   処理: [
    #     1: fixtureで候補バイト数とリンク先を検査する
    #     2: 範囲外のファイルを絞り込み候補から除外したことを確認する
    #     3: トークン・エージェントの実行を未計測として返すことを検証する
    #   ]
    #   引数: [self: 一時fixtureを持つテストケース]
    #   戻り値: [なし、根拠の不一致なら失敗]
    # }
    def test_complete_evidence_and_bounded_candidates(self):
        report = build_report(self.root, self.trial)
        sample = report["tasks"][0]
        self.assertTrue(sample["required_evidence_complete"])
        self.assertEqual(sample["routed"]["files"], 3)
        self.assertGreater(sample["baseline"]["utf8_bytes"], sample["routed"]["utf8_bytes"])
        self.assertNotIn("src/unrelated.py", sample["selected_paths"])
        self.assertIsNone(report["model_input_tokens"])
        self.assertIsNone(report["agent_executions"])

    # {
    #   責務: [test_existing_wrong_contract_is_rejected: 存在するが誤った仕様書への案内を検出する]
    #   処理: [
    #     1: 別の仕様書を作って案内先だけを差し替える
    #     2: 原本を選ばない案内が必須根拠不足として失敗することを確認する
    #   ]
    #   引数: [self: テストケース]
    #   戻り値: [なし、不足を見逃した場合は失敗]
    # }
    def test_existing_wrong_contract_is_rejected(self):
        (self.root / "docs/other.md").write_text("# Wrong subject\n", encoding="utf-8")
        route_path = self.root / "docs/agents/task-map.md"
        text = route_path.read_text(encoding="utf-8")
        route_path.write_text(text.replace("../contract.md", "../other.md"),
                              encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "missing required evidence"):
            build_report(self.root, self.trial)

    # {
    #   責務: [test_missing_or_escaping_link_fails: 参照欠落とリポジトリ外への飛び出しを検出する]
    #   処理: [
    #     1: 仕様書リンクを存在しない場所に変更する
    #     2: ディレクトリ外リンクも不正として拒否する
    #   ]
    #   引数: [self: 一時fixtureを持つテストケース]
    #   戻り値: [なし、不正リンクが通った場合は失敗]
    # }
    def test_missing_or_escaping_link_fails(self):
        route_path = self.root / "docs/agents/task-map.md"
        source = route_path.read_text(encoding="utf-8")
        route_path.write_text(source.replace("../contract.md", "../missing.md"),
                              encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "missing/outside"):
            task_routes(self.root)
        route_path.write_text(source.replace("../contract.md", "../../../../secret.md"),
                              encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "missing/outside"):
            task_routes(self.root)

    # {
    #   責務: [test_baseline_excludes_generated_outputs: 出力物が比較対象を水増ししないことを検査する]
    #   処理: [
    #     1: 配布物・target・仮想環境のダミーファイルを用意する
    #     2: 幅広い比較候補へ含まれないことを確認する
    #   ]
    #   引数: [self: 比較用リポジトリを持つテストケース]
    #   戻り値: [なし、不適切な候補があれば失敗]
    # }
    def test_baseline_excludes_generated_outputs(self):
        for relative in ("dist/output.md", "build/cached.py",
                         "rust/target/debug/untracked.rs", ".venv/module.py"):
            output = self.root / relative
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text("noise" * 1000, encoding="utf-8")
        pool = eligible_paths(self.root)
        self.assertTrue(all(not p.startswith(("dist/", "build/", "rust/target/",
                                               ".venv/")) for p in pool))
        self.assertIn("src/example.py", pool)

    # {
    #   責務: [test_real_repository_three_routes: 実repoの代表3作業で必須根拠を検証する]
    #   処理: [
    #     1: 共有ルート案内から三作業を読み込む
    #     2: 必須のコード・テスト・fixture・説明の欠落がないことを検査する
    #   ]
    #   引数: [self: テストケース]
    #   戻り値: [なし、ルートの欠落や誤案内で失敗]
    # }
    def test_real_repository_three_routes(self):
        report = build_report(ROOT)
        self.assertEqual([task["id"] for task in report["tasks"]],
                         ["rust-project-json", "python-cli", "gui-keyboard"])
        self.assertTrue(report["aggregate"]["required_evidence_complete"])
        self.assertLess(report["aggregate"]["routed_candidate_bytes"],
                        report["aggregate"]["baseline_candidate_bytes"])
