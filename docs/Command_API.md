# 共通 Command API

`PixelCommandAPI` は GUI / CUI / Automation / AI / ゲーム開発者ツールが共有する操作面です。作品データを複製して保持せず、`PixelCanvas` または `LayeredPixelCanvas` に対して同じ検証と操作を適用します。

## Pythonから使う

```python
from pixel_commands import PixelCommandAPI

commands = PixelCommandAPI.new(16, 16, layered=True)
commands.paint(4, 3, (255, 0, 0, 255))
commands.split(4, 3)
commands.paint(4, 3, (0, 0, 255, 255), child=(1, 0))
commands.collapse(4, 3)

commands.set_resolution(7, 7)
commands.set_resolution(23, 17)
state = commands.inspect()

commands.discard_detail(2, 2, 1, 1)
commands.save("art.json")
commands.export_png("art.png", output_resolution=(256, 256))
```

既存プロジェクトは `PixelCommandAPI.load("art.json")` で読み込めます。`commands.canvas` は共有バックエンドそのもので、別のGUI専用/CUI専用コピーではありません。

## Automation向け execute

文字列コマンドから呼ぶ必要があるツールは `execute()` を使えます。

```python
commands.execute("paint", x=4, y=3, color=(255, 0, 0, 255))
commands.execute("set_resolution", width=23, height=17)
pixel = commands.execute("sample", x=4, y=3)
```

未知のコマンド、範囲外座標、不正領域、不正レイヤーなどは例外になります。対話入力は行いません。

## 公開操作

| Command API | CUI | GUI |
| --- | --- | --- |
| `set_resolution` / `upscale` | `--resolution` / `--upscale` | 論理解像度変更 / 解像度アップ |
| `split` / `split_region` | `--split` / `--split-region` | 選択セルを4分割 |
| `collapse` | `--collapse` | 選択セルを折りたたむ |
| `paint` | `--paint` / `--paint-child` | ブラシ |
| `erase` | `--erase` / `--erase-child` | 消しゴム |
| `fill` | `--fill` | 塗りつぶし |
| `sample` | `inspect --sample` | スポイト |
| `discard_detail` | `--discard-detail` | 選択セルの細部を破棄 |
| `add_layer` / `select_layer` / `remove_layer` | 各layerオプション | レイヤー操作 |
| `inspect` / `inspect_sample` | `inspect` | 状態表示に利用可能 |
| `save` / `load` | project入出力 | プロジェクト保存/読込 |
| `export_png` | `export` | PNG保存 |
| `import_image` | `--import-image` | 画像読込 |

GUIにだけ存在する編集データはありません。表示サイズ、ズーム、パン、ファイル選択ダイアログ、ツール選択などの表示/UI状態だけをGUI側で管理します。

## 詳細ポリシー

親セル編集・解像度変更・折りたたみでは `detail_policy="preserve"` が既定です。`"discard"` を指定すると対象の下位詳細を明示的に統合します。子セルのpaint/eraseは指定した子だけを変更し、親色を変更しません。

消しゴムはGUI/CUI/APIの全経路でRGBAの透明色への編集です。

## ファイルI/O

`load_project()` / `save_project()` はCommand APIとCLI/GUIが共有します。JSON保存は同じディレクトリの一時ファイルを完成させてから置換します。PNG exportも `export_png()` へ統一されています。

## 回帰検証

```bash
python test_commands.py
```

主な検証内容:

- API直呼びとバックエンド直呼びの結果一致。
- GUIの主要編集ハンドラーが `PixelCommandAPI` を経由すること。
- CLIアダプタが同じAPIを呼ぶこと。
- 16x16で細部作成 → 7x7 → 23x17 → 7x7 → 局所破棄 → 16x16 → 保存/再読込 → PNG export の非対話CUIシナリオ。
- レイヤー選択sampleが保存済みactive layerを変更しないこと。
- 領域分割が非正方形解像度と分割数上限を編集前に検証すること。

CIではPython 3.10 / 3.11 / 3.12 / 3.13 / 3.14の全環境で実行します。

## Layer order

Layer order is also available through the shared API. The last layer in the project list is topmost:

    commands.move_layer("up")
    commands.move_layer("down", name="背景")

The name is optional and defaults to the active layer. A move past either end returns false without changing the project. Successful moves are part of document undo/redo.
