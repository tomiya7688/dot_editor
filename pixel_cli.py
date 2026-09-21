from __future__ import annotations

import argparse
import json
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
    path.write_text(
        json.dumps(canvas.to_source(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def canvas_status(canvas: Canvas) -> dict[str, Any]:
    status: dict[str, Any] = {
        "width": canvas.width,
        "height": canvas.height,
        "resolution": [canvas.width, canvas.height],
        "has_detail": canvas.has_detail,
        "has_refinements": canvas.has_refinements,
        "layered": isinstance(canvas, LayeredPixelCanvas),
    }
    if isinstance(canvas, LayeredPixelCanvas):
        status["active_layer"] = canvas.active_layer
        status["layers"] = list(canvas.layers)
        status["detail_resolutions"] = {
            name: list(layer.detail_resolution)
            for name, layer in canvas.layers.items()
        }
    else:
        status["detail_resolution"] = list(canvas.detail_resolution)
    return status


def main() -> int:
    parser = argparse.ArgumentParser(description="PixelCanvas command line editor")
    subparsers = parser.add_subparsers(dest="command", required=True)

    new_parser = subparsers.add_parser("new")
    new_parser.add_argument("--size", type=int, default=16)
    new_parser.add_argument("--resolution", nargs=2, type=int, metavar=("WIDTH", "HEIGHT"))
    new_parser.add_argument("--layered", action="store_true")
    new_parser.add_argument("--output", type=Path, required=True)

    edit_parser = subparsers.add_parser("edit")
    edit_parser.add_argument("--project", type=Path, required=True)
    edit_parser.add_argument("--output", type=Path)
    edit_parser.add_argument("--resolution", nargs=2, type=int, metavar=("WIDTH", "HEIGHT"))
    edit_parser.add_argument(
        "--detail-policy",
        choices=("preserve", "discard"),
        default="preserve",
    )
    edit_parser.add_argument("--split", nargs=2, metavar=("X", "Y"))
    edit_parser.add_argument("--collapse", nargs=2, metavar=("X", "Y"))
    edit_parser.add_argument(
        "--discard-detail",
        nargs="+",
        metavar="N",
        help="X Y [WIDTH HEIGHT]",
    )
    edit_parser.add_argument("--paint", nargs=3, metavar=("X", "Y", "COLOR"))
    edit_parser.add_argument(
        "--paint-child",
        nargs=5,
        metavar=("X", "Y", "CHILD_X", "CHILD_Y", "COLOR"),
    )
    edit_parser.add_argument("--fill", nargs=3, metavar=("X", "Y", "COLOR"))
    edit_parser.add_argument("--erase", nargs=2, metavar=("X", "Y"))
    edit_parser.add_argument(
        "--erase-child",
        nargs=4,
        metavar=("X", "Y", "CHILD_X", "CHILD_Y"),
    )
    edit_parser.add_argument("--upscale", action="store_true")
    edit_parser.add_argument("--import-image", type=Path)
    edit_parser.add_argument("--add-layer")
    edit_parser.add_argument("--select-layer")
    edit_parser.add_argument("--remove-layer", action="store_true")

    export_parser = subparsers.add_parser("export")
    export_parser.add_argument("--project", type=Path, required=True)
    export_parser.add_argument("--output", type=Path, required=True)
    export_parser.add_argument("--size", type=int)
    export_parser.add_argument("--resolution", nargs=2, type=int, metavar=("WIDTH", "HEIGHT"))

    inspect_parser = subparsers.add_parser("inspect")
    inspect_parser.add_argument("--project", type=Path, required=True)

    args = parser.parse_args()

    try:
        if args.command == "new":
            resolution = tuple(args.resolution) if args.resolution else (args.size, args.size)
            PixelCanvas._validate_resolution(*resolution)
            canvas: Canvas = (
                LayeredPixelCanvas(resolution)
                if args.layered
                else PixelCanvas(resolution)
            )
            save_project(canvas, args.output)
            return 0

        canvas = load_project(args.project)

        if args.command == "inspect":
            print(json.dumps(canvas_status(canvas), ensure_ascii=False, indent=2))
            return 0

        if args.command == "export":
            export_size = tuple(args.resolution) if args.resolution else args.size
            canvas.save_png(args.output, export_size)
            return 0

        changed = False
        if isinstance(canvas, LayeredPixelCanvas):
            if args.add_layer:
                canvas.add_layer(args.add_layer)
                changed = True
            if args.select_layer:
                canvas.select_layer(args.select_layer)
                changed = True
            if args.remove_layer:
                canvas.remove_layer()
                changed = True
        elif args.add_layer or args.select_layer or args.remove_layer:
            parser.error("layer operations require a layered project")

        if args.resolution:
            changed = canvas.set_resolution(*args.resolution) or changed

        if args.import_image:
            if isinstance(canvas, LayeredPixelCanvas):
                canvas.active.import_image(args.import_image)
            else:
                canvas.import_image(args.import_image)
            changed = True

        if args.split:
            x, y = (int(value) for value in args.split)
            changed = canvas.split_cell(x, y) or changed

        if args.collapse:
            x, y = (int(value) for value in args.collapse)
            changed = canvas.collapse_cell(x, y) or changed

        if args.discard_detail:
            values = [int(value) for value in args.discard_detail]
            if len(values) == 2:
                x, y = values
                width = height = 1
            elif len(values) == 4:
                x, y, width, height = values
            else:
                parser.error("--discard-detail requires X Y or X Y WIDTH HEIGHT")
            changed = canvas.discard_detail(x, y, width, height) > 0 or changed

        if args.paint:
            x, y, color = args.paint
            changed = canvas.paint(
                int(x),
                int(y),
                parse_color(color),
                detail_policy=args.detail_policy,
            ) or changed

        if args.paint_child:
            x, y, child_x, child_y, color = args.paint_child
            changed = canvas.paint(
                int(x),
                int(y),
                parse_color(color),
                child=(int(child_x), int(child_y)),
                detail_policy=args.detail_policy,
            ) or changed

        if args.fill:
            x, y, color = args.fill
            changed = canvas.fill(
                int(x),
                int(y),
                parse_color(color),
                detail_policy=args.detail_policy,
            ) > 0 or changed

        if args.erase:
            x, y = args.erase
            changed = canvas.paint(
                int(x),
                int(y),
                (0, 0, 0, 0),
                erase=True,
                detail_policy=args.detail_policy,
            ) or changed

        if args.erase_child:
            x, y, child_x, child_y = args.erase_child
            changed = canvas.paint(
                int(x),
                int(y),
                (0, 0, 0, 0),
                erase=True,
                child=(int(child_x), int(child_y)),
                detail_policy=args.detail_policy,
            ) or changed

        if args.upscale:
            changed = canvas.upscale() or changed

        if not changed:
            parser.error("edit requires an operation that changes the project")
        save_project(canvas, args.output or args.project)
        return 0
    except (ValueError, KeyError, IndexError, OSError, UnicodeError, argparse.ArgumentTypeError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    raise SystemExit(main())
