---
name: cli-anything-dot-editor
description: Hyper Dot Editorのドット絵プロジェクトを、画面を使わずにシェルから作る・編集する・PNGへ書き出すためのコマンド（pixel-cli）。ゲームエンジンやAIエージェントが、別プロセスとして呼び出す用途に使う。任意解像度、細部の保持と破棄、レイヤー、JSON出力、dry-runに対応する。
---

# cli-anything-dot-editor（pixel-cli）の使い方

## できること

ドット絵の作品（プロジェクトファイル）を、1回の起動で1つの操作として、作る・変える・調べる・PNGに書き出します。画面は使いません。Pythonも要りません。

- 実行ファイルの名前は`pixel-cli`と`cli-anything-dot-editor`の2つで、動作はまったく同じです。
- 入手: リポジトリで`cargo build --release --manifest-path rust/Cargo.toml -p hyper-dot-cli`を実行すると、`rust/target/release/`に2つの実行ファイルができます。3つのOS向けの配布アーカイブへの同梱は、別のIssue（#38）で行います。
- GUIの`dot-editor`（Python）とは別物です。Python版は参照実装で、正式な入口ではありません。

## 共通の約束

| 項目 | 内容 |
| --- | --- |
| `-p`, `--project PATH` | 対象のプロジェクトファイル。すべてのコマンドで必須です。 |
| `--json` | 標準出力を、1つのJSONだけにします。 |
| `--dry-run` | ファイルを保存・書き出さずに、結果だけを評価します。 |
| 標準出力 / 標準エラー | 結果は標準出力、説明とエラーは標準エラーです。 |
| 終了値 | 0=成功、1=実行時やプロジェクトの失敗、2=使い方の誤り。 |

成功時のJSONは`{"status":"ok","operation":"pixel.paint","project":"art.json","result":{...},"dry_run":false,"saved":true}`です。失敗時は`{"status":"error","operation":"...","error":"out_of_bounds","message":"..."}`で、`error`の種別名は変わりません（`usage`、`out_of_bounds`、`file_not_found`、`invalid_project`、`file_exists`、`no_such_layer`、`duplicate_layer`、`last_layer`、`invalid_export_size`、`invalid_output`など）。

座標は0から始まる整数、色は`#RRGGBB`か`#RRGGBBAA`です。画素と細部の操作は、選択中のレイヤーだけに効きます。

## コマンド

| コマンド | 内容 |
| --- | --- |
| `project new --size N` または `project new --resolution W H` | 新しいプロジェクトを作る。既存ファイルは`--force`なしでは上書きしない。 |
| `project info` / `project validate` | 概要を見る / 正しく読めるか確かめる。 |
| `canvas info` | 解像度・層数・選択中の層。 |
| `canvas resolution set W H [--discard-detail]` | 全レイヤーの解像度を変える。細部は既定で保持される。 |
| `pixel paint X Y COLOR [--child CX CY] [--discard-detail]` | 塗る。`--child`は分割したセルの子セル（0か1）。 |
| `pixel erase X Y [--child CX CY]` | 透明にする。 |
| `pixel fill X Y COLOR` | 同じ色でつながった範囲を塗りつぶす。 |
| `pixel sample X Y [--child CX CY]` | 色を読む。 |
| `detail split X Y` / `detail split-region X Y W H` | セルを4つに分割する（領域は1回の操作）。 |
| `detail discard X Y` | 見た目の色を保ったまま、保持している細部を捨てる。 |
| `detail info X Y` | 分割済みか、細部があるかを調べる。 |
| `layer add NAME` | 最上層に空の層を足して選ぶ。 |
| `layer remove [--layer NAME]` | 層を消す（最後の1枚は消せない）。 |
| `layer select NAME` | 編集する層を選ぶ。 |
| `layer rename NEW [--layer NAME]` | 名前を変える。 |
| `layer move up\|down [--layer NAME]` | 重なり順を1つ動かす。 |
| `layer visibility on\|off [--layer NAME]` | 表示・非表示。 |
| `layer list` | 下の層から順に一覧する。 |
| `export render -o PATH [--size N \| --resolution W H]` | 見えている層を重ねてPNGにする。 |
| `status` | 解像度・選択中の層・層の一覧をまとめて見る。 |

## 作品の考え方

- **任意解像度**: 解像度を変えても、描いた細部は失われません。`canvas resolution set`で下げた後に`export render --resolution W H`で細かい解像度の絵を書き出すと、細部が戻ります。細部を捨てたいときだけ`--discard-detail`や`detail discard`を使います。
- **レイヤー**: 下から順に重なり、保存形式はレイヤー付きのJSON（version 2）です。旧形式の1枚だけの作品は、背景1枚として読み込まれます。
- **変更がなければ保存しない**: 何も変わらない操作はファイルを書き換えません（結果の`saved`がfalse）。失敗した操作は何も保存しません。

## 手順の例

```bash
pixel-cli --json -p art.json project new --size 16
pixel-cli --json -p art.json pixel paint 3 4 "#FF8800"
pixel-cli --json -p art.json detail split 3 4
pixel-cli --json -p art.json pixel paint 3 4 "#0000FF" --child 1 0
pixel-cli --json -p art.json layer add 影
pixel-cli --json -p art.json export render -o art.png --size 64
pixel-cli --json -p art.json status | jq '.result.layers[].name'
```

実行前に確かめたいときは`--dry-run`を付けます。付けても、プロジェクトのバイト列は変わりません。

## ゲームエンジンやスクリプトから使う

実行ファイルを別プロセスとして起動し、標準出力のJSONと終了値だけで判断します。

```python
import json, subprocess
run = subprocess.run(["pixel-cli", "--json", "-p", "art.json", "status"],
                     capture_output=True, text=True)
if run.returncode == 0:
    resolution = json.loads(run.stdout)["result"]["resolution"]
else:
    error = json.loads(run.stdout)["error"]   # 説明文は run.stderr にも出る
```

## 制約

- 1回の起動が1つの操作です。操作の履歴（元に戻す）はプロセスをまたぎません。
- 複数のプロセスが同じファイルを同時に編集した場合の保護は、まだありません。順番に実行してください。
- 多数の画素をまとめて1回で編集する機能は、まだありません。
