# Hyper Dot Editor

Hyper Dot Editor は、GUI と CLI から同じバックエンドを使ってドット絵を編集できるピクセルアートエディタです。バックエンドは複数のゲーム向け開発者ツールから共通利用できることを前提にし、レイヤー、セル分割、任意解像度の非破壊切替、JSONプロジェクト保存、PNG書き出しを扱います。

## 実装の正本と移行方針

製品バックエンドの正本は `rust/` のRust実装とします。Python版は既存GUI・参照実装として残し、移行中はプロジェクトJSONや描画結果など外部から確認できる振る舞いで互換性を検証します。仕様や互換テストに差異がある場合はRust Coreを基準にします。

移行の順序はRust Core、Rust CLI、Rust配布物です。GUIのRust化は初期移行の必須条件にしません。Rust workspaceは現在基盤作成中であり、機能移植の完了を示すものではありません。

## 必要環境

- Python 3.10〜3.14（CIで全バージョンを必須検証）
- Pillow（パッケージ依存は `pyproject.toml` で管理）
- GUIとGUI関連テストにはTkinter。バックエンドとCLIだけの利用にはGUI起動は不要です。

## セットアップ

### Windows (PowerShell)

リポジトリ直下で次を実行します。

```powershell
powershell -ExecutionPolicy Bypass -File scripts/setup_environment.ps1
.venv\Scripts\Activate.ps1
```

`.venv` を作成し、安全なpip・certifiへ更新してから依存関係のインストールと評価を実行します。個人PC固有のPythonパスは不要です。更新と依存取得を省く場合は `-SkipInstall` を付けてください。この場合もtrust検査は行い、古い環境では停止します。

### macOS / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
python scripts/python_trust.py
python -m pip install -e .
```

Windowsで手動セットアップする場合は、仮想環境の有効化を `.venv\Scripts\Activate.ps1` に読み替えてください。

証明書インシデントへの対策として、bootstrapは[Python公式告知](https://discuss.python.org/t/109576)のSHA-256付きwheelで必要に応じてpipを更新します。新しい安定版pipは維持しますが、不明な版形式・開発版は固定wheelへの更新対象になります。単体certifiは更新後のpipでTLS検証を行い、公開PyPIから最低版以上を取得します。certifiの版・wheel hashは固定していません。

pip同梱・単体の実CA bundle、Python既定SSLContextの読込済みroot、OpenSSL既定capath内のhash名ファイルに対象rootが残る場合は停止します。未対応のPEMラベルや追加の `SSL_CERT_DIR` 指定も安全とみなさず停止します。確認だけ行う場合は `python scripts/python_trust.py --check` を実行してください。実行したPython、版、bundleの実パス・件数・hashと既定capathの検査件数がJSONで表示されます。

この検査は対象rootのfingerprintと最低版の確認であり、OS全体・独自CA設定・任意の代替チェーンの安全性を保証しません。失敗した場合は診断に従って環境を更新し、再実行してください。TLS検証を無効化して回避しないでください。CIはビルドとスモークテストを継続しますが、署名・attestation対策（Issue #55）の完了までは未署名成果物をアップロードしません。過去の配布物の再検証・再公開は別途対応します。

GitHub-hostedのUbuntu CIでは、runnerのOS設定で選択中の証明書を実DERで照合し、対象rootだけを無効化してCA bundleを再生成します。これは使い捨てrunner限定の処理です。ローカルPC・self-hosted runnerの証明書設定は自動変更しません。分離ビルドが別に作成するPython環境や、過去の成果物内の信頼設定の監査は、この検査とは別に必要です。

runnerのCA選択設定に欠落ファイル・不正PEM・余分な空白・範囲外パスがあれば、勝手に無視せずCIを停止します。対象rootの無効化後も、ローカル追加CAなどに対象rootが残れば後続の検査で停止します。

GitHub-hostedのWindows CIでは、LocalMachine・CurrentUserのRoot/CAストアを実DERのSHA-256で照合します。一致した証明書だけをDisallowedへ登録して信頼側から除去し、新しいPythonプロセスで再検査します。この修復も使い捨てrunner限定で、ローカルPCでは実行しません。

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

`inspect` のJSONに `"rgba": [0, 0, 255, 255]` が含まれれば子セルの編集結果を確認できます。`quickstart.json` は後で編集を再開するためのレイヤー・細部情報付き作品、`quickstart.png` は256×256の合成画像です。実行例はCIでも実際に起動して検証します。

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
キャンバス内の矢印キー移動とSpace描画はIssue #28/#29で扱います。

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

## ソース構成と開発ツール

- `src/`: GUI・CLI・共通バックエンド。既存のPython import名は維持しています。
- `rust/`: 製品正本へ移行するRust workspace。RGBAラスタ、細部保持・破棄、4子セル分割・描画、Undo/Redo付きCanvasを整備しています。Canvasの4近傍塗りつぶしと長方形の領域分割は、それぞれ全体を1回でUndoできます。
  単一CanvasのJSON読み込みは `Canvas::from_json()`（version 1・2）、書き出しは `Canvas::to_json()`（version 2）で利用できます。Pythonとの往復互換は `.venv/Scripts/python.exe scripts/test_rust_json_compat.py` で検証できます。レイヤー付きJSONとPNG出力は移植中です。
- `tests/`: 自動テスト。
- `scripts/`: 環境構築・評価・配布ビルド。
- `tools/tomiya_code_atlas/`: 図生成用の外部Gitサブモジュール。
- `dist/`: ローカルの配布成果物（Git対象外）。

クラス図・シーケンス図は独自生成器ではなく [Tomiya Code Atlas](https://github.com/tomiya7688/tomiya_code_atlas) を使用します。
導入・実行方法は [tools/README.md](tools/README.md) を参照してください。

## Rust Core のビルド・テスト

Rustコアの開発には **Rust stableツールチェーン（cargo / rustfmt / clippy）** が別途必要です。Pythonのセットアップと混同しないよう、Rust workspaceの確認はリポジトリ直下から次を実行します。

```bash
cargo fmt --manifest-path rust/Cargo.toml -- --check
cargo clippy --manifest-path rust/Cargo.toml --workspace --all-targets --all-features -- -D warnings
cargo test --manifest-path rust/Cargo.toml --workspace
cargo build --manifest-path rust/Cargo.toml --workspace
python scripts/test_rust_json_compat.py
```

最後の互換性テストはセットアップ済みのPython参照実装とRust Coreで、双方向のJSON互換性を検証します。Rust CLIやRust製配布物は移行途中であり、現在の `python -m pixel_cli` およびWindows配布EXEはPythonベースです。

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

## Windows配布ビルド

Windows x64環境で、先に[Windowsのセットアップ](#windows-powershell)を実行して `.venv` を作成してください。ビルド用依存はビルドスクリプトが `requirements-build.txt` からインストールします。


```powershell
powershell -ExecutionPolicy Bypass -File scripts/build_windows.ps1
```

Pythonパッケージ（wheel・sdist）と、Pythonのインストール不要なWindows x64配布物を生成します。
`dist/HyperDotEditor-windows-x64.zip` を展開し、`DotEditor/DotEditor.exe` を起動してください。
CLIは `DotEditorCLI/DotEditorCLI.exe` です。各フォルダの `_internal` を含めて配布してください。
ビルド時にCLIの保存・編集・PNG出力とGUI実行ファイルの非GUIスモーク検査を行います。
画面を操作するGUIテストとは異なります。既存の同名 `dist` 成果物は再ビルドで更新されます。

GitHub ActionsのWindowsジョブでもビルドし、配布ZIPとwheel・sdistをArtifactsへアップロードします。

## 自動評価

GUIウィンドウを開かない最低限の起動確認には `python -m dot_editor --smoke-test` を使えます。これは画面操作テストの代わりにはなりません。


```bash
python scripts/evaluate.py
python -m unittest discover -s tests
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
