from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image

from pixel_layers import LayeredPixelCanvas

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
try:
    ordered.move_layer("sideways")
except ValueError:
    pass
else:
    raise AssertionError("invalid layer direction must be rejected")

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
    before_rename = visibility.to_source()
    try:
        visibility.rename_layer(invalid_name)
    except ValueError:
        pass
    else:
        raise AssertionError("invalid or duplicate layer name must be rejected")
    assert visibility.to_source() == before_rename
try:
    visibility.set_layer_visibility(1)
except ValueError:
    pass
else:
    raise AssertionError("non-boolean layer visibility must be rejected")

legacy_visibility = LayeredPixelCanvas.from_source({
    "canvas_size": 2,
    "active_layer": "背景",
    "layers": [{"name": "背景", "source": {
        "canvas_size": 2,
        "pixels": [[None, None], [None, None]],
    }}],
})
assert legacy_visibility.is_layer_visible("背景")

with TemporaryDirectory() as directory:
    path = Path(directory) / "layered-refined.png"
    restored_layers.save_png(path)
    with Image.open(path) as exported:
        assert exported.size == (8, 8)
        assert exported.getpixel((3, 2)) == (0, 0, 255, 255)

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


def expect_invalid(source):
    try:
        LayeredPixelCanvas.from_source(source)
    except ValueError:
        return
    raise AssertionError("invalid layered project must be rejected")

base_layer = {
    "canvas_size": 2,
    "pixels": [[None, None], [None, None]],
}
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
expect_invalid(
    {
        "canvas_size": 2,
        "active_layer": "",
        "layers": [{"name": "", "source": base_layer}],
    }
)
expect_invalid(
    {
        "canvas_size": 2,
        "active_layer": "不存在",
        "layers": [{"name": "背景", "source": base_layer}],
    }
)
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
expect_invalid(
    {
        "canvas_size": 4,
        "active_layer": "背景",
        "layers": [{"name": "背景", "source": base_layer}],
    }
)

print("layer backend ok")
