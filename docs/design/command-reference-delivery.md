# コマンドカタログ生成・同梱の実装設計

対応する受け入れIssue: [#66](https://github.com/tomiya7688/dot_editor/issues/66)（利用者向け要件正本は[ユーザー操作インターフェース仕様](../ユーザー操作インターフェース仕様.md)）。**現行の成果物に同梱されていることを主張する文書ではありません。**

## 1. 現行の正本

- Rust CLI: [`command_table.rs`](../../rust/crates/hyper-dot-cli/src/command_table.rs)の22コマンドの`CommandSpec`と`FlagSpec`。ヘルプは[`help_text.rs`](../../rust/crates/hyper-dot-cli/src/help_text.rs)が同じ定義から生成します。
- Python CLI: [`pixel_cli.py`](../../src/pixel_cli.py)の`build_parser()`が`new/edit/inspect/export/palette`、オプション、nargs、選択肢を定義します。RustとPythonで同じ文字列コマンドでも同一実装であるとは扱いません。
- GUI: [`dot_editor.py`](../../src/dot_editor.py)。Windowsの既存[ビルドスクリプト](../../scripts/build_windows.ps1)はPython GUI/CLIを同梱し、Rust CLIはまだ入っていません。

## 2. 機械可読な中間形式

```json
{
  "schema_version": 1,
  "cli_implementation": "rust",
  "cli_version": "0.1.0",
  "commands": [
    {
      "path": ["pixel", "paint"],
      "usage": "pixel paint X Y COLOR [--child CX CY] [--discard-detail]",
      "summary": "指定のセルに色を塗る",
      "effect": "edit",
      "arguments": [
        {"name": "x", "required": true, "kind": "integer"},
        {"name": "y", "required": true, "kind": "integer"},
        {"name": "color", "required": true, "kind": "color"}
      ],
      "flags": [
        {"name": "--child", "aliases": [], "values": 2, "required": false},
        {"name": "--discard-detail", "aliases": [], "values": 0, "required": false}
      ],
      "examples": ["pixel-cli -p art.json pixel paint 3 4 \"#FF8800\""],
      "warnings": ["細部破棄は既存の詳細情報を失うことがあります"]
    }
  ]
}
```

このJSONは**schema案**であり、上の日本語説明・例は公開コマンドの動作契約を検証した後に確定します。色文字列は引数配列として渡すかShellで引用符を付けます。JSONの`path/arguments/flags/effect`はランタイムのコマンド定義から抽出します。`examples`と利用者向け日本語説明はコマンドIDに対応する補助メタデータとして同じ実装に隣接して管理し、**別の独立したコマンド一覧を手管理しません**。

## 3. Rust側の出力

- **追加予定**：`pixel-cli --commands-json`（あるいは同等の文書化した安定入口）を設け、`--project`/GUI/ネット接続不要で上のカタログを返す。成功時`stdout`は1つのJSON、exit 0。バージョンはビルド済みバイナリの`CARGO_PKG_VERSION`と一致させます。
- `--help`と`pixel-cli pixel paint --help`は従来どおり人が読める文章を返し、カタログと同じ`COMMANDS`定義を参照する。説明表の追加で引数パーサーやエラーの契約を壊しません。
- 生成器は**実際にビルドしたバイナリのカタログJSON**を入力として`COMMANDS.md`を生成する。Rustソースのregexでコマンド名を抽出する脆い方式や、PythonのCLI一覧をRust版へ転用する方式は採用しません。
- 生成順序は既存`COMMANDS`順、Markdown/JSONはUTF-8 LFで同じ入力ならbyte-identical。JSON`schema_version`と`cli_version`を記録します。

## 4. Python側の出力

- `build_parser()`の全サブコマンド・`argparse.Action`からメタデータを取得する。フラグが正しいのに`--help`から説明が欠落している場合、説明を補って同じパーサーへ反映します。
- `cli_implementation=python`とPythonパッケージの`version`を固定し、Rustの表と区別します。GUIと同梱される現行Windows配布ZIPにRust版の構文を表示しません。
- 補助の日本語説明は`argparse`内の`help`や関連する一か所のメタデータから生成。独立した手書きコマンド表は作らず、未知/削除されたオプションのメタデータはCIでエラーとします。

## 5. 配布への組み込み（自動、fail-closed）

```text
source command definitions
 → compile actual CLI / construct argparse parser
 → export commands.json
 → render COMMANDS.md and short QUICKSTART
 → compare --help and generated catalog
 → package files and executables
 → inspect ZIP/wheel/sdist or Rust archive by extracting it
 → verify CLI implementation/version + catalog/hash/required files
 → checksum and cryptographic signing/attestation
 → release gate
```

現在のWindows Python配布工程では`scripts/build_windows.ps1`が`dist/windows`へ資料をコピーした後に`Compress-Archive`します。ここでPython版の生成ファイルを置き、[`smoke_distribution.py`](../../scripts/smoke_distribution.py)から**展開済み配布物の実CLIと資料**を検証します。zip作成後もzipの中に資料が入ったことを検証します。

wheel/sdistについては、生成後に単にルート`dist/`へ資料を置くのでなく、**実際にユーザーが入手するwheel/sdist内**にPython版カタログを含めます。setuptoolsのパッケージデータと`importlib.resources`等で参照可能な構成を使い、Python 3.10～3.14ごとにインストール後の参照と元パーサーとの一致を確認します。

将来のRust配布アーカイブ（#38）では同じrelease binaryの`--commands-json`から生成し、`docs/cli/rust/COMMANDS.md`と`commands.json`をバイナリ・ライセンス・短い説明と同梱します。macOS/Windows/Linuxそれぞれの実アーカイブから全資料を取り出せることを確認します。実CLIに存在しない#63/#64などの将来コマンドを先行掲載しません。

署名・attestation #55が未完了なら、生成/CIが通っても成果物を**公開・アップロードしない**既存制約を維持します。説明表は必ず署名前に最終アーカイブへ入れ、署名後に追記しません。

## 6. テストと失敗条件

| 検査 | 実行・照合内容 | 失敗条件 |
| --- | --- | --- |
| 登録とヘルプの一致 | 実CLI`--help`/個別help vs. JSONの全ID/引数/フラグ | コマンドや説明の欠落、構文差異 |
| バイナリと表の版一致 | `--version`と`commands.json`の`cli_version` | 版/実装種別の不一致 |
| deterministic | 同じバイナリ/パーサーから2回生成 | Markdown/JSONのbyte差 |
| Python配布 | wheel/sdistを開き、さらにインストールして参照 | 同梱されない・古い・到達不可 |
| Windows配布 | ZIPを実展開、`DotEditorCLI.exe --help`とPython表 | 表の欠落・Rust版誤同梱 |
| Rust 3OS配布 | 最終Rust CLIアーカイブを実展開、`pixel-cli --help`とRust表 | 表/JSON/CLIの差・欠落 |
| 動作/副作用 | 引数を誤った場合やhelp/JSONカタログ取得 | プロジェクトを作成・変更してしまう |
| 表記 | 日本語の破壊的操作説明、可読性、UTF-8 | 危険な上書き・破棄の説明が欠落 |

GitHub CIが必要な検証を実行しない場合は実装済みとしない。テストログ/候補を`AGENTS.md`や利用者向け資料へ複製しない。

## 7. 実装分割と既存Issue

1. **#66-A** Rust CLIのデータ抽出・ヘルプ一致・日本語の利用者向け説明（Core/CLI契約は変更しない）。
2. **#66-B** Python `argparse`カタログとWindows ZIP / wheel / sdistの実成果物同梱。
3. **#66-C** Rust OS別配布#38への同梱・署名gate・cross-platform実E2E。
4. **#67** 軽量GUIから同梱したオフライン資料への導線。GUIの入力状態や作品保存へ干渉しない。

関連：[#32](https://github.com/tomiya7688/dot_editor/issues/32) CLI互換入口、[#33](https://github.com/tomiya7688/dot_editor/issues/33) release binary subprocess E2E、[#38](https://github.com/tomiya7688/dot_editor/issues/38) Rust OS別配布、[#55](https://github.com/tomiya7688/dot_editor/issues/55) 署名。
