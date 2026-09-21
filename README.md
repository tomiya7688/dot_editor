# Hyper Dot Editor

Hyper Dot Editor は、GUI と CLI から同じバックエンドを使ってドット絵を編集できる小さなピクセルアートエディタです。レイヤー、2x2 のセル分割、JSONプロジェクト保存、PNG書き出しを扱えます。

## 必要環境

- Python 3.10〜3.14（CIで全バージョンを必須検証）
- Pillow（`requirements.txt` で管理）

GitHub Actions では Python 3.10 / 3.11 / 3.12 / 3.13 / 3.14 の全バージョンを検証しています。

## セットアップ

### Windows (PowerShell)

リポジトリ直下で次を実行します。

```powershell
powershell -ExecutionPolicy Bypass -File scripts/setup_environment.ps1
```

このスクリプトは `.venv` を作成し、依存関係をインストールしてから `python scripts/evaluate.py` 相当の評価を実行します。個人PC固有のPythonパスは不要です。

既に依存関係をインストール済みなら:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/setup_environment.ps1 -SkipInstall
```

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

GUIでは通常描画、消しゴム、スポイト、塗りつぶし、レイヤー、セル分割、論理解像度変更、表示サイズ変更、JSONプロジェクト保存/読込、PNG保存を利用できます。

## CLIを使う

### 新規プロジェクト

```bash
python pixel_cli.py new --size 16 --output project.json
```

レイヤープロジェクトとして作る場合:

```bash
python pixel_cli.py new --size 16 --layered --output project.json
```

### 編集

1セルを赤で塗る例:

```bash
python pixel_cli.py edit --project project.json --paint 1 1 "#FF0000"
```

レイヤーを追加して選択する例:

```bash
python pixel_cli.py edit --project project.json --add-layer "人物"
python pixel_cli.py edit --project project.json --select-layer "人物" --paint 2 2 "#00AAFF"
```

### セル分割

親セル `(1, 1)` を2x2に分割し、右上の子セルを青で塗る例:

```bash
python pixel_cli.py edit --project project.json --split 1 1
python pixel_cli.py edit --project project.json --paint-child 1 1 1 0 "#0000FF"
```

子セルを透明化する場合:

```bash
python pixel_cli.py edit --project project.json --erase-child 1 1 0 1
```

### PNGへ書き出す

```bash
python pixel_cli.py export --project project.json --output pixel_art.png --size 256
```

`--size` は書き出すPNGの辺長です。分割セルがある場合は内部の詳細解像度より小さい値にはできません。

## JSONプロジェクトとPNGの違い

- **JSONプロジェクト**: 編集を続けるためのデータです。論理解像度、各ピクセル、レイヤー、選択レイヤー、セル分割情報を保持します。
- **PNG**: 共有・表示用の完成画像です。レイヤーやセル分割などの編集情報は画像へ合成されます。

編集を続ける場合はJSONを保存し、成果物として画像が必要なときにPNGへexportしてください。

## ビルド・評価

変更後の最低条件は次です。

```bash
python scripts/evaluate.py
```

バックエンド回帰テストを個別に実行する場合:

```bash
python test_pixel_backend.py
python test_pixel_layers.py
```

GitHub Actions でも push / pull request ごとに同じ評価とテストを実行します。評価処理はGUIウィンドウを起動しません。

## 開発資料

- [開発ワークフロー](doc/ワークフロー/ワークフロー.md)
- [開発予定](docs/開発予定.md)
- [コーディングルール](docs/コーディングルール.md)
- [提案書](docs/提案.md)

## ライセンス

このプロジェクトは [MIT License](LICENSE) の下で公開します。依存ライブラリにはそれぞれのライセンスが適用されます。
