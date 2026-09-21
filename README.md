# dot_editor

ドット絵エディタの開発リポジトリです。

## 開発環境

- Python 3.10〜3.14（CIで全バージョンを必須検証）
- Pillow（`requirements.txt` で管理）

GitHub Actions では Python 3.10 / 3.11 / 3.12 / 3.13 / 3.14 の全バージョンで検証します。

### Windows (PowerShell)

```powershell
powershell -ExecutionPolicy Bypass -File scripts/setup_environment.ps1
```

このスクリプトはリポジトリ直下に `.venv` を作成し、依存関係をインストールしたあと `scripts/evaluate.py` を実行します。個人PC固有のPythonパスは必要ありません。

既に依存関係をインストール済みの場合は次のように実行できます。

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

## ビルド・評価

変更後は最低限、次を成功させてください。

```bash
python scripts/evaluate.py
```

追加のバックエンド確認:

```bash
python test_pixel_backend.py
python test_pixel_layers.py
```

GitHub Actions でも push / pull request ごとに同じ評価とテストを実行します。GUIは評価処理から起動しません。
