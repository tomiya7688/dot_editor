from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image

from pixel_backend import CanvasState, ChildCoordinate, DetailPolicy, PixelCanvas
from resolution_field import resolution

LayerState = tuple[list[tuple[str, CanvasState]], str]


class LayeredPixelCanvas:
    """Layer-aware composition and atomic document-wide resolution changes."""

    HISTORY_LIMIT = 50
    MAX_LAYERS = 256

    def __init__(self, size: int = 16, height: int | None = None) -> None:
        self.layers: dict[str, PixelCanvas] = {"背景": PixelCanvas(size, height)}
        self.active_layer = "背景"
        self._history: list[LayerState] = []
        self._future: list[LayerState] = []

    @property
    def size(self) -> int:
        return self.width

    @property
    def width(self) -> int:
        return self.active.width

    @property
    def height(self) -> int:
        return self.active.height

    @property
    def resolution(self) -> tuple[int, int]:
        return self.active.resolution

    @property
    def active(self) -> PixelCanvas:
        return self.layers[self.active_layer]

    @property
    def has_refinements(self) -> bool:
        return any(layer.has_refinements for layer in self.layers.values())

    @property
    def has_detail(self) -> bool:
        return any(layer.has_detail for layer in self.layers.values())

    @property
    def retained_resolution(self) -> tuple[int, int]:
        shapes = [layer.retained_resolution for layer in self.layers.values()]
        return max(w for w, _ in shapes), max(h for _, h in shapes)

    @property
    def native_resolution(self) -> tuple[int, int]:
        return (self.width * 2, self.height * 2) if self.has_refinements else self.resolution

    @property
    def native_size(self) -> int:
        return self.native_resolution[0]

    def _state(self) -> LayerState:
        return [(name, layer._state()) for name, layer in self.layers.items()], self.active_layer

    def _record(self, state: LayerState) -> None:
        self._history.append(state)
        del self._history[:-self.HISTORY_LIMIT]
        self._future.clear()

    def _restore(self, state: LayerState) -> None:
        entries, active = state
        self.layers = {}
        for name, canvas_state in entries:
            canvas = PixelCanvas(*canvas_state[0])
            canvas._restore_state(canvas_state)
            self.layers[name] = canvas
        self.active_layer = active

    def _edit_active(self, operation: str, *args: Any, **kwargs: Any) -> Any:
        before = self._state()
        result = getattr(self.active, operation)(*args, **kwargs)
        if result:
            self._record(before)
        return result

    def add_layer(self, name: str) -> None:
        if not isinstance(name, str) or not name.strip():
            raise ValueError("layer name must not be empty")
        clean = name.strip()
        if clean in self.layers:
            raise ValueError(f"layer already exists: {clean}")
        if len(self.layers) >= self.MAX_LAYERS:
            raise ValueError("too many layers")
        before = self._state()
        self.layers[clean] = PixelCanvas(*self.resolution)
        self.active_layer = clean
        self._record(before)

    def select_layer(self, name: str) -> None:
        if name not in self.layers:
            raise KeyError(name)
        self.active_layer = name

    def remove_layer(self, name: str | None = None) -> None:
        target = self.active_layer if name is None else name
        if target not in self.layers:
            raise KeyError(target)
        if len(self.layers) == 1:
            raise ValueError("at least one layer is required")
        before = self._state()
        del self.layers[target]
        if target == self.active_layer:
            self.active_layer = next(iter(self.layers))
        self._record(before)

    def is_split(self, x: int, y: int) -> bool:
        return self.active.is_split(x, y)

    def split_cell(self, x: int, y: int) -> bool:
        return self._edit_active("split_cell", x, y)

    def collapse_cell(self, x: int, y: int, discard_detail: bool = False) -> bool:
        return self._edit_active("collapse_cell", x, y, discard_detail=discard_detail)

    def has_detail_at(self, x: int, y: int) -> bool:
        return self.active.has_detail_at(x, y)

    def paint(self, x: int, y: int, color: tuple[int, ...], erase: bool = False,
              child: ChildCoordinate | None = None, detail_policy: DetailPolicy = "preserve") -> bool:
        return self._edit_active("paint", x, y, color, erase=erase, child=child, detail_policy=detail_policy)

    def sample(self, x: int, y: int, child: ChildCoordinate | None = None) -> tuple[int, int, int, int]:
        return self.active.sample(x, y, child)

    def fill(self, x: int, y: int, color: tuple[int, ...], erase: bool = False,
             detail_policy: DetailPolicy = "preserve") -> int:
        return self._edit_active("fill", x, y, color, erase=erase, detail_policy=detail_policy)

    def discard_detail(self, x: int, y: int, width: int = 1, height: int = 1) -> int:
        return self._edit_active("discard_detail", x, y, width, height)

    def set_resolution(self, width: int, height: int | None = None,
                       detail_policy: DetailPolicy = "preserve") -> bool:
        target = resolution(width, height)
        PixelCanvas._validate_detail_policy(detail_policy)
        if target == self.resolution and detail_policy == "preserve":
            return False
        # Stage every layer first. Validation/allocation failure leaves the
        # original layers, document history and selection unchanged.
        candidates = {}
        for name, layer in self.layers.items():
            candidate = PixelCanvas(*layer.resolution)
            candidate._restore_state(layer._state())
            candidate.set_resolution(*target, detail_policy=detail_policy)
            candidates[name] = candidate
        before = self._state()
        self.layers = candidates
        self._record(before)
        return True

    def resize(self, target: int, height: int | None = None,
               detail_policy: DetailPolicy = "preserve") -> bool:
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
        self._restore(self._history.pop())
        return True

    def redo(self) -> bool:
        if not self._future:
            return False
        self._history.append(self._state())
        del self._history[:-self.HISTORY_LIMIT]
        self._restore(self._future.pop())
        return True

    def composite(self) -> Image.Image:
        target = self.native_resolution
        result = Image.new("RGBA", target)
        for layer in self.layers.values():
            result.alpha_composite(layer.render(target))
        return result

    def render_resolution(self, width: int, height: int | None = None) -> Image.Image:
        target = resolution(width, height)
        result = Image.new("RGBA", target)
        for layer in self.layers.values():
            result.alpha_composite(layer.render_resolution(*target))
        return result

    def save_png(self, path: str | Path, export_size: int | None = None,
                 *, output_resolution: tuple[int, int] | None = None) -> None:
        if export_size is not None and output_resolution is not None:
            raise ValueError("choose export size or output resolution, not both")
        if output_resolution is not None:
            output = self.render_resolution(*output_resolution)
        else:
            output = self.composite()
            if export_size is not None:
                target = resolution(export_size)
                if export_size < max(output.size):
                    raise ValueError("export size cannot be smaller than native canvas size")
                output = output.resize(target, Image.Resampling.NEAREST)
        output.save(path, "PNG")

    def to_source(self) -> dict[str, Any]:
        return {
            "version": 2, "canvas_size": self.width, "resolution": list(self.resolution),
            "active_layer": self.active_layer,
            "layers": [{"name": name, "source": canvas.to_source()}
                       for name, canvas in self.layers.items()],
        }

    @classmethod
    def from_source(cls, source: dict[str, Any]) -> LayeredPixelCanvas:
        if not isinstance(source, dict):
            raise ValueError("layered project must be a JSON object")
        version = source.get("version", 1)
        if type(version) is not int or version not in (1, 2):
            raise ValueError("unsupported layered project version")
        entries = source.get("layers")
        if not isinstance(entries, list) or not (1 <= len(entries) <= cls.MAX_LAYERS):
            raise ValueError("layer source must contain 1..256 layers")
        layers: dict[str, PixelCanvas] = {}
        expected = None
        for entry in entries:
            if not isinstance(entry, dict):
                raise ValueError("invalid layer entry")
            name = entry.get("name")
            if not isinstance(name, str) or not name.strip():
                raise ValueError("layer name must not be empty")
            if name in layers:
                raise ValueError(f"duplicate layer name: {name}")
            layer = PixelCanvas.from_source(entry.get("source"))
            if expected is None:
                expected = layer.resolution
            elif layer.resolution != expected:
                raise ValueError("all layers must use the same canvas size and resolution")
            layers[name] = layer
        declared = source.get("canvas_size")
        if declared is not None and (type(declared) is not int or declared != expected[0]):
            raise ValueError("layered canvas_size does not match layer size")
        if version == 2:
            shape = source.get("resolution")
            if not isinstance(shape, list) or len(shape) != 2 or resolution(*shape) != expected:
                raise ValueError("layered resolution does not match layer resolution")
        active = source.get("active_layer", next(iter(layers)))
        if not isinstance(active, str) or active not in layers:
            raise ValueError("active_layer must reference an existing layer")
        model = cls(*expected)
        model.layers, model.active_layer = layers, active
        return model
