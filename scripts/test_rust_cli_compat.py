"""Verify the Rust `pixel-cli` against the Python reference without a GUI."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from PIL import Image
from pixel_layers import LayeredPixelCanvas


# {
#   責務: [build_binary: Rustのpixel-cliをビルドして実行ファイルの場所を返す]
#   処理: [
#     1: cargoでhyper-dot-cliをビルドする
#     2: ターゲットフォルダの実行ファイルを返す
#   ]
#   引数: []
#   戻り値: [pixel-cliの実行ファイルのパス]
# }
def build_binary():
    manifest = ROOT / "rust" / "Cargo.toml"
    subprocess.run(
        ["cargo", "build", "--quiet", "--manifest-path", str(manifest), "-p", "hyper-dot-cli"],
        cwd=ROOT,
        check=True,
        timeout=600,
    )
    suffix = ".exe" if sys.platform == "win32" else ""
    return ROOT / "rust" / "target" / "debug" / f"pixel-cli{suffix}"


# {
#   責務: [run_cli: pixel-cliを標準入力なしで実行し、JSON結果を返す]
#   処理: [
#     1: --jsonを付けて起動し、終了値0を確認する
#     2: 標準出力を1つのJSONとして解析する
#   ]
#   引数: [
#     binary: 実行ファイルのパス
#     project: プロジェクトファイルのパス
#     words: コマンドの語
#   ]
#   戻り値: [解析したJSON辞書]
# }
def run_cli(binary, project, *words):
    result = subprocess.run(
        [str(binary), "--json", "-p", str(project), *words],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
    )
    assert result.returncode == 0, (words, result.stderr)
    return json.loads(result.stdout)


# {
#   責務: [image_rows: 画像をRGBA行列へ変換して比較できるようにする]
#   処理: [
#     1: 行ごとに各画素のRGBAを取り出す
#   ]
#   引数: [
#     image: RGBA画像
#   ]
#   戻り値: [RGBA行列]
# }
def image_rows(image):
    return [[list(image.getpixel((x, y))) for x in range(image.width)] for y in range(image.height)]


# {
#   責務: [export_rows: CLIで書き出したPNGをPillowで読んでRGBA行列にする]
#   処理: [
#     1: pixel-cliのexport renderを実行する
#     2: 書き出されたPNGをPillowで開き、RGBAであることを確認する
#   ]
#   引数: [
#     binary: 実行ファイルのパス
#     project: プロジェクトファイルのパス
#     output: PNGの書き出し先
#     options: export renderへ追加するオプション
#   ]
#   戻り値: [PNGのRGBA行列]
# }
def export_rows(binary, project, output, *options):
    run_cli(binary, project, "export", "render", "-o", str(output), *options)
    with Image.open(output) as image:
        image.load()
        assert image.mode == "RGBA", image.mode
        return image_rows(image)


# {
#   責務: [assert_same_render: PythonとRust CLIのPNG出力が3方式すべてで一致するか確認する]
#   処理: [
#     1: 自然な解像度・保持細部の直接描画・正方形への拡大を、それぞれRustとPythonで書き出す
#     2: Pillowで読んだ画素を比較する
#   ]
#   引数: [
#     binary: 実行ファイルのパス
#     project: プロジェクトファイルのパス
#     model: 同じ内容のPythonの作品
#     folder: 書き出し用の作業フォルダ
#     label: 失敗時に出すケース名
#   ]
#   戻り値: [なし、食い違えばAssertionError]
# }
def assert_same_render(binary, project, model, folder, label):
    modes = (
        ("native", (), {}),
        ("detail", ("--resolution", "12", "8"), {"output_resolution": (12, 8)}),
        ("scaled", ("--size", "16"), {"export_size": 16}),
    )
    for name, options, python_options in modes:
        rust = export_rows(binary, project, folder / f"rust_{name}.png", *options)
        python_path = folder / f"python_{name}.png"
        model.save_png(python_path, **python_options)
        with Image.open(python_path) as image:
            image.load()
            assert rust == image_rows(image), (label, name)


# {
#   責務: [layer_state: CLIのlayer listをPythonの作品と同じ形に整える]
#   処理: [
#     1: layer listの結果から名前・表示状態・選択中の層を取り出す
#   ]
#   引数: [
#     binary: 実行ファイルのパス
#     project: プロジェクトファイルのパス
#   ]
#   戻り値: [名前・表示状態・選択名を持つ辞書]
# }
def layer_state(binary, project):
    layers = run_cli(binary, project, "layer", "list")["result"]["layers"]
    return {
        "names": [layer["name"] for layer in layers],
        "visible": [layer["visible"] for layer in layers],
        "active": next(layer["name"] for layer in layers if layer["active"]),
    }


# {
#   責務: [check_rust_made: Rust CLIで作った文書をPythonが読み、構成と描画が一致するか確認する]
#   処理: [
#     1: 層・領域分割・子セル・半透明・非表示・解像度変更をpixel-cliで行う
#     2: 保存したJSONをPythonで読み、構成とPNG出力を比較する
#   ]
#   引数: [
#     binary: 実行ファイルのパス
#     folder: 作業フォルダ
#   ]
#   戻り値: [なし、食い違えばAssertionError]
# }
def check_rust_made(binary, folder):
    project = folder / "rust_made.json"
    run_cli(binary, project, "project", "new", "--resolution", "6", "4")
    steps = (
        ("pixel", "paint", "1", "1", "#336699"),
        ("layer", "add", "上"),
        ("pixel", "paint", "1", "1", "#FF000080"),
        ("pixel", "paint", "2", "1", "#00FF0003"),
        ("detail", "split-region", "0", "0", "2", "2"),
        ("pixel", "paint", "1", "1", "#00FF00", "--child", "1", "0"),
        ("layer", "add", "隠し"),
        ("pixel", "paint", "0", "3", "#010203"),
        ("layer", "visibility", "off"),
        ("layer", "select", "上"),
        ("canvas", "resolution", "set", "3", "2"),
    )
    for words in steps:
        run_cli(binary, project, *words)
    model = LayeredPixelCanvas.from_source(json.loads(project.read_text(encoding="utf-8")))
    state = layer_state(binary, project)
    assert state["names"] == list(model.layers), state
    assert state["visible"] == [model.layer_visibility[name] for name in model.layers], state
    assert state["active"] == model.active_layer, state
    assert_same_render(binary, project, model, folder, "rust_made")


# {
#   責務: [check_python_made: Pythonで作った文書をRust CLIが読み書きし、描画と編集が一致するか確認する]
#   処理: [
#     1: Pythonで層・半透明・展開セル・非表示を持つ文書を保存する
#     2: Rust CLIで構成と描画を比較する
#     3: Rust CLIで編集した結果をPythonで読み戻す
#   ]
#   引数: [
#     binary: 実行ファイルのパス
#     folder: 作業フォルダ
#   ]
#   戻り値: [なし、食い違えばAssertionError]
# }
def check_python_made(binary, folder):
    model = LayeredPixelCanvas(4, 3)
    model.fill(0, 0, (10, 120, 200, 255))
    model.add_layer("半透明")
    model.paint(1, 1, (255, 0, 0, 128))
    model.split_cell(2, 1)
    model.paint(2, 1, (5, 6, 7, 200), child=(1, 0))
    model.add_layer("隠し")
    model.paint(0, 0, (1, 2, 3, 255))
    model.set_layer_visibility(False)
    model.select_layer("半透明")
    project = folder / "python_made.json"
    project.write_text(json.dumps(model.to_source(), ensure_ascii=False), encoding="utf-8")
    state = layer_state(binary, project)
    assert state["names"] == list(model.layers), state
    assert state["active"] == model.active_layer, state
    assert_same_render(binary, project, model, folder, "python_made")
    run_cli(binary, project, "pixel", "paint", "0", "2", "#ABCDEF")
    reloaded = LayeredPixelCanvas.from_source(json.loads(project.read_text(encoding="utf-8")))
    assert reloaded.sample(0, 2) == (171, 205, 239, 255)
    assert reloaded.active_layer == "半透明"


# {
#   責務: [main: Rust CLIとPython参照実装の相互運用を検証する]
#   処理: [
#     1: Rust CLIが作った文書をPythonで読んで比較する
#     2: Pythonが作った文書をRust CLIで読み書きして比較する
#   ]
#   引数: []
#   戻り値: [なし、失敗時は例外]
# }
def main():
    binary = build_binary()
    with tempfile.TemporaryDirectory() as directory:
        folder = Path(directory)
        check_rust_made(binary, folder)
        check_python_made(binary, folder)
    print("pixel-cli interchange ok")


if __name__ == "__main__":
    main()
