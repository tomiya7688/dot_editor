from __future__ import annotations

import argparse
import json
import os
from collections.abc import Sequence
from pathlib import Path

from pixel_commands import Canvas, PixelCommandAPI, load_project, save_project


def parse_color(value: str) -> tuple[int, int, int, int]:
    clean = value.strip().lstrip("#")
    if len(clean) != 6:
        raise argparse.ArgumentTypeError("color must be #RRGGBB")
    try:
        return tuple(int(clean[index:index + 2], 16) for index in (0, 2, 4)) + (255,)
    except ValueError as error:
        raise argparse.ArgumentTypeError("color must be #RRGGBB") from error


def inspect_project(canvas: Canvas) -> dict:
    return PixelCommandAPI(canvas).inspect()


def inspect_command(canvas: Canvas, args: argparse.Namespace) -> dict:
    if args.child is not None and args.sample is None:
        raise ValueError("--child requires --sample X Y")
    if args.layer is not None and args.sample is None:
        raise ValueError("--layer requires --sample X Y")
    api = PixelCommandAPI(canvas)
    if args.sample is None:
        return api.inspect()
    return api.inspect_sample(
        args.sample[0], args.sample[1],
        child=args.child,
        layer=args.layer,
    )


def edit_project(canvas: Canvas, args: argparse.Namespace) -> bool:
    """Translate CLI arguments into the shared command API's fixed order."""
    operations = (
        args.resolution, args.import_image, args.split, args.split_region,
        args.paint, args.paint_child, args.fill, args.erase, args.erase_child,
        args.collapse, args.discard_detail, args.add_layer, args.select_layer,
        args.move_layer,
    )
    if not (
        any(value is not None for value in operations)
        or args.upscale
        or args.remove_layer
    ):
        raise ValueError("edit requires an operation")

    api = PixelCommandAPI(canvas)
    changed = False

    if args.add_layer is not None:
        changed = api.add_layer(args.add_layer) or changed
    if args.select_layer is not None:
        changed = api.select_layer(args.select_layer) or changed
    if args.move_layer is not None:
        changed = api.move_layer(args.move_layer) or changed
    if args.remove_layer:
        changed = api.remove_layer() or changed

    if args.resolution is not None:
        changed = api.set_resolution(
            *args.resolution, detail_policy=args.detail_policy
        ) or changed
    if args.import_image is not None:
        changed = api.import_image(args.import_image) or changed
    if args.split is not None:
        changed = api.split(*args.split) or changed
    if args.split_region is not None:
        changed = api.split_region(*args.split_region) > 0 or changed
    if args.paint is not None:
        x, y, color = args.paint
        changed = api.paint(
            x, y, parse_color(color), detail_policy=args.detail_policy
        ) or changed
    if args.paint_child is not None:
        x, y, child_x, child_y, color = args.paint_child
        changed = api.paint(
            x, y, parse_color(color),
            child=(child_x, child_y),
            detail_policy=args.detail_policy,
        ) or changed
    if args.fill is not None:
        x, y, color = args.fill
        changed = api.fill(
            x, y, parse_color(color), detail_policy=args.detail_policy
        ) > 0 or changed
    if args.erase is not None:
        changed = api.erase(
            *args.erase, detail_policy=args.detail_policy
        ) or changed
    if args.erase_child is not None:
        x, y, child_x, child_y = args.erase_child
        changed = api.erase(
            x, y, child=(child_x, child_y),
            detail_policy=args.detail_policy,
        ) or changed
    if args.collapse is not None:
        changed = api.collapse(
            *args.collapse, detail_policy=args.detail_policy
        ) or changed
    if args.discard_detail is not None:
        values = args.discard_detail
        if len(values) not in (2, 4):
            raise ValueError("region requires X Y or X Y WIDTH HEIGHT")
        if len(values) == 2:
            values = [*values, 1, 1]
        changed = api.discard_detail(*values) > 0 or changed
    if args.upscale:
        changed = api.upscale(detail_policy=args.detail_policy) or changed
    return changed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="PixelCanvas command line editor")
    subparsers = parser.add_subparsers(dest="command", required=True)

    new_parser = subparsers.add_parser("new")
    new_shape = new_parser.add_mutually_exclusive_group()
    new_shape.add_argument(
        "--size", type=int, help="square logical resolution (default: 16)"
    )
    new_shape.add_argument(
        "--resolution", nargs=2, type=int, metavar=("WIDTH", "HEIGHT")
    )
    new_parser.add_argument("--layered", action="store_true")
    new_parser.add_argument("--output", type=Path, required=True)

    edit_parser = subparsers.add_parser(
        "edit",
        epilog=(
            "Order: layers, resolution, import, split, paint, paint-child, "
            "fill, erase, erase-child, collapse, discard-detail, upscale. "
            "Use separate invocations for another order."
        ),
    )
    edit_parser.add_argument("--project", type=Path, required=True)
    edit_parser.add_argument("--output", type=Path)
    edit_shape = edit_parser.add_mutually_exclusive_group()
    edit_shape.add_argument(
        "--resolution", nargs=2, type=int, metavar=("WIDTH", "HEIGHT")
    )
    edit_shape.add_argument("--upscale", action="store_true")
    edit_parser.add_argument("--split", nargs=2, type=int, metavar=("X", "Y"))
    edit_parser.add_argument(
        "--split-region", nargs=4, type=int,
        metavar=("X", "Y", "WIDTH", "HEIGHT"),
    )
    edit_parser.add_argument("--paint", nargs=3, metavar=("X", "Y", "COLOR"))
    edit_parser.add_argument(
        "--paint-child", nargs=5,
        metavar=("X", "Y", "CHILD_X", "CHILD_Y", "COLOR"),
    )
    edit_parser.add_argument("--fill", nargs=3, metavar=("X", "Y", "COLOR"))
    edit_parser.add_argument(
        "--erase", nargs=2, type=int, metavar=("X", "Y")
    )
    edit_parser.add_argument(
        "--erase-child", nargs=4, type=int,
        metavar=("X", "Y", "CHILD_X", "CHILD_Y"),
    )
    edit_parser.add_argument(
        "--collapse", nargs=2, type=int, metavar=("X", "Y"),
        help="collapse a cell; keeps its detail by default",
    )
    edit_parser.add_argument(
        "--discard-detail", nargs="+", type=int, metavar="N",
        help="discard a cell (X Y) or a region (X Y WIDTH HEIGHT)",
    )
    edit_parser.add_argument(
        "--detail-policy", choices=("preserve", "discard"), default="preserve",
        help="detail policy for resolution changes and editing (default: preserve)",
    )
    edit_parser.add_argument("--import-image", type=Path)
    edit_parser.add_argument("--add-layer")
    edit_parser.add_argument("--select-layer")
    edit_parser.add_argument(
        "--move-layer", choices=("up", "down"),
        help="move the active layer one position in compositing order",
    )
    edit_parser.add_argument("--remove-layer", action="store_true")

    inspect_parser = subparsers.add_parser(
        "inspect", help="read-only project state as JSON"
    )
    inspect_parser.add_argument("--project", type=Path, required=True)
    inspect_parser.add_argument(
        "--sample", nargs=2, type=int, metavar=("X", "Y")
    )
    inspect_parser.add_argument(
        "--child", nargs=2, type=int, metavar=("CHILD_X", "CHILD_Y"),
        help="sample retained child detail, even if collapsed",
    )
    inspect_parser.add_argument(
        "--layer", help="sample this layer instead of the saved active layer"
    )

    export_parser = subparsers.add_parser("export")
    export_parser.add_argument("--project", type=Path, required=True)
    export_parser.add_argument("--output", type=Path, required=True)
    export_shape = export_parser.add_mutually_exclusive_group()
    export_shape.add_argument(
        "--size", type=int, help="enlarge the current view to a square PNG"
    )
    export_shape.add_argument(
        "--resolution", nargs=2, type=int, metavar=("WIDTH", "HEIGHT"),
        help="project retained detail directly to this PNG resolution",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "new":
            size = 16 if args.size is None else args.size
            shape = (
                tuple(args.resolution)
                if args.resolution is not None
                else (size, size)
            )
            api = PixelCommandAPI.new(*shape, layered=args.layered)
            api.save(args.output)
            return 0

        api = PixelCommandAPI.load(args.project)
        if args.command == "export":
            shape = (
                tuple(args.resolution)
                if args.resolution is not None
                else None
            )
            api.export_png(
                args.output, args.size, output_resolution=shape
            )
        elif args.command == "inspect":
            print(
                json.dumps(
                    inspect_command(api.canvas, args),
                    ensure_ascii=True,
                    sort_keys=True,
                )
            )
        else:
            changed = edit_project(api.canvas, args)
            if changed or args.output is not None:
                save_project(api.canvas, args.output or args.project)
        return 0
    except (
        ValueError, KeyError, IndexError, OSError, UnicodeError,
        argparse.ArgumentTypeError,
    ) as error:
        parser.error(str(error))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
