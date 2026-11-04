# Rust正本・Python参照実装・互換検証・必須CIゲートの設計

対象: [#34](https://github.com/tomiya7688/dot_editor/issues/34)（Rustが正本）、[#35](https://github.com/tomiya7688/dot_editor/issues/35)・[#36](https://github.com/tomiya7688/dot_editor/issues/36)（Rust Coreの移植。実装済み）、[#39](https://github.com/tomiya7688/dot_editor/issues/39)（Python参照実装と互換テスト）、[#40](https://github.com/tomiya7688/dot_editor/issues/40)（必須ゲートのRust中心化）。必須チェックを保護設定に反映する手順は[mainの保護設定の手順](main-protection-runbook.md)（#46）です。状態: 方針と対応表は2026-11-05時点の実装に基づく確定案で、未達の項目は各表に明記します。

## 背景・目的

ゲームエンジンやツールは、Pythonを同梱せずに単体の実行ファイルを起動して使います。そのため「何が正しいか」の最終判断をRust実装に置き、Python実装は参照実装・GUI・比較対象として残します。この文書は、判断の優先順位、仕様を変えるときの手順、互換性を何で保証するか、CIのどのジョブが何を止めるかを1か所にまとめます。

## 判断の優先順位（#34）

1. 仕様とgolden fixtures
2. Rust Core
3. Rust CLI
4. Python参照実装
5. GUI

食い違ったときは上位に合わせます。Pythonだけに新しいCoreの仕様を足しません。新機能は、仕様（設計書）→ golden fixture → Rust実装 → Pythonへの反映（必要な場合のみ、Rustの意味に合わせる）→ 互換テスト、の順で入れます。

### 構成

| 場所 | 役割 |
| --- | --- |
| `rust/crates/hyper-dot-core` | 正本のCore（解像度・保持/破棄・分割・レイヤー・JSON・PNG） |
| `rust/crates/hyper-dot-cli` | 正本のシェルCLI（`pixel-cli`、別名`cli-anything-dot-editor`） |
| `src/*.py` | Python参照実装とTkinter GUI。`python scripts/evaluate.py`と回帰テストで維持 |
| `tests/fixtures/project_json/` | 言語に依存しない見本（旧形式、透明画素つき単一、レイヤー付き） |
| `scripts/test_rust_*_compat.py`、`scripts/e2e_rust_cli.py` | Rust⇔Pythonの互換検証と、リリースバイナリの別プロセス検証 |

### Pythonの扱い

- Python 3.10〜3.14でのwheel/sdistのビルド、インストール、評価、回帰テストは、これまでどおり必須の互換性要件です。Rustのためにサポート対象を縮小しません。縮小が必要なら、別の仕様変更Issueで承認を得てからにします。
- PyInstallerなどのPython同梱exeは製品要件にしません。現行のWindows配布物（Python GUI/CLI）は[配布の設計](release-distribution.md)で位置づけます。
- Rustの実行ファイルのビルドとテストは、Pythonを要求しません。

## 互換検証の対応表（#39）

Issue #39が挙げる比較項目と、現在それを保証するものです。

| 比較項目 | 保証するもの | 状態 |
| --- | --- | --- |
| 論理解像度 | `test_rust_json_compat.py`（複数解像度での論理表示）、`layered_*`の合成 | 実装済み |
| レイヤー（名前・順序・表示・選択） | `test_rust_layered_json_compat.py`、`test_rust_cli_compat.py` | 実装済み |
| 画素の取得（sample） | 描画行列の比較で間接的に確認。`pixel sample`の値そのものはRustのCLI契約テストが確認 | **直接比較は未整備**（後続で追加） |
| 保持細部・分割のメタデータ | `test_rust_json_compat.py`（保持パッチ・分割記録の往復） | 実装済み |
| PNGの画素 | `test_rust_layered_json_compat.py`、`test_rust_cli_compat.py`、`e2e_rust_cli.py`（PNGを標準ライブラリで検査） | 実装済み（代表画素より強く、全画素を比較） |
| 不正な文書の拒否 | レイヤー付きJSONの不正10種を両言語で拒否 | 実装済み |
| 見本ファイル | `legacy_refinement_v1.json`、`transparent_rectangular_v2.json`、`layered_v2.json` | 実装済み。「細部を破棄したレイヤー付き」見本は**未整備** |

見本ファイルを足す手順: (1)Pythonで作る、またはRustで作る、(2)`tests/fixtures/project_json/`に置く、(3)両言語の読み込みテストに追加する、(4)描画行列が一致することを確認する。

## 必須ゲート（#40）

CIは次のジョブで構成され、ジョブごとに止める原因を分けています（現行の名前。名前は保護設定の「必須チェック名」と一致させるため変更しません）。

| ジョブ | 内容 | 失敗の意味 |
| --- | --- | --- |
| `Rust Core` | `cargo fmt --all --check`、`clippy -D warnings`、`test`、`build`、`build --release`、Rust⇔Python互換（JSON、レイヤー付きJSON、CLI）、リリースバイナリのE2E | 製品（Rust）の不具合。マージ不可 |
| `Python 3.10`〜`Python 3.14` | パッケージのビルド、インストール、評価、全回帰テスト | Python参照実装・互換性の不具合。マージ不可 |
| `Declaration comments` | 宣言コメントの検査、Pythonの整形検査 | 規約違反。マージ不可 |
| `Agent policy` | 担当者向け文書の制限、PR本文の様式 | 運用規則違反。マージ不可 |
| `windows-build` | 配布物のビルドと起動の検査。上の4種が成功してから実行 | 配布不可 |

### 表示順と分離

Issue #40は「CI表示上もRustを先に」と述べています。GitHubのチェックの表示順は制御できず、Pythonのジョブを`needs`でRustの後ろに連結すると、Rustが失敗したときPythonの原因が見えなくなります。そのため**ジョブは並列のまま**とし、順序は(1)`Rust Core`ジョブの内部の手順の並び（整形→静的検査→テスト→ビルド→リリースビルド→互換→E2E）、(2)この表と[品質ゲート](../agents/quality-gates.md)での優先順位の明記、で表します。

### Issueの完了条件との対応

| 条件 | 状態 |
| --- | --- |
| Rustのビルド・テストが必須 | 実装済み（保護設定への反映は#46） |
| リリースバイナリのビルド失敗でマージ不可 | 実装済み（`Rust Core`内の`build --release`） |
| Python 3.10〜3.14の必須CIを維持 | 実装済み |
| PythonジョブとRustジョブの分離 | 実装済み |
| Rustバイナリの別プロセスE2E | #33で追加（`scripts/e2e_rust_cli.py`） |
| README/CONTRIBUTING等にCIの優先順位を明記 | 担当者向けの文書（品質ゲート）に記載する。READMEは利用者向けなので手順を入れない |
| 他OSのRustバイナリのE2E | [配布の設計](release-distribution.md)（#38）で実施 |

## 変更の手順

CIのゲートを緩める、ジョブ名を変える、Pythonの対応版を減らす変更は、(1)その理由を書いたIssueを立て、(2)保護設定の必須チェック名との対応を同時に更新し（#46の手順）、(3)所有者の判断を得てからPRにします。テストの削除や条件の緩和で失敗を隠しません。
