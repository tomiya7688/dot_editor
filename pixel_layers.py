from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image

from pixel_backend import ChildCoordinate, DetailPolicy, PixelCanvas


class LayeredPixelCanvas:
    """Layer-aware composition built on the shared PixelCanvas model."""

    def __init__(self, size: int = 16) -> None:
        self.layers: dict[str, PixelCanvas] = {"背景": PixelCanvas(size)}
        self.active_layer = "背景"

    @property
    def size(self) -> int:
        return self.layers[self.active_layer].size

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
    def native_size(self) -> int:
        return self.size * 2 if self.has_refinements else self.size

    def add_layer(self, name: str) -> None:
        clean = str(name).strip()
        if not clean:
            raise ValueError("layer name must not be empty")
        if clean in self.layers:
            raise ValueError(f"layer already exists: {clean}")
        self.layers[clean] = PixelCanvas(self.size)
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

    def resize(self, target: int) -> bool:
        if target == self.size:
            return False
        PixelCanvas._validate_size(target)
        for layer in self.layers.values():
            layer.resize(target)
        return True

    def upscale(self) -> bool:
        if self.size >= PixelCanvas.SUPPORTED_SIZES[-1]:
            return False
        return self.resize(self.size * 2)

    def composite(self) -> Image.Image:
        target_size = self.native_size
        result = Image.new("RGBA", (target_size, target_size), (0, 0, 0, 0))
        for layer in self.layers.values():
            result.alpha_composite(layer.render(target_size))
        return result

    def save_png(self, path: str | Path, export_size: int | None = None) -> None:
        output = self.composite()
        if export_size is not None:
            if export_size < output.width:
                raise ValueError("export size cannot be smaller than native canvas size")
            output = output.resize((export_size, export_size), Image.Resampling.NEAREST)
        output.save(path, "PNG")

    def to_source(self) -> dict[str, Any]:
        return {
            "canvas_size": self.size,
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
        expected_size: int | None = None
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

            if expected_size is None:
                expected_size = layer.size
                model = cls(layer.size)
                model.layers.clear()
            elif layer.size != expected_size:
                raise ValueError("all layers must use the same canvas size")

            assert model is not None
            model.layers[name] = layer

        assert model is not None and expected_size is not None

        declared_size = source.get("canvas_size")
        if declared_size is not None:
            if not isinstance(declared_size, int) or declared_size != expected_size:
                raise ValueError("layered canvas_size does not match layer size")

        active = source.get("active_layer", next(iter(model.layers)))
        if not isinstance(active, str) or active not in model.layers:
            raise ValueError("active_layer must reference an existing layer")
        model.active_layer = active
        return model
