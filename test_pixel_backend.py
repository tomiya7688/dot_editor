from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image

from pixel_backend import PixelCanvas

canvas = PixelCanvas(4)
assert canvas.paint(1, 1, (255, 0, 0, 255))
assert canvas.sample(1, 1) == (255, 0, 0, 255)
assert canvas.undo() and canvas.sample(1, 1)[3] == 0
assert canvas.redo() and canvas.sample(1, 1) == (255, 0, 0, 255)
assert canvas.fill(0, 0, (0, 255, 0, 255)) == 15
assert canvas.sample(3, 3) == (0, 255, 0, 255)
source = canvas.to_source()
restored = PixelCanvas.from_source(source)
assert restored.size == 4 and restored.sample(1, 1) == (255, 0, 0, 255)
canvas.upscale()
assert canvas.size == 8 and canvas.sample(2, 2) == (255, 0, 0, 255)
assert canvas.render(32).size == (32, 32)
with TemporaryDirectory() as directory:
    path = Path(directory) / "export.png"
    canvas.save_png(path, 16)
    assert Image.open(path).size == (16, 16)

refined = PixelCanvas(4)
assert refined.paint(1, 1, (255, 0, 0, 255))
assert refined.split_cell(1, 1)
for child_y in range(2):
    for child_x in range(2):
        assert refined.sample(1, 1, (child_x, child_y)) == (255, 0, 0, 255)

assert refined.paint(1, 1, (0, 0, 255, 255), child=(1, 0))
assert refined.paint(1, 1, (0, 0, 0, 0), erase=True, child=(0, 1))
assert refined.sample(1, 1, (1, 0)) == (0, 0, 255, 255)
assert refined.sample(1, 1, (0, 1))[3] == 0

native = refined.render()
assert native.size == (8, 8)
assert native.getpixel((3, 2)) == (0, 0, 255, 255)
assert native.getpixel((2, 3))[3] == 0

refined_source = refined.to_source()
assert refined_source["refined_cells"][0]["x"] == 1
refined_restored = PixelCanvas.from_source(refined_source)
assert refined_restored.is_split(1, 1)
assert refined_restored.sample(1, 1, (1, 0)) == (0, 0, 255, 255)
assert refined_restored.render().tobytes() == native.tobytes()

legacy = PixelCanvas.from_source(
    {
        "canvas_size": 2,
        "pixels": [
            ["#112233", None],
            [None, "#445566"],
        ],
    }
)
assert not legacy.has_refinements
assert legacy.sample(0, 0) == (17, 34, 51, 255)

with TemporaryDirectory() as directory:
    path = Path(directory) / "refined.png"
    refined_restored.save_png(path)
    with Image.open(path) as exported:
        assert exported.size == (8, 8)
        assert exported.getpixel((3, 2)) == (0, 0, 255, 255)
        assert exported.getpixel((2, 3))[3] == 0

assert refined_restored.resize(8)
assert refined_restored.size == 8
assert not refined_restored.has_refinements
assert refined_restored.sample(3, 2) == (0, 0, 255, 255)

resized = PixelCanvas(2)
resized.paint(0, 0, (255, 0, 0, 255))
resized.paint(1, 0, (0, 255, 0, 255))
resized.paint(0, 1, (0, 0, 255, 255))
resized.paint(1, 1, (255, 255, 0, 255))
original = resized.to_source()
assert resized.resize(4)
assert resized.size == 4
assert resized.sample(0, 0) == (255, 0, 0, 255)
assert resized.sample(1, 1) == (255, 0, 0, 255)
assert resized.sample(2, 0) == (0, 255, 0, 255)
assert resized.sample(0, 2) == (0, 0, 255, 255)
assert resized.sample(3, 3) == (255, 255, 0, 255)
assert PixelCanvas.from_source(resized.to_source()).to_source() == resized.to_source()
assert resized.resize(2)
assert resized.to_source() == original

detail_policy = PixelCanvas(4)
assert detail_policy.paint(1, 1, (255, 0, 0, 255))
assert detail_policy.split_cell(1, 1)
assert detail_policy.paint(1, 1, (0, 0, 255, 255), child=(1, 0))
assert detail_policy.paint(1, 1, (0, 255, 0, 255), detail_policy="preserve")
assert detail_policy.sample(1, 1) == (0, 255, 0, 255)
assert detail_policy.is_split(1, 1)
assert detail_policy.sample(1, 1, (1, 0)) == (0, 0, 255, 255)

assert detail_policy.collapse_cell(1, 1)
assert not detail_policy.is_split(1, 1)
assert detail_policy.has_detail_at(1, 1)
assert detail_policy.has_detail
assert not detail_policy.has_refinements
assert detail_policy.render().size == (4, 4)
assert detail_policy.sample(1, 1) == (0, 255, 0, 255)
assert detail_policy.sample(1, 1, (1, 0)) == (0, 0, 255, 255)

preserved_source = detail_policy.to_source()
assert preserved_source["refined_cells"][0]["expanded"] is False
preserved_restored = PixelCanvas.from_source(preserved_source)
assert not preserved_restored.is_split(1, 1)
assert preserved_restored.has_detail_at(1, 1)
assert preserved_restored.sample(1, 1) == (0, 255, 0, 255)
assert preserved_restored.sample(1, 1, (1, 0)) == (0, 0, 255, 255)
assert preserved_restored.split_cell(1, 1)
assert preserved_restored.is_split(1, 1)
assert preserved_restored.sample(1, 1, (1, 0)) == (0, 0, 255, 255)

assert detail_policy.split_cell(1, 1)
assert detail_policy.paint(
    1,
    1,
    (255, 255, 0, 255),
    detail_policy="discard",
)
assert not detail_policy.is_split(1, 1)
assert detail_policy.sample(1, 1) == (255, 255, 0, 255)
assert detail_policy.undo()
assert detail_policy.is_split(1, 1)
assert detail_policy.sample(1, 1) == (0, 255, 0, 255)
assert detail_policy.sample(1, 1, (1, 0)) == (0, 0, 255, 255)
assert detail_policy.redo()
assert not detail_policy.is_split(1, 1)

local_detail = PixelCanvas(4)
for point in ((0, 0), (1, 0), (2, 0)):
    assert local_detail.split_cell(*point)
assert local_detail.paint(0, 0, (255, 0, 0, 255), child=(1, 1))
assert local_detail.paint(1, 0, (0, 255, 0, 255), child=(1, 1))
assert local_detail.paint(2, 0, (0, 0, 255, 255), child=(1, 1))
assert local_detail.discard_detail(0, 0, width=2, height=1) == 2
assert not local_detail.is_split(0, 0)
assert not local_detail.is_split(1, 0)
assert local_detail.is_split(2, 0)
assert local_detail.undo()
assert local_detail.is_split(0, 0)
assert local_detail.is_split(1, 0)
assert local_detail.is_split(2, 0)
assert local_detail.sample(1, 0, (1, 1)) == (0, 255, 0, 255)

try:
    local_detail.paint(0, 0, (0, 0, 0, 255), detail_policy="invalid")  # type: ignore[arg-type]
except ValueError:
    pass
else:
    raise AssertionError("invalid detail policy must be rejected")

try:
    resized.resize(3)
except ValueError:
    pass
else:
    raise AssertionError("unsupported logical size must be rejected")

try:
    PixelCanvas.from_source(["not", "an", "object"])  # type: ignore[arg-type]
except ValueError:
    pass
else:
    raise AssertionError("non-object pixel project must be rejected")

print("pixel backend ok")
