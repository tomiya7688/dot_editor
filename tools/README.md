# 開発用外部ツール

`tomiya_code_atlas` は https://github.com/tomiya7688/tomiya_code_atlas のGitサブモジュールです。
本体や配布EXEには組み込みません。独自の図生成器は使いません。

```powershell
git submodule update --init tools/tomiya_code_atlas
py -3 -m venv .venv-atlas
.venv-atlas/Scripts/python.exe -m pip install -e tools/tomiya_code_atlas
.venv-atlas/Scripts/python.exe tools/tomiya_code_atlas/app.py class-diagram src/pixel_commands.py --output-dir docs/atlas/classes
.venv-atlas/Scripts/python.exe tools/tomiya_code_atlas/app.py sequence-diagram src/pixel_cli.py --output-dir docs/atlas/sequences
```

Atlasの必要環境はPython 3.11以降です。解析対象のソースファイルは用途に合わせて指定します。
図は静的解析の結果です。実行トレースではありません。生成物は `docs/atlas/`（Git対象外）へ保存します。
サブモジュールは固定コミットを使用します。更新は明示的に行い、親リポジトリに更新コミットを記録してください。
