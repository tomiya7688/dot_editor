# 作業別の案内（担当者向け）

`AGENTS.md`から来るページです。**今回の作業に関係する行だけ**を読んでください。ここは索引で、規則の本文ではありません。規則は[R01〜R20](../../コーディング規約.md)と[ワークフロー](../../doc/ワークフロー/ワークフロー.md)にあります。

## 読む順番

1. Issueの完了条件、担当するファイル、`git status`、`origin/main`との差を確認する。
2. 下の「作業別の表」で、今回の作業の行を見つける。**設計書 → 仕様・契約 → ソース → テスト**の順に読む。
3. 検索してから読む（`rg --files`、`rg -n`）。ソースとテストの場所が分かっているなら直接開く。分からなければ[ソースとテストの対応表](task-map.md)と[よく触る場所](hotspots.md)を使う。
4. 検索結果や表は根拠ではありません。原典（ソース・テスト・仕様）を読んで確かめる。
5. 実装の前に[手戻りを防ぐチェック表](../../doc/ワークフロー/実装前チェック.md)を確認する。

## 作業別の表

| 作業 | 設計書・仕様 | 主なソース | テスト・確認 |
| --- | --- | --- | --- |
| Rust Coreの解像度・保持/破棄・分割 | [非破壊解像度](../Non_destructive_resolution.md)、[Rust正本と必須ゲート](../design/rust-canonical-and-gates.md) | `rust/crates/hyper-dot-core/src/` | `rust/crates/hyper-dot-core/tests/`、`scripts/test_rust_json_compat.py` |
| レイヤー・保存形式（JSON）・PNG | 同上、[見本ファイル](../../tests/fixtures/project_json/) | `layered_canvas*.rs`、`project_json*.rs`、`png_export.rs` | `scripts/test_rust_layered_json_compat.py` |
| Rust CLI（コマンド・出力・終了値） | [CLI契約](../CLI契約.md)、[別名・SKILL.md・E2E](../design/cli-alias-skill-e2e.md) | `rust/crates/hyper-dot-cli/src/` | `tests/cli_contract.rs`、`scripts/e2e_rust_cli.py`、`scripts/test_rust_cli_compat.py` |
| CLIの同時編集・バッチ・コマンド表 | [保存安全性](../design/cli-concurrency.md)、[バッチ](../design/cli-batch.md)、[コマンド表の同梱](../design/command-reference-delivery.md) | `project_file.rs`、`runner.rs`、`command_table.rs` | CLIの契約テスト |
| GUIのキーボード・メニュー | [キーボード操作](../design/keyboard-operation.md)、[軽量GUI](../design/lightweight-gui.md) | `src/dot_editor.py` | `tests/test_menu_structure.py`、`tests/test_keyboard_focus_regions.py` |
| Python参照実装・Command API | [Command API](../Command_API.md)、[細部操作](../CUI_detail_operations.md) | `src/pixel_*.py`、`src/resolution_field.py` | `tests/`、`python scripts/evaluate.py` |
| CI・必須チェック・保護設定 | [Rust正本と必須ゲート](../design/rust-canonical-and-gates.md)、[保護設定の手順書](../design/main-protection-runbook.md)、[品質ゲート](quality-gates.md) | `.github/workflows/ci.yml` | `gh pr checks`、`tests/test_agent_policy.py` |
| 配布・署名・出所の検証 | [配布の設計](../design/release-distribution.md)、[供給網の設計](../design/supply-chain-security.md)、[成果物の検証](../成果物の検証.md) | `scripts/build_windows.ps1`、`scripts/artifact_checksums.py` | `scripts/smoke_distribution.py` |
| Pythonの信頼ストア（証明書） | [供給網の設計](../design/supply-chain-security.md) | `scripts/python_trust.py` | `tests/test_python_trust.py` |
| 担当者向けの規則・案内の変更 | [共同作業](collaboration.md)、[品質ゲート](quality-gates.md) | `scripts/check_agent_policy.py` | `tests/test_agent_policy.py` |
| 案内の効果の測定 | [実験計画](../design/context-routing-experiment.md) | `scripts/context_route_benchmark.py` | 同名のテスト |
| 描画AI（将来のアプリ） | [設計書](../dot-editor-ai/設計書.md)、[優先度とロードマップ](../優先度とロードマップ.md) | （本体にはAIのコードを入れない） | — |

設計書がない作業は、[設計書の書き方](../../doc/ワークフロー/設計書.md)で先に書き、[設計書の一覧](../design/README.md)に追加します。

## 読まないもの（原則）

関係のないIssue・文書・古いログ、`dist/`、`build/`、`rust/target/`、`.venv/`、生成された索引。ただし成果物の検証など、直接関係する場合は読みます。

## 止める・広げる

必要な振る舞い、ソース、テスト、守る条件、確認方法が分かったら調べるのをやめます。公開API・共有の保存形式に触れる、テストが失敗する、根拠が足りない場合は、利用側・見本ファイル・契約へ広げます。局所のテストと、該当する必須のCI/E2Eを実行し、読んだもの・実行したもの・未確認のものを報告します。測定していない削減量は主張しません。

## 必要なときに読む

- 並行作業・引き継ぎの様式: [共同作業](collaboration.md)
- CI・ビルド・配布の確認: [品質ゲート](quality-gates.md)、[内部のビルド手順](development.md)
- セル細部の回帰: [細分化の仕様](../Refinement_regressions.md)
