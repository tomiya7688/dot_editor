# Rust CLI 別名・SKILL.md・リリースバイナリE2Eの詳細設計

対象: [Issue #32](https://github.com/tomiya7688/dot_editor/issues/32)（別名とSKILL.md）、[Issue #33](https://github.com/tomiya7688/dot_editor/issues/33)（リリースバイナリのE2E）。現行の外部契約は[CLI契約](../CLI契約.md)が正本で、本書はそれを変更しません。状態: 実装と同時に確定した設計です。

## 背景と目的

ゲームエンジンやAIエージェントは、`pixel-cli`の実体を探して起動する必要があります。CLI-Anything系の道具は`cli-anything-<名前>`という名前と、同梱の`SKILL.md`で操作方法を見つけます。また、配布物が実際に動くことは、関数の単体テストではなく、利用者と同じ「別プロセスの起動」で確かめる必要があります。

目的は次の3つです。

1. `cli-anything-dot-editor`という名前でも、`pixel-cli`と同じ動作に到達できること。
2. `SKILL.md`だけを読んだエージェントが、主要な編集を組み立てられること。
3. ビルドしたリリースバイナリを、Pythonの実装に頼らず別プロセスで通しで検証し、同じ検証を#38の配布物へ再利用できること。

## 利用者から見た入口

```bash
pixel-cli --json -p art.json status
cli-anything-dot-editor --json -p art.json status      # 同じ結果
```

- 利用者の直接操作は、コマンド名を選んで起動することだけです。2つの名前で、引数・標準出力・標準エラー・終了値は同一です。
- エージェントは`skills/cli-anything-dot-editor/SKILL.md`を読み、そこに書かれたコマンドだけで新規作成・編集・書き出しを行います。
- E2Eは開発者とCIが`python scripts/e2e_rust_cli.py <実行ファイルのフォルダ>`で実行します。

## 別名の設計（#32）

| 項目 | 決定 | 理由 |
| --- | --- | --- |
| 実装 | 実行処理を`hyper_dot_cli`ライブラリに置き、2つの実行ファイルは1行の入口だけを持つ | 起動用のラッパーやスクリプトを避け、同じRustコードに到達させる。Python不要 |
| 配布 | 同じ内容の実行ファイルを2つの名前で置く | シンボリックリンクはWindowsなど環境で使えないことがある。複製のほうが全OSで同じ配布手順になる |
| 表示名 | ヘルプとバージョンの文言は、どちらの名前でも`pixel-cli`のまま | 出力が名前によって変わらないので、呼び出し側が名前を意識しなくてよい |
| GUI | `dot-editor`（Pythonの入口）とは別物として保つ | 混同を避ける |

失敗時の扱い: 2つの名前の出力が食い違った場合は、E2Eが失敗します（下記）。

## SKILL.mdの設計（#32）

配置は`skills/cli-anything-dot-editor/SKILL.md`です。先頭に`name`と`description`のフロントマターを置き、本文は次の順に自己完結で書きます。

1. 何ができるか（ゲームのドット絵を、画面を使わずに作る・直す・書き出す）。
2. 入手と配置（`cargo build --release`の成果物、または配布物。2つの名前）。
3. 共通の約束（`-p`、`--json`、`--dry-run`、標準出力と標準エラー、終了値0/1/2、`error`の種別名）。
4. コマンド表（プロジェクト・キャンバス・画素・細部・レイヤー・書き出し・状態）。
5. 作品の考え方（任意解像度、細部の保持と破棄、レイヤー、レイヤー付きversion 2）。
6. 手順の例（新規作成→塗る→分割→解像度変更→確認→書き出し）、`jq`の例、ゲームエンジンからのsubprocess利用の例。
7. 制約（履歴はプロセスをまたがない、同時編集の保護は#63、バッチは#64）。
8. Python版は参照実装であり、正式な入口ではないこと。

SKILL.mdが実装とずれないよう、E2Eが`--help`に出るすべてのコマンドの語がSKILL.mdに書かれていることを検査します。コマンド表を自動生成して同梱する仕組みは[#66](command-reference-delivery.md)で扱い、本書はそれを置き換えません。

## READMEへの追加（#32）

利用者向けの説明だけを追加します。担当者向けの手順は入れません。

- シェル中心であること、Rust版が正本でPython版は参照実装であること。
- `--json`の標準出力の例、`jq`で値を取り出す例、別プロセスから使う例。

## E2Eの設計（#33）

### 検証の入口と隔離

`scripts/e2e_rust_cli.py <フォルダ>`は、指定フォルダの`pixel-cli`と`cli-anything-dot-editor`（Windowsでは`.exe`付き）を対象にします。Python標準ライブラリだけを使い、リポジトリのPythonコードを読み込みません。

- 作業は新しい一時フォルダで行い、リポジトリのフォルダに依存しません。
- 子プロセスの環境変数は最小限にし（PATHと、Windowsで必要なシステム変数のみ）、Pythonの環境に依存しないことを確かめます。
- 標準入力は閉じます。コマンドは何も待たない契約です。
- すべての呼び出しで、終了値、標準出力をJSONとして解析できること、標準エラーの内容を確認します。

### 通しの手順（すべて別プロセス）

| 順 | 操作 | 確認すること |
| --- | --- | --- |
| 1 | `--help`、`--version`（両方の名前） | 終了値0。2つの名前の出力が同一 |
| 2 | `project new --size 4` | 作成され、`status`に4x4が出る |
| 3 | `pixel paint 1 1 #FF0000` | 保存され、別プロセスの`pixel sample`で読める |
| 4 | `detail split 1 1` | `detail info`が分割済みを示す |
| 5 | `canvas resolution set 2 2`（保持） | `export render --resolution 4 4`で、塗った細部が復元される |
| 6 | `detail discard 0 0` | 表示色が保たれ、細部が破棄される（4x4の描画が一様な色になる） |
| 7 | `canvas resolution set 4 4` | 解像度が戻る |
| 8 | `layer add`、レイヤー上で`pixel paint`、`layer list` | 層が2枚で、選択が保たれる |
| 9 | プロセス終了後に`status`で再読み込み | 内容が保存されている |
| 10 | `export render -o out.png`（自然・`--size`・`--resolution`） | PNGを検証する |
| 11 | `--dry-run`の前後でプロジェクトのSHA-256 | 変わらない |
| 12 | 失敗系: 範囲外の座標、存在しないファイル | 終了値1、`error`の種別名、プロジェクトが不変 |
| 13 | 使い方の誤り | 終了値2 |
| 14 | 同じ手順を`cli-anything-dot-editor`でも実行 | 結果が`pixel-cli`と同一 |

### PNGの検証

成功コードだけで合格にしません。PNGの署名、各チャンクのCRC、IHDR（幅・高さ・8bit RGBA）、データの伸長とフィルタ0の走査線を、標準ライブラリ（`zlib`）で検査します。代表画素の値と、透明画素のアルファが0であることを確認します。

### #38への再利用

E2Eは「実行ファイルのフォルダ」だけを引数に取るため、#38が展開した配布物のフォルダにそのまま適用できます。OSごとの違いは実行ファイルの拡張子だけで、検査の内容は変わりません。

## CIへの組み込み

`Rust Core`ジョブがリリースビルドを作った後に、`python scripts/e2e_rust_cli.py rust/target/release`を実行します。失敗は他の検査と同様にマージを止めます。

## 失敗時の扱いと受け入れ条件

- どれか1つの確認が失敗したら、どの手順で何が食い違ったかを表示して非0で終了します。
- 受け入れ条件: (1) `cargo build --release`で2つの実行ファイルができる、(2) 2つの名前の出力が同一、(3) SKILL.mdが存在し、`--help`の全コマンドを含む、(4) E2Eが通る、(5) Python版の実装に依存しない。

## 対象外

配布アーカイブの作成・署名（[#38](https://github.com/tomiya7688/dot_editor/issues/38)、[#55](https://github.com/tomiya7688/dot_editor/issues/55)）、同時編集の保護（[#63](https://github.com/tomiya7688/dot_editor/issues/63)）、バッチ（[#64](https://github.com/tomiya7688/dot_editor/issues/64)）、コマンド表の自動生成（[#66](https://github.com/tomiya7688/dot_editor/issues/66)）。
