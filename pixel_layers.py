from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image

from pixel_backend import ChildCoordinate, PixelCanvas


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

    def paint(
        self,
        x: int,
        y: int,
        color: tuple[int, ...],
        erase: bool = False,
        child: ChildCoordinate | None = None,
    ) -> bool:
        return self.active.paint(x, y, color, erase, child)

    def sample(
        self,
        x: int,
        y: int,
        child: ChildCoordinate | None = None,
    ) -> tuple[int, int, int, int]:
        return self.active.sample(x, y, child)

    def fill(self, x: int, y: int, color: tuple[int, ...], erase: bool = False) -> int:
        return self.active.fill(x, y, color, erase)

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
        entries = source.get("layers")
        if not isinstance(entries, list) or not entries:
            raise ValueError("layer source must contain layers")
        first_source = entries[0].get("source") if isinstance(entries[0], dict) else None
        if not isinstance(first_source, dict):
            raise ValueError("invalid layer source")
        first_canvas = PixelCanvas.from_source(first_source)
        model = cls(first_canvas.size)
        model.layers.clear()
        for index, entry in enumerate(entries):
            if not isinstance(entry, dict) or not isinstance(entry.get("name"), str):
                raise ValueError("invalid layer entry")
            layer_source = entry.get("source")
            if not isinstance(layer_source, dict):
                raise ValueError("invalid layer source")
            layer = first_canvas if index == 0 else PixelCanvas.from_source(layer_source)
            if layer.size != first_canvas.size:
                raise ValueError("all layers must use the same canvas size")
            model.layers[entry["name"]] = layer
        active = source.get("active_layer", next(iter(model.layers)))
        model.select_layer(active if isinstance(active, str) else next(iter(model.layers)))
        return model
