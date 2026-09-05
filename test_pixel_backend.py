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
print("pixel backend ok")
