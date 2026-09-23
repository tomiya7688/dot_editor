# Hyper Dot Editor

Hyper Dot Editor は、GUI と CLI から同じバックエンドを使ってドット絵を編集できるピクセルアートエディタです。バックエンドは複数のゲーム向け開発者ツールから共通利用できることを前提にし、レイヤー、セル分割、任意解像度の非破壊切替、JSONプロジェクト保存、PNG書き出しを扱います。

## 必要環境

- Python 3.10〜3.14（CIで全バージョンを必須検証）
- Pillow（`requirements.txt` で管理）
- GUIとGUI関連テストにはTkinter。バックエンドとCLIだけの利用にはGUI起動は不要です。

## セットアップ

### Windows (PowerShell)

リポジトリ直下で次を実行します。

```powershell
powershell -ExecutionPolicy Bypass -File scripts/setup_environment.ps1
```

`.venv` を作成し、依存関係をインストールしてから評価を実行します。個人PC固有のPythonパスは不要です。依存関係のインストールを省く場合は `-SkipInstall` を付けてください。

### macOS / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Windowsで手動セットアップする場合は、仮想環境の有効化を `.venv\Scripts\Activate.ps1` に読み替えてください。

## GUIを起動する

```bash
python dot_editor.py
```

ブラシ、消しゴム、スポイト、塗りつぶし、レイヤー、セル分割、折りたたみ、細部破棄、任意の縦横解像度、表示サイズ、JSON保存/読込、PNG保存を利用できます。描画・解像度変更時の細部ポリシーは「保持」が既定です。操作が画面に収まらない場合は右サイドバーをスクロールしてください。

## Python Command API

ゲーム開発者ツール、Automation、AIなどから直接利用する場合は `PixelCommandAPI` を使います。GUIとCLIも同じCommand APIを経由します。

```python
from pixel_commands import PixelCommandAPI

commands = PixelCommandAPI.new(16, layered=True)
commands.paint(4, 3, (255, 0, 0, 255))
commands.set_resolution(23, 17)
commands.save("project.json")
commands.export_png("pixel_art.png", output_resolution=(256, 256))
```

文字列ベースの呼び出しには `commands.execute("paint", ...)` も利用できます。詳細は [共通Command API](docs/Command_API.md) を参照してください。

## CLIを使う

### 新規プロジェクトと基本編集

```bash
python pixel_cli.py new --size 16 --layered --output project.json
python pixel_cli.py edit --project project.json --paint 1 1 "#FF0000"
python pixel_cli.py edit --project project.json --add-layer "人物"
python pixel_cli.py edit --project project.json --select-layer "人物" --paint 2 2 "#00AAFF"
```

`--size` は任意の正の整数で正方形を作ります。`--layered` を省くと単一レイヤーのプロジェクトになります。非正方形は次のように指定します。

```bash
python pixel_cli.py new --resolution 23 17 --output rectangular.json
```

### 非破壊の解像度切替

```bash
python pixel_cli.py edit --project project.json --resolution 7 7
python pixel_cli.py edit --project project.json --resolution 23 17
python pixel_cli.py edit --project project.json --resolution 16 16
python pixel_cli.py inspect --project project.json
```

解像度を変えただけでは細部を破棄しません。無編集の往復では元の情報が復元します。`--detail-policy discard` を解像度変更と組み合わせた場合だけ、全体を新しい粗さへ統合します。

### セル分割と保持・破棄

```bash
python pixel_cli.py edit --project project.json --split 1 1
python pixel_cli.py edit --project project.json --paint-child 1 1 1 0 "#0000FF"
python pixel_cli.py edit --project project.json --collapse 1 1
python pixel_cli.py inspect --project project.json --sample 1 1 --child 1 0
python pixel_cli.py edit --project project.json --split 1 1
python pixel_cli.py edit --project project.json --erase-child 1 1 0 1
python pixel_cli.py edit --project project.json --paint 1 1 "#00FF00" --detail-policy preserve
python pixel_cli.py edit --project project.json --discard-detail 1 1
```

`preserve` での通常の粗い描画は、細部の元データを残して色の差分を重ねます。明示的な分割セルの親だけを編集する場合は、既存の親/子独立の挙動を維持します。置換して細部を削除する場合は `discard` を指定してください。詳しくは [CUI操作仕様](docs/CUI_detail_operations.md) と [非破壊解像度の仕様](docs/Non_destructive_resolution.md) を参照してください。

### PNGへ書き出す

現在の表示を拡大する従来の書き出し:

```bash
python pixel_cli.py export --project project.json --output pixel_art.png --size 256
```

保持中の細部から、指定した出力解像度へ直接投影する書き出し:

```bash
python pixel_cli.py export --project project.json --output detail.png --resolution 23 17
```

後者はプロジェクトの現在解像度を変更しません。JSONはレイヤー・保持中の細部・局所分割状態を残して編集を続けるための形式、PNGは合成済み画像です。

## 保存形式と安全上限

新規保存はversion 2で、現在解像度と保持データを別々に保存します。旧JSONは読み込めますが、新JSONを旧版エディタで編集し直すことはサポートしません。Undo/Redoの操作スタックはセッション内のみで、JSONへ保存しません。

解像度は1辺1〜4096、1ラスタ最大4,194,304画素です。保持パッチ等にも安全上限があります。上限超過時は無断で情報を捨てずにエラーにします。詳細は[データモデル・制限](docs/Non_destructive_resolution.md)を参照してください。

## ビルド・評価

```bash
python scripts/evaluate.py
python test_pixel_backend.py
python test_pixel_layers.py
python test_pixel_cli.py
python test_resolution.py
python test_refinement.py
python test_commands.py
```

push / pull request ごとに Python 3.10 / 3.11 / 3.12 / 3.13 / 3.14 の全ジョブで評価・回帰テストを実行します。通常の自動評価はGUIウィンドウを起動しません。

## 開発資料

- [開発ワークフロー](doc/ワークフロー/ワークフロー.md)
- [開発予定](docs/開発予定.md)
- [コーディングルール](docs/コーディングルール.md)
- [提案書](docs/提案.md)
- [共通Command API](docs/Command_API.md)
- [セル分割回帰仕様](docs/Refinement_regressions.md)
- [非破壊解像度の仕様](docs/Non_destructive_resolution.md)

## ライセンス

このプロジェクトは [MIT License](LICENSE) の下で公開します。依存ライブラリにはそれぞれのライセンスが適用されます。
