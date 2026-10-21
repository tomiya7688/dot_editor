"""Verify layered project JSON interchange between Rust and Python without a GUI."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pixel_layers import LayeredPixelCanvas


# {
#   責務: [image_rows: 描画画像を言語間比較用のRGBA行列へ変換する]
#   処理: [
#     1: 行ごとに各画素のRGBAを取り出す
#   ]
#   引数: [
#     image: RGBA比較対象の画像
#   ]
#   戻り値: [RGBA行列]
# }
def image_rows(image):
    return [[list(image.getpixel((x, y))) for x in range(image.width)]
            for y in range(image.height)]


# {
#   責務: [run_example: Rustの互換検証用実行例を起動してJSONを受け取る]
#   処理: [
#     1: cargoでexampleを実行し、必要なら標準入力へ文書を渡す
#     2: 失敗した場合は標準エラーを添えて例外にする
#   ]
#   引数: [
#     arguments: exampleへ渡す追加引数
#     stdin: 標準入力へ渡すJSON文字列。なければNone
#   ]
#   戻り値: [標準出力をJSONとして解析した値]
# }
def run_example(arguments, stdin=None):
    command = [
        "cargo", "run", "--quiet", "--manifest-path", str(ROOT / "rust" / "Cargo.toml"),
        "--example", "layered_json_compat_fixture", *(["--", *arguments] if arguments else []),
    ]
    result = subprocess.run(command, input=stdin, cwd=ROOT, capture_output=True,
                            text=True, encoding="utf-8", timeout=180)
    if result.returncode:
        raise RuntimeError(result.stderr)
    return json.loads(result.stdout)


# {
#   責務: [observe: Pythonの作品をRustの観測結果と同じ形で記録する]
#   処理: [
#     1: 層の名前・表示状態・選択名を取り出す
#     2: 自然な解像度の合成と、16x12の保持細部合成を取り出す
#   ]
#   引数: [
#     model: 観測するレイヤー付き作品
#   ]
#   戻り値: [Rustの観測結果と比較できる辞書]
# }
def observe(model):
    return {
        "names": list(model.layers),
        "visible": [model.layer_visibility[name] for name in model.layers],
        "active_layer": model.active_layer,
        "native": image_rows(model.composite()),
        "detail": image_rows(model.render_resolution(16, 12)),
    }


# {
#   責務: [assert_same: PythonとRustの観測結果が一致するか確認する]
#   処理: [
#     1: 比較する項目ごとに食い違いを検出する
#   ]
#   引数: [
#     name: ケース名
#     expected: 片方の観測結果
#     actual: もう片方の観測結果
#   ]
#   戻り値: [なし、食い違えばAssertionError]
# }
def assert_same(name, expected, actual):
    for key in ("names", "visible", "active_layer", "native", "detail"):
        assert expected[key] == actual[key], (name, key)


# {
#   責務: [python_documents: Pythonで作るレイヤー付き作品を列挙する]
#   処理: [
#     1: 半透明と非表示、展開セルと保持細部を持つ作品を作る
#     2: 旧形式（version 1）のレイヤー付き文書を手書きで加える
#   ]
#   引数: []
#   戻り値: [ケース名とJSON辞書の組の一覧]
# }
def python_documents():
    stacked = LayeredPixelCanvas(4, 3)
    stacked.fill(0, 0, (10, 120, 200, 255))
    stacked.add_layer("半透明")
    stacked.paint(1, 1, (255, 0, 0, 128))
    stacked.paint(2, 1, (0, 255, 0, 3))
    stacked.add_layer("隠し")
    stacked.paint(0, 0, (1, 2, 3, 255))
    stacked.set_layer_visibility(False)
    stacked.select_layer("背景")
    refined = LayeredPixelCanvas(4, 3)
    refined.paint(2, 2, (40, 50, 60, 255))
    refined.add_layer("上")
    refined.split_cell(1, 1)
    refined.paint(1, 1, (5, 6, 7, 200), child=(1, 0))
    refined.paint(3, 0, (9, 99, 199, 90))
    refined.set_resolution(2, 2)
    refined.move_layer("down")
    refined.rename_layer("手前だった層")
    legacy = {"layers": [
        {"name": "旧背景", "source": {"canvas_size": 2, "pixels": [["#102030", None], [None, "#FF000080"]]}},
        {"name": "旧上", "visible": False, "source": {"canvas_size": 2, "pixels": [[None, None], ["#00FF00", None]]}},
    ], "active_layer": "旧上"}
    return [
        ("python_stacked", stacked.to_source()),
        ("python_refined", refined.to_source()),
        ("legacy_layers_v1", legacy),
    ]


# {
#   責務: [malformed_documents: 両言語が拒否すべき不正文書を列挙する]
#   処理: [
#     1: 正常な文書を基に、構造や寸法を一つずつ壊した文書を作る
#   ]
#   引数: []
#   戻り値: [ケース名とJSON辞書の組の一覧]
# }
def malformed_documents():
    model = LayeredPixelCanvas(2, 2)
    model.add_layer("上")
    good = model.to_source()
    cases = {}

    # {
    #   責務: [broken: 正常な文書を複製して一か所だけ壊し、ケースへ登録する]
    #   処理: [
    #     1: 正常な文書を深く複製する
    #     2: 渡された変更を適用してケース名で登録する
    #   ]
    #   引数: [name: ケース名, change: 複製した文書を壊す処理]
    #   戻り値: [なし。casesへ追加される]
    # }
    def broken(name, change):
        source = copy.deepcopy(good)
        change(source)
        cases[name] = source

    broken("unsupported_version", lambda s: s.update(version=3))
    broken("no_layers", lambda s: s.update(layers=[]))
    broken("duplicate_names", lambda s: s["layers"][1].update(name="背景"))
    broken("blank_name", lambda s: s["layers"][1].update(name="   "))
    broken("visible_not_boolean", lambda s: s["layers"][1].update(visible="yes"))
    broken("missing_active_layer", lambda s: s.update(active_layer="無い"))
    broken("resolution_mismatch", lambda s: s.update(resolution=[3, 2]))
    broken("canvas_size_mismatch", lambda s: s.update(canvas_size=5))
    broken("layer_size_mismatch",
           lambda s: s["layers"][1].update(source=LayeredPixelCanvas(3, 3).to_source()["layers"][0]["source"]))
    broken("layer_source_missing", lambda s: s["layers"][1].pop("source"))
    return list(cases.items())


# {
#   責務: [main: レイヤー付きJSONの往復互換と不正文書の拒否を検証する]
#   処理: [
#     1: Rustが作った文書をPythonで読み、合成結果と構成を照合する
#     2: Pythonが作った文書と旧形式をRustで読み、同じ照合を行う
#     3: 不正文書を両言語が拒否することを確認する
#   ]
#   引数: []
#   戻り値: [なし、失敗時は例外]
# }
def main():
    for case in run_example([]):
        model = LayeredPixelCanvas.from_source(case["source"])
        assert_same(case["name"], case, observe(model))
        assert_same(case["name"], case, observe(LayeredPixelCanvas.from_source(model.to_source())))
    documents = python_documents()
    imports = [{"name": name, "source": source} for name, source in documents]
    for loaded, (name, source) in zip(run_example(["--import"], json.dumps(imports)), documents):
        assert "error" not in loaded, (name, loaded.get("error"))
        assert loaded["name"] == name
        assert_same(name, loaded, observe(LayeredPixelCanvas.from_source(source)))
        assert_same(name, loaded, observe(LayeredPixelCanvas.from_source(loaded["source"])))
        assert loaded["source"]["version"] == 2
    broken = malformed_documents()
    reports = run_example(["--import"], json.dumps([{"name": n, "source": s} for n, s in broken]))
    for report, (name, source) in zip(reports, broken):
        assert "error" in report, (name, "Rust accepted a malformed document")
        try:
            LayeredPixelCanvas.from_source(source)
        except (ValueError, KeyError, TypeError):
            continue
        raise AssertionError((name, "Python accepted a malformed document"))
    print("layered JSON interchange ok")


if __name__ == "__main__":
    main()
