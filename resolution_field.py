"""Resolution-independent RGBA field made of clipped, immutable raster patches.

All positions are exact rational coordinates in [0, 1]. Changing the output
resolution never resamples the stored patches. A write builds a new partition;
old patch tuples remain usable by undo history.
"""
from __future__ import annotations

from bisect import bisect_left
from fractions import Fraction
from math import ceil, floor, lcm
from typing import Any

from PIL import Image

Box = tuple[Fraction, Fraction, Fraction, Fraction]
Offset = tuple[int, int, int, int]
Tile = tuple[Box, Box, Image.Image, Offset]
FULL: Box = (Fraction(0), Fraction(0), Fraction(1), Fraction(1))
ZERO: Offset = (0, 0, 0, 0)
MAX_DIMENSION = 4096
MAX_PIXELS = 4_194_304
MAX_TILES = 4096
MAX_STORED_PIXELS = 16_777_216


def resolution(width: int, height: int | None = None) -> tuple[int, int]:
    height = width if height is None else height
    if type(width) is not int or type(height) is not int:
        raise ValueError("resolution must contain positive integers")
    if not (1 <= width <= MAX_DIMENSION and 1 <= height <= MAX_DIMENSION):
        raise ValueError(f"resolution dimensions must be 1..{MAX_DIMENSION}")
    if width * height > MAX_PIXELS:
        raise ValueError(f"resolution must contain at most {MAX_PIXELS} pixels")
    return width, height


def cell_box(x: int, y: int, width: int, height: int) -> Box:
    return (Fraction(x, width), Fraction(y, height),
            Fraction(x + 1, width), Fraction(y + 1, height))


def intersection(a: Box, b: Box) -> Box | None:
    left, top = max(a[0], b[0]), max(a[1], b[1])
    right, bottom = min(a[2], b[2]), min(a[3], b[3])
    return (left, top, right, bottom) if left < right and top < bottom else None


def outside(box: Box, cut: Box) -> list[Box]:
    """Disjoint pieces of box outside cut; cut is an intersection with box."""
    left, top, right, bottom = box
    x0, y0, x1, y1 = cut
    candidates = [(left, top, right, y0), (left, y1, right, bottom),
                  (left, y0, x0, y1), (x1, y0, right, y1)]
    return [b for b in candidates if b[0] < b[2] and b[1] < b[3]]


def encoded_color(value: tuple[int, int, int, int]) -> str | None:
    r, g, b, a = value
    if value == (0, 0, 0, 0):
        return None
    return f"#{r:02X}{g:02X}{b:02X}" + (f"{a:02X}" if a != 255 else "")


def decoded_color(value: object) -> tuple[int, int, int, int]:
    if value is None:
        return (0, 0, 0, 0)
    if (not isinstance(value, str) or len(value) not in (7, 9)
            or value[0] != "#" or any(c not in "0123456789abcdefABCDEF" for c in value[1:])):
        raise ValueError("pixel colors must use #RRGGBB or #RRGGBBAA")
    channels = tuple(int(value[i:i + 2], 16) for i in range(1, len(value), 2))
    return channels + (255,) if len(channels) == 3 else channels


def image_source(image: Image.Image) -> list[list[str | None]]:
    return [[encoded_color(image.getpixel((x, y))) for x in range(image.width)]
            for y in range(image.height)]


def source_image(pixels: object, width: int, height: int) -> Image.Image:
    resolution(width, height)
    if (not isinstance(pixels, list) or len(pixels) != height
            or any(not isinstance(row, list) or len(row) != width for row in pixels)):
        raise ValueError("pixel source dimensions do not match resolution")
    image = Image.new("RGBA", (width, height))
    image.putdata([decoded_color(v) for row in pixels for v in row])
    return image


class ResolutionField:
    """Immutable-by-convention partition supporting exact local replacement."""

    def __init__(self, tiles: tuple[Tile, ...] | None = None) -> None:
        self.tiles = tiles if tiles is not None else (
            (FULL, FULL, Image.new("RGBA", (1, 1)), ZERO),
        )

    @classmethod
    def from_image(cls, image: Image.Image) -> ResolutionField:
        resolution(*image.size)
        return cls(((FULL, FULL, image.convert("RGBA").copy(), ZERO),))

    @staticmethod
    def _crop(tile: Tile, clip: Box, offset: Offset | None = None) -> Tile:
        """Crop inaccessible source pixels, without moving any pixel boundary."""
        _, extent, image, old_offset = tile
        dx = (extent[2] - extent[0]) / image.width
        dy = (extent[3] - extent[1]) / image.height
        x0 = max(0, floor((clip[0] - extent[0]) / dx))
        y0 = max(0, floor((clip[1] - extent[1]) / dy))
        x1 = min(image.width, ceil((clip[2] - extent[0]) / dx))
        y1 = min(image.height, ceil((clip[3] - extent[1]) / dy))
        new_extent = (extent[0] + x0 * dx, extent[1] + y0 * dy,
                      extent[0] + x1 * dx, extent[1] + y1 * dy)
        if (x0, y0, x1, y1) == (0, 0, image.width, image.height):
            cropped = image
        else:
            cropped = image.crop((x0, y0, x1, y1))
        return clip, new_extent, cropped, old_offset if offset is None else offset

    @staticmethod
    def _checked(tiles: list[Tile]) -> ResolutionField:
        over_tiles = len(tiles) > MAX_TILES
        over_pixels = sum(tile[2].width * tile[2].height for tile in tiles) > MAX_STORED_PIXELS
        field = ResolutionField(tuple(tiles))
        if not (over_tiles or over_pixels):
            return field
        # Optional lossless compaction of zero-offset patches on a bounded
        # common grid. It is never required for resolution changes. Unaligned
        # grids whose common raster is too large remain clipped patches.
        if not any(tile[3] != ZERO for tile in tiles):
            width = height = 1
            for clip, extent, image, _ in tiles:
                dx = (extent[2] - extent[0]) / image.width
                dy = (extent[3] - extent[1]) / image.height
                width = lcm(width, dx.denominator, *(v.denominator for v in (clip[0], clip[2], extent[0])))
                height = lcm(height, dy.denominator, *(v.denominator for v in (clip[1], clip[3], extent[1])))
                if width > MAX_DIMENSION or height > MAX_DIMENSION or width * height > MAX_PIXELS:
                    break
            else:
                if width * height <= MAX_STORED_PIXELS:
                    return ResolutionField.from_image(field.render(width, height))
        raise ValueError("retained field exceeds the patch/pixel budget; discard unused detail first")

    def replace(self, box: Box, color: tuple[int, int, int, int]) -> ResolutionField:
        """Physically remove old support in box, then install one coarse patch."""
        tiles: list[Tile] = []
        for tile in self.tiles:
            overlap = intersection(tile[0], box)
            if overlap is None:
                tiles.append(tile)
            else:
                tiles.extend(self._crop(tile, piece) for piece in outside(tile[0], overlap))
        tiles.append((box, box, Image.new("RGBA", (1, 1), color), ZERO))
        return self._checked(tiles)

    def shift(self, box: Box, delta: Offset) -> ResolutionField:
        """A reversible color offset keeps original fine samples, even at clipping."""
        if delta == ZERO:
            return self
        tiles: list[Tile] = []
        for tile in self.tiles:
            overlap = intersection(tile[0], box)
            if overlap is None:
                tiles.append(tile)
                continue
            tiles.extend(self._crop(tile, piece) for piece in outside(tile[0], overlap))
            offset = tuple(a + b for a, b in zip(tile[3], delta))
            if any(abs(v) > 1_000_000 for v in offset):
                raise ValueError("retained color offset exceeds the safety limit")
            tiles.append(self._crop(tile, overlap, offset))
        return self._checked(tiles)

    def has_detail(self, box: Box) -> bool:
        overlapping = [tile for tile in self.tiles if intersection(tile[0], box) is not None]
        if len(overlapping) > 1:
            return True
        for _, extent, image, _ in overlapping:
            if ((extent[2] - extent[0]) / image.width < box[2] - box[0]
                    or (extent[3] - extent[1]) / image.height < box[3] - box[1]):
                return True
        return False

    def sample_raw(self, x: Fraction, y: Fraction) -> tuple[int, int, int, int]:
        for clip, extent, image, offset in self.tiles:
            if clip[0] <= x < clip[2] and clip[1] <= y < clip[3]:
                ix = min(image.width - 1, floor((x - extent[0]) * image.width / (extent[2] - extent[0])))
                iy = min(image.height - 1, floor((y - extent[1]) * image.height / (extent[3] - extent[1])))
                return tuple(c + d for c, d in zip(image.getpixel((ix, iy)), offset))
        raise ValueError("retained field has an uncovered coordinate")

    def sample(self, x: Fraction, y: Fraction) -> tuple[int, int, int, int]:
        return tuple(max(0, min(255, v)) for v in self.sample_raw(x, y))

    def render(self, width: int, height: int) -> Image.Image:
        """Sample at exact pixel centers; never change stored source rasters."""
        resolution(width, height)
        out = Image.new("RGBA", (width, height))
        destination = out.load()
        half = Fraction(1, 2)
        for clip, extent, image, offset in self.tiles:
            x0 = max(0, ceil(clip[0] * width - half))
            y0 = max(0, ceil(clip[1] * height - half))
            x1 = min(width, ceil(clip[2] * width - half))
            y1 = min(height, ceil(clip[3] * height - half))
            if x0 >= x1 or y0 >= y1:
                continue
            xs = [min(image.width - 1, floor(((Fraction(2 * x + 1, 2 * width) - extent[0])
                    * image.width) / (extent[2] - extent[0]))) for x in range(x0, x1)]
            ys = [min(image.height - 1, floor(((Fraction(2 * y + 1, 2 * height) - extent[1])
                    * image.height) / (extent[3] - extent[1]))) for y in range(y0, y1)]
            if offset != ZERO:
                lut = [max(0, min(255, c + d)) for d in offset for c in range(256)]
                source = image.point(lut).load()
            else:
                source = image.load()
            for y, sy in enumerate(ys, y0):
                for x, sx in enumerate(xs, x0):
                    destination[x, y] = source[sx, sy]
        return out

    @property
    def retained_resolution(self) -> tuple[int, int]:
        return (max(ceil(t[2].width / (t[1][2] - t[1][0])) for t in self.tiles),
                max(ceil(t[2].height / (t[1][3] - t[1][1])) for t in self.tiles))

    def to_source(self) -> list[dict[str, Any]]:
        return [{"clip": [[v.numerator, v.denominator] for v in clip],
                 "extent": [[v.numerator, v.denominator] for v in extent],
                 "resolution": list(image.size), "pixels": image_source(image),
                 "offset": list(offset)} for clip, extent, image, offset in self.tiles]

    @staticmethod
    def _source_box(values: object) -> Box:
        if not isinstance(values, list) or len(values) != 4:
            raise ValueError("patch bounds must contain four rational coordinates")
        result = []
        for pair in values:
            if (not isinstance(pair, list) or len(pair) != 2
                    or any(type(v) is not int for v in pair)
                    or not (0 <= pair[0] <= pair[1] <= 16_777_216) or pair[1] == 0):
                raise ValueError("invalid rational patch coordinate")
            result.append(Fraction(*pair))
        if not (result[0] < result[2] and result[1] < result[3]):
            raise ValueError("patch bounds must have positive area")
        return tuple(result)

    @classmethod
    def from_source(cls, entries: object) -> ResolutionField:
        if not isinstance(entries, list) or not (1 <= len(entries) <= MAX_TILES):
            raise ValueError("invalid retained patch list")
        tiles = []
        stored_pixels = 0
        for entry in entries:
            if not isinstance(entry, dict):
                raise ValueError("invalid retained patch")
            clip = cls._source_box(entry.get("clip"))
            extent = cls._source_box(entry.get("extent"))
            if intersection(clip, extent) != clip:
                raise ValueError("patch clip must be inside its source extent")
            shape = entry.get("resolution")
            if not isinstance(shape, list) or len(shape) != 2:
                raise ValueError("invalid patch resolution")
            width, height = resolution(*shape)
            stored_pixels += width * height
            if stored_pixels > MAX_STORED_PIXELS:
                raise ValueError("retained field exceeds the stored-pixel budget")
            offset = entry.get("offset")
            if (not isinstance(offset, list) or len(offset) != 4
                    or any(type(v) is not int or abs(v) > 1_000_000 for v in offset)):
                raise ValueError("invalid retained color offset")
            tiles.append((clip, extent, source_image(entry.get("pixels"), width, height), tuple(offset)))
        # Disjoint clips with total area one partition the entire unit rectangle.
        events = []
        area = Fraction(0)
        for clip, *_ in tiles:
            x0, y0, x1, y1 = clip
            area += (x1 - x0) * (y1 - y0)
            events.extend(((x0, 1, y0, y1), (x1, 0, y0, y1)))
        if area != 1:
            raise ValueError("retained patches must cover the canvas exactly")
        active: list[tuple[Fraction, Fraction]] = []
        for _, kind, y0, y1 in sorted(events):
            interval = (y0, y1)
            index = bisect_left(active, interval)
            if kind == 0:
                if index >= len(active) or active[index] != interval:
                    raise ValueError("invalid retained patch partition")
                active.pop(index)
            else:
                if ((index and active[index - 1][1] > y0)
                        or (index < len(active) and active[index][0] < y1)):
                    raise ValueError("retained patches must not overlap")
                active.insert(index, interval)
        return cls(tuple(tiles))
