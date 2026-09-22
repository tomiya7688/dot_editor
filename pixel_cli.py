from __future__ import annotations

import argparse
import json
import os
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from pixel_backend import PixelCanvas
from pixel_layers import LayeredPixelCanvas

Canvas = PixelCanvas | LayeredPixelCanvas


def parse_color(value: str) -> tuple[int, int, int, int]:
    clean = value.strip().lstrip("#")
    if len(clean) != 6:
        raise argparse.ArgumentTypeError("color must be #RRGGBB")
    try:
        return tuple(int(clean[index:index + 2], 16) for index in (0, 2, 4)) + (255,)
    except ValueError as error:
        raise argparse.ArgumentTypeError("color must be #RRGGBB") from error


def load_project(path: Path) -> Canvas:
    try:
        source = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"failed to read project: {error}") from error

    if not isinstance(source, dict):
        raise ValueError("project root must be a JSON object")
    if "layers" in source:
        return LayeredPixelCanvas.from_source(source)
    return PixelCanvas.from_source(source)


def save_project(canvas: Canvas, path: Path) -> None:
    """Publish a complete JSON file; a failed write must not truncate the project."""
    content = json.dumps(canvas.to_source(), ensure_ascii=False, indent=2) + "\n"
    # Follow an existing symlink as write_text did, rather than replacing the link.
    target = path.resolve()
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


def checked_point(canvas: Canvas, values: Sequence[str | int]) -> tuple[int, int]:
    x, y = (int(value) for value in values)
    if not (0 <= x < canvas.size and 0 <= y < canvas.size):
        raise ValueError(f"pixel coordinate ({x}, {y}) outside {canvas.size}x{canvas.size}")
    return x, y


def checked_region(canvas: Canvas, values: Sequence[int]) -> tuple[int, int, int, int]:
    if len(values) not in (2, 4):
        raise ValueError("region requires X Y or X Y WIDTH HEIGHT")
    x, y = checked_point(canvas, values[:2])
    width, height = values[2:] if len(values) == 4 else (1, 1)
    if width <= 0 or height <= 0:
        raise ValueError("region width and height must be positive")
    if x + width > canvas.size or y + height > canvas.size:
        raise ValueError("region must fit entirely inside the canvas")
    return x, y, width, height


def inspect_project(canvas: Canvas) -> dict[str, Any]:
    """Describe public backend state without editing it or serializing history."""
    entries = canvas.layers.items() if isinstance(canvas, LayeredPixelCanvas) else [(None, canvas)]
    layers = []
    for name, layer in entries:
        cells = [
            {"x": cell["x"], "y": cell["y"], "expanded": cell.get("expanded", True)}
            for cell in layer.to_source().get("refined_cells", [])
        ]
        expanded = sum(cell["expanded"] for cell in cells)
        layers.append({
            "name": name,
            "retained_detail_cells": len(cells),
            "expanded_cells": expanded,
            "collapsed_detail_cells": len(cells) - expanded,
            "detail_cells": cells,
        })
    return {
        "schema_version": 1,
        "project_type": "layered" if isinstance(canvas, LayeredPixelCanvas) else "flat",
        "resolution": [canvas.size, canvas.size],
        "native_resolution": [canvas.native_size, canvas.native_size],
        "active_layer": canvas.active_layer if isinstance(canvas, LayeredPixelCanvas) else None,
        "has_detail": canvas.has_detail,
        "has_refinements": canvas.has_refinements,
        "layers": layers,
    }


def inspect_command(canvas: Canvas, args: argparse.Namespace) -> dict[str, Any]:
    if args.child is not None and args.sample is None:
        raise ValueError("--child requires --sample X Y")
    if args.layer is not None and args.sample is None:
        raise ValueError("--layer requires --sample X Y")
    report = inspect_project(canvas)
    if args.sample is not None:
        layer_name = canvas.active_layer if isinstance(canvas, LayeredPixelCanvas) else None
        target = canvas
        if args.layer is not None:
            if not isinstance(canvas, LayeredPixelCanvas):
                raise ValueError("--layer requires a layered project")
            if args.layer not in canvas.layers:
                raise ValueError(f"layer does not exist: {args.layer}")
            layer_name = args.layer
            target = canvas.layers[layer_name]
        x, y = checked_point(target, args.sample)
        child = tuple(args.child) if args.child is not None else None
        report["sample"] = {
            "x": x, "y": y, "child": child, "layer": layer_name,
            "rgba": target.sample(x, y, child),
        }
    return report


def edit_project(canvas: Canvas, args: argparse.Namespace) -> bool:
    """Dispatch in the documented fixed order; editing rules stay in the backend."""
    operations = (
        args.import_image, args.split, args.split_region, args.paint, args.paint_child,
        args.fill, args.erase, args.erase_child, args.collapse, args.discard_detail,
        args.add_layer, args.select_layer,
    )
    if not (any(value is not None for value in operations) or args.upscale or args.remove_layer):
        raise ValueError("edit requires an operation")
    changed = False
    if isinstance(canvas, LayeredPixelCanvas):
        if args.add_layer is not None:
            canvas.add_layer(args.add_layer)
            changed = True
        if args.select_layer is not None:
            changed = args.select_layer != canvas.active_layer or changed
            canvas.select_layer(args.select_layer)
        if args.remove_layer:
            canvas.remove_layer()
            changed = True
    elif args.add_layer is not None or args.select_layer is not None or args.remove_layer:
        raise ValueError("layer operations require a layered project")

    if args.import_image is not None:
        target = canvas.active if isinstance(canvas, LayeredPixelCanvas) else canvas
        target.import_image(args.import_image)
        changed = True
    if args.split is not None:
        changed = canvas.split_cell(*checked_point(canvas, args.split)) or changed
    if args.split_region is not None:
        x, y, width, height = checked_region(canvas, args.split_region)
        for py in range(y, y + height):
            for px in range(x, x + width):
                changed = canvas.split_cell(px, py) or changed
    if args.paint is not None:
        x, y = checked_point(canvas, args.paint[:2])
        changed = canvas.paint(x, y, parse_color(args.paint[2]), detail_policy=args.detail_policy) or changed
    if args.paint_child is not None:
        x, y = checked_point(canvas, args.paint_child[:2])
        cx, cy = (int(value) for value in args.paint_child[2:4])
        changed = canvas.paint(x, y, parse_color(args.paint_child[4]), child=(cx, cy)) or changed
    if args.fill is not None:
        x, y = checked_point(canvas, args.fill[:2])
        changed = canvas.fill(x, y, parse_color(args.fill[2]), detail_policy=args.detail_policy) > 0 or changed
    if args.erase is not None:
        x, y = checked_point(canvas, args.erase)
        changed = canvas.paint(x, y, (0, 0, 0, 0), erase=True, detail_policy=args.detail_policy) or changed
    if args.erase_child is not None:
        x, y = checked_point(canvas, args.erase_child[:2])
        cx, cy = args.erase_child[2:]
        changed = canvas.paint(x, y, (0, 0, 0, 0), erase=True, child=(cx, cy)) or changed
    if args.collapse is not None:
        x, y = checked_point(canvas, args.collapse)
        changed = canvas.collapse_cell(x, y, discard_detail=args.detail_policy == "discard") or changed
    if args.discard_detail is not None:
        changed = canvas.discard_detail(*checked_region(canvas, args.discard_detail)) > 0 or changed
    if args.upscale:
        changed = canvas.upscale() or changed
    return changed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="PixelCanvas command line editor")
    subparsers = parser.add_subparsers(dest="command", required=True)
    new_parser = subparsers.add_parser("new")
    new_parser.add_argument("--size", type=int, default=16, choices=PixelCanvas.SUPPORTED_SIZES)
    new_parser.add_argument("--layered", action="store_true")
    new_parser.add_argument("--output", type=Path, required=True)

    edit_parser = subparsers.add_parser(
        "edit",
        epilog="Order: layers, import, split, paint, paint-child, fill, erase, "
               "erase-child, collapse, discard-detail, upscale. Split inherits the "
               "parent color before paint; use separate invocations for another order.",
    )
    edit_parser.add_argument("--project", type=Path, required=True)
    edit_parser.add_argument("--output", type=Path)
    edit_parser.add_argument("--split", nargs=2, type=int, metavar=("X", "Y"))
    edit_parser.add_argument("--split-region", nargs=4, type=int, metavar=("X", "Y", "WIDTH", "HEIGHT"))
    edit_parser.add_argument("--paint", nargs=3, metavar=("X", "Y", "COLOR"))
    edit_parser.add_argument("--paint-child", nargs=5, metavar=("X", "Y", "CHILD_X", "CHILD_Y", "COLOR"))
    edit_parser.add_argument("--fill", nargs=3, metavar=("X", "Y", "COLOR"))
    edit_parser.add_argument("--erase", nargs=2, type=int, metavar=("X", "Y"))
    edit_parser.add_argument("--erase-child", nargs=4, type=int, metavar=("X", "Y", "CHILD_X", "CHILD_Y"))
    edit_parser.add_argument("--collapse", nargs=2, type=int, metavar=("X", "Y"),
                             help="collapse a cell; keeps its detail by default")
    edit_parser.add_argument("--discard-detail", nargs="+", type=int, metavar="N",
                             help="discard a cell (X Y) or a region (X Y WIDTH HEIGHT)")
    edit_parser.add_argument("--detail-policy", choices=("preserve", "discard"), default="preserve",
                             help="detail policy for parent paint/fill/erase and collapse (default: preserve)")
    edit_parser.add_argument("--upscale", action="store_true")
    edit_parser.add_argument("--import-image", type=Path)
    edit_parser.add_argument("--add-layer")
    edit_parser.add_argument("--select-layer")
    edit_parser.add_argument("--remove-layer", action="store_true")

    inspect_parser = subparsers.add_parser("inspect", help="read-only project state as JSON")
    inspect_parser.add_argument("--project", type=Path, required=True)
    inspect_parser.add_argument("--sample", nargs=2, type=int, metavar=("X", "Y"))
    inspect_parser.add_argument("--child", nargs=2, type=int, metavar=("CHILD_X", "CHILD_Y"),
                                help="sample retained child detail, even if collapsed")
    inspect_parser.add_argument("--layer", help="sample this layer instead of the saved active layer")

    export_parser = subparsers.add_parser("export")
    export_parser.add_argument("--project", type=Path, required=True)
    export_parser.add_argument("--output", type=Path, required=True)
    export_parser.add_argument("--size", type=int)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "new":
            canvas: Canvas = LayeredPixelCanvas(args.size) if args.layered else PixelCanvas(args.size)
            save_project(canvas, args.output)
            return 0
        canvas = load_project(args.project)
        if args.command == "export":
            canvas.save_png(args.output, args.size)
        elif args.command == "inspect":
            # ASCII escaping also works in non-UTF-8 terminal/pipeline environments.
            print(json.dumps(inspect_command(canvas, args), ensure_ascii=True, sort_keys=True))
        else:
            changed = edit_project(canvas, args)
            # Valid idempotent commands are successful; a no-op need not touch disk.
            if changed or args.output is not None:
                save_project(canvas, args.output or args.project)
        return 0
    except (ValueError, KeyError, IndexError, OSError, UnicodeError, argparse.ArgumentTypeError) as error:
        parser.error(str(error))
    return 2  # argparse.error exits; useful to callers/static type checkers.


if __name__ == "__main__":
    raise SystemExit(main())
