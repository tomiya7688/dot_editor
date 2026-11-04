# コマンドカタログ生成・同梱の実装設計

対応する受け入れIssue: [#66](https://github.com/tomiya7688/dot_editor/issues/66)（利用者向け要件正本は[ユーザー操作インターフェース仕様](../ユーザー操作インターフェース仕様.md)）。**現行の成果物に同梱されていることを主張する文書ではありません。**

## 1. 現行の正本

- Rust CLI: [`command_table.rs`](../../rust/crates/hyper-dot-cli/src/command_table.rs)の22コマンドの`CommandSpec`と`FlagSpec`。ヘルプは[`help_text.rs`](../../rust/crates/hyper-dot-cli/src/help_text.rs)が同じ定義から生成します。
- Python CLI: [`pixel_cli.py`](../../src/pixel_cli.py)の`build_parser()`が`new/edit/inspect/export/palette`、オプション、nargs、選択肢を定義します。RustとPythonで同じ文字列コマンドでも同一実装であるとは扱いません。
- GUI: [`dot_editor.py`](../../src/dot_editor.py)。Windowsの既存[ビルドスクリプト](../../scripts/build_windows.ps1)はPython GUI/CLIを同梱し、Rust CLIはまだ入っていません。

## 2. 機械可読な中間形式

カタログの構造は[正式なJSON Schema v1](catalog-schema-v1.json)と[詳細項目・JSONサンプル](#8-確定するカタログ構造66の実装契約案)で定めます。実装されたコマンドだけを含め、引数・フラグ・副作用・使用例のargv配列を返します。これはまだ未実装の取得API案であり、実行ファイルの`--help`と独立した手書きコマンド表を増やすものではありません。

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

## 8. 確定するカタログ構造（#66の実装契約案）

[JSON Schema v1](catalog-schema-v1.json)をカタログ検証の唯一の機械可読正本とする。これは作品のproject JSON v2と**別の形式**。現在の実装で使用可能なコマンドだけを列挙し、未実装の#63/#64を含めない。Schemaファイル自体は機能実装ではない。

| 属性 | 役割 | 適合性検査 |
| --- | --- | --- |
| `schema_version` | カタログのメジャー版、v1は整数1 | 未対応のmajorは黙って解釈せず拒否 |
| `cli_implementation` | `rust`または`python` | 実際の配布CLIと一致 |
| `cli_version` | Rust binaryまたはPython packageの版 | 実際の`--version`/package metadataと一致 |
| `entrypoint` | 利用者に示す実行入口 | 同名`pixel-cli`によるRust/Python混同を避ける |
| `global_options` | 共通オプションの列 | 省略・alias・値の個数を実定義と照合 |
| `commands[]` | 実装済みコマンド列 | `id`/`path`の一意性、全件・定義順を照合 |
| `effect` / `side_effects` | read/create/edit/export/interactiveと副作用 | force/discard等を安全な読取と誤認させない |
| `examples[].argv` | **文字列配列**による実行例 | Shell文字列を再parseせずゲームエンジンに渡せる |

`summary`はCLIの英語概要、`summary_ja`と`description_ja`は人間に向けた短い日本語説明とする。日本語説明が空のコマンドは生成失敗。`id`は`path`をドット結合した正規ID（Rust例`pixel.paint`、Python例`edit`）。個々の`path`はCLIへ渡すコマンド語そのものとし、日本語に翻訳しない。

オプションの`min_values/max_values`は値の個数。`max_values: null`は不定長（Python argparseの`nargs="+"`等）を示す。`min_values <= max_values`（null以外）、`metavars`の整合性、短いaliasの衝突、`default`と`choices`の整合、コマンドIDの重複など、JSON Schemaでは表しにくい関係は別途semantic validatorで拒否する。

### 具体例（案。現行ランタイムの出力ではない）

```json
{
  "schema_version": 1,
  "cli_implementation": "rust",
  "cli_version": "0.1.0",
  "entrypoint": "pixel-cli",
  "global_options": [],
  "commands": [
    {
      "id": "pixel.paint",
      "path": ["pixel", "paint"],
      "usage": "pixel paint <x> <y> <color> [--child CX CY] [--discard-detail]",
      "summary": "paint a cell of the selected layer",
      "summary_ja": "選択中レイヤーのセルを塗る",
      "effect": "edit",
      "requires_project": true,
      "positionals": [
        {"name": "x", "kind": "integer", "description_ja": "左から0始まりの列"},
        {"name": "y", "kind": "integer", "description_ja": "上から0始まりの行"},
        {"name": "color", "kind": "color", "description_ja": "RGBA色"}
      ],
      "options": [
        {"name": "--child", "aliases": [], "kind": "integer", "min_values": 2, "max_values": 2, "required": false, "description_ja": "分割した2×2内の子セル"},
        {"name": "--discard-detail", "aliases": [], "kind": "boolean", "min_values": 0, "max_values": 0, "required": false, "description_ja": "対象の保持細部を破棄する"}
      ],
      "side_effects": ["writes_project", "discards_detail"],
      "examples": [
        {"argv": ["pixel-cli", "--json", "-p", "art.json", "pixel", "paint", "3", "4", "#FF8800"], "description_ja": "セルを橙色に塗る"}
      ]
    }
  ]
}
```

これはスキーマ形状を示す**部分的なサンプル**であり、実際の22コマンドを収録した完全カタログではない。`side_effects`はそのコマンドが取り得るリスクの**上限**を示し、オプション無しの呼び出しが必ず細部を捨てるという意味ではない。実行時の変更有無は別の結果JSONで判定する。

## 9. カタログ取得時のCLI挙動と競合優先順位

Rustの追加予定入口は`pixel-cli --commands-json`。GUI、作品ファイル、ネット接続は不要。成功時`stdout`には**JSON値一個とLF**だけ、`stderr`は空、exit 0。`--json`を同時指定しても同一のJSON一個だけを返す。

- `--commands-json`と編集サブコマンドを同時指定した場合は**usage（exit 2）**。表示だけ要求して編集部分を黙って無視しない。
- `--commands-json`と`--project`、`--dry-run`、`--help`、`--version`の併用はusage（exit 2）で拒否する。利用者が意図せず引数を捨てたまま成功することを防ぐ。
- 現行`runner::show_help`は不明なコマンドに対して全体ヘルプへ戻る場合がある。追加実装時は、`pixel-cli wrong --help`を成功した既知コマンドと誤認させないよう、**usageで失敗**させる方針を採用する。
- `--help`と個別`--help`は人間向けのテキスト出力を維持し、機械可読出力は`--commands-json`だけに固定。`--help`にJSON断片や警告ログを混ぜない。
- Python版`argparse`からも同等の読取専用取得経路を用意するが、Rustのサブコマンド名・引数構造を流用せず、`new/edit/inspect/export/palette`の本当の動作とオプションを列挙する。`palette`はinteractiveとして別扱い。
- 現行v1で非対応のrevision検出/バッチやGUIの未対応機能は掲載しない。新機能が実装・検証されて初めて生成結果へ現れる。

## 10. ソース定義の一元性と生成器

Rustでは`CommandSpec`/`FlagSpec`/`COMMANDS`を唯一の定義にし、カタログとヘルプが**同じコマンドの集合・alias・値の個数**を返す。日本語の説明・使用例・リスク表示はコマンドIDに付属する補助メタデータとして隣接させる。IDだけ存在し説明が欠けた場合も、説明だけ残って実コマンドがない場合も検査失敗。

Pythonでは`build_parser()`の`argparse.Action`を正本にし、`nargs`、`choices`、`required`、オプションのaliasを抽出する。`argparse`にないコマンドを別のテキスト表に手書きで追加しない。Python3.10でも動作させるため標準`tomllib`（3.11以降）だけに依存する生成器にはしない。インストール済みpackageのmetadataとビルドmetadataを照合して版を決定する。

MarkdownはカタログJSONを入力とする**純粋なレンダラ**で生成する。構成は「用途別の一覧表 → 個別コマンド → 位置引数とフラグ → 副作用・破棄注意 → 引数配列からShell別に整形した例」。パイプ、角括弧、改行、バッククォート等をエスケープし、表のセルを壊さない。同じカタログを二度変換した結果はバイト単位で一致させ、生成時刻・開発者PCの絶対パスを含めない。

## 11. Python・Windows・Rustでの同梱位置と順序

| 対象 | 内容の配置（案） | 検証入口 |
| --- | --- | --- |
| 現行Windows Python GUI/CLI ZIP | `docs/cli/python/COMMANDS.md`、`docs/cli/python/commands.json`、GUIの最短ガイド | ZIPを別フォルダに展開し`DotEditorCLI.exe --help`と比較 |
| Python wheel | 追加する`hyper_dot_editor_help`リソースパッケージ内 | clean venvへwheel installし`importlib.resources`で取得 |
| Python sdist | 同じリソースと再生成に必要なコード | sdistを展開→隔離環境でwheel再build→資料とhelp照合 |
| 将来Rust 3OS CLIアーカイブ (#38) | `docs/cli/rust/COMMANDS.md`、`docs/cli/rust/commands.json` | **同梱のrelease binary**の`--commands-json`と比較 |

`hyper_dot_editor_help`は新規実装するパッケージ名の**設計案**で、現状の`pyproject.toml`（`py-modules`）にはまだ存在しない。wheel/sdistへ入れるにはpackages/package-data/ビルドhookを更新する。配布物の外にあるsource文書だけを見て「同梱済み」と判定してはいけない。

実際の流れは「ソースと依存を確定 → Rust release CLI/Pythonパーサーから生成 → 一時ステージへ保存 → コマンド集合・説明・版の比較 → 各成果物に同梱 → **最終アーカイブを展開** → 同梱CLIと照合 → SHA-256・署名/attestation → 公開gate」。署名後にファイルを差し込まない。

既存のWindows ZIPにはPython版CLIが入っており、Rust版コマンドを表示させない。`dist`の最終成果物一覧は現行の`artifact_checksums.py`が固定で検査するので、資料を`dist`直下の**新しい未署名成果物**として増やさず、配布ZIP/wheel/sdistの**内部**へ格納する。#55の未署名物アップロード停止は維持する。

## 12. E2E受け入れマトリクス（#66）

| ケース | 検査 | fail-closed条件 |
| --- | --- | --- |
| CAT-01 | Rust real binaryで`--commands-json`、作品なし/任意cwd | JSON以外のstdout、stderr、非0終了 |
| CAT-02 | Rust現行22件、Pythonの全`argparse`コマンド | helpとカタログでID/alias/引数個数に差 |
| CAT-03 | `--commands-json`＋未知コマンド/`--project` | usageにならない、作品/一時ファイルを変更 |
| CAT-04 | 同じ入力から2回生成 | Markdown/JSONのbyte差 |
| CAT-05 | 日本語・空白・`#`・Windowsパスのargv例 | Shell表示の引用ミス、機械実行時の引数差 |
| CAT-06 | 説明に`|`/改行/Markdown記号がある | 表が壊れる、特殊文字が未処理 |
| CAT-07 | Python ZIPにRust版表を混入させる | 実装種別/版不一致でもパス |
| CAT-08 | ZIP/wheel/sdist内の表を欠落・旧版化 | 元sourceだけ見て誤って成功 |
| CAT-09 | Python 3.10～3.14のwheelとsdist再build | `importlib.resources`で取得不可/版不一致 |
| CAT-10 | Rust Windows/Linux/macOS配布（#38時） | 配布バイナリ自身とのcatalog不一致 |
| CAT-11 | 未実装の#63/#64を説明表に追加 | 実コマンドの不存在を検出できない |
| CAT-12 | schema major変更/未知キー/空説明/重複alias | validatorで拒否できない |
| CAT-13 | 生成表を含む最終アーカイブの署名欠如 | #55の公開gateを通してしまう |

**完了判定**はGitHub CIで実成果物の展開・照合まで実行すること。資料自体の仕様書作成やテスト対象バイナリのhelp成功だけでは#66をcloseしない。
