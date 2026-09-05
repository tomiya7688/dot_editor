from __future__ import annotations

import argparse
import json
from pathlib import Path

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
    source = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(source, dict) and "layers" in source:
        return LayeredPixelCanvas.from_source(source)
    return PixelCanvas.from_source(source)


def save_project(canvas: Canvas, path: Path) -> None:
    path.write_text(json.dumps(canvas.to_source(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="PixelCanvas command line editor")
    subparsers = parser.add_subparsers(dest="command", required=True)

    new_parser = subparsers.add_parser("new")
    new_parser.add_argument("--size", type=int, default=16, choices=PixelCanvas.SUPPORTED_SIZES)
    new_parser.add_argument("--layered", action="store_true")
    new_parser.add_argument("--output", type=Path, required=True)

    edit_parser = subparsers.add_parser("edit")
    edit_parser.add_argument("--project", type=Path, required=True)
    edit_parser.add_argument("--output", type=Path)
    edit_parser.add_argument("--paint", nargs=3, metavar=("X", "Y", "COLOR"))
    edit_parser.add_argument("--fill", nargs=3, metavar=("X", "Y", "COLOR"))
    edit_parser.add_argument("--erase", nargs=2, metavar=("X", "Y"))
    edit_parser.add_argument("--upscale", action="store_true")
    edit_parser.add_argument("--import-image", type=Path)
    edit_parser.add_argument("--add-layer")
    edit_parser.add_argument("--select-layer")
    edit_parser.add_argument("--remove-layer", action="store_true")

    export_parser = subparsers.add_parser("export")
    export_parser.add_argument("--project", type=Path, required=True)
    export_parser.add_argument("--output", type=Path, required=True)
    export_parser.add_argument("--size", type=int)

    args = parser.parse_args()
    if args.command == "new":
        canvas: Canvas = LayeredPixelCanvas(args.size) if args.layered else PixelCanvas(args.size)
        save_project(canvas, args.output)
        return 0

    canvas = load_project(args.project)
    if args.command == "export":
        canvas.save_png(args.output, args.size)
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

    if args.import_image:
        if isinstance(canvas, LayeredPixelCanvas):
            canvas.active.import_image(args.import_image)
        else:
            canvas.import_image(args.import_image)
        changed = True
    if args.paint:
        x, y, color = args.paint
        changed = canvas.paint(int(x), int(y), parse_color(color)) or changed
    if args.fill:
        x, y, color = args.fill
        changed = canvas.fill(int(x), int(y), parse_color(color)) > 0 or changed
    if args.erase:
        x, y = args.erase
        changed = canvas.paint(int(x), int(y), (0, 0, 0, 0), erase=True) or changed
    if args.upscale:
        changed = canvas.upscale() or changed
    if not changed:
        parser.error("edit requires an operation")
    save_project(canvas, args.output or args.project)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
