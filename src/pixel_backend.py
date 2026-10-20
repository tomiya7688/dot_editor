from __future__ import annotations

from collections import deque
from fractions import Fraction
from pathlib import Path
from typing import Any, Literal

from PIL import Image

from resolution_field import (
    MAX_DIMENSION, MAX_PIXELS, ResolutionField, Box, cell_box, intersection,
    resolution, encoded_color, decoded_color, image_source, source_image,
)

Color = tuple[int, int, int, int]
ChildCoordinate = tuple[int, int]
DetailPolicy = Literal["preserve", "discard"]
RefinedCells = dict[tuple[int, int], list[list[Color]]]
SplitKey = tuple[int, int, int, int]  # width, height, parent x, parent y
SplitState = tuple[Color, bool]  # retained parent value, expanded at this grid
CanvasState = tuple[tuple[int, int], ResolutionField, dict[SplitKey, SplitState]]


# {
#   責務: [PixelCanvas: 画素・細部・分割状態を保持し、描画と履歴操作を提供する]
#   フィールド: [
#     _resolution: 現在の論理解像度,
#     _field: 解像度をまたいで細部を保持する空間フィールド,
#     _splits: 解像度別の分割親色と展開状態,
#     _history: Undo用の過去状態,
#     _future: Redo用の未来状態,
#     _view_cache: 現在解像度で投影した画像のキャッシュ
#   ]
# }
class PixelCanvas:
    """GUI-independent canvas with an independent, non-destructive spatial field.

    ``size`` remains a width alias for square-canvas clients. New code should
    use ``resolution`` or ``width``/``height``. ``image`` is a read-only projected
    copy; mutate the document through paint/fill/import_image instead.
    """

    SUPPORTED_SIZES = (2, 4, 8, 16, 32, 64, 128, 256)  # presets, not a whitelist
    MAX_DIMENSION = MAX_DIMENSION
    MAX_PIXELS = MAX_PIXELS
    HISTORY_LIMIT = 50
    MAX_SPLITS = 4096

    # {
    #   責務: [__init__: 解像度と空の画素・履歴状態で作品を初期化する]
    #   処理: [解像度を検証し、細部フィールド・分割記録・履歴・表示キャッシュを用意する]
    #   引数: [size: 横幅, height: 縦幅。省略時は横幅と同じ]
    #   戻り値: [なし。初期化済みのPixelCanvasになる]
    # }
    def __init__(self, size: int = 16, height: int | None = None) -> None:
        self._resolution = resolution(size, height)
        self._field = ResolutionField()
        self._splits: dict[SplitKey, SplitState] = {}
        self._history: list[CanvasState] = []
        self._future: list[CanvasState] = []
        self._view_cache: Image.Image | None = None

    # {
    #   責務: [_validate_size: 解像度指定がバックエンドの上限内か検証する]
    #   処理: [共通解像度検証へ横幅を渡し、不正値ならValueErrorにする]
    #   引数: [cls: PixelCanvas型, size: 検証する横幅]
    #   戻り値: [なし。検証失敗時はValueErrorになる]
    # }
    @classmethod
    def _validate_size(cls, size: int) -> None:
        resolution(size)

    # {
    #   責務: [resolution: 横幅と縦幅からなる現在の論理解像度を返す]
    #   処理: [保持中の解像度タプルを返す]
    #   引数: []
    #   戻り値: [横幅と縦幅の組]
    # }
    @property
    def resolution(self) -> tuple[int, int]:
        return self._resolution

    # {
    #   責務: [width: 現在の論理画素の横幅を返す]
    #   処理: [保持中の解像度から横幅を取り出す]
    #   引数: []
    #   戻り値: [横方向の画素数]
    # }
    @property
    def width(self) -> int:
        return self._resolution[0]

    # {
    #   責務: [height: 現在の論理画素の縦幅を返す]
    #   処理: [保持中の解像度から縦幅を取り出す]
    #   引数: []
    #   戻り値: [縦方向の画素数]
    # }
    @property
    def height(self) -> int:
        return self._resolution[1]

    # {
    #   責務: [size: 互換API向けに現在の横幅を返す]
    #   処理: [widthプロパティへ委譲する]
    #   引数: []
    #   戻り値: [現在の横幅]
    # }
    @property
    def size(self) -> int:
        return self.width

    # {
    #   責務: [_key: 座標を現在の解像度付き分割キーへ変換する]
    #   処理: [横幅・縦幅・画素座標を順に組み合わせる]
    #   引数: [x: 横座標, y: 縦座標]
    #   戻り値: [解像度と座標を含む分割キー]
    # }
    def _key(self, x: int, y: int) -> SplitKey:
        return self.width, self.height, x, y

    # {
    #   責務: [_key_box: 分割キーが表す画素領域を取得する]
    #   処理: [キーから解像度と座標を取り出して共通領域計算へ渡す]
    #   引数: [key: 解像度と親座標を含む分割キー]
    #   戻り値: [分割画素の空間領域]
    # }
    @staticmethod
    def _key_box(key: SplitKey) -> Box:
        width, height, x, y = key
        return cell_box(x, y, width, height)

    # {
    #   責務: [_box: 親画素または子画素に対応する空間領域を求める]
    #   処理: [親座標を使い、子座標があれば検証して2倍解像度の領域へ変換する]
    #   引数: [x: 親画素の横座標, y: 親画素の縦座標, child: 任意の0または1の子座標]
    #   戻り値: [対象画素の空間領域]
    # }
    def _box(self, x: int, y: int, child: ChildCoordinate | None = None) -> Box:
        if child is None:
            return cell_box(x, y, self.width, self.height)
        cx, cy = self._validate_child(child)
        return cell_box(2 * x + cx, 2 * y + cy, 2 * self.width, 2 * self.height)

    # {
    #   責務: [_center: 空間領域の中心座標を正確な分数で求める]
    #   処理: [左右端と上下端の中点をそれぞれ計算する]
    #   引数: [box: 中心を求める空間領域]
    #   戻り値: [横・縦の中心座標]
    # }
    @staticmethod
    def _center(box: Box) -> tuple[Fraction, Fraction]:
        return (box[0] + box[2]) / 2, (box[1] + box[3]) / 2

    # {
    #   責務: [_normalize_color: RGBまたはRGBA入力を検証済みRGBA色へ正規化する]
    #   処理: [RGBには不透明度を補い、各成分が整数の0から255か確認する]
    #   引数: [color: 検証・正規化する色成分]
    #   戻り値: [4成分のRGBA色]
    # }
    @staticmethod
    def _normalize_color(color: tuple[int, ...]) -> Color:
        values = tuple(color)
        if len(values) == 3:
            values += (255,)
        if len(values) != 4 or any(type(v) is not int or not 0 <= v <= 255 for v in values):
            raise ValueError("color must contain 3 or 4 integers in the range 0..255")
        return values

    # {
    #   責務: [_validate_detail_policy: 細部の保持・破棄方針を検証する]
    #   処理: [preserveまたはdiscardだけを受け入れ、それ以外をValueErrorにする]
    #   引数: [detail_policy: 適用する細部方針]
    #   戻り値: [検証済みの細部方針]
    # }
    @staticmethod
    def _validate_detail_policy(detail_policy: str) -> DetailPolicy:
        if detail_policy not in ("preserve", "discard"):
            raise ValueError("detail_policy must be 'preserve' or 'discard'")
        return detail_policy

    # {
    #   責務: [_validate_child: 子画素座標が0または1の組か検証する]
    #   処理: [要素数と厳密な整数値を確認し、不正値をIndexErrorにする]
    #   引数: [child: 検証する子画素の横・縦座標]
    #   戻り値: [検証済みの子画素座標]
    # }
    @staticmethod
    def _validate_child(child: ChildCoordinate) -> ChildCoordinate:
        if len(child) != 2 or any(type(v) is not int or v not in (0, 1) for v in child):
            raise IndexError("child coordinate must be 0 or 1")
        return tuple(child)

    # {
    #   責務: [_in_bounds: 座標が整数でキャンバス内にあるか判定する]
    #   処理: [型と横・縦それぞれの下限・上限を確認する]
    #   引数: [x: 判定する横座標, y: 判定する縦座標]
    #   戻り値: [有効な座標ならTrue、それ以外はFalse]
    # }
    def _in_bounds(self, x: int, y: int) -> bool:
        return type(x) is int and type(y) is int and 0 <= x < self.width and 0 <= y < self.height

    # {
    #   責務: [_state: Undo・Redo用に現在状態のスナップショットを作る]
    #   処理: [解像度とフィールドを保持し、分割辞書を複製する]
    #   引数: []
    #   戻り値: [解像度・空間フィールド・分割状態の組]
    # }
    def _state(self) -> CanvasState:
        return self.resolution, self._field, dict(self._splits)

    # {
    #   責務: [_restore_state: 履歴スナップショットから作品状態を復元する]
    #   処理: [解像度・フィールド・分割状態を戻し、表示キャッシュを無効化する]
    #   引数: [state: 復元する作品状態]
    #   戻り値: [なし。作品状態が更新される]
    # }
    def _restore_state(self, state: CanvasState) -> None:
        self._resolution, self._field, splits = state
        self._splits = dict(splits)
        self._view_cache = None

    # {
    #   責務: [_snapshot: Undo用の状態を記録してRedo履歴を破棄する]
    #   処理: [現在状態を追加し、履歴上限を適用して未来状態を消去する]
    #   引数: []
    #   戻り値: [なし。Undo履歴が更新される]
    # }
    def _snapshot(self) -> None:
        self._history.append(self._state())
        del self._history[:-self.HISTORY_LIMIT]
        self._future.clear()

    # {
    #   責務: [_commit: 編集済みフィールドと分割状態を履歴付きで確定する]
    #   処理: [編集前状態を記録してから新状態を設定し、表示キャッシュを消去する]
    #   引数: [field: 確定する空間フィールド, splits: 確定する分割状態]
    #   戻り値: [なし。作品状態が更新される]
    # }
    def _commit(self, field: ResolutionField, splits: dict[SplitKey, SplitState]) -> None:
        self._snapshot()
        self._field = field
        self._splits = splits
        self._view_cache = None

    # {
    #   責務: [_expanded_cells: 現在の解像度で展開済みの親画素座標を集める]
    #   処理: [分割記録を現在の解像度で絞り、展開状態の座標だけを集合化する]
    #   引数: []
    #   戻り値: [展開済み親画素の座標集合]
    # }
    @property
    def _expanded_cells(self) -> set[tuple[int, int]]:
        return {(x, y) for (w, h, x, y), (_, expanded) in self._splits.items()
                if (w, h) == self.resolution and expanded}

    # {
    #   責務: [_refined_cells: 現在の解像度に属する分割画素の子色を構成する]
    #   処理: [各分割画素の4子領域中心を空間フィールドから読み取る]
    #   引数: []
    #   戻り値: [親座標から子色2次元配列への辞書]
    # }
    @property
    def _refined_cells(self) -> RefinedCells:
        return {(x, y): [[self._field.sample(*self._center(self._box(x, y, (cx, cy))))
                          for cx in range(2)] for cy in range(2)]
                for w, h, x, y in self._splits if (w, h) == self.resolution}

    # {
    #   責務: [has_refinements: 現在の解像度に展開済みの細分画素があるか調べる]
    #   処理: [展開済み座標集合が空でないか判定する]
    #   引数: []
    #   戻り値: [展開済みセルがあればTrue]
    # }
    @property
    def has_refinements(self) -> bool:
        return bool(self._expanded_cells)

    # {
    #   責務: [has_detail: 作品内に現在解像度より細かい保持情報があるか調べる]
    #   処理: [分割記録・高解像度フィールド・画素境界にまたがる細部を確認する]
    #   引数: []
    #   戻り値: [保持中の細部があればTrue]
    # }
    @property
    def has_detail(self) -> bool:
        rw, rh = self._field.retained_resolution
        return bool(self._splits) or rw > self.width or rh > self.height or any(
            (v * (self.width if i % 2 == 0 else self.height)).denominator != 1
            for tile in self._field.tiles for i, v in enumerate(tile.clip)
        )

    # {
    #   責務: [retained_resolution: 空間フィールドが保持する解像度を返す]
    #   処理: [ResolutionFieldの保持解像度をそのまま公開する]
    #   引数: []
    #   戻り値: [保持フィールドの横幅と縦幅]
    # }
    @property
    def retained_resolution(self) -> tuple[int, int]:
        return self._field.retained_resolution

    # {
    #   責務: [retained_patch_count: 空間フィールドが保持する局所パッチ数を返す]
    #   処理: [保持中のタイル一覧の要素数を数える]
    #   引数: []
    #   戻り値: [局所パッチ数]
    # }
    @property
    def retained_patch_count(self) -> int:
        return len(self._field.tiles)

    # {
    #   責務: [detail_cells: 現在の解像度に属する細部セルを一覧化する]
    #   処理: [分割記録を座標順に並べ、座標と展開状態を辞書へ変換する]
    #   引数: []
    #   戻り値: [細部セルの座標・展開状態を持つ辞書のリスト]
    # }
    def detail_cells(self) -> list[dict[str, Any]]:
        return [{"x": x, "y": y, "expanded": expanded}
                for (w, h, x, y), (_, expanded) in sorted(self._splits.items())
                if (w, h) == self.resolution]

    # {
    #   責務: [native_resolution: 分割状態を含む自然な出力解像度を返す]
    #   処理: [展開済み細部があれば縦横を2倍し、なければ論理解像度を使う]
    #   引数: []
    #   戻り値: [自然な出力の横幅と縦幅]
    # }
    @property
    def native_resolution(self) -> tuple[int, int]:
        return (2 * self.width, 2 * self.height) if self.has_refinements else self.resolution

    # {
    #   責務: [native_size: 互換API向けに自然な出力の横幅を返す]
    #   処理: [native_resolutionから横幅を取り出す]
    #   引数: []
    #   戻り値: [自然な出力の横幅]
    # }
    @property
    def native_size(self) -> int:
        return self.native_resolution[0]

    # {
    #   責務: [is_split: 指定画素が現在の解像度で分割済みか判定する]
    #   処理: [解像度付きキーから展開状態を取得する]
    #   引数: [x: 横座標, y: 縦座標]
    #   戻り値: [分割済みならTrue、それ以外はFalse]
    # }
    def is_split(self, x: int, y: int) -> bool:
        return self._splits.get(self._key(x, y), (None, False))[1]

    # {
    #   責務: [has_detail_at: 指定画素に破棄対象となる細部があるか調べる]
    #   処理: [座標を検証し、直接の細部・空間フィールド・重なる親色記録を確認する]
    #   引数: [x: 横座標, y: 縦座標]
    #   戻り値: [細部または影響する分割記録があればTrue]
    # }
    def has_detail_at(self, x: int, y: int) -> bool:
        if not self._in_bounds(x, y):
            return False
        box = self._box(x, y)
        if self._key(x, y) in self._splits or self._field.has_detail(box):
            return True
        # A split at another grid can retain a parent override even when the
        # raster field is uniform. Include metadata that discard would remove
        # or change, otherwise same-color edits can resurrect the old parent.
        for key, (base, _) in self._splits.items():
            split_box = self._key_box(key)
            overlap = intersection(split_box, box)
            if overlap is None:
                continue
            if overlap == split_box:
                return True
            center = self._center(split_box)
            if (box[0] <= center[0] < box[2] and box[1] <= center[1] < box[3]
                    and base != self._field.sample(*center)):
                return True
        return False

    # {
    #   責務: [_projection: 指定解像度へ空間フィールドと分割親色を投影する]
    #   処理: [フィールド画像を描画し、同じ解像度の親色記録を上書きする]
    #   引数: [width: 出力横幅, height: 出力縦幅]
    #   戻り値: [投影したRGBA画像]
    # }
    def _projection(self, width: int, height: int) -> Image.Image:
        output = self._field.render(width, height)
        for (w, h, x, y), (base, _) in self._splits.items():
            if (w, h) == (width, height):
                output.putpixel((x, y), base)
        return output

    # {
    #   責務: [image: 現在の作品画像を独立した読み取り用コピーとして返す]
    #   処理: [未生成なら投影をキャッシュし、返却時に画像を複製する]
    #   引数: []
    #   戻り値: [現在の論理解像度のRGBA画像コピー]
    # }
    @property
    def image(self) -> Image.Image:
        if self._view_cache is None:
            self._view_cache = self._projection(*self.resolution)
        return self._view_cache.copy()

    # {
    #   責務: [split_cell: 指定した論理画素を4つの子画素へ分割する]
    #   処理: [座標・解像度・分割上限を確認し、親色を保存して履歴付きで確定する]
    #   引数: [x: 横座標, y: 縦座標]
    #   戻り値: [分割状態が変化した場合はTrue、それ以外はFalse]
    # }
    def split_cell(self, x: int, y: int) -> bool:
        if not self._in_bounds(x, y) or self.is_split(x, y):
            return False
        resolution(2 * self.width, 2 * self.height)
        key = self._key(x, y)
        if key not in self._splits and len(self._splits) >= self.MAX_SPLITS:
            raise ValueError("too many retained split cells")
        splits = dict(self._splits)
        base = splits[key][0] if key in splits else self.sample(x, y)
        splits[key] = (base, True)
        self._commit(self._field, splits)
        return True

    # {
    #   責務: [split_region: 矩形領域に含まれる画素をまとめて4分割する]
    #   処理: [引数・境界・全分割予算を検証し、変更があれば一度の履歴操作で確定する]
    #   引数: [x: 左上の横座標, y: 左上の縦座標, width: 領域幅, height: 領域高さ]
    #   戻り値: [新たに分割した画素数]
    # }
    def split_region(self, x: int, y: int, width: int, height: int) -> int:
        # 型・範囲・子セル描画の予算を、画像や履歴の更新前に検証する。
        if any(type(value) is not int for value in (x, y, width, height)):
            raise ValueError("split region coordinates and dimensions must be integers")
        if width <= 0 or height <= 0:
            raise ValueError("split region dimensions must be positive")
        if x < 0 or y < 0 or x + width > self.width or y + height > self.height:
            raise ValueError("split region must fit entirely inside the canvas")
        resolution(2 * self.width, 2 * self.height)

        # 候補だけを編集し、予算超過や色の参照失敗で部分更新を残さない。
        splits = None
        changed = 0
        for row in range(y, y + height):
            for column in range(x, x + width):
                if self.is_split(column, row):
                    continue
                if splits is None:
                    # 全セルが展開済みなら、辞書の複製も履歴の追加も行わない。
                    splits = dict(self._splits)
                key = self._key(column, row)
                if key not in splits and len(splits) >= self.MAX_SPLITS:
                    raise ValueError("too many retained split cells")
                # 折りたたみ済みの親色は再利用し、既存の子画素を保持する。
                base = splits[key][0] if key in splits else self.sample(column, row)
                splits[key] = (base, True)
                changed += 1
        if splits is None:
            return 0
        # 領域全体を1回のUndoで戻せるよう、成功した候補を一度だけ確定する。
        self._commit(self._field, splits)
        return changed

    # {
    #   責務: [collapse_cell: 指定画素の分割表示を折りたたむ]
    #   処理: [必要なら細部を破棄し、通常は分割親色を保ったまま展開状態を解除する]
    #   引数: [x: 横座標, y: 縦座標, discard_detail: 細部も破棄するか]
    #   戻り値: [状態が変化した場合はTrue、それ以外はFalse]
    # }
    def collapse_cell(self, x: int, y: int, discard_detail: bool = False) -> bool:
        if not self._in_bounds(x, y):
            return False
        if discard_detail:
            return self.discard_detail(x, y) > 0
        key = self._key(x, y)
        if not self.is_split(x, y):
            return False
        splits = dict(self._splits)
        splits[key] = (splits[key][0], False)
        self._commit(self._field, splits)
        return True

    # {
    #   責務: [new: 空の作品を指定または現在の解像度で作り直す]
    #   処理: [変更前を履歴へ記録し、空の空間フィールドと分割記録へ置き換える]
    #   引数: [size: 任意の横幅, height: 任意の縦幅]
    #   戻り値: [なし。空の作品に置き換わる]
    # }
    def new(self, size: int | None = None, height: int | None = None) -> None:
        target = self.resolution if size is None else resolution(size, height)
        self._snapshot()
        self._resolution = target
        self._field = ResolutionField()
        self._splits.clear()
        self._view_cache = None

    # {
    #   責務: [_edited: 細部方針に従って画素領域と分割親色を編集する]
    #   処理: [
    #     1: 対象領域で保持・破棄の適用範囲を決める,
    #     2: preserveでは色差分を保持し、関連する親色へ反映する,
    #     3: discardでは重なる分割記録を除去または置換する
    #   ]
    #   引数: [field: 編集元フィールド, splits: 編集元分割状態, x: 横座標, y: 縦座標, replacement: 置換色, child: 任意の子座標, policy: 細部方針]
    #   戻り値: [編集後の空間フィールドと分割状態]
    # }
    def _edited(
        self, field: ResolutionField, splits: dict[SplitKey, SplitState],
        x: int, y: int, replacement: Color, child: ChildCoordinate | None,
        policy: DetailPolicy,
    ) -> tuple[ResolutionField, dict[SplitKey, SplitState]]:
        box = self._box(x, y, child)
        key = self._key(x, y)
        # Preserve the legacy explicit-parent/child override contract. Children
        # remain independently editable; a parent-only write changes its base.
        if child is None and key in splits and policy == "preserve":
            splits[key] = (replacement, splits[key][1])
            return field, splits
        if policy == "preserve" and field.has_detail(box):
            reference = field.sample_raw(*self._center(box))
            delta = tuple(new - old for new, old in zip(replacement, reference))
            field = field.shift(box, delta)
            # Keep parent values at other stored grids consistent with the tint.
            for split_key, (base, expanded) in list(splits.items()):
                # A child write must not alter its independently saved parent.
                # The parent's center lies on the bottom-right child's edge.
                if child is not None and split_key == key:
                    continue
                center = self._center(self._key_box(split_key))
                if box[0] <= center[0] < box[2] and box[1] <= center[1] < box[3]:
                    splits[split_key] = (tuple(max(0, min(255, v + d)) for v, d in zip(base, delta)), expanded)
        else:
            field = field.replace(box, replacement)
            if policy == "discard":
                for split_key in list(splits):
                    if child is not None and split_key == key:
                        continue
                    split_box = self._key_box(split_key)
                    overlap = intersection(split_box, box)
                    if overlap == split_box:
                        del splits[split_key]
                    elif overlap is not None:
                        # Partially intersecting metadata must not expose an old
                        # base at a discarded sample position. Exterior child
                        # samples remain in the exact clipped spatial field.
                        center = self._center(split_box)
                        if box[0] <= center[0] < box[2] and box[1] <= center[1] < box[3]:
                            splits[split_key] = (replacement, splits[split_key][1])
        return field, splits

    # {
    #   責務: [paint: 指定画素または子画素を描画色で置き換える]
    #   処理: [
    #     1: 方針・色・座標・子画素指定を検証する,
    #     2: 変更不要なら履歴を作らず、必要なら編集結果を一度で確定する
    #   ]
    #   引数: [x: 横座標, y: 縦座標, color: 描画色, erase: 透明色で消すか, child: 任意の子座標, detail_policy: 細部方針]
    #   戻り値: [画素が変化した場合はTrue、それ以外はFalse]
    # }
    def paint(self, x: int, y: int, color: tuple[int, ...], erase: bool = False,
              child: ChildCoordinate | None = None, detail_policy: DetailPolicy = "preserve") -> bool:
        # Validate every option before building a replacement model state.
        policy = self._validate_detail_policy(detail_policy)
        replacement = (0, 0, 0, 0) if erase else self._normalize_color(color)
        if not self._in_bounds(x, y):
            return False
        if child is not None:
            self._validate_child(child)
            if not self.is_split(x, y):
                raise ValueError("child painting requires a split cell")
        current = self.sample(x, y, child)
        has_detail = self.has_detail_at(x, y) if child is None else self._field.has_detail(self._box(x, y, child))
        if current == replacement and not (policy == "discard" and has_detail):
            return False
        field, splits = self._edited(self._field, dict(self._splits), x, y, replacement, child, policy)
        self._commit(field, splits)
        return True

    # {
    #   責務: [sample: 親画素または保持された子画素のRGBA色を取得する]
    #   処理: [座標を検証し、親色記録または空間フィールドの対象中心を読む]
    #   引数: [x: 横座標, y: 縦座標, child: 任意の子画素横・縦座標]
    #   戻り値: [取得したRGBA色]
    # }
    def sample(self, x: int, y: int, child: ChildCoordinate | None = None) -> Color:
        if not self._in_bounds(x, y):
            raise IndexError("pixel coordinate out of range")
        # A retained parent override is authoritative for parent-level reads.
        if child is None and self._key(x, y) in self._splits:
            return self._splits[self._key(x, y)][0]
        if child is not None:
            self._validate_child(child)
            if not self.has_detail_at(x, y):
                raise ValueError("child sampling requires preserved child detail")
        return self._field.sample(*self._center(self._box(x, y, child)))

    # {
    #   責務: [fill: 4近傍で連結する同色領域を指定色へ置き換える]
    #   処理: [
    #     1: 表示画像を基準に領域を幅優先探索する,
    #     2: 方針に応じて細部を保持・破棄し、全体置換は単色フィールドへまとめる,
    #     3: 編集結果全体を一度の履歴操作で確定する
    #   ]
    #   引数: [x: 起点の横座標, y: 起点の縦座標, color: 置換色, erase: 透明色で消すか, detail_policy: 細部方針]
    #   戻り値: [変更した論理画素数]
    # }
    def fill(self, x: int, y: int, color: tuple[int, ...], erase: bool = False,
             detail_policy: DetailPolicy = "preserve") -> int:
        policy = self._validate_detail_policy(detail_policy)
        replacement = (0, 0, 0, 0) if erase else self._normalize_color(color)
        if not self._in_bounds(x, y):
            return 0
        # Determine connectivity from one immutable preview before editing cells.
        view = self.image
        original = view.getpixel((x, y))
        if original == replacement and policy == "preserve":
            return 0
        points = []
        pending = deque([(x, y)])
        visited = {(x, y)}
        # Mark neighbors when queued so each canvas coordinate is visited once.
        while pending:
            px, py = pending.popleft()
            if view.getpixel((px, py)) != original:
                continue
            if original != replacement or self.has_detail_at(px, py):
                points.append((px, py))
            for nx, ny in ((px - 1, py), (px + 1, py), (px, py - 1), (px, py + 1)):
                if self._in_bounds(nx, ny) and (nx, ny) not in visited:
                    visited.add((nx, ny))
                    pending.append((nx, ny))
        if not points:
            return 0
        # A uniform whole-canvas result needs no per-cell refinement patches.
        if len(points) == self.width * self.height and (policy == "discard" or not self.has_detail):
            self._commit(ResolutionField.from_image(Image.new("RGBA", (1, 1), replacement)), {})
            return len(points)
        # Apply all selected cells to local state and publish them in one history step.
        field, splits = self._field, dict(self._splits)
        for px, py in points:
            field, splits = self._edited(field, splits, px, py, replacement, None, policy)
        self._commit(field, splits)
        return len(points)

    # {
    #   責務: [discard_detail: 矩形領域内の保持細部を親色へ置き換えて破棄する]
    #   処理: [寸法と境界を検証し、細部を持つ画素だけを集めて一括確定する]
    #   引数: [x: 左上の横座標, y: 左上の縦座標, width: 領域幅, height: 領域高さ]
    #   戻り値: [細部を破棄した画素数]
    # }
    def discard_detail(self, x: int, y: int, width: int = 1, height: int = 1) -> int:
        if (type(width) is not int or type(height) is not int or width <= 0 or height <= 0):
            raise ValueError("detail discard region must have positive integer width and height")
        if not self._in_bounds(x, y) or x + width > self.width or y + height > self.height:
            raise IndexError("detail discard region must fit inside the canvas")
        # Snapshot target colors before changing any overlapping retained detail.
        targets = [(px, py, self.sample(px, py)) for py in range(y, y + height)
                   for px in range(x, x + width) if self.has_detail_at(px, py)]
        if not targets:
            return 0
        # Prepare every replacement locally, then create only one undo entry.
        field, splits = self._field, dict(self._splits)
        for px, py, color in targets:
            field, splits = self._edited(field, splits, px, py, color, None, "discard")
        self._commit(field, splits)
        return len(targets)

    # {
    #   責務: [import_image: 画像ファイルまたは画像オブジェクトを作品へ読み込む]
    #   処理: [RGBAへ変換し、最近傍縮小で収めて中央配置した結果を履歴付きで確定する]
    #   引数: [source: 読み込む画像オブジェクトまたはファイルパス]
    #   戻り値: [なし。作品画像が置き換わる]
    # }
    def import_image(self, source: str | Path | Image.Image) -> None:
        # Convert both accepted input forms before fitting them to the canvas.
        if isinstance(source, Image.Image):
            loaded = source.convert("RGBA")
        else:
            with Image.open(source) as opened:
                loaded = opened.convert("RGBA")
        # Preserve aspect ratio, avoid enlarging small images, and center the result.
        ratio = min(1.0, self.width / loaded.width, self.height / loaded.height)
        target = max(1, round(loaded.width * ratio)), max(1, round(loaded.height * ratio))
        fitted = Image.new("RGBA", self.resolution)
        resized = loaded.resize(target, Image.Resampling.NEAREST)
        fitted.paste(resized, ((self.width - target[0]) // 2, (self.height - target[1]) // 2))
        self._commit(ResolutionField.from_image(fitted), {})

    # {
    #   責務: [set_resolution: 作品の論理解像度を変更する]
    #   処理: [
    #     1: 解像度と細部方針を検証し、同一解像度の保持操作は終了する,
    #     2: discardなら現在の投影画像を新しい解像度へ焼き込む,
    #     3: 履歴を記録して解像度・フィールド・分割状態を更新する
    #   ]
    #   引数: [width: 新しい横幅, height: 新しい縦幅, detail_policy: 細部の保持・破棄方針]
    #   戻り値: [解像度または細部状態が変化した場合はTrue]
    # }
    def set_resolution(self, width: int, height: int | None = None,
                       detail_policy: DetailPolicy = "preserve") -> bool:
        target = resolution(width, height)
        policy = self._validate_detail_policy(detail_policy)
        if target == self.resolution and policy == "preserve":
            return False
        field = self._field
        if policy == "discard":
            # An explicit global discard bakes only the requested coarse view.
            field = ResolutionField.from_image(self._projection(*target))
        # Record the old field before replacing dimensions or clearing split metadata.
        self._snapshot()
        self._resolution = target
        self._field = field
        if policy == "discard":
            self._splits.clear()
        self._view_cache = None
        return True

    # {
    #   責務: [resize: 旧APIとの互換性を保って解像度を変更する]
    #   処理: [引数をset_resolutionへそのまま委譲する]
    #   引数: [target: 新しい横幅, height: 新しい縦幅, detail_policy: 細部の保持・破棄方針]
    #   戻り値: [解像度が変化した場合はTrue、それ以外はFalse]
    # }
    def resize(self, target: int, height: int | None = None,
               detail_policy: DetailPolicy = "preserve") -> bool:
        """Compatibility alias: resolution changes now preserve detail by default."""
        return self.set_resolution(target, height, detail_policy)

    # {
    #   責務: [upscale: 現在の論理解像度を縦横2倍へ拡大する]
    #   処理: [上限検証に失敗した場合はFalseを返し、適合時はset_resolutionへ委譲する]
    #   引数: []
    #   戻り値: [解像度が変更された場合はTrue、それ以外はFalse]
    # }
    def upscale(self) -> bool:
        try:
            target = resolution(self.width * 2, self.height * 2)
        except ValueError:
            return False
        return self.set_resolution(*target)

    # {
    #   責務: [undo: 直前の作品状態へ戻す]
    #   処理: [現在状態をRedo側へ移してからUndo履歴の状態を復元する]
    #   引数: []
    #   戻り値: [復元した場合はTrue、履歴がなければFalse]
    # }
    def undo(self) -> bool:
        if not self._history:
            return False
        self._future.append(self._state())
        self._restore_state(self._history.pop())
        return True

    # {
    #   責務: [redo: Undoで戻した作品状態を再適用する]
    #   処理: [現在状態をUndo履歴へ追加し、Redo側の状態を復元する]
    #   引数: []
    #   戻り値: [再適用した場合はTrue、履歴がなければFalse]
    # }
    def redo(self) -> bool:
        if not self._future:
            return False
        self._history.append(self._state())
        del self._history[:-self.HISTORY_LIMIT]
        self._restore_state(self._future.pop())
        return True

    # {
    #   責務: [_native_image: 分割表示を反映した自然な出力画像を作る]
    #   処理: [必要なら最近傍拡大し、展開済みセルの子画素色を反映する]
    #   引数: []
    #   戻り値: [自然な出力解像度のRGBA画像]
    # }
    def _native_image(self) -> Image.Image:
        view = self.image
        if not self.has_refinements:
            return view
        # Scale the parent view first, then overlay independently stored children.
        output = view.resize(self.native_resolution, Image.Resampling.NEAREST)
        for x, y in self._expanded_cells:
            for cy in range(2):
                for cx in range(2):
                    output.putpixel((2 * x + cx, 2 * y + cy), self.sample(x, y, (cx, cy)))
        return output

    # {
    #   責務: [render: 現在の作品を必要な表示解像度へ描画する]
    #   処理: [自然な画像を作り、表示寸法が指定された場合だけ最近傍拡大・縮小する]
    #   引数: [display_size: 任意の正方形サイズまたは横幅・縦幅]
    #   戻り値: [描画したRGBA画像]
    # }
    def render(self, display_size: int | tuple[int, int] | None = None) -> Image.Image:
        """Nearest-neighbour display of the current logical view, including splits."""
        output = self._native_image()
        if display_size is None:
            return output
        target = resolution(*display_size) if isinstance(display_size, tuple) else resolution(display_size)
        return output.resize(target, Image.Resampling.NEAREST)

    # {
    #   責務: [render_resolution: 保持中の細部を指定解像度へ直接描画する]
    #   処理: [寸法を検証して空間フィールドの描画へ渡す]
    #   引数: [width: 出力横幅, height: 出力縦幅]
    #   戻り値: [指定解像度のRGBA画像]
    # }
    def render_resolution(self, width: int, height: int | None = None) -> Image.Image:
        """Project retained detail directly at an explicit output resolution."""
        return self._field.render(*resolution(width, height))

    # {
    #   責務: [save_png: 現在の作品をPNGファイルへ保存する]
    #   処理: [
    #     1: 出力寸法の指定方法が重複していないか確認する,
    #     2: 指定解像度または自然な画像を選び必要なら最近傍拡大する,
    #     3: 画像をPNG形式で保存する
    #   ]
    #   引数: [path: 保存先, export_size: 任意の正方形サイズ, output_resolution: 任意の横幅・縦幅]
    #   戻り値: [なし。保存失敗時は例外になる]
    # }
    def save_png(self, path: str | Path, export_size: int | None = None,
                 *, output_resolution: tuple[int, int] | None = None) -> None:
        if export_size is not None and output_resolution is not None:
            raise ValueError("choose export size or output resolution, not both")
        if output_resolution is not None:
            output = self.render_resolution(*output_resolution)
        else:
            output = self._native_image()
            if export_size is not None:
                target = resolution(export_size)
                if export_size < max(output.size):
                    raise ValueError("export size cannot be smaller than native canvas size")
                output = output.resize(target, Image.Resampling.NEAREST)
        output.save(path, "PNG")

    _color_to_source = staticmethod(encoded_color)
    _color_from_source = staticmethod(decoded_color)

    # {
    #   責務: [to_source: 作品と保持細部をversion 2 JSON互換辞書へ変換する]
    #   処理: [
    #     1: 論理解像度・表示画素・空間フィールド・分割状態を構成する,
    #     2: 現在解像度に属する子画素情報があれば追加する
    #   ]
    #   引数: []
    #   戻り値: [保存可能な作品状態の辞書]
    # }
    def to_source(self) -> dict[str, Any]:
        # Store both a compatibility preview and the retained spatial representation.
        source: dict[str, Any] = {
            "version": 2, "canvas_size": self.width, "resolution": list(self.resolution),
            "pixels": image_source(self.image),
            "retained_field": self._field.to_source(),
            "retained_splits": [
                {"resolution": [w, h], "x": x, "y": y,
                 "base": encoded_color(base), "expanded": expanded}
                for (w, h, x, y), (base, expanded) in sorted(self._splits.items())
            ],
        }
        cells = self._refined_cells
        if cells:
            # Emit child colors as an explicit compatibility view for current splits.
            source["refined_cells"] = [
                {"x": x, "y": y, "expanded": self.is_split(x, y),
                 "children": [[encoded_color(c) for c in row] for row in children]}
                for (x, y), children in sorted(cells.items())
            ]
        return source

    # {
    #   責務: [from_source: version 1または2の辞書から作品状態を復元する]
    #   処理: [
    #     1: 形式バージョンと画素・分割入力を検証する,
    #     2: version 1の子画素形式を移行するかversion 2の細部状態を復元する,
    #     3: 表示画素と保持フィールドの一致を確認して返す
    #   ]
    #   引数: [cls: PixelCanvas型, source: 読み込む作品辞書]
    #   戻り値: [復元したPixelCanvas]
    # }
    @classmethod
    def from_source(cls, source: dict[str, Any]) -> PixelCanvas:
        if not isinstance(source, dict):
            raise ValueError("pixel project must be a JSON object")
        version = source.get("version", 1)
        if type(version) is not int or version not in (1, 2):
            raise ValueError("unsupported pixel project version")
        if version == 1:
            # Migrate the legacy square preview and its optional 2x2 child images.
            size = source.get("canvas_size")
            model = cls(size)
            image = source_image(source.get("pixels"), size, size)
            field = ResolutionField.from_image(image)
            cells = source.get("refined_cells", [])
            if not isinstance(cells, list) or len(cells) > cls.MAX_SPLITS:
                raise ValueError("invalid refined_cells")
            for cell in cells:
                if not isinstance(cell, dict):
                    raise ValueError("invalid refined cell")
                x, y = cell.get("x"), cell.get("y")
                if not model._in_bounds(x, y) or model._key(x, y) in model._splits:
                    raise ValueError("invalid or duplicate refined cell coordinate")
                expanded = cell.get("expanded", True)
                if type(expanded) is not bool:
                    raise ValueError("refined cell expanded must be a boolean")
                children = source_image(cell.get("children"), 2, 2)
                if expanded:
                    resolution(2 * size, 2 * size)
                model._splits[model._key(x, y)] = (image.getpixel((x, y)), expanded)
                for cy in range(2):
                    for cx in range(2):
                        field = field.replace(model._box(x, y, (cx, cy)), children.getpixel((cx, cy)))
            model._field = field
            return model
        # Version 2 stores the logical size and retained field separately.
        shape = source.get("resolution")
        if not isinstance(shape, list) or len(shape) != 2:
            raise ValueError("invalid project resolution")
        model = cls(*resolution(*shape))
        if type(source.get("canvas_size")) is not int or source["canvas_size"] != model.width:
            raise ValueError("canvas_size does not match resolution width")
        model._field = ResolutionField.from_source(source.get("retained_field"))
        splits = source.get("retained_splits")
        if not isinstance(splits, list) or len(splits) > cls.MAX_SPLITS:
            raise ValueError("invalid retained split list")
        for entry in splits:
            if not isinstance(entry, dict):
                raise ValueError("invalid retained split")
            dims = entry.get("resolution")
            if not isinstance(dims, list) or len(dims) != 2:
                raise ValueError("invalid split resolution")
            w, h = resolution(*dims)
            x, y = entry.get("x"), entry.get("y")
            if type(x) is not int or type(y) is not int or not (0 <= x < w and 0 <= y < h):
                raise ValueError("invalid retained split coordinate")
            expanded = entry.get("expanded")
            if type(expanded) is not bool:
                raise ValueError("invalid retained split expansion state")
            if expanded:
                resolution(2 * w, 2 * h)
            key = (w, h, x, y)
            if key in model._splits:
                raise ValueError("duplicate retained split")
            model._splits[key] = (decoded_color(entry.get("base")), expanded)
        # Reject files whose redundant preview disagrees with the authoritative field.
        preview = source_image(source.get("pixels"), *model.resolution)
        if preview.tobytes() != model.image.tobytes():
            raise ValueError("project pixels disagree with retained field")
        expected = model.to_source().get("refined_cells", [])
        if source.get("refined_cells", []) != expected:
            raise ValueError("project refined_cells disagree with retained field")
        return model
