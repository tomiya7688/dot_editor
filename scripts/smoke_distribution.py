"""Validate packaged executables without opening the editor GUI."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile


# {
#   責務: [main: 配布CLIの編集・書き出しとGUI起動検査をヘッドレス実行する]
#   処理: [
#     1: 一時作業フォルダーでCLIに新規作成・編集・検査・PNG書出しを行わせる
#     2: 保存後のRGBAとPNG寸法・画素が期待値どおりであることを確認する
#     3: GUI実行ファイルのsmoke-testモードを起動しウィンドウを表示せず確認する
#     4: 検査結果を出力して一時作業フォルダーを破棄する
#   ]
#   引数: [なし、検証する配布フォルダーをコマンドライン第1引数で受け取る]
#   戻り値: [成功時は0、CLI・GUIの起動やアサーションに失敗した場合は例外]
# }
def main() -> int:
    distribution = Path(sys.argv[1]).resolve()
    cli = distribution / "DotEditorCLI" / "DotEditorCLI.exe"
    gui = distribution / "DotEditor" / "DotEditor.exe"
    with tempfile.TemporaryDirectory(prefix="dot-distribution-") as directory:
        root = Path(directory)

        # 個別コマンドが同じ一時プロジェクトを安全に共有する。
        # {
        #   責務: [run: 配布CLIの1コマンドを一時フォルダーで実行する]
        #   処理: [引数を文字列化してCLIへ渡し、失敗・出力を保ったまま完了を待つ]
        #   引数: [arguments: CLIサブコマンドとそのコマンドライン引数]
        #   戻り値: [標準出力・標準エラーを含むCompletedProcess、失敗や60秒超過時は例外]
        # }
        def run(*arguments):
            return subprocess.run([str(cli), *map(str, arguments)], cwd=root,
                                  check=True, capture_output=True, text=True, timeout=60)

        # 配布CLIに小さなレイヤー付きプロジェクトを新規作成させる。
        run("new", "--size", 2, "--layered", "--output", "project.json")
        # 作成したファイルを編集し、保存データから変更結果を読み取る。
        run("edit", "--project", "project.json", "--paint", 0, 0, "#FF0000")
        result = run("inspect", "--project", "project.json", "--sample", 0, 0)
        assert json.loads(result.stdout)["sample"]["rgba"] == [255, 0, 0, 255]
        run("export", "--project", "project.json", "--output", "image.png", "--size", 2)
        from PIL import Image
        # PNGの寸法と代表画素を読み、JSONの編集結果と照合する。
        with Image.open(root / "image.png") as image:
            assert image.size == (2, 2)
            assert image.getpixel((0, 0)) == (255, 0, 0, 255)
        # GUIはウィンドウを開かない専用モードで配布物として起動する。
        subprocess.run([str(gui), "--smoke-test"], cwd=root, check=True, timeout=60)
    print("Packaged CLI and GUI headless smoke passed (no GUI window opened).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
