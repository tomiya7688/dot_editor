from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image

from pixel_backend import ChildCoordinate, DetailPolicy, PixelCanvas, Resolution


class LayeredPixelCanvas:
    """Layer-aware composition built on the shared PixelCanvas model."""

    def __init__(self, size: int | Resolution = 16, height: int | None = None) -> None:
        self.layers: dict[str, PixelCanvas] = {"背景": PixelCanvas(size, height)}
        self.active_layer = "背景"

    @property
    def active(self) -> PixelCanvas:
        return self.layers[self.active_layer]

    @property
    def width(self) -> int:
        return self.active.width

    @property
    def height(self) -> int:
        return self.active.height

    @property
    def resolution(self) -> Resolution:
        return self.active.resolution

    @property
    def size(self) -> int:
        return self.active.size

    @property
    def has_refinements(self) -> bool:
        return any(layer.has_refinements for layer in self.layers.values())

    @property
    def has_detail(self) -> bool:
        return any(layer.has_detail for layer in self.layers.values())

    @property
    def native_resolution(self) -> Resolution:
        return (
            self.width * 2 if self.has_refinements else self.width,
            self.height * 2 if self.has_refinements else self.height,
        )

    @property
    def native_size(self) -> int | Resolution:
        width, height = self.native_resolution
        return width if width == height else (width, height)

    def add_layer(self, name: str) -> None:
        clean = str(name).strip()
        if not clean:
            raise ValueError("layer name must not be empty")
        if clean in self.layers:
            raise ValueError(f"layer already exists: {clean}")
        self.layers[clean] = PixelCanvas(self.resolution)
        self.active_layer = clean

    def select_layer(self, name: str) -> None:
        if name not in self.layers:
            raise KeyError(name)
        self.active_layer = name

    def remove_layer(self, name: str | None = None) -> None:
        target = name or self.active_layer
        if target not in self.layers:
            raise KeyError(target)
        if len(self.layers) == 1:
            raise ValueError("at least one layer is required")
        del self.layers[target]
        self.active_layer = next(iter(self.layers))

    def is_split(self, x: int, y: int) -> bool:
        return self.active.is_split(x, y)

    def split_cell(self, x: int, y: int) -> bool:
        return self.active.split_cell(x, y)

    def collapse_cell(self, x: int, y: int, discard_detail: bool = False) -> bool:
        return self.active.collapse_cell(x, y, discard_detail=discard_detail)

    def has_detail_at(self, x: int, y: int) -> bool:
        return self.active.has_detail_at(x, y)

    def paint(
        self,
        x: int,
        y: int,
        color: tuple[int, ...],
        erase: bool = False,
        child: ChildCoordinate | None = None,
        detail_policy: DetailPolicy = "preserve",
    ) -> bool:
        return self.active.paint(
            x,
            y,
            color,
            erase=erase,
            child=child,
            detail_policy=detail_policy,
        )

    def sample(
        self,
        x: int,
        y: int,
        child: ChildCoordinate | None = None,
    ) -> tuple[int, int, int, int]:
        return self.active.sample(x, y, child)

    def fill(
        self,
        x: int,
        y: int,
        color: tuple[int, ...],
        erase: bool = False,
        detail_policy: DetailPolicy = "preserve",
    ) -> int:
        return self.active.fill(
            x,
            y,
            color,
            erase=erase,
            detail_policy=detail_policy,
        )

    def discard_detail(self, x: int, y: int, width: int = 1, height: int = 1) -> int:
        return self.active.discard_detail(x, y, width, height)

    def set_resolution(self, width: int, height: int | None = None) -> bool:
        resolved_height = width if height is None else height
        PixelCanvas._validate_resolution(int(width), int(resolved_height))
        target = (int(width), int(resolved_height))
        if target == self.resolution:
            return False
        for layer in self.layers.values():
            layer.set_resolution(*target)
        return True

    def resize(self, target: int) -> bool:
        return self.set_resolution(target, target)

    def upscale(self) -> bool:
        target = (self.width * 2, self.height * 2)
        if target[0] > PixelCanvas.MAX_RESOLUTION or target[1] > PixelCanvas.MAX_RESOLUTION:
            return False
        return self.set_resolution(*target)

    def composite(self, resolution: Resolution | None = None) -> Image.Image:
        target = self.native_resolution if resolution is None else resolution
        result = Image.new("RGBA", target, (0, 0, 0, 0))
        for layer in self.layers.values():
            result.alpha_composite(layer.render(target))
        return result

    def save_png(
        self,
        path: str | Path,
        export_size: int | Resolution | None = None,
    ) -> None:
        if export_size is None:
            target = self.native_resolution
        elif isinstance(export_size, tuple):
            target = PixelCanvas._coerce_resolution(export_size)
        else:
            target = (int(export_size), int(export_size))
        self.composite(target).save(path, "PNG")

    def to_source(self) -> dict[str, Any]:
        canvas_size: int | list[int] = (
            self.width if self.width == self.height else [self.width, self.height]
        )
        return {
            "canvas_size": canvas_size,
            "canvas_width": self.width,
            "canvas_height": self.height,
            "active_layer": self.active_layer,
            "layers": [
                {"name": name, "source": canvas.to_source()}
                for name, canvas in self.layers.items()
            ],
        }

    @classmethod
    def from_source(cls, source: dict[str, Any]) -> "LayeredPixelCanvas":
        if not isinstance(source, dict):
            raise ValueError("layered project must be a JSON object")

        entries = source.get("layers")
        if not isinstance(entries, list) or not entries:
            raise ValueError("layer source must contain at least one layer")

        model: LayeredPixelCanvas | None = None
        expected_resolution: Resolution | None = None
        seen_names: set[str] = set()

        for entry in entries:
            if not isinstance(entry, dict):
                raise ValueError("invalid layer entry")
            name = entry.get("name")
            if not isinstance(name, str) or not name.strip():
                raise ValueError("layer name must not be empty")
            if name in seen_names:
                raise ValueError(f"duplicate layer name: {name}")
            seen_names.add(name)

            layer_source = entry.get("source")
            if not isinstance(layer_source, dict):
                raise ValueError("invalid layer source")
            layer = PixelCanvas.from_source(layer_source)

            if expected_resolution is None:
                expected_resolution = layer.resolution
                model = cls(expected_resolution)
                model.layers.clear()
            elif layer.resolution != expected_resolution:
                raise ValueError("all layers must use the same canvas resolution")

            assert model is not None
            model.layers[name] = layer

        assert model is not None and expected_resolution is not None

        declared_width = source.get("canvas_width")
        declared_height = source.get("canvas_height")
        if declared_width is not None or declared_height is not None:
            if (
                not isinstance(declared_width, int)
                or not isinstance(declared_height, int)
                or (declared_width, declared_height) != expected_resolution
            ):
                raise ValueError("layered canvas resolution does not match layer resolution")
        elif "canvas_size" in source:
            declared = source["canvas_size"]
            expected_declared: int | list[int] = (
                expected_resolution[0]
                if expected_resolution[0] == expected_resolution[1]
                else [expected_resolution[0], expected_resolution[1]]
            )
            if declared != expected_declared:
                raise ValueError("layered canvas_size does not match layer resolution")

        active = source.get("active_layer", next(iter(model.layers)))
        if not isinstance(active, str) or active not in model.layers:
            raise ValueError("active_layer must reference an existing layer")
        model.active_layer = active
        return model
