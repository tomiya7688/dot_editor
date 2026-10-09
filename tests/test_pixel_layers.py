from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image

from pixel_layers import LayeredPixelCanvas

# レイヤー追加後の親画素・子画素を合成し、JSON往復後にも状態が保たれることを確認する。
layers = LayeredPixelCanvas(4)
layers.add_layer("人物")
layers.paint(1, 1, (255, 0, 0, 255))
assert layers.split_cell(1, 1)
layers.paint(1, 1, (0, 0, 255, 255), child=(1, 0))

layers.select_layer("背景")
layers.paint(0, 0, (0, 0, 30, 255))
composite = layers.composite()
assert composite.size == (8, 8)
assert composite.getpixel((0, 0)) == (0, 0, 30, 255)
assert composite.getpixel((3, 2)) == (0, 0, 255, 255)
assert composite.getpixel((2, 2)) == (255, 0, 0, 255)

restored_layers = LayeredPixelCanvas.from_source(layers.to_source())
assert set(restored_layers.layers) == {"背景", "人物"}
restored_layers.select_layer("人物")
assert restored_layers.is_split(1, 1)
assert restored_layers.sample(1, 1, (1, 0)) == (0, 0, 255, 255)
assert restored_layers.composite().tobytes() == composite.tobytes()

restored_layers.select_layer("背景")
assert restored_layers.composite().getpixel((3, 2)) == (0, 0, 255, 255)

# レイヤー順の変更を合成結果へ反映し、Undo・Redoで順序と表示を復元する。
ordered = LayeredPixelCanvas(2)
ordered.paint(0, 0, (255, 0, 0, 255))
ordered.add_layer("人物")
ordered.paint(0, 0, (0, 0, 255, 255))
assert ordered.composite().getpixel((0, 0)) == (0, 0, 255, 255)
ordered.select_layer("背景")
assert ordered.move_layer("up")
assert list(ordered.layers) == ["人物", "背景"]
assert ordered.composite().getpixel((0, 0)) == (255, 0, 0, 255)
assert ordered.undo()
assert list(ordered.layers) == ["背景", "人物"]
assert ordered.composite().getpixel((0, 0)) == (0, 0, 255, 255)
assert ordered.redo()
assert list(ordered.layers) == ["人物", "背景"]
assert not ordered.move_layer("up")
# 無効な移動方向は例外として拒否する。
try:
    ordered.move_layer("sideways")
except ValueError:
    pass
else:
    raise AssertionError("invalid layer direction must be rejected")

# 可視状態の切替を合成へ反映し、Undo・RedoとJSON往復後にも保持する。
visibility = LayeredPixelCanvas(2)
visibility.paint(0, 0, (255, 0, 0, 255))
visibility.add_layer("人物")
visibility.paint(0, 0, (0, 0, 255, 255))
assert visibility.is_layer_visible()
assert visibility.composite().getpixel((0, 0)) == (0, 0, 255, 255)
assert visibility.set_layer_visibility(False)
assert not visibility.is_layer_visible()
assert visibility.composite().getpixel((0, 0)) == (255, 0, 0, 255)
assert visibility.render_resolution(4, 4).getpixel((0, 0)) == (255, 0, 0, 255)
assert visibility.undo()
assert visibility.is_layer_visible()
assert visibility.redo()
source_with_hidden_layer = visibility.to_source()
assert source_with_hidden_layer["layers"][1]["visible"] is False
visibility_copy = LayeredPixelCanvas.from_source(source_with_hidden_layer)
assert not visibility_copy.is_layer_visible("人物")
assert visibility_copy.composite().tobytes() == visibility.composite().tobytes()
assert not visibility.set_layer_visibility(False)
assert visibility.rename_layer("人物レイヤー")
assert visibility.active_layer == "人物レイヤー"
assert visibility.is_layer_visible("人物レイヤー") is False
assert list(visibility.layers) == ["背景", "人物レイヤー"]
assert visibility.undo()
assert "人物" in visibility.layers
assert visibility.redo()
assert "人物レイヤー" in visibility.layers
for invalid_name in ("", "   ", "背景"):
    # 空名・空白名・予約済み背景名を拒否し、レイヤー状態を変えない。
    before_rename = visibility.to_source()
    try:
        visibility.rename_layer(invalid_name)
    except ValueError:
        pass
    else:
        raise AssertionError("invalid or duplicate layer name must be rejected")
    assert visibility.to_source() == before_rename
# 可視状態に真偽値以外を渡した場合は拒否する。
try:
    visibility.set_layer_visibility(1)
except ValueError:
    pass
else:
    raise AssertionError("non-boolean layer visibility must be rejected")

# 旧形式で可視状態が省略されたレイヤーは、既定で表示される。
legacy_visibility = LayeredPixelCanvas.from_source({
    "canvas_size": 2,
    "active_layer": "背景",
    "layers": [{"name": "背景", "source": {
        "canvas_size": 2,
        "pixels": [[None, None], [None, None]],
    }}],
})
assert legacy_visibility.is_layer_visible("背景")

# 保存したレイヤー合成をPNGへ出力し、寸法と子画素の色を確認する。
with TemporaryDirectory() as directory:
    path = Path(directory) / "layered-refined.png"
    restored_layers.save_png(path)
    with Image.open(path) as exported:
        assert exported.size == (8, 8)
        assert exported.getpixel((3, 2)) == (0, 0, 255, 255)

# 解像度変更後も各レイヤーの画素を保ち、保存・再読込と縮小を確認する。
resizable = LayeredPixelCanvas(2)
resizable.paint(0, 0, (0, 0, 30, 255))
resizable.add_layer("人物")
resizable.paint(1, 1, (255, 0, 0, 255))
assert resizable.resize(4)
assert resizable.size == 4
assert {layer.size for layer in resizable.layers.values()} == {4}
resizable.select_layer("背景")
assert resizable.sample(0, 0) == (0, 0, 30, 255)
resizable.select_layer("人物")
assert resizable.sample(2, 2) == (255, 0, 0, 255)
resized_source = resizable.to_source()
resizable_restored = LayeredPixelCanvas.from_source(resized_source)
assert resizable_restored.to_source() == resized_source
assert resizable_restored.resize(2)
assert {layer.size for layer in resizable_restored.layers.values()} == {2}
resizable_restored.select_layer("人物")
assert resizable_restored.sample(1, 1) == (255, 0, 0, 255)

# 細部保持・折りたたみ・再展開・局所破棄を通して親子画素とUndoを確認する。
detail_layers = LayeredPixelCanvas(4)
detail_layers.add_layer("人物")
assert detail_layers.paint(1, 1, (255, 0, 0, 255))
assert detail_layers.split_cell(1, 1)
assert detail_layers.paint(1, 1, (0, 0, 255, 255), child=(1, 0))
assert detail_layers.paint(
    1,
    1,
    (0, 255, 0, 255),
    detail_policy="preserve",
)
assert detail_layers.is_split(1, 1)
assert detail_layers.sample(1, 1) == (0, 255, 0, 255)
assert detail_layers.sample(1, 1, (1, 0)) == (0, 0, 255, 255)
assert detail_layers.collapse_cell(1, 1)
assert not detail_layers.is_split(1, 1)
assert detail_layers.has_detail_at(1, 1)
assert detail_layers.has_detail
assert detail_layers.split_cell(1, 1)
assert detail_layers.sample(1, 1, (1, 0)) == (0, 0, 255, 255)
assert detail_layers.discard_detail(1, 1) == 1
assert not detail_layers.is_split(1, 1)
assert detail_layers.active.undo()
assert detail_layers.is_split(1, 1)
assert detail_layers.sample(1, 1, (1, 0)) == (0, 0, 255, 255)


# {
#   責務: [expect_invalid: 不正なレイヤープロジェクトを読み込み時に拒否する]
#   処理: [
#     1: LayeredPixelCanvas.from_sourceへ入力を渡す
#     2: ValueErrorを受け取った場合は不正入力として正常終了する
#     3: 読み込みが成功した場合はAssertionErrorで検証失敗を通知する
#   ]
#   引数: [source: 読み込み可否を確認するプロジェクト形式]
#   戻り値: [なし、不正形式では正常終了し、受理された場合はAssertionErrorを送出する]
# }
def expect_invalid(source):
    try:
        LayeredPixelCanvas.from_source(source)
    except ValueError:
        return
    raise AssertionError("invalid layered project must be rejected")

# 次の入力群で重複名・空名・不正な選択先・レイヤー間の寸法不整合を拒否する。
base_layer = {
    "canvas_size": 2,
    "pixels": [[None, None], [None, None]],
}
# 重複するレイヤー名を含むプロジェクトを拒否する。
expect_invalid(
    {
        "canvas_size": 2,
        "active_layer": "背景",
        "layers": [
            {"name": "背景", "source": base_layer},
            {"name": "背景", "source": base_layer},
        ],
    }
)
# 空のレイヤー名とactive_layerを拒否する。
expect_invalid(
    {
        "canvas_size": 2,
        "active_layer": "",
        "layers": [{"name": "", "source": base_layer}],
    }
)
# active_layerが実在するレイヤーを指さないプロジェクトを拒否する。
expect_invalid(
    {
        "canvas_size": 2,
        "active_layer": "不存在",
        "layers": [{"name": "背景", "source": base_layer}],
    }
)
# レイヤーごとに保存されたCanvas解像度が揃わないプロジェクトを拒否する。
expect_invalid(
    {
        "canvas_size": 2,
        "active_layer": "背景",
        "layers": [
            {"name": "背景", "source": base_layer},
            {
                "name": "人物",
                "source": {
                    "canvas_size": 4,
                    "pixels": [[None] * 4 for _ in range(4)],
                },
            },
        ],
    }
)
# トップレベルとレイヤーCanvasの解像度が一致しないプロジェクトを拒否する。
expect_invalid(
    {
        "canvas_size": 4,
        "active_layer": "背景",
        "layers": [{"name": "背景", "source": base_layer}],
    }
)

print("layer backend ok")
