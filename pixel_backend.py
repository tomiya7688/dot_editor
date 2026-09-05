from __future__ import annotations

from collections import deque
from pathlib import Path
from typing import Any

from PIL import Image


class PixelCanvas:
    """GUI-independent pixel canvas shared by editors and tools."""

    SUPPORTED_SIZES = (2, 4, 8, 16, 32, 64, 128, 256)
    HISTORY_LIMIT = 50

    def __init__(self, size: int = 16) -> None:
        self._validate_size(size)
        self.size = size
        self.image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        self._history: list[Image.Image] = []
        self._future: list[Image.Image] = []

    @classmethod
    def _validate_size(cls, size: int) -> None:
        if size not in cls.SUPPORTED_SIZES:
            raise ValueError(f"unsupported canvas size: {size}")

    def _snapshot(self) -> None:
        self._history.append(self.image.copy())
        if len(self._history) > self.HISTORY_LIMIT:
            del self._history[0]
        self._future.clear()

    def new(self, size: int | None = None) -> None:
        target = self.size if size is None else size
        self._validate_size(target)
        self._snapshot()
        self.size = target
        self.image = Image.new("RGBA", (target, target), (0, 0, 0, 0))

    def paint(self, x: int, y: int, color: tuple[int, int, int, int], erase: bool = False) -> bool:
        if not (0 <= x < self.size and 0 <= y < self.size):
            return False
        replacement = (0, 0, 0, 0) if erase else tuple(color)
        if self.image.getpixel((x, y)) == replacement:
            return False
        self._snapshot()
        self.image.putpixel((x, y), replacement)
        return True

    def sample(self, x: int, y: int) -> tuple[int, int, int, int]:
        if not (0 <= x < self.size and 0 <= y < self.size):
            raise IndexError("pixel coordinate out of range")
        return self.image.getpixel((x, y))

    def fill(self, x: int, y: int, color: tuple[int, int, int, int], erase: bool = False) -> int:
        if not (0 <= x < self.size and 0 <= y < self.size):
            return 0
        replacement = (0, 0, 0, 0) if erase else tuple(color)
        original = self.image.getpixel((x, y))
        if original == replacement:
            return 0
        points: list[tuple[int, int]] = []
        pending = deque([(x, y)])
        visited = {(x, y)}
        while pending:
            px, py = pending.popleft()
            if self.image.getpixel((px, py)) != original:
                continue
            points.append((px, py))
            for nx, ny in ((px - 1, py), (px + 1, py), (px, py - 1), (px, py + 1)):
                if 0 <= nx < self.size and 0 <= ny < self.size and (nx, ny) not in visited:
                    visited.add((nx, ny))
                    pending.append((nx, ny))
        if not points:
            return 0
        self._snapshot()
        for point in points:
            self.image.putpixel(point, replacement)
        return len(points)

    def import_image(self, source: str | Path | Image.Image) -> None:
        loaded = Image.open(source).convert("RGBA") if not isinstance(source, Image.Image) else source.convert("RGBA")
        ratio = min(1.0, self.size / loaded.width, self.size / loaded.height)
        target_size = (max(1, round(loaded.width * ratio)), max(1, round(loaded.height * ratio)))
        fitted = Image.new("RGBA", (self.size, self.size), (0, 0, 0, 0))
        resized = loaded.resize(target_size, Image.Resampling.NEAREST)
        fitted.alpha_composite(resized, ((self.size - target_size[0]) // 2, (self.size - target_size[1]) // 2))
        self._snapshot()
        self.image = fitted

    def upscale(self) -> bool:
        if self.size >= self.SUPPORTED_SIZES[-1]:
            return False
        target = self.size * 2
        self._snapshot()
        self.image = self.image.resize((target, target), Image.Resampling.NEAREST)
        self.size = target
        return True

    def undo(self) -> bool:
        if not self._history:
            return False
        self._future.append(self.image.copy())
        self.image = self._history.pop()
        self.size = self.image.width
        return True

    def redo(self) -> bool:
        if not self._future:
            return False
        self._history.append(self.image.copy())
        self.image = self._future.pop()
        self.size = self.image.width
        return True

    def render(self, display_size: int | None = None) -> Image.Image:
        """Return a nearest-neighbour view without changing the logical canvas."""
        if display_size is None:
            return self.image.copy()
        if display_size <= 0:
            raise ValueError("display size must be positive")
        return self.image.resize((display_size, display_size), Image.Resampling.NEAREST)

    def save_png(self, path: str | Path, export_size: int | None = None) -> None:
        output = self.image
        if export_size is not None:
            if export_size < self.size:
                raise ValueError("export size cannot be smaller than canvas size")
            output = output.resize((export_size, export_size), Image.Resampling.NEAREST)
        output.save(path, "PNG")

    def to_source(self) -> dict[str, Any]:
        pixels: list[list[str | None]] = []
        for y in range(self.size):
            row: list[str | None] = []
            for x in range(self.size):
                red, green, blue, alpha = self.image.getpixel((x, y))
                row.append(None if alpha == 0 else f"#{red:02X}{green:02X}{blue:02X}")
            pixels.append(row)
        return {"canvas_size": self.size, "pixels": pixels}

    @classmethod
    def from_source(cls, source: dict[str, Any]) -> "PixelCanvas":
        size = source.get("canvas_size")
        pixels = source.get("pixels")
        if not isinstance(size, int) or not isinstance(pixels, list):
            raise ValueError("invalid pixel source")
        canvas = cls(size)
        if len(pixels) != size or any(not isinstance(row, list) or len(row) != size for row in pixels):
            raise ValueError("pixel source dimensions do not match canvas size")
        for y, row in enumerate(pixels):
            for x, value in enumerate(row):
                if value is None:
                    continue
                if not isinstance(value, str) or len(value) != 7 or value[0] != "#":
                    raise ValueError("pixel colors must use #RRGGBB")
                try:
                    color = tuple(int(value[index:index + 2], 16) for index in (1, 3, 5))
                except ValueError as error:
                    raise ValueError("pixel colors must use #RRGGBB") from error
                canvas.image.putpixel((x, y), (*color, 255))
        return canvas
