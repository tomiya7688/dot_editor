from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image

from pixel_layers import LayeredPixelCanvas


def expect_invalid(source) -> None:
    try:
        LayeredPixelCanvas.from_source(source)
    except ValueError:
        return
    raise AssertionError("invalid layered project must be rejected")


layers = LayeredPixelCanvas(4)
layers.add_layer("人物")
layers.paint(1, 1, (100, 20, 20, 255))
assert layers.split_cell(1, 1)
layers.paint(1, 1, (20, 20, 180, 255), child=(1, 0))

layers.select_layer("背景")
layers.paint(0, 0, (0, 0, 30, 255))
composite = layers.composite()
assert composite.size == (8, 8)
assert composite.getpixel((0, 0)) == (0, 0, 30, 255)
assert composite.getpixel((3, 2)) == (20, 20, 180, 255)

restored_layers = LayeredPixelCanvas.from_source(layers.to_source())
assert set(restored_layers.layers) == {"背景", "人物"}
restored_layers.select_layer("人物")
assert restored_layers.is_split(1, 1)
assert restored_layers.composite().tobytes() == composite.tobytes()

with TemporaryDirectory() as directory:
    path = Path(directory) / "layered-refined.png"
    restored_layers.save_png(path)
    with Image.open(path) as exported:
        assert exported.size == (8, 8)
        assert exported.getpixel((3, 2)) == (20, 20, 180, 255)


# Every layer changes logical resolution together without destroying its fine image.
resizable = LayeredPixelCanvas(16)
resizable.paint(0, 0, (0, 0, 30, 255))
resizable.add_layer("人物")
resizable.paint(1, 0, (120, 30, 30, 255))
before_16 = resizable.composite((16, 16)).tobytes()

assert resizable.set_resolution(7, 7)
assert resizable.resolution == (7, 7)
assert {layer.resolution for layer in resizable.layers.values()} == {(7, 7)}
assert resizable.set_resolution(16, 16)
assert resizable.composite((16, 16)).tobytes() == before_16

assert resizable.set_resolution(23, 17)
assert resizable.resolution == (23, 17)
assert {layer.resolution for layer in resizable.layers.values()} == {(23, 17)}
rect_source = resizable.to_source()
assert rect_source["canvas_size"] == [23, 17]
rect_restored = LayeredPixelCanvas.from_source(rect_source)
assert rect_restored.resolution == (23, 17)
assert rect_restored.to_source() == rect_source

with TemporaryDirectory() as directory:
    path = Path(directory) / "rect.png"
    rect_restored.save_png(path, (230, 170))
    with Image.open(path) as exported:
        assert exported.size == (230, 170)


# Preserve keeps variation; discard removes only the selected active-layer region.
detail_layers = LayeredPixelCanvas(4)
detail_layers.add_layer("人物")
assert detail_layers.paint(1, 1, (100, 20, 20, 255))
assert detail_layers.split_cell(1, 1)
assert detail_layers.paint(1, 1, (20, 20, 180, 255), child=(1, 0))
assert detail_layers.paint(
    1,
    1,
    (140, 100, 80, 255),
    detail_policy="preserve",
)
assert detail_layers.has_detail_at(1, 1)
children = {
    detail_layers.sample(1, 1, (child_x, child_y))
    for child_y in range(2)
    for child_x in range(2)
}
assert len(children) > 1

assert detail_layers.collapse_cell(1, 1)
assert not detail_layers.is_split(1, 1)
assert detail_layers.has_detail_at(1, 1)
assert detail_layers.split_cell(1, 1)
assert len({
    detail_layers.sample(1, 1, (child_x, child_y))
    for child_y in range(2)
    for child_x in range(2)
}) > 1

assert detail_layers.discard_detail(1, 1) == 1
assert not detail_layers.has_detail_at(1, 1)
assert detail_layers.active.undo()
assert detail_layers.has_detail_at(1, 1)


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
                    "canvas_size": [2, 3],
                    "canvas_width": 2,
                    "canvas_height": 3,
                    "pixels": [[None, None] for _ in range(3)],
                },
            },
        ],
    }
)
expect_invalid(
    {
        "canvas_width": 3,
        "canvas_height": 2,
        "canvas_size": [3, 2],
        "active_layer": "背景",
        "layers": [{"name": "背景", "source": base_layer}],
    }
)

print("layer backend ok")
