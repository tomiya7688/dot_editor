from __future__ import annotations

from collections import deque
from math import gcd
from pathlib import Path
from typing import Any, Literal

from PIL import Image

Color = tuple[int, int, int, int]
ChildCoordinate = tuple[int, int]
DetailPolicy = Literal["preserve", "discard"]
Resolution = tuple[int, int]
RefinementKey = tuple[int, int, int, int]
CanvasState = tuple[Resolution, Image.Image, set[RefinementKey], set[RefinementKey]]


class PixelCanvas:
    """GUI-independent non-destructive pixel canvas shared by editors and tools."""

    PRESET_SIZES = (2, 4, 8, 16, 32, 64, 128, 256)
    SUPPORTED_SIZES = PRESET_SIZES
    MAX_RESOLUTION = 4096
    MAX_DETAIL_DIMENSION = 8192
    MAX_DETAIL_PIXELS = 1_048_576
    HISTORY_LIMIT = 50

    def __init__(self, size: int | Resolution = 16, height: int | None = None) -> None:
        width, resolved_height = self._coerce_resolution(size, height)
        self._validate_resolution(width, resolved_height)
        self._resolution: Resolution = (width, resolved_height)
        self._detail_image = Image.new("RGBA", self._resolution, (0, 0, 0, 0))
        self._detail_regions: set[RefinementKey] = set()
        self._expanded_regions: set[RefinementKey] = set()
        self._history: list[CanvasState] = []
        self._future: list[CanvasState] = []

    @classmethod
    def _coerce_resolution(cls, size: int | Resolution, height: int | None = None) -> Resolution:
        if isinstance(size, tuple):
            if height is not None or len(size) != 2:
                raise ValueError("resolution must contain width and height")
            width, resolved_height = size
        else:
            width = size
            resolved_height = size if height is None else height
        if not isinstance(width, int) or not isinstance(resolved_height, int):
            raise ValueError("resolution must use integer width and height")
        return width, resolved_height

    @classmethod
    def _validate_resolution(cls, width: int, height: int) -> None:
        if width <= 0 or height <= 0:
            raise ValueError("resolution must be positive")
        if width > cls.MAX_RESOLUTION or height > cls.MAX_RESOLUTION:
            raise ValueError(
                f"resolution exceeds maximum {cls.MAX_RESOLUTION}x{cls.MAX_RESOLUTION}"
            )

    @classmethod
    def _validate_size(cls, size: int) -> None:
        cls._validate_resolution(int(size), int(size))

    @staticmethod
    def _normalize_color(color: tuple[int, ...]) -> Color:
        values = tuple(int(component) for component in color)
        if len(values) == 3:
            values += (255,)
        if len(values) != 4 or any(component < 0 or component > 255 for component in values):
            raise ValueError("color must contain 3 or 4 components in the range 0..255")
        return values  # type: ignore[return-value]

    @staticmethod
    def _validate_child(child: ChildCoordinate) -> ChildCoordinate:
        child_x, child_y = child
        if child_x not in (0, 1) or child_y not in (0, 1):
            raise IndexError("child coordinate must be 0 or 1")
        return child_x, child_y

    @staticmethod
    def _validate_detail_policy(detail_policy: str) -> DetailPolicy:
        if detail_policy not in ("preserve", "discard"):
            raise ValueError("detail_policy must be 'preserve' or 'discard'")
        return detail_policy  # type: ignore[return-value]

    @staticmethod
    def _lcm(left: int, right: int) -> int:
        return abs(left * right) // gcd(left, right)

    @classmethod
    def _aligned_dimension(cls, current: int, target: int) -> int:
        candidate = cls._lcm(current, target)
        if candidate <= cls.MAX_DETAIL_DIMENSION:
            return candidate
        return max(current, target)

    def _ensure_alignment(self, width: int, height: int) -> None:
        detail_width, detail_height = self._detail_image.size
        target_width = self._aligned_dimension(detail_width, width)
        target_height = self._aligned_dimension(detail_height, height)
        if target_width * target_height > self.MAX_DETAIL_PIXELS:
            target_width = max(detail_width, width)
            target_height = max(detail_height, height)
        if target_width > self.MAX_DETAIL_DIMENSION or target_height > self.MAX_DETAIL_DIMENSION:
            raise ValueError("detail resolution exceeds safe maximum")
        if target_width * target_height > self.MAX_DETAIL_PIXELS:
            raise ValueError("detail resolution exceeds safe pixel budget")
        if (target_width, target_height) != self._detail_image.size:
            self._detail_image = self._detail_image.resize(
                (target_width, target_height), Image.Resampling.NEAREST
            )

    def _state(self) -> CanvasState:
        return (
            self._resolution,
            self._detail_image.copy(),
            set(self._detail_regions),
            set(self._expanded_regions),
        )

    def _restore_state(self, state: CanvasState) -> None:
        resolution, detail_image, detail_regions, expanded_regions = state
        self._resolution = resolution
        self._detail_image = detail_image.copy()
        self._detail_regions = set(detail_regions)
        self._expanded_regions = set(expanded_regions)

    def _snapshot(self) -> None:
        self._history.append(self._state())
        if len(self._history) > self.HISTORY_LIMIT:
            del self._history[0]
        self._future.clear()

    @property
    def width(self) -> int:
        return self._resolution[0]

    @property
    def height(self) -> int:
        return self._resolution[1]

    @property
    def resolution(self) -> Resolution:
        return self._resolution

    @property
    def size(self) -> int:
        if self.width != self.height:
            raise ValueError("non-square canvas has no scalar size; use resolution")
        return self.width

    @property
    def detail_resolution(self) -> Resolution:
        return self._detail_image.size

    @property
    def image(self) -> Image.Image:
        return self.render_resolution(self.width, self.height)

    def _in_bounds(self, x: int, y: int) -> bool:
        return 0 <= x < self.width and 0 <= y < self.height

    def _current_refinement_key(self, x: int, y: int) -> RefinementKey:
        return self.width, self.height, x, y

    @staticmethod
    def _region_bounds(
        resolution: Resolution,
        x: int,
        y: int,
        width: int,
        height: int,
        detail_resolution: Resolution,
    ) -> tuple[int, int, int, int]:
        logical_width, logical_height = resolution
        detail_width, detail_height = detail_resolution
        left = x * detail_width // logical_width
        top = y * detail_height // logical_height
        right = (x + width) * detail_width // logical_width
        bottom = (y + height) * detail_height // logical_height
        if right <= left:
            right = min(detail_width, left + 1)
        if bottom <= top:
            bottom = min(detail_height, top + 1)
        return left, top, right, bottom

    def _cell_bounds(self, x: int, y: int) -> tuple[int, int, int, int]:
        return self._region_bounds(
            self._resolution, x, y, 1, 1, self._detail_image.size
        )

    @property
    def has_refinements(self) -> bool:
        return any(
            marker[0] == self.width and marker[1] == self.height
            for marker in self._expanded_regions
        )

    @property
    def has_detail(self) -> bool:
        if self._detail_regions:
            return True
        return self._detail_image.size != self._resolution

    @property
    def native_resolution(self) -> Resolution:
        if self.has_refinements:
            return self.width * 2, self.height * 2
        return self._resolution

    @property
    def native_size(self) -> int | Resolution:
        width, height = self.native_resolution
        return width if width == height else (width, height)

    def is_split(self, x: int, y: int) -> bool:
        return self._current_refinement_key(x, y) in self._expanded_regions

    def has_detail_at(self, x: int, y: int) -> bool:
        if not self._in_bounds(x, y):
            return False
        key = self._current_refinement_key(x, y)
        if key in self._detail_regions:
            return True
        left, top, right, bottom = self._cell_bounds(x, y)
        region = self._detail_image.crop((left, top, right, bottom))
        if region.width <= 1 and region.height <= 1:
            return False
        pixels = list(region.getdata())
        return bool(pixels) and any(pixel != pixels[0] for pixel in pixels[1:])

    def split_cell(self, x: int, y: int) -> bool:
        if not self._in_bounds(x, y) or self.is_split(x, y):
            return False
        self._snapshot()
        self._ensure_alignment(self.width * 2, self.height * 2)
        key = self._current_refinement_key(x, y)
        self._detail_regions.add(key)
        self._expanded_regions.add(key)
        return True

    def collapse_cell(self, x: int, y: int, discard_detail: bool = False) -> bool:
        if not self._in_bounds(x, y):
            return False
        key = self._current_refinement_key(x, y)
        has_expanded = key in self._expanded_regions
        has_detail = self.has_detail_at(x, y)
        if not has_expanded and not (discard_detail and has_detail):
            return False
        self._snapshot()
        self._expanded_regions.discard(key)
        if discard_detail:
            self._discard_region_without_snapshot(x, y, 1, 1)
        return True

    def new(
        self,
        size: int | Resolution | None = None,
        height: int | None = None,
    ) -> None:
        target = self._resolution if size is None else self._coerce_resolution(size, height)
        self._validate_resolution(*target)
        self._snapshot()
        self._resolution = target
        self._detail_image = Image.new("RGBA", target, (0, 0, 0, 0))
        self._detail_regions.clear()
        self._expanded_regions.clear()

    def render_resolution(self, width: int, height: int) -> Image.Image:
        self._validate_resolution(width, height)
        return self._detail_image.resize((width, height), Image.Resampling.NEAREST)

    def _apply_preserve_color(self, x: int, y: int, replacement: Color) -> None:
        current = self.sample(x, y)
        left, top, right, bottom = self._cell_bounds(x, y)
        delta = tuple(replacement[i] - current[i] for i in range(4))
        pixels = self._detail_image.load()
        for py in range(top, bottom):
            for px in range(left, right):
                old = pixels[px, py]
                pixels[px, py] = tuple(
                    max(0, min(255, old[i] + delta[i])) for i in range(4)
                )  # type: ignore[assignment]

    def _apply_discard_color(self, x: int, y: int, replacement: Color) -> None:
        left, top, right, bottom = self._cell_bounds(x, y)
        pixels = self._detail_image.load()
        for py in range(top, bottom):
            for px in range(left, right):
                pixels[px, py] = replacement
        self._remove_refinement_markers_for_region(x, y, 1, 1)

    def _remove_refinement_markers_for_region(
        self, x: int, y: int, width: int, height: int
    ) -> None:
        current_width, current_height = self._resolution

        def overlaps(marker: RefinementKey) -> bool:
            marker_width, marker_height, marker_x, marker_y = marker
            return (
                marker_x * current_width < (x + width) * marker_width
                and (marker_x + 1) * current_width > x * marker_width
                and marker_y * current_height < (y + height) * marker_height
                and (marker_y + 1) * current_height > y * marker_height
            )

        self._detail_regions = {
            marker for marker in self._detail_regions if not overlaps(marker)
        }
        self._expanded_regions = {
            marker for marker in self._expanded_regions if not overlaps(marker)
        }

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
            target_resolution = (self.width * 2, self.height * 2)
            self._ensure_alignment(*target_resolution)
            child_point = (x * 2 + child_x, y * 2 + child_y)
            current = self.render_resolution(*target_resolution).getpixel(child_point)
            if current == replacement and not (
                policy == "discard" and self.has_detail_at(x, y)
            ):
                return False
            self._snapshot()
            original_resolution = self._resolution
            self._resolution = target_resolution
            try:
                if policy == "discard":
                    self._apply_discard_color(*child_point, replacement)
                else:
                    self._apply_preserve_color(*child_point, replacement)
            finally:
                self._resolution = original_resolution
            self._detail_regions.add(self._current_refinement_key(x, y))
            return True

        current = self.sample(x, y)
        has_detail = self.has_detail_at(x, y)
        if current == replacement and not (policy == "discard" and has_detail):
            return False
        self._snapshot()
        if policy == "discard":
            self._apply_discard_color(x, y, replacement)
        else:
            self._apply_preserve_color(x, y, replacement)
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
            return self.render_resolution(self.width, self.height).getpixel((x, y))
        child_x, child_y = self._validate_child(child)
        if not self.has_detail_at(x, y):
            raise ValueError("child sampling requires preserved child detail")
        view = self.render_resolution(self.width * 2, self.height * 2)
        return view.getpixel((x * 2 + child_x, y * 2 + child_y))

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
        view = self.render_resolution(self.width, self.height)
        original = view.getpixel((x, y))
        if original == replacement and policy == "preserve":
            return 0
        points: list[tuple[int, int]] = []
        pending = deque([(x, y)])
        visited = {(x, y)}
        while pending:
            px, py = pending.popleft()
            if view.getpixel((px, py)) != original:
                continue
            points.append((px, py))
            for nx, ny in ((px - 1, py), (px + 1, py), (px, py - 1), (px, py + 1)):
                if self._in_bounds(nx, ny) and (nx, ny) not in visited:
                    visited.add((nx, ny))
                    pending.append((nx, ny))
        if original == replacement and policy == "discard":
            points = [point for point in points if self.has_detail_at(*point)]
        if not points:
            return 0
        self._snapshot()
        for point in points:
            if policy == "discard":
                self._apply_discard_color(*point, replacement)
            else:
                self._apply_preserve_color(*point, replacement)
        return len(points)

    def _discard_region_without_snapshot(
        self, x: int, y: int, width: int, height: int
    ) -> None:
        view = self.render_resolution(self.width, self.height)
        for py in range(y, min(self.height, y + height)):
            for px in range(x, min(self.width, x + width)):
                self._apply_discard_color(px, py, view.getpixel((px, py)))

    def discard_detail(self, x: int, y: int, width: int = 1, height: int = 1) -> int:
        if width <= 0 or height <= 0:
            raise ValueError("detail discard region must have positive width and height")
        if not self._in_bounds(x, y):
            raise IndexError("detail discard region starts outside the canvas")
        end_x = min(self.width, x + width)
        end_y = min(self.height, y + height)
        affected = [
            (px, py)
            for py in range(y, end_y)
            for px in range(x, end_x)
            if self.has_detail_at(px, py)
        ]
        if not affected:
            return 0
        self._snapshot()
        self._discard_region_without_snapshot(x, y, end_x - x, end_y - y)
        return len(affected)

    def import_image(self, source: str | Path | Image.Image) -> None:
        loaded = (
            Image.open(source).convert("RGBA")
            if not isinstance(source, Image.Image)
            else source.convert("RGBA")
        )
        ratio = min(1.0, self.width / loaded.width, self.height / loaded.height)
        target_size = (
            max(1, round(loaded.width * ratio)),
            max(1, round(loaded.height * ratio)),
        )
        fitted = Image.new("RGBA", self._resolution, (0, 0, 0, 0))
        resized = loaded.resize(target_size, Image.Resampling.NEAREST)
        fitted.alpha_composite(
            resized,
            ((self.width - target_size[0]) // 2, (self.height - target_size[1]) // 2),
        )
        self._snapshot()
        self._detail_image = fitted
        self._detail_regions.clear()
        self._expanded_regions.clear()

    def set_resolution(self, width: int, height: int | None = None) -> bool:
        resolved_height = width if height is None else height
        width = int(width)
        resolved_height = int(resolved_height)
        self._validate_resolution(width, resolved_height)
        target = (width, resolved_height)
        if target == self._resolution:
            return False
        self._snapshot()
        self._ensure_alignment(width, resolved_height)
        self._resolution = target
        return True

    def resize(self, target: int) -> bool:
        return self.set_resolution(target, target)

    def upscale(self) -> bool:
        target = (self.width * 2, self.height * 2)
        if target[0] > self.MAX_RESOLUTION or target[1] > self.MAX_RESOLUTION:
            return False
        return self.set_resolution(*target)

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

    def render(self, display_size: int | Resolution | None = None) -> Image.Image:
        if display_size is None:
            target = self.native_resolution
        elif isinstance(display_size, tuple):
            target = self._coerce_resolution(display_size)
        else:
            target = (int(display_size), int(display_size))
        return self.render_resolution(*target)

    def save_png(
        self, path: str | Path, export_size: int | Resolution | None = None
    ) -> None:
        if export_size is None:
            target = self.native_resolution
        elif isinstance(export_size, tuple):
            target = self._coerce_resolution(export_size)
        else:
            target = (int(export_size), int(export_size))
        self.render_resolution(*target).save(path, "PNG")

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

    def _pixels_source(self, image: Image.Image) -> list[list[str | None]]:
        return [
            [self._color_to_source(image.getpixel((x, y))) for x in range(image.width)]
            for y in range(image.height)
        ]

    def _legacy_refined_cells_source(self) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        view = self.render_resolution(self.width * 2, self.height * 2)
        for marker in sorted(self._detail_regions):
            if marker[0] != self.width or marker[1] != self.height:
                continue
            x, y = marker[2], marker[3]
            result.append(
                {
                    "x": x,
                    "y": y,
                    "expanded": marker in self._expanded_regions,
                    "children": [
                        [
                            self._color_to_source(
                                view.getpixel((x * 2 + child_x, y * 2 + child_y))
                            )
                            for child_x in range(2)
                        ]
                        for child_y in range(2)
                    ],
                }
            )
        return result

    def to_source(self) -> dict[str, Any]:
        current = self.render_resolution(self.width, self.height)
        canvas_size: int | list[int] = (
            self.width if self.width == self.height else [self.width, self.height]
        )
        source: dict[str, Any] = {
            "canvas_size": canvas_size,
            "canvas_width": self.width,
            "canvas_height": self.height,
            "pixels": self._pixels_source(current),
            "detail_width": self._detail_image.width,
            "detail_height": self._detail_image.height,
            "detail_pixels": self._pixels_source(self._detail_image),
            "refinements": [
                {
                    "width": marker[0],
                    "height": marker[1],
                    "x": marker[2],
                    "y": marker[3],
                    "expanded": marker in self._expanded_regions,
                }
                for marker in sorted(self._detail_regions)
            ],
        }
        legacy = self._legacy_refined_cells_source()
        if legacy:
            source["refined_cells"] = legacy
        return source

    @classmethod
    def _parse_resolution(cls, source: dict[str, Any]) -> Resolution:
        width = source.get("canvas_width")
        height = source.get("canvas_height")
        if isinstance(width, int) and isinstance(height, int):
            cls._validate_resolution(width, height)
            return width, height
        size = source.get("canvas_size")
        if isinstance(size, int):
            cls._validate_resolution(size, size)
            return size, size
        if (
            isinstance(size, list)
            and len(size) == 2
            and all(isinstance(value, int) for value in size)
        ):
            cls._validate_resolution(size[0], size[1])
            return size[0], size[1]
        raise ValueError("invalid pixel source resolution")

    @classmethod
    def _image_from_source_pixels(
        cls, pixels: object, width: int, height: int, label: str
    ) -> Image.Image:
        if (
            not isinstance(pixels, list)
            or len(pixels) != height
            or any(not isinstance(row, list) or len(row) != width for row in pixels)
        ):
            raise ValueError(f"{label} dimensions do not match resolution")
        image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        for y, row in enumerate(pixels):
            for x, value in enumerate(row):
                image.putpixel((x, y), cls._color_from_source(value))
        return image

    @classmethod
    def from_source(cls, source: dict[str, Any]) -> "PixelCanvas":
        if not isinstance(source, dict):
            raise ValueError("pixel project must be a JSON object")
        width, height = cls._parse_resolution(source)
        canvas = cls((width, height))

        detail_width = source.get("detail_width")
        detail_height = source.get("detail_height")
        detail_pixels = source.get("detail_pixels")
        if detail_width is not None or detail_height is not None or detail_pixels is not None:
            if not isinstance(detail_width, int) or not isinstance(detail_height, int):
                raise ValueError("detail resolution must use integer width and height")
            if detail_width <= 0 or detail_height <= 0:
                raise ValueError("detail resolution must be positive")
            if (
                detail_width > cls.MAX_DETAIL_DIMENSION
                or detail_height > cls.MAX_DETAIL_DIMENSION
                or detail_width * detail_height > cls.MAX_DETAIL_PIXELS
            ):
                raise ValueError("detail resolution exceeds maximum")
            canvas._detail_image = cls._image_from_source_pixels(
                detail_pixels, detail_width, detail_height, "detail_pixels"
            )
            refinements = source.get("refinements", [])
            if not isinstance(refinements, list):
                raise ValueError("refinements must be a list")
            for entry in refinements:
                if not isinstance(entry, dict):
                    raise ValueError("invalid refinement")
                ref_width = entry.get("width")
                ref_height = entry.get("height")
                x = entry.get("x")
                y = entry.get("y")
                expanded = entry.get("expanded", False)
                if (
                    not isinstance(ref_width, int)
                    or not isinstance(ref_height, int)
                    or not isinstance(x, int)
                    or not isinstance(y, int)
                    or not isinstance(expanded, bool)
                ):
                    raise ValueError("invalid refinement")
                cls._validate_resolution(ref_width, ref_height)
                if not (0 <= x < ref_width and 0 <= y < ref_height):
                    raise ValueError("refinement coordinate out of range")
                marker = (ref_width, ref_height, x, y)
                if marker in canvas._detail_regions:
                    raise ValueError("duplicate refinement")
                canvas._detail_regions.add(marker)
                if expanded:
                    canvas._expanded_regions.add(marker)
            return canvas

        pixels = source.get("pixels")
        canvas._detail_image = cls._image_from_source_pixels(
            pixels, width, height, "pixel source"
        )
        refined = source.get("refined_cells", [])
        if not isinstance(refined, list):
            raise ValueError("refined_cells must be a list")
        if refined:
            canvas._ensure_alignment(width * 2, height * 2)
            detail_view = canvas._detail_image
            for entry in refined:
                if not isinstance(entry, dict):
                    raise ValueError("invalid refined cell")
                x = entry.get("x")
                y = entry.get("y")
                children = entry.get("children")
                expanded = entry.get("expanded", True)
                if (
                    not isinstance(x, int)
                    or not isinstance(y, int)
                    or not (0 <= x < width and 0 <= y < height)
                ):
                    raise ValueError("refined cell coordinate out of range")
                if not isinstance(expanded, bool):
                    raise ValueError("refined cell expanded must be a boolean")
                if (
                    not isinstance(children, list)
                    or len(children) != 2
                    or any(not isinstance(row, list) or len(row) != 2 for row in children)
                ):
                    raise ValueError("refined cell children must be a 2x2 array")
                marker = (width, height, x, y)
                if marker in canvas._detail_regions:
                    raise ValueError("duplicate refined cell")
                child_resolution = (width * 2, height * 2)
                for child_y, row in enumerate(children):
                    for child_x, value in enumerate(row):
                        logical_x = x * 2 + child_x
                        logical_y = y * 2 + child_y
                        left, top, right, bottom = canvas._region_bounds(
                            child_resolution,
                            logical_x,
                            logical_y,
                            1,
                            1,
                            detail_view.size,
                        )
                        color = cls._color_from_source(value)
                        for py in range(top, bottom):
                            for px in range(left, right):
                                detail_view.putpixel((px, py), color)
                canvas._detail_regions.add(marker)
                if expanded:
                    canvas._expanded_regions.add(marker)
        return canvas
