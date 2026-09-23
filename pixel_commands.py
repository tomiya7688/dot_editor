from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from pixel_backend import ChildCoordinate, Color, DetailPolicy, PixelCanvas
from pixel_layers import LayeredPixelCanvas
from resolution_field import resolution

Canvas = PixelCanvas | LayeredPixelCanvas


def canvas_from_source(source: object) -> Canvas:
    if not isinstance(source, dict):
        raise ValueError("project root must be a JSON object")
    if "layers" in source:
        return LayeredPixelCanvas.from_source(source)
    return PixelCanvas.from_source(source)


def load_project(path: str | Path) -> Canvas:
    target = Path(path)
    try:
        source = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"failed to read project: {error}") from error
    return canvas_from_source(source)


def save_project(canvas: Canvas, path: str | Path) -> None:
    """Atomically publish a complete project JSON file."""
    target = Path(path).resolve()
    content = json.dumps(canvas.to_source(), ensure_ascii=False, indent=2) + "\n"
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="\n", dir=target.parent,
            prefix=f".{target.name}.", suffix=".tmp", delete=False,
        ) as stream:
            temporary = Path(stream.name)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        if target.exists():
            temporary.chmod(target.stat().st_mode & 0o777)
        os.replace(temporary, target)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


class PixelCommandAPI:
    """Shared command surface for GUI, CUI, automation and game developer tools.

    The class owns no duplicate artwork state. Every command delegates to the
    supplied PixelCanvas/LayeredPixelCanvas and applies the same validation
    regardless of caller.
    """

    def __init__(self, canvas: Canvas) -> None:
        if not isinstance(canvas, (PixelCanvas, LayeredPixelCanvas)):
            raise TypeError("canvas must be PixelCanvas or LayeredPixelCanvas")
        self.canvas = canvas

    @classmethod
    def new(
        cls, width: int = 16, height: int | None = None, *, layered: bool = False
    ) -> "PixelCommandAPI":
        model: Canvas = (
            LayeredPixelCanvas(width, height) if layered else PixelCanvas(width, height)
        )
        return cls(model)

    @classmethod
    def load(cls, path: str | Path) -> "PixelCommandAPI":
        return cls(load_project(path))

    @property
    def resolution(self) -> tuple[int, int]:
        return self.canvas.resolution

    def _point(self, x: object, y: object) -> tuple[int, int]:
        try:
            px, py = int(x), int(y)
        except (TypeError, ValueError) as error:
            raise ValueError("pixel coordinates must be integers") from error
        if not (0 <= px < self.canvas.width and 0 <= py < self.canvas.height):
            raise ValueError(
                f"pixel coordinate ({px}, {py}) outside "
                f"{self.canvas.width}x{self.canvas.height}"
            )
        return px, py

    def _child(self, child: Sequence[object] | None) -> ChildCoordinate | None:
        if child is None:
            return None
        if len(child) != 2:
            raise ValueError("child coordinate requires CHILD_X CHILD_Y")
        try:
            values = tuple(int(value) for value in child)
        except (TypeError, ValueError) as error:
            raise ValueError("child coordinates must be integers") from error
        if values[0] not in (0, 1) or values[1] not in (0, 1):
            raise ValueError("child coordinate must be 0 or 1")
        return values  # type: ignore[return-value]

    def _region(
        self, x: object, y: object, width: object = 1, height: object = 1
    ) -> tuple[int, int, int, int]:
        px, py = self._point(x, y)
        try:
            region_width, region_height = int(width), int(height)
        except (TypeError, ValueError) as error:
            raise ValueError("region width and height must be integers") from error
        if region_width <= 0 or region_height <= 0:
            raise ValueError("region width and height must be positive")
        if px + region_width > self.canvas.width or py + region_height > self.canvas.height:
            raise ValueError("region must fit entirely inside the canvas")
        return px, py, region_width, region_height

    @staticmethod
    def _color(color: Sequence[int]) -> Color:
        return PixelCanvas._normalize_color(tuple(color))

    def set_resolution(
        self, width: int, height: int | None = None,
        detail_policy: DetailPolicy = "preserve",
    ) -> bool:
        return self.canvas.set_resolution(width, height, detail_policy=detail_policy)

    def upscale(self, detail_policy: DetailPolicy = "preserve") -> bool:
        return self.canvas.set_resolution(
            self.canvas.width * 2,
            self.canvas.height * 2,
            detail_policy=detail_policy,
        )

    def is_split(self, x: object, y: object) -> bool:
        px, py = self._point(x, y)
        return self.canvas.is_split(px, py)

    def split(self, x: object, y: object) -> bool:
        px, py = self._point(x, y)
        return self.canvas.split_cell(px, py)

    def split_region(
        self, x: object, y: object, width: object, height: object
    ) -> int:
        px, py, region_width, region_height = self._region(x, y, width, height)
        # Validate all failure conditions before making the first edit.
        resolution(self.canvas.width * 2, self.canvas.height * 2)
        target = (
            self.canvas.active
            if isinstance(self.canvas, LayeredPixelCanvas)
            else self.canvas
        )
        requested = sum(
            not target.is_split(column, row)
            for row in range(py, py + region_height)
            for column in range(px, px + region_width)
        )
        retained = len(target.to_source().get("retained_splits", []))
        if retained + requested > PixelCanvas.MAX_SPLITS:
            raise ValueError("too many retained split cells")
        changed = 0
        for row in range(py, py + region_height):
            for column in range(px, px + region_width):
                changed += int(self.canvas.split_cell(column, row))
        return changed

    def collapse(
        self, x: object, y: object, detail_policy: DetailPolicy = "preserve"
    ) -> bool:
        px, py = self._point(x, y)
        PixelCanvas._validate_detail_policy(detail_policy)
        return self.canvas.collapse_cell(
            px, py, discard_detail=detail_policy == "discard"
        )

    def paint(
        self, x: object, y: object, color: Sequence[int], *,
        child: Sequence[object] | None = None,
        detail_policy: DetailPolicy = "preserve",
    ) -> bool:
        px, py = self._point(x, y)
        return self.canvas.paint(
            px, py, self._color(color), child=self._child(child),
            detail_policy=detail_policy,
        )

    def erase(
        self, x: object, y: object, *,
        child: Sequence[object] | None = None,
        detail_policy: DetailPolicy = "preserve",
    ) -> bool:
        px, py = self._point(x, y)
        return self.canvas.paint(
            px, py, (0, 0, 0, 0), erase=True, child=self._child(child),
            detail_policy=detail_policy,
        )

    def fill(
        self, x: object, y: object, color: Sequence[int], *,
        detail_policy: DetailPolicy = "preserve",
    ) -> int:
        px, py = self._point(x, y)
        return self.canvas.fill(
            px, py, self._color(color), detail_policy=detail_policy
        )

    def sample(
        self, x: object, y: object, *,
        child: Sequence[object] | None = None,
        layer: str | None = None,
    ) -> Color:
        target: Canvas = self.canvas
        if layer is not None:
            if not isinstance(self.canvas, LayeredPixelCanvas):
                raise ValueError("layer selection requires a layered project")
            if layer not in self.canvas.layers:
                raise ValueError(f"layer does not exist: {layer}")
            target = self.canvas.layers[layer]
        px, py = self._point_for(target, x, y)
        return target.sample(px, py, self._child(child))

    @staticmethod
    def _point_for(canvas: Canvas, x: object, y: object) -> tuple[int, int]:
        try:
            px, py = int(x), int(y)
        except (TypeError, ValueError) as error:
            raise ValueError("pixel coordinates must be integers") from error
        if not (0 <= px < canvas.width and 0 <= py < canvas.height):
            raise ValueError(
                f"pixel coordinate ({px}, {py}) outside {canvas.width}x{canvas.height}"
            )
        return px, py

    def discard_detail(
        self, x: object, y: object, width: object = 1, height: object = 1
    ) -> int:
        region = self._region(x, y, width, height)
        return self.canvas.discard_detail(*region)

    def import_image(self, source: str | Path) -> bool:
        target = (
            self.canvas.active
            if isinstance(self.canvas, LayeredPixelCanvas)
            else self.canvas
        )
        target.import_image(source)
        return True

    def add_layer(self, name: str) -> bool:
        if not isinstance(self.canvas, LayeredPixelCanvas):
            raise ValueError("layer operations require a layered project")
        self.canvas.add_layer(name)
        return True

    def select_layer(self, name: str) -> bool:
        if not isinstance(self.canvas, LayeredPixelCanvas):
            raise ValueError("layer operations require a layered project")
        changed = name != self.canvas.active_layer
        self.canvas.select_layer(name)
        return changed

    def remove_layer(self, name: str | None = None) -> bool:
        if not isinstance(self.canvas, LayeredPixelCanvas):
            raise ValueError("layer operations require a layered project")
        self.canvas.remove_layer(name)
        return True

    def move_layer(self, direction: str, name: str | None = None) -> bool:
        if not isinstance(self.canvas, LayeredPixelCanvas):
            raise ValueError("layer operations require a layered project")
        return self.canvas.move_layer(direction, name)

    def set_layer_visibility(self, visible: bool, name: str | None = None) -> bool:
        if not isinstance(self.canvas, LayeredPixelCanvas):
            raise ValueError("layer operations require a layered project")
        return self.canvas.set_layer_visibility(visible, name)

    def inspect(self) -> dict[str, Any]:
        entries = (
            self.canvas.layers.items()
            if isinstance(self.canvas, LayeredPixelCanvas)
            else [(None, self.canvas)]
        )
        layers = []
        for name, layer in entries:
            cells = layer.detail_cells()
            expanded = sum(bool(cell["expanded"]) for cell in cells)
            layers.append({
                "name": name,
                "visible": (
                    self.canvas.layer_visibility.get(name, True)
                    if isinstance(self.canvas, LayeredPixelCanvas)
                    else True
                ),
                "retained_detail_cells": len(cells),
                "expanded_cells": expanded,
                "collapsed_detail_cells": len(cells) - expanded,
                "detail_cells": cells,
                "retained_resolution": list(layer.retained_resolution),
                "retained_patch_count": layer.retained_patch_count,
            })
        return {
            "schema_version": 1,
            "project_type": (
                "layered" if isinstance(self.canvas, LayeredPixelCanvas) else "flat"
            ),
            "resolution": list(self.canvas.resolution),
            "native_resolution": list(self.canvas.native_resolution),
            "retained_resolution": list(self.canvas.retained_resolution),
            "active_layer": (
                self.canvas.active_layer
                if isinstance(self.canvas, LayeredPixelCanvas)
                else None
            ),
            "has_detail": self.canvas.has_detail,
            "has_refinements": self.canvas.has_refinements,
            "layers": layers,
        }

    def inspect_sample(
        self, x: object, y: object, *,
        child: Sequence[object] | None = None,
        layer: str | None = None,
    ) -> dict[str, Any]:
        report = self.inspect()
        if layer is not None:
            if not isinstance(self.canvas, LayeredPixelCanvas):
                raise ValueError("layer selection requires a layered project")
            if layer not in self.canvas.layers:
                raise ValueError(f"layer does not exist: {layer}")
            sample_canvas: Canvas = self.canvas.layers[layer]
        else:
            sample_canvas = self.canvas
        px, py = self._point_for(sample_canvas, x, y)
        layer_name = (
            layer if layer is not None
            else self.canvas.active_layer
            if isinstance(self.canvas, LayeredPixelCanvas)
            else None
        )
        color = self.sample(px, py, child=child, layer=layer)
        report["sample"] = {
            "x": px, "y": py,
            "child": list(child) if child is not None else None,
            "layer": layer_name,
            "rgba": list(color),
        }
        return report

    def save(self, path: str | Path) -> None:
        save_project(self.canvas, path)

    def export_png(
        self, path: str | Path, export_size: int | None = None, *,
        output_resolution: tuple[int, int] | None = None,
    ) -> None:
        self.canvas.save_png(
            path, export_size, output_resolution=output_resolution
        )

    def execute(self, command: str, /, **parameters: Any) -> Any:
        """Execute one named command for automation/AI callers."""
        commands = {
            "set_resolution": self.set_resolution,
            "upscale": self.upscale,
            "split": self.split,
            "split_region": self.split_region,
            "collapse": self.collapse,
            "paint": self.paint,
            "erase": self.erase,
            "fill": self.fill,
            "sample": self.sample,
            "discard_detail": self.discard_detail,
            "import_image": self.import_image,
            "add_layer": self.add_layer,
            "select_layer": self.select_layer,
            "remove_layer": self.remove_layer,
            "move_layer": self.move_layer,
            "set_layer_visibility": self.set_layer_visibility,
            "inspect": self.inspect,
            "inspect_sample": self.inspect_sample,
            "save": self.save,
            "export_png": self.export_png,
        }
        try:
            operation = commands[command]
        except KeyError as error:
            raise ValueError(f"unknown command: {command}") from error
        return operation(**parameters)
