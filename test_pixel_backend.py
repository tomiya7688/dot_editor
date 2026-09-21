from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image

from pixel_backend import PixelCanvas


def expect_value_error(callback) -> None:
    try:
        callback()
    except ValueError:
        return
    raise AssertionError("expected ValueError")


# Basic editing and history.
canvas = PixelCanvas(4)
assert canvas.paint(1, 1, (255, 0, 0, 255))
assert canvas.sample(1, 1) == (255, 0, 0, 255)
assert canvas.undo() and canvas.sample(1, 1)[3] == 0
assert canvas.redo() and canvas.sample(1, 1) == (255, 0, 0, 255)
assert canvas.fill(0, 0, (0, 255, 0, 255)) == 15
assert canvas.sample(3, 3) == (0, 255, 0, 255)

source = canvas.to_source()
restored = PixelCanvas.from_source(source)
assert restored.resolution == (4, 4)
assert restored.sample(1, 1) == (255, 0, 0, 255)

assert canvas.upscale()
assert canvas.resolution == (8, 8)
assert canvas.sample(2, 2) == (255, 0, 0, 255)
assert canvas.render(32).size == (32, 32)

with TemporaryDirectory() as directory:
    path = Path(directory) / "export.png"
    canvas.save_png(path, 16)
    with Image.open(path) as exported:
        assert exported.size == (16, 16)


# Local refinement survives save/load, collapse and re-expansion.
refined = PixelCanvas(4)
assert refined.paint(1, 1, (100, 20, 20, 255))
assert refined.split_cell(1, 1)
assert refined.paint(1, 1, (20, 20, 180, 255), child=(1, 0))
assert refined.paint(1, 1, (0, 0, 0, 0), erase=True, child=(0, 1))

native = refined.render()
assert native.size == (8, 8)
assert native.getpixel((3, 2)) == (20, 20, 180, 255)
assert native.getpixel((2, 3))[3] == 0

refined_source = refined.to_source()
assert refined_source["refined_cells"][0]["x"] == 1
refined_restored = PixelCanvas.from_source(refined_source)
assert refined_restored.is_split(1, 1)
assert refined_restored.render().tobytes() == native.tobytes()

# A coarse preserve edit changes the coarse color but keeps child variation.
assert refined_restored.paint(
    1,
    1,
    (140, 100, 80, 255),
    detail_policy="preserve",
)
assert refined_restored.sample(1, 1) == (140, 100, 80, 255)
children = {
    refined_restored.sample(1, 1, (child_x, child_y))
    for child_y in range(2)
    for child_x in range(2)
}
assert len(children) > 1

assert refined_restored.collapse_cell(1, 1)
assert not refined_restored.is_split(1, 1)
assert refined_restored.has_detail_at(1, 1)
assert refined_restored.render().size == (4, 4)
collapsed_source = refined_restored.to_source()
collapsed = PixelCanvas.from_source(collapsed_source)
assert not collapsed.is_split(1, 1)
assert collapsed.has_detail_at(1, 1)
assert collapsed.split_cell(1, 1)
assert len({
    collapsed.sample(1, 1, (child_x, child_y))
    for child_y in range(2)
    for child_x in range(2)
}) > 1

# Discard is explicit, local, and undoable.
assert collapsed.paint(
    1,
    1,
    (255, 255, 0, 255),
    detail_policy="discard",
)
assert not collapsed.is_split(1, 1)
assert not collapsed.has_detail_at(1, 1)
assert collapsed.sample(1, 1) == (255, 255, 0, 255)
assert collapsed.undo()
assert collapsed.is_split(1, 1)
assert collapsed.has_detail_at(1, 1)
assert collapsed.redo()
assert not collapsed.has_detail_at(1, 1)

local_detail = PixelCanvas(4)
for point in ((0, 0), (1, 0), (2, 0)):
    assert local_detail.split_cell(*point)
assert local_detail.paint(0, 0, (120, 0, 0, 255), child=(1, 1))
assert local_detail.paint(1, 0, (0, 120, 0, 255), child=(1, 1))
assert local_detail.paint(2, 0, (0, 0, 120, 255), child=(1, 1))
assert local_detail.discard_detail(0, 0, width=2, height=1) == 2
assert not local_detail.has_detail_at(0, 0)
assert not local_detail.has_detail_at(1, 0)
assert local_detail.has_detail_at(2, 0)
assert local_detail.undo()
assert local_detail.has_detail_at(0, 0)
assert local_detail.has_detail_at(1, 0)
assert local_detail.has_detail_at(2, 0)


# Arbitrary resolution round-trip is non-destructive.
arbitrary = PixelCanvas(16)
assert arbitrary.paint(0, 0, (80, 30, 30, 255))
assert arbitrary.paint(1, 0, (120, 30, 30, 255))
assert arbitrary.paint(15, 15, (30, 80, 120, 255))
original_16 = arbitrary.render_resolution(16, 16).tobytes()
assert arbitrary.set_resolution(7, 7)
assert arbitrary.resolution == (7, 7)
assert arbitrary.set_resolution(16, 16)
assert arbitrary.render_resolution(16, 16).tobytes() == original_16

# Coarse preserve edit keeps fine variation.
assert arbitrary.set_resolution(7, 7)
assert arbitrary.paint(0, 0, (160, 90, 90, 255), detail_policy="preserve")
assert arbitrary.sample(0, 0) == (160, 90, 90, 255)
assert arbitrary.set_resolution(16, 16)
fine_region = {
    arbitrary.sample(x, y)
    for y in range(3)
    for x in range(3)
}
assert len(fine_region) > 1

# Non-square and non-preset resolutions are first-class.
assert arbitrary.set_resolution(23, 17)
assert arbitrary.resolution == (23, 17)
assert arbitrary.width == 23
assert arbitrary.height == 17
assert arbitrary.render().size == (23, 17)
expect_value_error(lambda: arbitrary.size)

# Save/load retains the active resolution and high-detail backing data.
saved = arbitrary.to_source()
assert saved["canvas_width"] == 23
assert saved["canvas_height"] == 17
assert saved["canvas_size"] == [23, 17]
saved_restore = PixelCanvas.from_source(saved)
assert saved_restore.resolution == (23, 17)
assert saved_restore.to_source() == saved

history = PixelCanvas(16)
assert history.paint(0, 0, (10, 20, 30, 255))
assert history.paint(1, 0, (80, 90, 100, 255))
history_16 = history.render_resolution(16, 16).tobytes()
assert history.set_resolution(7, 7)
history_source = history.to_source()
history_restored = PixelCanvas.from_source(history_source)
assert history_restored.resolution == (7, 7)
assert history_restored.set_resolution(16, 16)
assert history_restored.render_resolution(16, 16).tobytes() == history_16

# Coarse discard removes old detail and Undo restores it.
discard = PixelCanvas(16)
assert discard.paint(0, 0, (40, 40, 40, 255))
assert discard.paint(1, 0, (100, 40, 40, 255))
assert discard.set_resolution(7, 7)
assert discard.has_detail_at(0, 0)
assert discard.paint(0, 0, (0, 200, 0, 255), detail_policy="discard")
assert not discard.has_detail_at(0, 0)
assert discard.undo()
assert discard.has_detail_at(0, 0)

# Legacy projects remain readable.
legacy = PixelCanvas.from_source(
    {
        "canvas_size": 2,
        "pixels": [
            ["#112233", None],
            [None, "#445566"],
        ],
    }
)
assert legacy.resolution == (2, 2)
assert legacy.sample(0, 0) == (17, 34, 51, 255)

expect_value_error(lambda: PixelCanvas(0))
expect_value_error(lambda: PixelCanvas(PixelCanvas.MAX_RESOLUTION + 1))
expect_value_error(
    lambda: local_detail.paint(
        0,
        0,
        (0, 0, 0, 255),
        detail_policy="invalid",  # type: ignore[arg-type]
    )
)
expect_value_error(lambda: PixelCanvas.from_source(["not", "an", "object"]))  # type: ignore[arg-type]

print("pixel backend ok")
