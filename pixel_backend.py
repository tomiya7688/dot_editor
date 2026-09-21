from __future__ import annotations

from collections import deque
from pathlib import Path
from typing import Any, Literal

from PIL import Image

Color = tuple[int, int, int, int]
ChildCoordinate = tuple[int, int]
RefinedCells = dict[tuple[int, int], list[list[Color]]]
DetailPolicy = Literal["preserve", "discard"]


class PixelCanvas:
    """GUI-independent pixel canvas shared by editors and tools."""

    SUPPORTED_SIZES = (2, 4, 8, 16, 32, 64, 128, 256)
    HISTORY_LIMIT = 50

    def __init__(self, size: int = 16) -> None:
        self._validate_size(size)
        self.size = size
        self.image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        self._refined_cells: RefinedCells = {}
        self._history: list[tuple[Image.Image, RefinedCells]] = []
        self._future: list[tuple[Image.Image, RefinedCells]] = []

    @classmethod
    def _validate_size(cls, size: int) -> None:
        if size not in cls.SUPPORTED_SIZES:
            raise ValueError(f"unsupported canvas size: {size}")

    @staticmethod
    def _normalize_color(color: tuple[int, ...]) -> Color:
        values = tuple(int(component) for component in color)
        if len(values) == 3:
            values += (255,)
        if len(values) != 4 or any(component < 0 or component > 255 for component in values):
            raise ValueError("color must contain 3 or 4 components in the range 0..255")
        return values  # type: ignore[return-value]

    @staticmethod
    def _copy_refined_cells(source: RefinedCells) -> RefinedCells:
        return {
            key: [[tuple(color) for color in row] for row in rows]
            for key, rows in source.items()
        }

    def _state(self) -> tuple[Image.Image, RefinedCells]:
        return self.image.copy(), self._copy_refined_cells(self._refined_cells)

    def _restore_state(self, state: tuple[Image.Image, RefinedCells]) -> None:
        image, refined = state
        self.image = image.copy()
        self.size = self.image.width
        self._refined_cells = self._copy_refined_cells(refined)

    def _snapshot(self) -> None:
        self._history.append(self._state())
        if len(self._history) > self.HISTORY_LIMIT:
            del self._history[0]
        self._future.clear()

    def _in_bounds(self, x: int, y: int) -> bool:
        return 0 <= x < self.size and 0 <= y < self.size

    @staticmethod
    def _validate_child(child: ChildCoordinate) -> ChildCoordinate:
        child_x, child_y = child
        if child_x not in (0, 1) or child_y not in (0, 1):
            raise IndexError("child coordinate must be 0 or 1")
        return child_x, child_y

    @property
    def has_refinements(self) -> bool:
        return bool(self._refined_cells)

    @property
    def native_size(self) -> int:
        return self.size * 2 if self.has_refinements else self.size

    def is_split(self, x: int, y: int) -> bool:
        return (x, y) in self._refined_cells

    def split_cell(self, x: int, y: int) -> bool:
        if not self._in_bounds(x, y) or self.is_split(x, y):
            return False
        base = self.image.getpixel((x, y))
        self._snapshot()
        self._refined_cells[(x, y)] = [
            [base, base],
            [base, base],
        ]
        return True

    def new(self, size: int | None = None) -> None:
        target = self.size if size is None else size
        self._validate_size(target)
        self._snapshot()
        self.size = target
        self.image = Image.new("RGBA", (target, target), (0, 0, 0, 0))
        self._refined_cells.clear()

    @staticmethod
    def _validate_detail_policy(detail_policy: str) -> DetailPolicy:
        if detail_policy not in ("preserve", "discard"):
            raise ValueError("detail_policy must be 'preserve' or 'discard'")
        return detail_policy  # type: ignore[return-value]

    def paint(
        self,
        x: int,
        y: int,
        color: tuple[int, ...],
        erase: bool = False,
        child: ChildCoordinate | None = None,
        detail_policy: DetailPolicy = "preserve",
    ) -> bool:
        if not self._in_bounds(x, y):
            return False
        replacement = (0, 0, 0, 0) if erase else self._normalize_color(color)
        policy = self._validate_detail_policy(detail_policy)

        if child is not None:
            child_x, child_y = self._validate_child(child)
            if not self.is_split(x, y):
                raise ValueError("child painting requires a split cell")
            if self._refined_cells[(x, y)][child_y][child_x] == replacement:
                return False
            self._snapshot()
            self._refined_cells[(x, y)][child_y][child_x] = replacement
            return True

        current = self.image.getpixel((x, y))
        has_detail = self.is_split(x, y)
        if current == replacement and not (has_detail and policy == "discard"):
            return False

        self._snapshot()
        self.image.putpixel((x, y), replacement)
        if has_detail and policy == "discard":
            del self._refined_cells[(x, y)]
        return True

    def sample(
        self,
        x: int,
        y: int,
        child: ChildCoordinate | None = None,
    ) -> Color:
        if not self._in_bounds(x, y):
            raise IndexError("pixel coordinate out of range")
        if child is None:
            return self.image.getpixel((x, y))
        child_x, child_y = self._validate_child(child)
        if not self.is_split(x, y):
            raise ValueError("child sampling requires a split cell")
        return self._refined_cells[(x, y)][child_y][child_x]

    def fill(
        self,
        x: int,
        y: int,
        color: tuple[int, ...],
        erase: bool = False,
        detail_policy: DetailPolicy = "preserve",
    ) -> int:
        if not self._in_bounds(x, y):
            return 0
        replacement = (0, 0, 0, 0) if erase else self._normalize_color(color)
        policy = self._validate_detail_policy(detail_policy)
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
                if self._in_bounds(nx, ny) and (nx, ny) not in visited:
                    visited.add((nx, ny))
                    pending.append((nx, ny))
        if not points:
            return 0
        self._snapshot()
        for point in points:
            self.image.putpixel(point, replacement)
            if policy == "discard":
                self._refined_cells.pop(point, None)
        return len(points)

    def discard_detail(self, x: int, y: int, width: int = 1, height: int = 1) -> int:
        """Discard refined child data only inside the requested parent-cell region."""
        if width <= 0 or height <= 0:
            raise ValueError("detail discard region must have positive width and height")
        if not self._in_bounds(x, y):
            raise IndexError("detail discard region starts outside the canvas")
        end_x = min(self.size, x + width)
        end_y = min(self.size, y + height)
        targets = [
            (px, py)
            for py in range(y, end_y)
            for px in range(x, end_x)
            if (px, py) in self._refined_cells
        ]
        if not targets:
            return 0
        self._snapshot()
        for point in targets:
            del self._refined_cells[point]
        return len(targets)

    def import_image(self, source: str | Path | Image.Image) -> None:
        loaded = Image.open(source).convert("RGBA") if not isinstance(source, Image.Image) else source.convert("RGBA")
        ratio = min(1.0, self.size / loaded.width, self.size / loaded.height)
        target_size = (max(1, round(loaded.width * ratio)), max(1, round(loaded.height * ratio)))
        fitted = Image.new("RGBA", (self.size, self.size), (0, 0, 0, 0))
        resized = loaded.resize(target_size, Image.Resampling.NEAREST)
        fitted.alpha_composite(resized, ((self.size - target_size[0]) // 2, (self.size - target_size[1]) // 2))
        self._snapshot()
        self.image = fitted
        self._refined_cells.clear()

    def _native_image(self) -> Image.Image:
        if not self.has_refinements:
            return self.image.copy()
        output = self.image.resize((self.size * 2, self.size * 2), Image.Resampling.NEAREST)
        for (x, y), children in self._refined_cells.items():
            for child_y, row in enumerate(children):
                for child_x, color in enumerate(row):
                    output.putpixel((x * 2 + child_x, y * 2 + child_y), color)
        return output

    def resize(self, target: int) -> bool:
        """Resize the logical canvas with nearest-neighbour sampling.

        Split-cell detail is rendered first, then normalized into regular
        pixels at the target logical resolution.
        """
        self._validate_size(target)
        if target == self.size:
            return False
        source = self._native_image()
        self._snapshot()
        self.image = source.resize((target, target), Image.Resampling.NEAREST)
        self.size = target
        self._refined_cells.clear()
        return True

    def upscale(self) -> bool:
        if self.size >= self.SUPPORTED_SIZES[-1]:
            return False
        return self.resize(self.size * 2)

    def undo(self) -> bool:
        if not self._history:
            return False
        self._future.append(self._state())
        self._restore_state(self._history.pop())
        return True

    def redo(self) -> bool:
        if not self._future:
            return False
        self._history.append(self._state())
        self._restore_state(self._future.pop())
        return True

    def render(self, display_size: int | None = None) -> Image.Image:
        """Return a nearest-neighbour view without changing the logical canvas."""
        output = self._native_image()
        if display_size is None:
            return output
        if display_size <= 0:
            raise ValueError("display size must be positive")
        return output.resize((display_size, display_size), Image.Resampling.NEAREST)

    def save_png(self, path: str | Path, export_size: int | None = None) -> None:
        output = self._native_image()
        if export_size is not None:
            if export_size < output.width:
                raise ValueError("export size cannot be smaller than native canvas size")
            output = output.resize((export_size, export_size), Image.Resampling.NEAREST)
        output.save(path, "PNG")

    @staticmethod
    def _color_to_source(color: Color) -> str | None:
        red, green, blue, alpha = color
        return None if alpha == 0 else f"#{red:02X}{green:02X}{blue:02X}"

    @staticmethod
    def _color_from_source(value: object) -> Color:
        if value is None:
            return (0, 0, 0, 0)
        if not isinstance(value, str) or len(value) != 7 or value[0] != "#":
            raise ValueError("pixel colors must use #RRGGBB")
        try:
            color = tuple(int(value[index:index + 2], 16) for index in (1, 3, 5))
        except ValueError as error:
            raise ValueError("pixel colors must use #RRGGBB") from error
        return (*color, 255)

    def to_source(self) -> dict[str, Any]:
        pixels: list[list[str | None]] = []
        for y in range(self.size):
            row: list[str | None] = []
            for x in range(self.size):
                row.append(self._color_to_source(self.image.getpixel((x, y))))
            pixels.append(row)

        source: dict[str, Any] = {"canvas_size": self.size, "pixels": pixels}
        if self._refined_cells:
            source["refined_cells"] = [
                {
                    "x": x,
                    "y": y,
                    "children": [
                        [self._color_to_source(color) for color in row]
                        for row in children
                    ],
                }
                for (x, y), children in sorted(self._refined_cells.items())
            ]
        return source

    @classmethod
    def from_source(cls, source: dict[str, Any]) -> "PixelCanvas":
        if not isinstance(source, dict):
            raise ValueError("pixel project must be a JSON object")
        size = source.get("canvas_size")
        pixels = source.get("pixels")
        if not isinstance(size, int) or not isinstance(pixels, list):
            raise ValueError("invalid pixel source")
        canvas = cls(size)
        if len(pixels) != size or any(not isinstance(row, list) or len(row) != size for row in pixels):
            raise ValueError("pixel source dimensions do not match canvas size")
        for y, row in enumerate(pixels):
            for x, value in enumerate(row):
                canvas.image.putpixel((x, y), cls._color_from_source(value))

        refined = source.get("refined_cells", [])
        if not isinstance(refined, list):
            raise ValueError("refined_cells must be a list")
        for entry in refined:
            if not isinstance(entry, dict):
                raise ValueError("invalid refined cell")
            x = entry.get("x")
            y = entry.get("y")
            children = entry.get("children")
            if not isinstance(x, int) or not isinstance(y, int) or not canvas._in_bounds(x, y):
                raise ValueError("refined cell coordinate out of range")
            if (x, y) in canvas._refined_cells:
                raise ValueError("duplicate refined cell")
            if (
                not isinstance(children, list)
                or len(children) != 2
                or any(not isinstance(row, list) or len(row) != 2 for row in children)
            ):
                raise ValueError("refined cell children must be a 2x2 array")
            canvas._refined_cells[(x, y)] = [
                [cls._color_from_source(value) for value in row]
                for row in children
            ]
        return canvas
