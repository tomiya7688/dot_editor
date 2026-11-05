# Rust CLI（`pixel-cli`）の契約

## 背景と目的

ゲームエンジン・開発ツール・AI自動化は、画面を使わずにドット絵の作品を作り、編集し、画像として書き出す必要があります。この文書は、Rust実装の`pixel-cli`が守る外部契約を定めます。Issue #31（契約）と #37（Rust実装）に対応します。Python版の`src/pixel_cli.py`は参照実装として残ります。コマンドの表面は一致させませんが、保存形式・操作の意味・シェル契約は互換にします。

## 実行方法

Rustのビルド成果物を実行してください。Pythonは不要です。

```bash
cargo build --release --manifest-path rust/Cargo.toml -p hyper-dot-cli
rust/target/release/pixel-cli --json -p art.json project new --size 16
rust/target/release/pixel-cli --json -p art.json pixel paint 3 4 "#FF8800"
rust/target/release/pixel-cli --json -p art.json export render -o art.png
```

1回の実行は1つの操作です。標準入力を読みません。どの作業フォルダからでも実行できます。コマンド名`cli-anything-dot-editor`の別名は #32 で追加します。

## 操作の発見性と同梱コマンド表

本製品は人間のGUI/端末操作に加え、ゲームエンジンやDot Editor AIなどがsubprocessから使うことを正式な利用形態とします。**人間が理解しやすい軽量GUI・明瞭なshellコマンド・個別ヘルプ・検索できるコマンド説明表**を提供する要件は[利用インターフェース仕様](ユーザー操作インターフェース仕様.md)に定めます。

**現在のRust CLI**は`--help`に全コマンドと共通オプション、`pixel-cli pixel paint --help`等に個別オプションの説明を表示します。実装・引数の正本は`command_table.rs`で、`help_text.rs`がそこから生成します。Python CLIは別の`argparse`文法を持つため、実行例と説明表でRust版と区別します。

**一部実装（[#66](https://github.com/tomiya7688/dot_editor/issues/66)）**：Rust CLIは`pixel-cli --commands-json`で、実行したCLI自身の全コマンド・引数・日本語説明・使用例をJSON（schema v1）で出します（他の引数とは併用できず、使用すると終了値2）。Python CLIは`python -m command_catalog`で、argparseの定義から同じ形式の表を出します。`python scripts/render_command_catalog.py <実行ファイル|python> --out <フォルダ>`が、そのJSONから`COMMANDS.md`と`commands.json`を決定的に生成します。同梱: Rustは配布アーカイブの`docs/cli/rust/`（#38）、Windows ZIPは`docs/cli/python/`、Python wheel・sdistはパッケージ`hyper_dot_editor_help`の中（`import hyper_dot_editor_help as h; h.read_text("COMMANDS.md")`）。CIは、ビルドの前に生成し、ビルド後にwheelとsdistを開いて今のソースから作り直した内容と一致するかを照合し（`scripts/verify_package_catalog.py`）、Windows ZIPは配布した`DotEditorCLI.exe`の`--help`と照合します。**未実装**: 署名・attestation後の最終配布物の照合（#55待ち）。

設計の生成/同梱経路は[コマンドカタログ設計](design/command-reference-delivery.md)に分割しています。操作表や将来の新オプションを、このv1の「実装済みコマンド」の一覧に先行記載しません。

## 共通オプション

| オプション | 意味 |
| --- | --- |
| `-p`, `--project PATH` | 対象のプロジェクトファイル。すべてのコマンドで必須です。 |
| `--json` | 標準出力を、1つのJSONだけにします。 |
| `--dry-run` | ファイルを保存・書き出さずに、結果だけを評価します。 |
| `--if-revision REV` | `status`の`result.revision`と同じ値のときだけ保存します。違えば`revision_conflict`で何も保存しません。 |
| `--lock-timeout-ms N` | 同じ作品のロックを待つ最長時間（0〜60000、既定5000ミリ秒）。超えると`project_busy`。 |
| `-h`, `--help` | ヘルプを表示します。`<コマンド> --help`でコマンドごとの説明を表示します。 |
| `-V`, `--version` | バージョンを表示します。 |

共通オプションはコマンドの前後どちらにも書けます。

## コマンド

| コマンド | 種類 | 内容 |
| --- | --- | --- |
| `project new (--size N \| --resolution W H) [--force]` | 作成 | 空のプロジェクトを作ります。既存ファイルは`--force`なしでは上書きしません。 |
| `project info` / `project validate` | 読み取り | 概要を表示します。`validate`は読み込みと検証が成功したことを示します。 |
| `canvas info` | 読み取り | 解像度・層数・選択中の層を表示します。 |
| `canvas resolution set W H [--discard-detail]` | 編集 | 全レイヤーの論理解像度を変えます。 |
| `pixel paint X Y COLOR [--child CX CY] [--discard-detail]` | 編集 | 親画素または子セルを塗ります。 |
| `pixel erase X Y [--child CX CY] [--discard-detail]` | 編集 | 透明にします。 |
| `pixel fill X Y COLOR [--discard-detail]` | 編集 | 同色の4近傍領域を塗りつぶします。 |
| `pixel sample X Y [--child CX CY]` | 読み取り | 色を読みます。 |
| `detail split X Y` / `detail split-region X Y W H` | 編集 | セルを4分割します。領域分割は1回の操作です。 |
| `detail discard X Y` | 編集 | 表示色を保ち、保持細部を破棄します。 |
| `detail info X Y` | 読み取り | 分割済みか、細部があるかを表示します。 |
| `layer add NAME` | 編集 | 最上層へ空の層を追加して選択します。 |
| `layer remove [--layer NAME]` | 編集 | 層を削除します。最後の1層は削除できません。 |
| `layer select NAME` | 編集 | 編集対象の層を選びます。 |
| `layer rename NEW [--layer NAME]` | 編集 | 層の名前を変えます。 |
| `layer move up\|down [--layer NAME]` | 編集 | 合成順を1段動かします。 |
| `layer visibility on\|off [--layer NAME]` | 編集 | 表示・非表示を切り替えます。 |
| `layer list` | 読み取り | 下層から順に層を表示します。 |
| `export render -o PATH [--size N \| --resolution W H]` | 書き出し | 表示中の層を合成してPNGに書き出します。 |
| `status` | 読み取り | 概要と層の一覧をまとめて表示します。 |

座標は0から始まる整数です。小数・負数・数字以外は使い方の誤りになります。色は`#RRGGBB`または`#RRGGBBAA`です。画素・細部の操作は、選択中の層だけに作用します。`--layer`を省略したときの対象も選択中の層です。

## 出力と終了値

成功した結果は標準出力、診断とエラーの説明は標準エラーへ出力します。`--json`のときの標準出力は、次のJSONだけです。

```json
{
  "status": "ok",
  "operation": "pixel.paint",
  "project": "art.json",
  "result": {"x": 3, "y": 4, "color": "#FF8800FF", "changed": true},
  "dry_run": false,
  "saved": true
}
```

失敗すると、`--json`の標準出力に次のJSONを出し、標準エラーにも説明を出します。

```json
{"status": "error", "operation": "pixel.paint", "error": "out_of_bounds", "message": "cell (5, 0) is outside the 2x2 canvas"}
```

| 終了値 | 意味 |
| --- | --- |
| 0 | 成功 |
| 1 | 実行時またはプロジェクトの失敗（範囲外・不正なファイル・予算超過など） |
| 2 | 使い方の誤り（未知のコマンド・引数の不足・数字以外・不正な色） |

`error`の種別名は変わりません。`usage`、`out_of_bounds`、`file_not_found`、`invalid_project`、`file_exists`、`invalid_resolution`、`invalid_region`、`invalid_child`、`cell_not_split`、`no_such_layer`、`duplicate_layer`、`invalid_layer_name`、`too_many_layers`、`last_layer`、`invalid_export_size`、`invalid_output`、`resource_limit`、`io_error`です。

## 保存形式と保存の安全性

- 保存形式は、レイヤー付きのversion 2です。単一キャンバスの文書（旧形式を含む）は、背景1層として読み込みます。編集して保存するとレイヤー付きになります。意味のある情報は失われず、Python版で開けます。
- 現行実装は、同じフォルダのPID由来一時ファイルへ書き、同期後に`rename`による置換を試みます。確定前の書込失敗では旧ファイルを維持する設計ですが、**同時更新の消失防止・複数OSの置換/耐久性・危険なパスの拒否を保証する仕様ではありません**。これらは[Issue #63](https://github.com/tomiya7688/dot_editor/issues/63)で扱います。
- 変更がない操作は、ファイルを書き換えません（結果の`saved`が`false`です）。
- 失敗した編集は何も保存しません。
- `--dry-run`は、新規作成・編集・書き出しのいずれでもファイルを作らず、変更もしません。結果の`result.changed`は、実行した場合に変わるかを示します。確認の質問はしません。
- 書き出し先がプロジェクトファイル自身なら拒否します。

## v1での決定事項

#31で実装前に決めるよう求められた項目の結論です。

| 項目 | 決定 |
| --- | --- |
| Undo/Redoと履歴 | v1では`session undo/redo/history`を**公開しません**。1回の実行は別のプロセスで、プロジェクトJSONは履歴を保存しないため、前回の操作を取り消せません。実態と矛盾するコマンドは出しません。履歴を扱う方法は、常駐プロセスまたは履歴の保存を設計する別Issueで決めます。 |
| 同時更新 | **協調するpixel-cli同士は保護されます（#63）**。変更コマンドは作品ごとのsidecarロック（`.<名前>.lock`）を取ってから読み込み、保存まで保持します。`--lock-timeout-ms`（0〜60000、既定5000）までに取れなければ`project_busy`。`status`と`project info`の`result.revision`（ファイルの生バイト列のSHA-256、`sha256:`+小文字16進64文字）を`--if-revision`で渡すと、違う場合は`revision_conflict`で何も保存しません。変更コマンドの成功結果にも、保存後の`revision`が入ります。ロックを使わない外部のプログラムが同時に書き換える場合の防止は保証しません。書き込み先がシンボリックリンク、通常でないもの、（Unixで）ハードリンクが複数あるファイルのときは、`unsafe_path`で拒否して何も書きません（PNGの書き出し先も同じ。Windowsのハードリンクは標準ライブラリで判定できず未対応）。残りの項目（`commit_uncertain`、親フォルダの同期などOS別の耐久性検証）は[保存安全性の詳細設計](design/cli-concurrency.md)に残っています。 |
| 一括編集 | **実装済み（#64）**。`batch apply --file operations.json`が、ファイルに書いた複数の編集（`pixel.paint`など13種）を順に同じ作品へ適用し、全件成功して変更があるときだけ1回保存します。1件でも失敗すると何も保存せず、`details.failed_index`（0始まり）と`details.op`を付けて失敗します。ファイルの不備は`invalid_batch`（終了値1）、`--file`の欠落は`usage`（終了値2）です。`--dry-run`は保存せず、`--if-revision`は全操作の前に照合します。入力は8MiBまで、操作は0〜10,000件、重複キー・未知のop・未知のフィールド・負数や小数の座標を拒否します。結果の`revision_before`と、保存した場合の`revision_after`を返します。詳しくは[バッチAPIの詳細設計](design/cli-batch.md)。 |
| dry-runと原子性 | 上記のとおり、dry-run前後でファイルのバイト列は変わりません。失敗時の副作用もありません。 |

## 期待される結果と確認方法

- 成功すると、標準出力に結果が出て、終了値が0になります。
- 失敗すると、終了値が1または2になり、プロジェクトは変わりません。
- 契約は`rust/crates/hyper-dot-cli/tests/cli_contract.rs`（実バイナリでの検証）と`scripts/test_rust_cli_compat.py`（Python版との相互確認）で固定します。どちらもCIで実行します。

## 次期拡張の契約案（この節は**未実装**）

以下は現行v1の「one-shot・非対話・JSON v2・終了値0/1/2」を壊さずに追加する計画です。現在の実行例やコマンド表へ、実装されていないコマンドを混在させません。

| 作業Issue | 追加予定の公開入口 | 保証の範囲 |
| --- | --- | --- |
| [#63 同時編集・保存安全性](https://github.com/tomiya7688/dot_editor/issues/63) | `status`の`result.revision`、変更コマンドの`--if-revision sha256:<64 hex>`、ロックタイムアウト | ロック下で再読込・照合して更新消失を防止。協調しない外部ライター、ネットワークFSの完全な排他は対象外 |
| [#64 原子的バッチ編集](https://github.com/tomiya7688/dot_editor/issues/64) | `batch apply --file operations.json`、`--dry-run`、`--if-revision` | 順序付きの編集操作群を一度だけ保存。途中失敗では確定前の作品を保存しない |

- **依存順は #63 → #64**。作成競合やPOSIX/Windowsでの原子的な確定・確定状態が不明な場合の扱いを先に検証します。
- #63の`revision_conflict`・`project_busy`と、#64の`invalid_batch`は実装済みです。`unsafe_path`の網羅と`commit_uncertain`は未実装で、追加する際は既存のerrorコード/終了値の意味を維持し、実バイナリE2Eで固定します。
- バッチは`1プロセス = 1トランザクション`であり、常駐daemon・永続Undoやstdinの暗黙待機を追加するものではありません。`operations.json`の`version`は作品JSONの`version: 2`とは別です。
- 詳細な契約案と受け入れ試験は[保存安全性](design/cli-concurrency.md)と[バッチAPI](design/cli-batch.md)で定義します。
