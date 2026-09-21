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
