# 開発者向け：構成・ビルド・評価

**対象は内部開発者だけです。** Claude Code・Codexの作業ルールは [AGENTS.md](../../AGENTS.md) と [エージェント用索引](README.md) に定義します。利用者向けのREADMEに開発者の作業規則や引き継ぎ手順を掲載しません。

## 実装の正本と移行方針

製品バックエンドの正本は `rust/` のRust実装とします。Python版は既存GUI・参照実装として残し、移行中はプロジェクトJSONや描画結果など外部から確認できる振る舞いで互換性を検証します。仕様や互換テストに差異がある場合はRust Coreを基準にします。

移行の順序はRust Core、Rust CLI、Rust配布物です。GUIのRust化は初期移行の必須条件にしません。Rust workspaceは現在基盤作成中であり、機能移植の完了を示すものではありません。


## ソース構成と開発ツール

- `src/`: GUI・CLI・共通バックエンド。既存のPython import名は維持しています。
- `rust/`: 製品正本へ移行するRust workspace。RGBAラスタ、細部保持・破棄、4子セル分割・描画、Undo/Redo付きCanvasを整備しています。Canvasの4近傍塗りつぶしと長方形の領域分割は、それぞれ全体を1回でUndoできます。
  単一CanvasのJSON読み込みは `Canvas::from_json()`（version 1・2）、書き出しは `Canvas::to_json()`（version 2）で利用できます。Pythonとの往復互換は `.venv/Scripts/python.exe scripts/test_rust_json_compat.py` で検証できます。レイヤー付きJSONとPNG出力は移植中です。
- `tests/`: 自動テスト。
- `scripts/`: 環境構築・評価・配布ビルド。
- `tools/tomiya_code_atlas/`: 図生成用の外部Gitサブモジュール。
- `dist/`: ローカルの配布成果物（Git対象外）。

クラス図・シーケンス図は独自生成器ではなく [Tomiya Code Atlas](https://github.com/tomiya7688/tomiya_code_atlas) を使用します。
導入・実行方法は [tools/README.md](../../tools/README.md) を参照してください。


## Rust Core のビルド・テスト

Rustコアの開発には **Rust stableツールチェーン（cargo / rustfmt / clippy）** が別途必要です。Pythonのセットアップと混同しないよう、Rust workspaceの確認はリポジトリ直下から次を実行します。

```bash
cargo fmt --all --manifest-path rust/Cargo.toml -- --check
cargo clippy --manifest-path rust/Cargo.toml --workspace --all-targets --all-features -- -D warnings
cargo test --manifest-path rust/Cargo.toml --workspace
cargo build --manifest-path rust/Cargo.toml --workspace
python scripts/test_rust_json_compat.py
```

最後の互換性テストはセットアップ済みのPython参照実装とRust Coreで、双方向のJSON互換性を検証します。Rust CLIやRust製配布物は移行途中であり、現在の `python -m pixel_cli` およびWindows配布EXEはPythonベースです。


## Windows配布ビルド

Windows x64環境で、先に[Windowsのセットアップ](../../README.md#windows-powershell)を実行して `.venv` を作成してください。ビルド用依存はビルドスクリプトが `requirements-build.txt` からインストールします。


```powershell
powershell -ExecutionPolicy Bypass -File scripts/build_windows.ps1
```

Pythonパッケージ（wheel・sdist）と、Pythonのインストール不要なWindows x64配布物を生成します。
`dist/HyperDotEditor-windows-x64.zip` を展開し、`DotEditor/DotEditor.exe` を起動してください。
CLIは `DotEditorCLI/DotEditorCLI.exe` です。各フォルダの `_internal` を含めて配布してください。
ビルド時にCLIの保存・編集・PNG出力とGUI実行ファイルの非GUIスモーク検査を行います。
画面を操作するGUIテストとは異なります。既存の同名 `dist` 成果物は再ビルドで更新されます。

GitHub ActionsのWindowsジョブでもビルドし、配布ZIPとwheel・sdistをArtifactsへアップロードします。


## 自動評価

GUIウィンドウを開かない最低限の起動確認には `python -m dot_editor --smoke-test` を使えます。これは画面操作テストの代わりにはなりません。


```bash
python scripts/evaluate.py
python -m unittest discover -s tests
```

push / pull request ごとに Python 3.10 / 3.11 / 3.12 / 3.13 / 3.14 の全ジョブで評価・回帰テストを実行します。通常の自動評価はGUIウィンドウを起動しません。


## 開発資料

- [開発ワークフロー](../../doc/ワークフロー/ワークフロー.md)
- [開発予定](../../docs/開発予定.md)
- [コーディングルール](../../docs/コーディングルール.md)
- [提案書](../../docs/提案.md)
- [共通Command API](../../docs/Command_API.md)
- [セル分割回帰仕様](../../docs/Refinement_regressions.md)
- [非破壊解像度の仕様](../../docs/Non_destructive_resolution.md)

