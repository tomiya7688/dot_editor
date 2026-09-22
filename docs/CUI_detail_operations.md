# CUIの細部操作と読み取り専用検査

Issue #4 のうち、PR #21で追加した細部保持モデルを非対話CUIへ公開する実装単位です。GUIとは別の描画モデルを作らず、`PixelCanvas` / `LayeredPixelCanvas` の同じAPIを呼びます。保存形式は既存のJSONを維持します。

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

`--collapse X Y` は親セル表示へ戻しますが、既定では子セルを削除しません。JSON保存・再読込を挟んでも `--split X Y` で子セルを復元します。折りたたみ中も `inspect --sample X Y --child CX CY` で保持中の色を確認できます。

親セルの色と子セルの色は別データです。`preserve` で親を緑に変えても、既に保持している青い子セルは青のままです。細部を含めて新しい親色から作り直す操作には `discard` を使います。子セル座標は各軸0または1です。

## 明示的な破棄

```bash
python pixel_cli.py edit --project art.json --paint 4 3 "#00FF00" --detail-policy preserve
python pixel_cli.py edit --project art.json --paint 4 3 "#00FF00" --detail-policy discard
python pixel_cli.py edit --project art.json --collapse 4 3 --detail-policy discard
python pixel_cli.py edit --project art.json --discard-detail 4 3
python pixel_cli.py edit --project art.json --discard-detail 2 2 4 3
```

`--detail-policy` は親セルの `--paint` / `--erase` / `--fill` と `--collapse` に適用します。既定値は `preserve`。`--paint-child` / `--erase-child` は指定した子セルだけを変更します。消しゴムは透明化です。

`--discard-detail X Y` は1セル、`--discard-detail X Y WIDTH HEIGHT` は矩形領域の子セル情報を破棄します。親セル色は変更せず、他の領域と他のレイヤーを保持します。レイヤー付きプロジェクトでは選択中レイヤーだけが対象です。同じ色への `--fill ... --detail-policy discard` でも対象領域の細部を破棄します。

破棄操作はバックエンドのUndo/Redo対象です。ただし、この非対話CLIではUndo履歴をJSONへ保存していないため、別プロセスにまたがるUndoは提供していません。変更前を残す場合は `--output edited.json` で別ファイルへ保存してください。

## 領域分割

```bash
python pixel_cli.py edit --project art.json --split-region 0 0 3 2
```

指定した3x2個の親セルを、それぞれ2x2に分割します。保持済みの細部があれば再展開し、なければ親セル色を継承します。領域はキャンバス内に完全に収まる必要があります。はみ出しを暗黙に切り詰めません。

## inspectの出力

```bash
python pixel_cli.py inspect --project art.json
python pixel_cli.py inspect --project art.json --sample 4 3
python pixel_cli.py inspect --project art.json --sample 4 3 --child 1 0 --layer "背景"
```

成功時は標準出力へ1つのJSONオブジェクトを出力します。入力ファイルと保存済みアクティブレイヤーは変更しません。GUIも対話入力も必要ありません。日本語名はASCIIエスケープして出力するため、非UTF-8端末からもJSONとして読み取れます。

| フィールド | 意味 |
| --- | --- |
| `schema_version` | 検査結果の形式。現在は1。プロジェクト形式のversionとは別 |
| `project_type` | `flat` または `layered` |
| `resolution` | 現在の論理解像度 `[width, height]` |
| `native_resolution` | 現在展開している細部を含めた画像サイズ |
| `active_layer` | 保存済み選択レイヤー。flatならnull |
| `has_detail` / `has_refinements` | 細部を保持中か / 展開中の細部があるか |
| `layers` | レイヤー順を保った一覧。保持セル数・展開セル数・折りたたみセル数・座標と展開状態 |
| `sample` | 指定時だけ追加。座標、子座標、レイヤー名、`rgba: [r, g, b, a]` |

サンプルは合成画像ではなく指定レイヤーのデータです。`--layer` を省略するとアクティブレイヤーを読みます。`--child` / `--layer` 単独はエラーです。

## 操作順と失敗時の扱い

既存CLIとの互換性のため、複数オプションは記述順ではなく次の固定順序で処理します。

```text
レイヤー追加 → 選択 → 削除 → 画像import → split → split-region
→ paint → paint-child → fill → erase → erase-child
→ collapse → discard-detail → upscale
```

例えば `--split ... --paint ...` の分割初期色は、同じ呼び出し内のpaintより前の親色です。別の順序が必要な場合は呼び出しを分けます。parent paintでdiscardした直後にchild paintすると子セルが存在しないためエラーになります。

有効な操作は変更がない場合も終了コード0です。分割済みセルの再分割や細部がないセルの破棄は安全に再実行できます。変更なしで `--output` を省略した場合はファイルを再保存しません。`--output` 指定時は変更がなくてもコピーを作ります。

操作なし、不正座標、不正領域、不正JSON、不正色、存在しないレイヤー等は終了コード2で標準エラーへ理由を出します。途中の操作が失敗した場合は入力JSONと出力JSONを保存しません。JSON保存は同じディレクトリの一時ファイルを書き終えてから置き換え、保存失敗による既存JSONの切り詰めを防ぎます。

## この実装単位に含まれないもの

任意解像度（7x7 / 23x17等）と非破壊の全体解像度切替はIssue #6の残作業です。現在の `new --size` は既存プリセットを使い、`--resolution` はまだ提供していません。既存の `--upscale` は最近傍リサイズであり、折りたたみ詳細を保持する操作ではありません。`--detail-policy` の適用対象にも含めません。

GUIの細部ポリシーUI、任意解像度を含む全Command API統一と総合回帰はIssue #4 / #6に残します。この実装単位だけでは両Issueを完了にしません。

## 検証

```bash
python scripts/evaluate.py
python test_pixel_backend.py
python test_pixel_layers.py
python test_pixel_cli.py
```

CIはPython 3.10 / 3.11 / 3.12 / 3.13 / 3.14の全ジョブで実行します。CUI回帰は実際に別プロセスを起動し、標準入力を閉じた状態で、保存・再読込・PNG一致・読取専用・失敗時の無変更・終了コードを検証します。
