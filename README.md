# Hyper Dot Editor

Hyper Dot Editor は、GUI と CLI から同じバックエンドを使ってドット絵を編集できるピクセルアートエディタです。バックエンドは複数のゲーム向け開発者ツールから共通利用できることを前提にし、レイヤー、セル分割、任意解像度の非破壊切替、JSONプロジェクト保存、PNG書き出しを扱います。

## 必要環境

- Python 3.10〜3.14
- Pillow（パッケージ依存は `pyproject.toml` で管理）
- GUIとGUI関連テストにはTkinter。バックエンドとCLIだけの利用にはGUI起動は不要です。

## セットアップ

### Windows (PowerShell)

リポジトリ直下で次を実行します。

```powershell
powershell -ExecutionPolicy Bypass -File scripts/setup_environment.ps1
.venv\Scripts\Activate.ps1
```

`.venv` を作成し、依存関係をインストールしてから評価を実行します。個人PC固有のPythonパスは不要です。依存関係のインストールを省く場合は `-SkipInstall` を付けてください。

### macOS / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
```

Windowsで手動セットアップする場合は、仮想環境の有効化を `.venv\Scripts\Activate.ps1` に読み替えてください。

## 最短の動作確認（CLI）

上記のセットアップを済ませ、**リポジトリ直下で以下を上から順に実行**してください。新しいレイヤー付き作品を作り、描画・セル分割・色の確認・PNG書き出しまで行います。いずれも対話操作は不要です。

```bash
python -m pixel_cli new --size 16 --layered --output quickstart.json
python -m pixel_cli edit --project quickstart.json --paint 1 1 "#FF0000"
python -m pixel_cli edit --project quickstart.json --split 1 1
python -m pixel_cli edit --project quickstart.json --paint-child 1 1 1 0 "#0000FF"
python -m pixel_cli inspect --project quickstart.json --sample 1 1 --child 1 0
python -m pixel_cli export --project quickstart.json --output quickstart.png --size 256
```

`inspect` のJSONに `"rgba": [0, 0, 255, 255]` が含まれれば子セルの編集結果を確認できます。`quickstart.json` は後で編集を再開するためのレイヤー・細部情報付き作品、`quickstart.png` は256×256の合成画像です。

## GUIを起動する

```bash
python -m dot_editor
```

ブラシ、消しゴム、スポイト、塗りつぶし、レイヤー、セル分割、折りたたみ、細部破棄、任意の縦横解像度、表示サイズ、JSON保存/読込、PNG保存を利用できます。描画・解像度変更時の細部ポリシーは「保持」が既定です。ウィンドウを広げると描画面も広がり、表示画像は余白の中央へ移動します。表示倍率は解像度欄に表示され、Ctrl+マウスホイールでも変更できます。操作が画面に収まらない場合は右サイドバーをスクロールしてください。

「表示サイズを変更」は作品・レイヤー・Undo/Redo履歴を保持します。
「作品をリセット」は確認ダイアログで承認した場合だけ全レイヤーと履歴を消去します。
確認の初期選択は「いいえ」です。承認後のリセットはUndoできません。

### キーボードからメニューを操作する

Altを押すとメニューバーに入り、表示中の括弧付き英字を続けて押すとメニューを開けます（例: Alt→Tで描画）。
トップ階層は左右、項目は上下、Enterで実行、右/Enterでサブメニュー、左/Escで一段戻り、Alt/Escでメニューを閉じます。
メニュー項目に表示された英字や色パレットの番号でも選択できます。Ctrl+Z/Ctrl+YはUndo/Redoです。
レイヤー一覧は「レイヤー (L)」→「レイヤーを選択 (S)」で現在のレイヤー名から選べます。
キャンバスとサイドバーの切替はF6/Shift+F6です。サイドバー内の操作要素はTab/Shift+Tabで巡回し、フォーカスが表示範囲外に進むと自動スクロールします。
キーボードフォーカスは水色の枠で表示します。メニューバーへは従来どおりAltで入ります。
Ctrl+Z/Ctrl+Yはエディター本体にフォーカスがあるときだけ作品のUndo/Redoを実行します。入力欄やダイアログでは文字編集側のキー操作を優先します。
キャンバス内の矢印キー移動とSpace描画は現在利用できません。

## Python Command API

ゲーム開発者ツール、Automation、AIなどから直接利用する場合は `PixelCommandAPI` を使います。GUIとCLIも同じCommand APIを経由します。

```python
from pixel_commands import PixelCommandAPI

commands = PixelCommandAPI.new(16, layered=True)
commands.paint(4, 3, (255, 0, 0, 255))
commands.set_resolution(23, 17)
commands.save("project.json")
commands.export_png("exported.png", output_resolution=(256, 256))
```

文字列ベースの呼び出しには `commands.execute("paint", ...)` も利用できます。詳細は [共通Command API](docs/Command_API.md) を参照してください。

## CLIを使う

### 一度起動して続けて編集する

作成済みプロジェクトを対話パレットで開くと、Pythonを起動し直さずに編集できます。

```bash
python -m pixel_cli palette --project project.json
```

起動後は次のように入力します。

```text
help
edit --paint 1 1 #FF0000
edit --add-layer "人物"
edit --paint 2 2 #00AAFF
inspect --sample 2 2
export --output "pixel art.png" --size 256
quit
```

`edit`、`inspect`、`export` は通常のCLIと同じオプションを使いますが、`--project` は不要です。
編集先は起動時のプロジェクトに固定され、`edit --output` は使用できません。
`help edit` などで各操作のヘルプを表示できます。空白を含む名前・パスは引用符で囲んでください。
Windowsの `\` と色指定の `#` はそのまま入力できます。

編集は成功した行ごとに自動保存されます。同じ行の途中で入力・処理・保存に失敗した場合は、
その行の変更をメモリにもファイルにも反映せず、次の入力を受け付けます。
一行に複数の編集を指定した場合の順序は通常の `edit` と同じです。
`quit` / `exit` または入力終了で閉じます。Ctrl+Cは終了コード130で終了します。
標準入力からコマンド列を渡す自動処理にも対応し、一度でもエラーがあったセッションは終了コード2を返します。
成功済みの行はエラーや終了後も保存されています。

### 新規プロジェクトと基本編集

```bash
python -m pixel_cli new --size 16 --layered --output project.json
python -m pixel_cli edit --project project.json --paint 1 1 "#FF0000"
python -m pixel_cli edit --project project.json --add-layer "人物"
python -m pixel_cli edit --project project.json --select-layer "人物" --paint 2 2 "#00AAFF"
```

`--size` は任意の正の整数で正方形を作ります。`--layered` を省くと単一レイヤーのプロジェクトになります。非正方形は次のように指定します。

```bash
python -m pixel_cli new --resolution 23 17 --output rectangular.json
```

### 非破壊の解像度切替

```bash
python -m pixel_cli edit --project project.json --resolution 7 7
python -m pixel_cli edit --project project.json --resolution 23 17
python -m pixel_cli edit --project project.json --resolution 16 16
python -m pixel_cli inspect --project project.json
```

解像度を変えただけでは細部を破棄しません。無編集の往復では元の情報が復元します。`--detail-policy discard` を解像度変更と組み合わせた場合だけ、全体を新しい粗さへ統合します。

### セル分割と保持・破棄

```bash
python -m pixel_cli edit --project project.json --split 1 1
python -m pixel_cli edit --project project.json --paint-child 1 1 1 0 "#0000FF"
python -m pixel_cli edit --project project.json --collapse 1 1
python -m pixel_cli inspect --project project.json --sample 1 1 --child 1 0
python -m pixel_cli edit --project project.json --split 1 1
python -m pixel_cli edit --project project.json --erase-child 1 1 0 1
python -m pixel_cli edit --project project.json --paint 1 1 "#00FF00" --detail-policy preserve
python -m pixel_cli edit --project project.json --discard-detail 1 1
```

`preserve` での通常の粗い描画は、細部の元データを残して色の差分を重ねます。明示的な分割セルの親だけを編集する場合は、既存の親/子独立の挙動を維持します。置換して細部を削除する場合は `discard` を指定してください。詳しくは [CUI操作仕様](docs/CUI_detail_operations.md) と [非破壊解像度の仕様](docs/Non_destructive_resolution.md) を参照してください。

### PNGへ書き出す

現在の表示を拡大する従来の書き出し:

```bash
python -m pixel_cli export --project project.json --output exported.png --size 256
```

保持中の細部から、指定した出力解像度へ直接投影する書き出し:

```bash
python -m pixel_cli export --project project.json --output detail.png --resolution 23 17
```

後者はプロジェクトの現在解像度を変更しません。JSONはレイヤー・保持中の細部・局所分割状態を残して編集を続けるための形式、PNGは合成済み画像です。

## 保存形式と安全上限

JSONの重複キー、非標準数値（NaN・Infinity）、128階層を超えるオブジェクト・配列の入れ子は読込エラーとして拒否します。
読込失敗時は編集中の作品を置き換えません。

新規保存はversion 2で、現在解像度と保持データを別々に保存します。旧JSONは読み込めますが、新JSONを旧版エディタで編集し直すことはサポートしません。Undo/Redoの操作スタックはセッション内のみで、JSONへ保存しません。

解像度は1辺1〜4096、1ラスタ最大4,194,304画素です。保持パッチ等にも安全上限があります。上限超過時は無断で情報を捨てずにエラーにします。詳細は[データモデル・制限](docs/Non_destructive_resolution.md)を参照してください。

## Windows配布版を利用する

Windows x64向けの `HyperDotEditor-windows-x64.zip` を展開し、`DotEditor/DotEditor.exe` を起動してください。CLIは `DotEditorCLI/DotEditorCLI.exe` です。各フォルダ内の `_internal` は削除しないでください。

## 起動を確認する

GUIウィンドウを開かず起動状態を確認したい場合は `python -m dot_editor --smoke-test` を実行します。このコマンドではGUIの画面操作をテストしません。

## 仕様・APIリファレンス

- [共通Command API](docs/Command_API.md)
- [非破壊解像度と保存形式](docs/Non_destructive_resolution.md)
- [CLI細部編集の仕様](docs/CUI_detail_operations.md)

## ライセンス

このプロジェクトは [MIT License](LICENSE) の下で公開します。依存ライブラリにはそれぞれのライセンスが適用されます。
