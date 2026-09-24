# CUIの細部操作と読み取り専用検査

GUIとCUIは `PixelCanvas` / `LayeredPixelCanvas` の同じ編集APIを呼びます。任意の縦横解像度、細部保持・破棄、version 2の保持JSONを扱います。旧JSONも読み込めます。詳細なデータモデルと互換性は[非破壊解像度の仕様](Non_destructive_resolution.md)を参照してください。

## 保持・折りたたみ・再展開

```bash
python pixel_cli.py new --size 16 --layered --output art.json
python pixel_cli.py edit --project art.json --paint 4 3 "#FF0000"
python pixel_cli.py edit --project art.json --split 4 3
python pixel_cli.py edit --project art.json --paint-child 4 3 1 0 "#0000FF"
python pixel_cli.py edit --project art.json --collapse 4 3
python pixel_cli.py inspect --project art.json --sample 4 3 --child 1 0
python pixel_cli.py edit --project art.json --split 4 3
python pixel_cli.py export --project art.json --output art.png --size 256
```

`--collapse X Y` は親セル表示へ戻しますが、既定では子セルを削除しません。JSON保存・再読込を挟んでも `--split X Y` で子セルを復元します。子セル座標は各軸0または1です。

明示的な分割セルの親色と子色は独立しています。`preserve` で親を緑に変えても、保持している青い子セルは青のままです。子セルを直接描くか、`discard` で新しい親色に統合するかを選べます。

## 任意解像度

```bash
python pixel_cli.py new --resolution 23 17 --output rectangular.json
python pixel_cli.py edit --project art.json --resolution 7 7
python pixel_cli.py edit --project art.json --resolution 23 17
python pixel_cli.py edit --project art.json --resolution 16 16
```

`new --size N` は正方形の任意解像度、`new --resolution W H` は縦横別です。両方の指定はエラーです。`edit --resolution W H` は、レイヤー間の整合性を維持して全体の編集グリッドを変更します。既定は非破壊。無編集で戻したとき、保持していた細部と局所分割状態が復元します。`--upscale` は縦横各2倍で、同じ保持APIを使用します。`--resolution` と `--upscale` の同時指定はエラーです。

## 明示的な破棄

```bash
python pixel_cli.py edit --project art.json --paint 4 3 "#00FF00" --detail-policy preserve
python pixel_cli.py edit --project art.json --paint 4 3 "#00FF00" --detail-policy discard
python pixel_cli.py edit --project art.json --collapse 4 3 --detail-policy discard
python pixel_cli.py edit --project art.json --discard-detail 4 3
python pixel_cli.py edit --project art.json --discard-detail 2 2 4 3
```

`--detail-policy` は解像度変更、描画、消去、塗りつぶし、折りたたみに適用し、既定値は `preserve` です。通常の粗いセルのpreserve編集は、細部の元データを残してRGBAの色差を対象領域へ重ねます。`discard` は対象領域を粗いセル値で置換します。

`--discard-detail X Y` は1セル、`--discard-detail X Y WIDTH HEIGHT` は矩形領域だけを対象にします。各セルの現在の代表色を維持し、対象外の描画情報を残します。レイヤー付きプロジェクトでは選択中レイヤーだけが対象です。同じ色へのfillでもdiscard指定は有効です。

解像度変更に `--detail-policy discard` を指定すると**全レイヤー・全体**が対象です。解像度だけ変えて一部分の細部だけを破棄する場合は、preserveでの解像度変更と局所discardを別の呼び出しにしてください。

破棄操作はバックエンドのUndo/Redo対象ですが、操作スタックをJSONへ保存しないため、非対話CUIの別プロセス間でのUndoは提供していません。変更前を残す場合は `--output edited.json` で別ファイルへ保存してください。

## 領域分割

```bash
python pixel_cli.py edit --project art.json --split-region 0 0 3 2
```

3x2個の親セルをそれぞれ2x2に分割します。保持済みの情報を利用し、細部がなければ親の色を継承します。領域はキャンバス内に完全に収まる必要があり、はみ出しを暗黙に切り詰めません。

## inspectとPNG

```bash
python pixel_cli.py inspect --project art.json
python pixel_cli.py inspect --project art.json --sample 4 3
python pixel_cli.py inspect --project art.json --sample 4 3 --child 1 0 --layer "背景"
python pixel_cli.py export --project art.json --output view.png --size 256
python pixel_cli.py export --project art.json --output detail.png --resolution 23 17
```

inspectは標準出力へ1つのJSONを出力します。入力ファイルと選択レイヤーは変更せず、対話入力もGUI起動も要求しません。日本語名はASCIIエスケープして出力します。

| フィールド | 意味 |
| --- | --- |
| `schema_version` | 検査結果の形式。1。保存形式versionとは別 |
| `project_type` | `flat` / `layered` |
| `resolution` | 現在の `[width, height]` |
| `native_resolution` | 現在の展開状態を含む表示画像サイズ |
| `retained_resolution` | 保持パッチの細かさを縦横別に示す値 |
| `active_layer` | 保存済み選択レイヤー。flatならnull |
| `has_detail` / `has_refinements` | 保持情報があるか / 現在グリッドで展開セルがあるか |
| `layers` | レイヤー順の一覧。現在グリッドの局所分割数、座標、展開状態、保持パッチ数 |
| `sample` | 指定時に追加。座標、子座標、レイヤー名、`rgba` |

局所分割数は現在のグリッド上の明示的な分割メタデータの数であり、保持用ラスターパッチの数とは異なります。全体解像度の切替で細部を保持していても局所分割数が0の場合があります。

サンプルは合成画像ではなく指定レイヤーのデータです。`--layer` 省略時はアクティブレイヤー。`--child` / `--layer` の単独指定はエラーです。

`export --size N` は従来どおり現在の表示をN×Nへ拡大します。Nは表示のnativeサイズ以上が必要です。`export --resolution W H` は、保持データから指定した大きさへ直接投影します。折りたたみ中の細部も保持データにある限り利用します。両方ともプロジェクト自体は変更しません。

## 操作順・終了コード・安全な保存

複数のオプションは記述順ではなく次の固定順で実行します。

```text
レイヤー追加 → 選択 → 削除 → resolution → import → split → split-region
→ paint → paint-child → fill → erase → erase-child
→ collapse → discard-detail → upscale
```

例えば同一呼び出しのsplitはpaintより先です。親をdiscardしてからchildを描こうとすると分割状態がないためエラーになります。別の順序が必要なら呼び出しを分けてください。

有効な変更なし操作も終了コード0です。変更なしで `--output` を省略した場合は再保存しません。`--output` 指定時はコピーを保存します。

不正座標・領域・JSON・色・レイヤー、操作なし、資源上限超過などは終了コード2で標準エラーへ理由を出します。途中の操作が失敗した場合は入力JSONも出力JSONも保存しません。保存時は同じディレクトリに一時ファイルを完全に書いてから置き換え、失敗による元JSONの切り詰めを防ぎます。

## 検証

```bash
python scripts/evaluate.py
python test_pixel_backend.py
python test_pixel_layers.py
python test_pixel_cli.py
python test_resolution.py
```

CIはPython 3.10 / 3.11 / 3.12 / 3.13 / 3.14で実行します。追加の解像度回帰は、非対話CUIだけの作成→低解像度→非正方形→局所破棄→復元→保存・再読込→PNG一致まで確認します。

## レイヤー順の変更

アクティブレイヤーを上下へ1段移動できます。合成ではリストの最後が最前面です。

    python pixel_cli.py edit --project art.json --select-layer "背景" --move-layer up
    python pixel_cli.py edit --project art.json --move-layer down

端を越える移動は変更なしになります。順序変更はプロジェクトJSONへ保存され、共有モデルのUndo/Redo対象です。

## レイヤー表示切替

アクティブレイヤーを表示・非表示にできます。非表示のレイヤーも編集可能で、合成画像とPNG書出しからだけ除外されます。旧プロジェクトで表示属性がないレイヤーは表示状態として読み込みます。

    python pixel_cli.py edit --project art.json --layer-visibility hide
    python pixel_cli.py edit --project art.json --layer-visibility show

inspectのlayers各要素にはvisibleが含まれます。表示状態の変更はプロジェクトに保存され、Undo/Redo対象です。

## レイヤー名称変更

アクティブレイヤーの名称を変更します。絵、表示状態、重ね順、選択状態は維持します。前後の空白は除去され、空名・重複名はエラー、同名への変更は無操作です。

    python pixel_cli.py edit --project art.json --rename-layer "登場人物"

名称変更はプロジェクトに保存され、Undo/Redo対象です。
