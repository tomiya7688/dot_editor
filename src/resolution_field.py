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


# {
#   責務: [resolution: 解像度を横幅・縦幅の組へ正規化して安全上限を検証する]
#   処理: [省略した縦幅を補い、整数型・各辺の範囲・総画素数を確認する]
#   引数: [width: 横方向の画素数, height: 縦方向の画素数。省略時は横幅と同じ]
#   戻り値: [検証済みの横幅と縦幅。不正値はValueErrorになる]
# }
def resolution(width: int, height: int | None = None) -> tuple[int, int]:
    # 正方形を扱う旧APIと長方形指定を共通の寸法検証へ揃える。
    height = width if height is None else height
    if type(width) is not int or type(height) is not int:
        raise ValueError("resolution must contain positive integers")
    if not (1 <= width <= MAX_DIMENSION and 1 <= height <= MAX_DIMENSION):
        raise ValueError(f"resolution dimensions must be 1..{MAX_DIMENSION}")
    if width * height > MAX_PIXELS:
        raise ValueError(f"resolution must contain at most {MAX_PIXELS} pixels")
    return width, height


# {
#   責務: [cell_box: 論理画素の座標を単位矩形内の正確な空間領域へ変換する]
#   処理: [画素の左右端と上下端を解像度で割り、有理数の境界を求める]
#   引数: [x: 横座標, y: 縦座標, width: 格子の横幅, height: 格子の縦幅]
#   戻り値: [左・上・右・下の境界。座標と寸法は呼び出し元で検証する]
# }
def cell_box(x: int, y: int, width: int, height: int) -> Box:
    return (Fraction(x, width), Fraction(y, height),
            Fraction(x + 1, width), Fraction(y + 1, height))


# {
#   責務: [intersection: 2つの空間領域が重なる正の面積を持つ矩形を求める]
#   処理: [左右・上下の共通範囲を計算し、幅と高さが正かを確認する]
#   引数: [a: 1つ目の領域, b: 2つ目の領域]
#   戻り値: [交差矩形。重なりがない場合や境界に接するだけの場合はNone]
# }
def intersection(a: Box, b: Box) -> Box | None:
    left, top = max(a[0], b[0]), max(a[1], b[1])
    right, bottom = min(a[2], b[2]), min(a[3], b[3])
    return (left, top, right, bottom) if left < right and top < bottom else None


# {
#   責務: [outside: 領域から内側の切除矩形を除いた部分を重ならない矩形へ分ける]
#   処理: [上下の帯と中央の左右の帯を作り、面積がない候補を除く]
#   引数: [box: 元の領域, cut: box内に含まれる切除領域。呼び出し元で交差を確認する]
#   戻り値: [切除後に残る最大4つの矩形]
# }
def outside(box: Box, cut: Box) -> list[Box]:
    """Disjoint pieces of box outside cut; cut is an intersection with box."""
    left, top, right, bottom = box
    x0, y0, x1, y1 = cut
    # 上下の帯を全幅に取り、左右の帯を中央だけに限定して重複を防ぐ。
    candidates = [(left, top, right, y0), (left, y1, right, bottom),
                  (left, y0, x0, y1), (x1, y0, right, y1)]
    return [b for b in candidates if b[0] < b[2] and b[1] < b[3]]


# {
#   責務: [encoded_color: RGBA色をプロジェクト保存用の色表現へ変換する]
#   処理: [全成分0だけをNoneにし、その他はRGBまたはRGBAの16進表記にする]
#   引数: [value: 検証済みのRGBA色]
#   戻り値: [None、#RRGGBB、または#RRGGBBAA形式の文字列]
# }
def encoded_color(value: tuple[int, int, int, int]) -> str | None:
    r, g, b, a = value
    if value == (0, 0, 0, 0):
        return None
    return f"#{r:02X}{g:02X}{b:02X}" + (f"{a:02X}" if a != 255 else "")


# {
#   責務: [decoded_color: 保存用の色表現を検証してRGBA色へ戻す]
#   処理: [Noneを透明色へ変換し、16進色の書式を検証して省略されたアルファを補う]
#   引数: [value: Noneまたは保存用の色文字列]
#   戻り値: [RGBA色。不正な書式はValueErrorになる]
# }
def decoded_color(value: object) -> tuple[int, int, int, int]:
    if value is None:
        return (0, 0, 0, 0)
    if (not isinstance(value, str) or len(value) not in (7, 9)
            or value[0] != "#" or any(c not in "0123456789abcdefABCDEF" for c in value[1:])):
        raise ValueError("pixel colors must use #RRGGBB or #RRGGBBAA")
    channels = tuple(int(value[i:i + 2], 16) for i in range(1, len(value), 2))
    return channels + (255,) if len(channels) == 3 else channels


# {
#   責務: [image_source: RGBA画像を行単位の保存用色配列へ変換する]
#   処理: [上から順に各画素を読み、encoded_colorで色表現へ変換する]
#   引数: [image: 変換するRGBA画像]
#   戻り値: [行・列の順に並んだ色文字列またはNoneの2次元配列]
# }
def image_source(image: Image.Image) -> list[list[str | None]]:
    return [[encoded_color(image.getpixel((x, y))) for x in range(image.width)]
            for y in range(image.height)]


# {
#   責務: [source_image: 保存用の色配列を検証してRGBA画像へ復元する]
#   処理: [寸法と配列形状を検証し、各色を復号して新しい画像へ格納する]
#   引数: [pixels: 行単位の保存用色配列, width: 横幅, height: 縦幅]
#   戻り値: [復元したRGBA画像。不正な寸法・配列・色はValueErrorになる]
# }
def source_image(pixels: object, width: int, height: int) -> Image.Image:
    # 配列形状と解像度を確認してから画像領域を確保する。
    resolution(width, height)
    if (not isinstance(pixels, list) or len(pixels) != height
            or any(not isinstance(row, list) or len(row) != width for row in pixels)):
        raise ValueError("pixel source dimensions do not match resolution")
    image = Image.new("RGBA", (width, height))
    image.putdata([decoded_color(v) for row in pixels for v in row])
    return image


# {
#   責務: [ResolutionField: 元画素の境界を保持しながら局所編集と任意解像度の描画を提供する]
#   フィールド: [tiles: 単位矩形を分割するパッチ列。表示領域・元画像領域・画像・色差分を保持する]
# }
class ResolutionField:
    """Immutable-by-convention partition supporting exact local replacement."""

    # {
    #   責務: [__init__: 構成済みパッチ列または全面透明なフィールドを保持する]
    #   処理: [指定のパッチ列を採用し、省略時は単位矩形全体を覆う透明パッチを作る]
    #   引数: [tiles: 呼び出し元で構成したパッチ列。省略時は全面透明]
    #   戻り値: [なし。指定の空間フィールドになる]
    # }
    def __init__(self, tiles: tuple[Tile, ...] | None = None) -> None:
        self.tiles = tiles if tiles is not None else (
            (FULL, FULL, Image.new("RGBA", (1, 1)), ZERO),
        )

    # {
    #   責務: [from_image: 画像全体を単一パッチとして保持するフィールドを作る]
    #   処理: [画像寸法を検証し、RGBA変換後の独立したコピーを全面パッチへ格納する]
    #   引数: [cls: ResolutionField型, image: 取り込む画像]
    #   戻り値: [画像と同じ内容を保持する新しいResolutionField]
    # }
    @classmethod
    def from_image(cls, image: Image.Image) -> ResolutionField:
        resolution(*image.size)
        return cls(((FULL, FULL, image.convert("RGBA").copy(), ZERO),))

    # {
    #   責務: [_crop: 元画素の境界を動かさずパッチの保持画像範囲を切り詰める]
    #   処理: [必要な元画像範囲を整数座標で求め、画像と空間領域を対応させて切り出す]
    #   引数: [tile: 元パッチ, clip: 残す表示領域, offset: 任意の新しい色差分。省略時は維持]
    #   戻り値: [指定の表示領域と対応する元画像を持つパッチ]
    # }
    @staticmethod
    def _crop(tile: Tile, clip: Box, offset: Offset | None = None) -> Tile:
        """Crop inaccessible source pixels, without moving any pixel boundary."""
        _, extent, image, old_offset = tile
        # 元画素の間隔を基準に切り出し範囲を外側へ丸め、境界の位置を保持する。
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

    # {
    #   責務: [_checked: パッチ数と保存画素数の予算内でフィールドを構成する]
    #   処理: [
    #     1: パッチ数と保存画素数の上限を確認する,
    #     2: 超過時は色差分なしのパッチを上限内の共通格子へ統合できるか調べる,
    #     3: 無損失統合できなければValueErrorにする
    #   ]
    #   引数: [tiles: 構成候補のパッチ一覧]
    #   戻り値: [予算内の新しいResolutionField]
    # }
    @staticmethod
    def _checked(tiles: list[Tile]) -> ResolutionField:
        # 編集結果の保存量を制限し、履歴へ過大なフィールドを渡さない。
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

    # {
    #   責務: [replace: 指定領域の保持細部を単色パッチへ置き換える]
    #   処理: [各パッチの対象外部分を残し、対象領域を単色で埋めて保存予算を検証する]
    #   引数: [box: 置換する空間領域, color: 検証済みRGBA色]
    #   戻り値: [置換後の新しいResolutionField。元フィールドは変更しない]
    # }
    def replace(self, box: Box, color: tuple[int, int, int, int]) -> ResolutionField:
        """Physically remove old support in box, then install one coarse patch."""
        # 元パッチを変更せず候補を組み立て、Undoで参照する旧状態を保つ。
        tiles: list[Tile] = []
        for tile in self.tiles:
            overlap = intersection(tile[0], box)
            if overlap is None:
                tiles.append(tile)
            else:
                tiles.extend(self._crop(tile, piece) for piece in outside(tile[0], overlap))
        tiles.append((box, box, Image.new("RGBA", (1, 1), color), ZERO))
        return self._checked(tiles)

    # {
    #   責務: [shift: 元の細部を維持して指定領域のRGBA色差分を加える]
    #   処理: [対象領域と外側を分離し、色差分を未飽和のまま加算して安全上限と予算を確認する]
    #   引数: [box: 色差分を加える空間領域, delta: RGBA各成分の加算値]
    #   戻り値: [編集後のフィールド。色差分が全て0なら現在のフィールド]
    # }
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
            # 飽和前の値は可逆な色編集に必要だが、累積量には安全上限を設ける。
            if any(abs(v) > 1_000_000 for v in offset):
                raise ValueError("retained color offset exceeds the safety limit")
            tiles.append(self._crop(tile, overlap, offset))
        return self._checked(tiles)

    # {
    #   責務: [has_detail: 指定領域に幾何学的な細部が保持されているか調べる]
    #   処理: [重なるパッチが複数あるか、元画素の間隔が対象領域より細かいかを確認する]
    #   引数: [box: 調べる空間領域]
    #   戻り値: [パッチ境界または細かい元画素があればTrue。重なりがなければFalse]
    # }
    def has_detail(self, box: Box) -> bool:
        # 色の一致ではなく、パッチ境界と元画素の細かさを保持情報として判定する。
        overlapping = [tile for tile in self.tiles if intersection(tile[0], box) is not None]
        if len(overlapping) > 1:
            return True
        for _, extent, image, _ in overlapping:
            if ((extent[2] - extent[0]) / image.width < box[2] - box[0]
                    or (extent[3] - extent[1]) / image.height < box[3] - box[1]):
                return True
        return False

    # {
    #   責務: [sample_raw: 空間座標に対応する未飽和のRGBA値を取得する]
    #   処理: [座標を覆うパッチの元画素を求め、保存中の色差分を加算する]
    #   引数: [x: 横方向の有理数座標, y: 縦方向の有理数座標]
    #   戻り値: [0から255の範囲外も含むRGBA値。未被覆座標はValueErrorになる]
    # }
    def sample_raw(self, x: Fraction, y: Fraction) -> tuple[int, int, int, int]:
        # 左上を含み右下を含まない領域で、境界上の参照先パッチを一意にする。
        for clip, extent, image, offset in self.tiles:
            if clip[0] <= x < clip[2] and clip[1] <= y < clip[3]:
                ix = min(image.width - 1, floor((x - extent[0]) * image.width / (extent[2] - extent[0])))
                iy = min(image.height - 1, floor((y - extent[1]) * image.height / (extent[3] - extent[1])))
                return tuple(c + d for c, d in zip(image.getpixel((ix, iy)), offset))
        raise ValueError("retained field has an uncovered coordinate")

    # {
    #   責務: [sample: 空間座標の色を表示可能なRGBA範囲へ収めて取得する]
    #   処理: [未飽和の値を読み、各成分を0から255へ制限する]
    #   引数: [x: 横方向の有理数座標, y: 縦方向の有理数座標]
    #   戻り値: [表示用のRGBA色]
    # }
    def sample(self, x: Fraction, y: Fraction) -> tuple[int, int, int, int]:
        return tuple(max(0, min(255, v)) for v in self.sample_raw(x, y))

    # {
    #   責務: [render: 保持中の元画像を変更せず指定解像度のRGBA画像を描画する]
    #   処理: [
    #     1: 出力寸法を検証し、各パッチに属する出力画素の範囲を求める,
    #     2: 正確な画素中心から参照する元画素を求め、色差分を表示範囲へ制限する,
    #     3: 各パッチの画素を出力画像へ転記する
    #   ]
    #   引数: [width: 出力横幅, height: 出力縦幅]
    #   戻り値: [指定寸法の新しいRGBA画像]
    # }
    def render(self, width: int, height: int) -> Image.Image:
        """Sample at exact pixel centers; never change stored source rasters."""
        resolution(width, height)
        out = Image.new("RGBA", (width, height))
        destination = out.load()
        # 半画素を正確な分数で扱い、表示倍率を変えても参照境界がずれないようにする。
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

    # {
    #   責務: [retained_resolution: 保持する元画素の密度を全体相当の解像度で要約する]
    #   処理: [各パッチの画素数を元画像の空間幅で割り、各軸の切り上げ最大値を求める]
    #   引数: []
    #   戻り値: [保持画素密度に相当する横幅と縦幅]
    # }
    @property
    def retained_resolution(self) -> tuple[int, int]:
        return (max(ceil(t[2].width / (t[1][2] - t[1][0])) for t in self.tiles),
                max(ceil(t[2].height / (t[1][3] - t[1][1])) for t in self.tiles))

    # {
    #   責務: [to_source: 空間フィールドを保存用のパッチ配列へ変換する]
    #   処理: [各パッチの表示領域・元画像領域・解像度・画素・色差分を辞書へ格納する]
    #   引数: []
    #   戻り値: [有理数座標を分子・分母の組で表したパッチ辞書の一覧]
    # }
    def to_source(self) -> list[dict[str, Any]]:
        return [{"clip": [[v.numerator, v.denominator] for v in clip],
                 "extent": [[v.numerator, v.denominator] for v in extent],
                 "resolution": list(image.size), "pixels": image_source(image),
                 "offset": list(offset)} for clip, extent, image, offset in self.tiles]

    # {
    #   責務: [_source_box: 保存された有理数座標を単位矩形内の正の面積の領域へ復元する]
    #   処理: [4つの分子・分母の組の型と上限を検証し、幅と高さが正か確認する]
    #   引数: [values: 4つの分子・分母の組からなる保存用配列]
    #   戻り値: [復元した有理数の領域。不正値はValueErrorになる]
    # }
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

    # {
    #   責務: [from_source: 保存用パッチ配列を検証して空間フィールドへ復元する]
    #   処理: [
    #     1: パッチ数・各領域・画像寸法・保存画素数・色差分を検証する,
    #     2: 各画像を復元し、パッチ面積の合計が1であることを確認する,
    #     3: 走査線でパッチの重なりを拒否し、単位矩形全体の分割を確認する
    #   ]
    #   引数: [cls: ResolutionField型, entries: 保存用のパッチ辞書配列]
    #   戻り値: [復元したResolutionField。不正形式・予算超過・分割不整合はValueErrorになる]
    # }
    @classmethod
    def from_source(cls, entries: object) -> ResolutionField:
        if not isinstance(entries, list) or not (1 <= len(entries) <= MAX_TILES):
            raise ValueError("invalid retained patch list")
        # 画像確保の前に各パッチの寸法と総保存量を検証し、候補を順に復元する。
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
        # 同じ横座標では終了を先に処理し、辺を共有するだけのパッチは重複としない。
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
