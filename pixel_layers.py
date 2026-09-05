from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image

from pixel_backend import PixelCanvas


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

    def paint(self, x: int, y: int, color: tuple[int, int, int, int], erase: bool = False) -> bool:
        return self.active.paint(x, y, color, erase)

    def fill(self, x: int, y: int, color: tuple[int, int, int, int], erase: bool = False) -> int:
        return self.active.fill(x, y, color, erase)

    def upscale(self) -> bool:
        changed = False
        for layer in self.layers.values():
            changed = layer.upscale() or changed
        return changed

    def composite(self) -> Image.Image:
        result = Image.new("RGBA", (self.size, self.size), (0, 0, 0, 0))
        for layer in self.layers.values():
            result.alpha_composite(layer.image)
        return result

    def save_png(self, path: str | Path, export_size: int | None = None) -> None:
        output = self.composite()
        if export_size is not None:
            if export_size < self.size:
                raise ValueError("export size cannot be smaller than canvas size")
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
        model = cls(first_source["canvas_size"])
        model.layers.clear()
        for entry in entries:
            if not isinstance(entry, dict) or not isinstance(entry.get("name"), str):
                raise ValueError("invalid layer entry")
            layer_source = entry.get("source")
            if not isinstance(layer_source, dict):
                raise ValueError("invalid layer source")
            model.layers[entry["name"]] = PixelCanvas.from_source(layer_source)
        active = source.get("active_layer", next(iter(model.layers)))
        model.select_layer(active if isinstance(active, str) else next(iter(model.layers)))
        return model
