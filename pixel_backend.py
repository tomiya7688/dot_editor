from __future__ import annotations

from collections import deque
from fractions import Fraction
from pathlib import Path
from typing import Any, Literal

from PIL import Image

from resolution_field import (
    MAX_DIMENSION, MAX_PIXELS, ResolutionField, Box, cell_box, intersection,
    resolution, encoded_color, decoded_color, image_source, source_image,
)

Color = tuple[int, int, int, int]
ChildCoordinate = tuple[int, int]
DetailPolicy = Literal["preserve", "discard"]
RefinedCells = dict[tuple[int, int], list[list[Color]]]
SplitKey = tuple[int, int, int, int]  # width, height, parent x, parent y
SplitState = tuple[Color, bool]  # retained parent value, expanded at this grid
CanvasState = tuple[tuple[int, int], ResolutionField, dict[SplitKey, SplitState]]


class PixelCanvas:
    """GUI-independent canvas with an independent, non-destructive spatial field.

    ``size`` remains a width alias for square-canvas clients. New code should
    use ``resolution`` or ``width``/``height``. ``image`` is a read-only projected
    copy; mutate the document through paint/fill/import_image instead.
    """

    SUPPORTED_SIZES = (2, 4, 8, 16, 32, 64, 128, 256)  # presets, not a whitelist
    MAX_DIMENSION = MAX_DIMENSION
    MAX_PIXELS = MAX_PIXELS
    HISTORY_LIMIT = 50
    MAX_SPLITS = 4096

    def __init__(self, size: int = 16, height: int | None = None) -> None:
        self._resolution = resolution(size, height)
        self._field = ResolutionField()
        self._splits: dict[SplitKey, SplitState] = {}
        self._history: list[CanvasState] = []
        self._future: list[CanvasState] = []
        self._view_cache: Image.Image | None = None

    @classmethod
    def _validate_size(cls, size: int) -> None:
        resolution(size)

    @property
    def resolution(self) -> tuple[int, int]:
        return self._resolution

    @property
    def width(self) -> int:
        return self._resolution[0]

    @property
    def height(self) -> int:
        return self._resolution[1]

    @property
    def size(self) -> int:
        return self.width

    def _key(self, x: int, y: int) -> SplitKey:
        return self.width, self.height, x, y

    @staticmethod
    def _key_box(key: SplitKey) -> Box:
        width, height, x, y = key
        return cell_box(x, y, width, height)

    def _box(self, x: int, y: int, child: ChildCoordinate | None = None) -> Box:
        if child is None:
            return cell_box(x, y, self.width, self.height)
        cx, cy = self._validate_child(child)
        return cell_box(2 * x + cx, 2 * y + cy, 2 * self.width, 2 * self.height)

    @staticmethod
    def _center(box: Box) -> tuple[Fraction, Fraction]:
        return (box[0] + box[2]) / 2, (box[1] + box[3]) / 2

    @staticmethod
    def _normalize_color(color: tuple[int, ...]) -> Color:
        values = tuple(color)
        if len(values) == 3:
            values += (255,)
        if len(values) != 4 or any(type(v) is not int or not 0 <= v <= 255 for v in values):
            raise ValueError("color must contain 3 or 4 integers in the range 0..255")
        return values

    @staticmethod
    def _validate_detail_policy(detail_policy: str) -> DetailPolicy:
        if detail_policy not in ("preserve", "discard"):
            raise ValueError("detail_policy must be 'preserve' or 'discard'")
        return detail_policy

    @staticmethod
    def _validate_child(child: ChildCoordinate) -> ChildCoordinate:
        if len(child) != 2 or any(type(v) is not int or v not in (0, 1) for v in child):
            raise IndexError("child coordinate must be 0 or 1")
        return tuple(child)

    def _in_bounds(self, x: int, y: int) -> bool:
        return type(x) is int and type(y) is int and 0 <= x < self.width and 0 <= y < self.height

    def _state(self) -> CanvasState:
        return self.resolution, self._field, dict(self._splits)

    def _restore_state(self, state: CanvasState) -> None:
        self._resolution, self._field, splits = state
        self._splits = dict(splits)
        self._view_cache = None

    def _snapshot(self) -> None:
        self._history.append(self._state())
        del self._history[:-self.HISTORY_LIMIT]
        self._future.clear()

    def _commit(self, field: ResolutionField, splits: dict[SplitKey, SplitState]) -> None:
        self._snapshot()
        self._field = field
        self._splits = splits
        self._view_cache = None

    @property
    def _expanded_cells(self) -> set[tuple[int, int]]:
        return {(x, y) for (w, h, x, y), (_, expanded) in self._splits.items()
                if (w, h) == self.resolution and expanded}

    @property
    def _refined_cells(self) -> RefinedCells:
        return {(x, y): [[self._field.sample(*self._center(self._box(x, y, (cx, cy))))
                          for cx in range(2)] for cy in range(2)]
                for w, h, x, y in self._splits if (w, h) == self.resolution}

    @property
    def has_refinements(self) -> bool:
        return bool(self._expanded_cells)

    @property
    def has_detail(self) -> bool:
        rw, rh = self._field.retained_resolution
        return bool(self._splits) or rw > self.width or rh > self.height or any(
            (v * (self.width if i % 2 == 0 else self.height)).denominator != 1
            for tile in self._field.tiles for i, v in enumerate(tile[0])
        )

    @property
    def retained_resolution(self) -> tuple[int, int]:
        return self._field.retained_resolution

    @property
    def retained_patch_count(self) -> int:
        return len(self._field.tiles)

    def detail_cells(self) -> list[dict[str, Any]]:
        return [{"x": x, "y": y, "expanded": expanded}
                for (w, h, x, y), (_, expanded) in sorted(self._splits.items())
                if (w, h) == self.resolution]

    @property
    def native_resolution(self) -> tuple[int, int]:
        return (2 * self.width, 2 * self.height) if self.has_refinements else self.resolution

    @property
    def native_size(self) -> int:
        return self.native_resolution[0]

    def is_split(self, x: int, y: int) -> bool:
        return self._splits.get(self._key(x, y), (None, False))[1]

    def has_detail_at(self, x: int, y: int) -> bool:
        if not self._in_bounds(x, y):
            return False
        box = self._box(x, y)
        if self._key(x, y) in self._splits or self._field.has_detail(box):
            return True
        # A split at another grid can retain a parent override even when the
        # raster field is uniform. Include metadata that discard would remove
        # or change, otherwise same-color edits can resurrect the old parent.
        for key, (base, _) in self._splits.items():
            split_box = self._key_box(key)
            overlap = intersection(split_box, box)
            if overlap is None:
                continue
            if overlap == split_box:
                return True
            center = self._center(split_box)
            if (box[0] <= center[0] < box[2] and box[1] <= center[1] < box[3]
                    and base != self._field.sample(*center)):
                return True
        return False

    def _projection(self, width: int, height: int) -> Image.Image:
        output = self._field.render(width, height)
        for (w, h, x, y), (base, _) in self._splits.items():
            if (w, h) == (width, height):
                output.putpixel((x, y), base)
        return output

    @property
    def image(self) -> Image.Image:
        if self._view_cache is None:
            self._view_cache = self._projection(*self.resolution)
        return self._view_cache.copy()

    def split_cell(self, x: int, y: int) -> bool:
        if not self._in_bounds(x, y) or self.is_split(x, y):
            return False
        resolution(2 * self.width, 2 * self.height)
        key = self._key(x, y)
        if key not in self._splits and len(self._splits) >= self.MAX_SPLITS:
            raise ValueError("too many retained split cells")
        splits = dict(self._splits)
        base = splits[key][0] if key in splits else self.sample(x, y)
        splits[key] = (base, True)
        self._commit(self._field, splits)
        return True

    def collapse_cell(self, x: int, y: int, discard_detail: bool = False) -> bool:
        if not self._in_bounds(x, y):
            return False
        if discard_detail:
            return self.discard_detail(x, y) > 0
        key = self._key(x, y)
        if not self.is_split(x, y):
            return False
        splits = dict(self._splits)
        splits[key] = (splits[key][0], False)
        self._commit(self._field, splits)
        return True

    def new(self, size: int | None = None, height: int | None = None) -> None:
        target = self.resolution if size is None else resolution(size, height)
        self._snapshot()
        self._resolution = target
        self._field = ResolutionField()
        self._splits.clear()
        self._view_cache = None

    def _edited(
        self, field: ResolutionField, splits: dict[SplitKey, SplitState],
        x: int, y: int, replacement: Color, child: ChildCoordinate | None,
        policy: DetailPolicy,
    ) -> tuple[ResolutionField, dict[SplitKey, SplitState]]:
        box = self._box(x, y, child)
        key = self._key(x, y)
        # Preserve the legacy explicit-parent/child override contract. Children
        # remain independently editable; a parent-only write changes its base.
        if child is None and key in splits and policy == "preserve":
            splits[key] = (replacement, splits[key][1])
            return field, splits
        if policy == "preserve" and field.has_detail(box):
            reference = field.sample_raw(*self._center(box))
            delta = tuple(new - old for new, old in zip(replacement, reference))
            field = field.shift(box, delta)
            # Keep parent values at other stored grids consistent with the tint.
            for split_key, (base, expanded) in list(splits.items()):
                # A child write must not alter its independently saved parent.
                # The parent's center lies on the bottom-right child's edge.
                if child is not None and split_key == key:
                    continue
                center = self._center(self._key_box(split_key))
                if box[0] <= center[0] < box[2] and box[1] <= center[1] < box[3]:
                    splits[split_key] = (tuple(max(0, min(255, v + d)) for v, d in zip(base, delta)), expanded)
        else:
            field = field.replace(box, replacement)
            if policy == "discard":
                for split_key in list(splits):
                    if child is not None and split_key == key:
                        continue
                    split_box = self._key_box(split_key)
                    overlap = intersection(split_box, box)
                    if overlap == split_box:
                        del splits[split_key]
                    elif overlap is not None:
                        # Partially intersecting metadata must not expose an old
                        # base at a discarded sample position. Exterior child
                        # samples remain in the exact clipped spatial field.
                        center = self._center(split_box)
                        if box[0] <= center[0] < box[2] and box[1] <= center[1] < box[3]:
                            splits[split_key] = (replacement, splits[split_key][1])
        return field, splits

    def paint(self, x: int, y: int, color: tuple[int, ...], erase: bool = False,
              child: ChildCoordinate | None = None, detail_policy: DetailPolicy = "preserve") -> bool:
        policy = self._validate_detail_policy(detail_policy)
        replacement = (0, 0, 0, 0) if erase else self._normalize_color(color)
        if not self._in_bounds(x, y):
            return False
        if child is not None:
            self._validate_child(child)
            if not self.is_split(x, y):
                raise ValueError("child painting requires a split cell")
        current = self.sample(x, y, child)
        has_detail = self.has_detail_at(x, y) if child is None else self._field.has_detail(self._box(x, y, child))
        if current == replacement and not (policy == "discard" and has_detail):
            return False
        field, splits = self._edited(self._field, dict(self._splits), x, y, replacement, child, policy)
        self._commit(field, splits)
        return True

    def sample(self, x: int, y: int, child: ChildCoordinate | None = None) -> Color:
        if not self._in_bounds(x, y):
            raise IndexError("pixel coordinate out of range")
        if child is None and self._key(x, y) in self._splits:
            return self._splits[self._key(x, y)][0]
        if child is not None:
            self._validate_child(child)
            if not self.has_detail_at(x, y):
                raise ValueError("child sampling requires preserved child detail")
        return self._field.sample(*self._center(self._box(x, y, child)))

    def fill(self, x: int, y: int, color: tuple[int, ...], erase: bool = False,
             detail_policy: DetailPolicy = "preserve") -> int:
        policy = self._validate_detail_policy(detail_policy)
        replacement = (0, 0, 0, 0) if erase else self._normalize_color(color)
        if not self._in_bounds(x, y):
            return 0
        view = self.image
        original = view.getpixel((x, y))
        if original == replacement and policy == "preserve":
            return 0
        points = []
        pending = deque([(x, y)])
        visited = {(x, y)}
        while pending:
            px, py = pending.popleft()
            if view.getpixel((px, py)) != original:
                continue
            if original != replacement or self.has_detail_at(px, py):
                points.append((px, py))
            for nx, ny in ((px - 1, py), (px + 1, py), (px, py - 1), (px, py + 1)):
                if self._in_bounds(nx, ny) and (nx, ny) not in visited:
                    visited.add((nx, ny))
                    pending.append((nx, ny))
        if not points:
            return 0
        if len(points) == self.width * self.height and (policy == "discard" or not self.has_detail):
            self._commit(ResolutionField.from_image(Image.new("RGBA", (1, 1), replacement)), {})
            return len(points)
        field, splits = self._field, dict(self._splits)
        for px, py in points:
            field, splits = self._edited(field, splits, px, py, replacement, None, policy)
        self._commit(field, splits)
        return len(points)

    def discard_detail(self, x: int, y: int, width: int = 1, height: int = 1) -> int:
        if (type(width) is not int or type(height) is not int or width <= 0 or height <= 0):
            raise ValueError("detail discard region must have positive integer width and height")
        if not self._in_bounds(x, y) or x + width > self.width or y + height > self.height:
            raise IndexError("detail discard region must fit inside the canvas")
        targets = [(px, py, self.sample(px, py)) for py in range(y, y + height)
                   for px in range(x, x + width) if self.has_detail_at(px, py)]
        if not targets:
            return 0
        field, splits = self._field, dict(self._splits)
        for px, py, color in targets:
            field, splits = self._edited(field, splits, px, py, color, None, "discard")
        self._commit(field, splits)
        return len(targets)

    def import_image(self, source: str | Path | Image.Image) -> None:
        if isinstance(source, Image.Image):
            loaded = source.convert("RGBA")
        else:
            with Image.open(source) as opened:
                loaded = opened.convert("RGBA")
        ratio = min(1.0, self.width / loaded.width, self.height / loaded.height)
        target = max(1, round(loaded.width * ratio)), max(1, round(loaded.height * ratio))
        fitted = Image.new("RGBA", self.resolution)
        resized = loaded.resize(target, Image.Resampling.NEAREST)
        fitted.paste(resized, ((self.width - target[0]) // 2, (self.height - target[1]) // 2))
        self._commit(ResolutionField.from_image(fitted), {})

    def set_resolution(self, width: int, height: int | None = None,
                       detail_policy: DetailPolicy = "preserve") -> bool:
        target = resolution(width, height)
        policy = self._validate_detail_policy(detail_policy)
        if target == self.resolution and policy == "preserve":
            return False
        field = self._field
        if policy == "discard":
            # An explicit global discard bakes only the requested coarse view.
            field = ResolutionField.from_image(self._projection(*target))
        self._snapshot()
        self._resolution = target
        self._field = field
        if policy == "discard":
            self._splits.clear()
        self._view_cache = None
        return True

    def resize(self, target: int, height: int | None = None,
               detail_policy: DetailPolicy = "preserve") -> bool:
        """Compatibility alias: resolution changes now preserve detail by default."""
        return self.set_resolution(target, height, detail_policy)

    def upscale(self) -> bool:
        try:
            target = resolution(self.width * 2, self.height * 2)
        except ValueError:
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
        del self._history[:-self.HISTORY_LIMIT]
        self._restore_state(self._future.pop())
        return True

    def _native_image(self) -> Image.Image:
        view = self.image
        if not self.has_refinements:
            return view
        output = view.resize(self.native_resolution, Image.Resampling.NEAREST)
        for x, y in self._expanded_cells:
            for cy in range(2):
                for cx in range(2):
                    output.putpixel((2 * x + cx, 2 * y + cy), self.sample(x, y, (cx, cy)))
        return output

    def render(self, display_size: int | tuple[int, int] | None = None) -> Image.Image:
        """Nearest-neighbour display of the current logical view, including splits."""
        output = self._native_image()
        if display_size is None:
            return output
        target = resolution(*display_size) if isinstance(display_size, tuple) else resolution(display_size)
        return output.resize(target, Image.Resampling.NEAREST)

    def render_resolution(self, width: int, height: int | None = None) -> Image.Image:
        """Project retained detail directly at an explicit output resolution."""
        return self._field.render(*resolution(width, height))

    def save_png(self, path: str | Path, export_size: int | None = None,
                 *, output_resolution: tuple[int, int] | None = None) -> None:
        if export_size is not None and output_resolution is not None:
            raise ValueError("choose export size or output resolution, not both")
        if output_resolution is not None:
            output = self.render_resolution(*output_resolution)
        else:
            output = self._native_image()
            if export_size is not None:
                target = resolution(export_size)
                if export_size < max(output.size):
                    raise ValueError("export size cannot be smaller than native canvas size")
                output = output.resize(target, Image.Resampling.NEAREST)
        output.save(path, "PNG")

    _color_to_source = staticmethod(encoded_color)
    _color_from_source = staticmethod(decoded_color)

    def to_source(self) -> dict[str, Any]:
        source: dict[str, Any] = {
            "version": 2, "canvas_size": self.width, "resolution": list(self.resolution),
            "pixels": image_source(self.image),
            "retained_field": self._field.to_source(),
            "retained_splits": [
                {"resolution": [w, h], "x": x, "y": y,
                 "base": encoded_color(base), "expanded": expanded}
                for (w, h, x, y), (base, expanded) in sorted(self._splits.items())
            ],
        }
        cells = self._refined_cells
        if cells:
            source["refined_cells"] = [
                {"x": x, "y": y, "expanded": self.is_split(x, y),
                 "children": [[encoded_color(c) for c in row] for row in children]}
                for (x, y), children in sorted(cells.items())
            ]
        return source

    @classmethod
    def from_source(cls, source: dict[str, Any]) -> PixelCanvas:
        if not isinstance(source, dict):
            raise ValueError("pixel project must be a JSON object")
        version = source.get("version", 1)
        if type(version) is not int or version not in (1, 2):
            raise ValueError("unsupported pixel project version")
        if version == 1:
            size = source.get("canvas_size")
            model = cls(size)
            image = source_image(source.get("pixels"), size, size)
            field = ResolutionField.from_image(image)
            cells = source.get("refined_cells", [])
            if not isinstance(cells, list) or len(cells) > cls.MAX_SPLITS:
                raise ValueError("invalid refined_cells")
            for cell in cells:
                if not isinstance(cell, dict):
                    raise ValueError("invalid refined cell")
                x, y = cell.get("x"), cell.get("y")
                if not model._in_bounds(x, y) or model._key(x, y) in model._splits:
                    raise ValueError("invalid or duplicate refined cell coordinate")
                expanded = cell.get("expanded", True)
                if type(expanded) is not bool:
                    raise ValueError("refined cell expanded must be a boolean")
                children = source_image(cell.get("children"), 2, 2)
                if expanded:
                    resolution(2 * size, 2 * size)
                model._splits[model._key(x, y)] = (image.getpixel((x, y)), expanded)
                for cy in range(2):
                    for cx in range(2):
                        field = field.replace(model._box(x, y, (cx, cy)), children.getpixel((cx, cy)))
            model._field = field
            return model
        shape = source.get("resolution")
        if not isinstance(shape, list) or len(shape) != 2:
            raise ValueError("invalid project resolution")
        model = cls(*resolution(*shape))
        if type(source.get("canvas_size")) is not int or source["canvas_size"] != model.width:
            raise ValueError("canvas_size does not match resolution width")
        model._field = ResolutionField.from_source(source.get("retained_field"))
        splits = source.get("retained_splits")
        if not isinstance(splits, list) or len(splits) > cls.MAX_SPLITS:
            raise ValueError("invalid retained split list")
        for entry in splits:
            if not isinstance(entry, dict):
                raise ValueError("invalid retained split")
            dims = entry.get("resolution")
            if not isinstance(dims, list) or len(dims) != 2:
                raise ValueError("invalid split resolution")
            w, h = resolution(*dims)
            x, y = entry.get("x"), entry.get("y")
            if type(x) is not int or type(y) is not int or not (0 <= x < w and 0 <= y < h):
                raise ValueError("invalid retained split coordinate")
            expanded = entry.get("expanded")
            if type(expanded) is not bool:
                raise ValueError("invalid retained split expansion state")
            if expanded:
                resolution(2 * w, 2 * h)
            key = (w, h, x, y)
            if key in model._splits:
                raise ValueError("duplicate retained split")
            model._splits[key] = (decoded_color(entry.get("base")), expanded)
        preview = source_image(source.get("pixels"), *model.resolution)
        if preview.tobytes() != model.image.tobytes():
            raise ValueError("project pixels disagree with retained field")
        expected = model.to_source().get("refined_cells", [])
        if source.get("refined_cells", []) != expected:
            raise ValueError("project refined_cells disagree with retained field")
        return model
