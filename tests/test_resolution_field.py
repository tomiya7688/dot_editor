"""名前付きパッチへの移行で保持フィールドの契約が変わらないことを検証する。"""
from fractions import Fraction
import unittest
from unittest.mock import patch

from PIL import Image

import resolution_field
from resolution_field import FULL, ZERO, ResolutionField, Tile


# {
#   責務: [ResolutionFieldTests: パッチの所有権・有理数境界・未飽和色・保存互換・細部判定を検証する]
#   フィールド: []
# }
class ResolutionFieldTests(unittest.TestCase):
    # {
    #   責務: [rational_box: テスト用の矩形境界をBox契約の有理数へ統一する]
    #   処理: [4つの境界値をFractionへ変換して順序どおりに返す]
    #   引数: [left: 左端, top: 上端, right: 右端, bottom: 下端]
    #   戻り値: [有理数4つからなる空間領域]
    # }
    @staticmethod
    def rational_box(left, top, right, bottom):
        # 内部APIはFractionのBoxを受け取るため、整数の除算によるfloat混入を避ける。
        return tuple(Fraction(value) for value in (left, top, right, bottom))

    # {
    #   責務: [test_named_record_owns_input_copy_and_keeps_json_shape: 名前付き記録への変更で入力画像の独立性と保存形式を失わないことを確認する]
    #   処理: [画像からパッチを作り、入力画像の変更・記録の再代入・保存用辞書の形を検証する]
    #   引数: [self: テストケース]
    #   戻り値: [なし、所有権や保存契約が異なればテスト失敗]
    # }
    def test_named_record_owns_input_copy_and_keeps_json_shape(self):
        source = Image.new("RGBA", (2, 1), (1, 2, 3, 255))
        field = ResolutionField.from_image(source)
        tile = field.tiles[0]
        self.assertIsInstance(tile, Tile)
        self.assertEqual((tile.clip, tile.extent, tile.offset), (FULL, FULL, ZERO))
        # NamedTupleは画像そのものを凍結しないため、入力画像は別所有で保持する。
        source.putpixel((0, 0), (255, 0, 0, 255))
        self.assertEqual(tile.image.getpixel((0, 0)), (1, 2, 3, 255))
        with self.assertRaises(AttributeError):
            tile.offset = (1, 0, 0, 0)
        self.assertEqual(field.to_source(), [{
            "clip": [[0, 1], [0, 1], [1, 1], [1, 1]],
            "extent": [[0, 1], [0, 1], [1, 1], [1, 1]],
            "resolution": [2, 1], "pixels": [["#010203", "#010203"]],
            "offset": [0, 0, 0, 0],
        }])

    # {
    #   責務: [test_crop_keeps_original_pixel_boundaries: 画素途中の切り抜きでも元画素境界が移動しないことを確認する]
    #   処理: [4画素画像を有理数境界で切り抜き、保持領域と各標本色を元画像で照合する]
    #   引数: [self: テストケース]
    #   戻り値: [なし、切り抜きで元画素の位置がずれればテスト失敗]
    # }
    def test_crop_keeps_original_pixel_boundaries(self):
        source = Image.new("RGBA", (4, 1))
        source.putdata([(x * 50, 0, 0, 255) for x in range(4)])
        tile = ResolutionField.from_image(source).tiles[0]
        clip = (Fraction(3, 8), Fraction(0), Fraction(7, 8), Fraction(1))
        cropped = ResolutionField._crop(tile, clip)
        self.assertIsInstance(cropped, Tile)
        self.assertEqual(cropped.extent, (Fraction(1, 4), 0, 1, 1))
        self.assertEqual(cropped.image.size, (3, 1))
        field = ResolutionField((cropped,))
        # 境界の左右と境界上を含め、元画像の同じ画素を参照する必要がある。
        for x in (Fraction(3, 8), Fraction(7, 16), Fraction(1, 2), Fraction(13, 16)):
            with self.subTest(x=x):
                self.assertEqual(field.sample(x, Fraction(1, 2)), source.getpixel((int(x * 4), 0)))

    # {
    #   責務: [test_unclamped_offsets_are_reversible_and_keep_old_snapshot: 表示範囲外の色差分を保持し逆操作と旧状態の参照ができることを確認する]
    #   処理: [正負の大きな差分を適用し、未飽和値・表示色・逆変換と元状態を比較する]
    #   引数: [self: テストケース]
    #   戻り値: [なし、飽和前の情報や旧状態が失われればテスト失敗]
    # }
    def test_unclamped_offsets_are_reversible_and_keep_old_snapshot(self):
        original = ResolutionField.from_image(Image.new("RGBA", (1, 1), (100, 150, 200, 255)))
        before = original.to_source()
        delta = (300, -300, 11, 0)
        shifted = original.shift(FULL, delta)
        self.assertEqual(shifted.sample_raw(Fraction(1, 2), Fraction(1, 2)), (400, -150, 211, 255))
        self.assertEqual(shifted.render(3, 2).getpixel((1, 1)), (255, 0, 211, 255))
        # 表示用に飽和しても、保持値へ逆差分を加えれば元色へ戻せる。
        restored = shifted.shift(FULL, tuple(-value for value in delta))
        self.assertEqual(restored.to_source(), before)
        self.assertEqual(original.to_source(), before)

    # {
    #   責務: [test_fractional_edits_match_independent_projection_and_json: 分数境界の局所編集を独立した画素計算とJSON復元で照合する]
    #   処理: [長方形画像へ置換と色差分を適用し、異なる出力格子の全画素を計算結果と比較する]
    #   引数: [self: テストケース]
    #   戻り値: [なし、座標計算・色差分・保存復元が変化すればテスト失敗]
    # }
    def test_fractional_edits_match_independent_projection_and_json(self):
        source = Image.new("RGBA", (4, 3))
        source.putdata([(x * 40, y * 70, 60, 255) for y in range(3) for x in range(4)])
        original = ResolutionField.from_image(source)
        before = original.to_source()
        box = self.rational_box(Fraction(1, 3), Fraction(1, 5), Fraction(2, 3), Fraction(4, 5))
        field = original.replace(box, (240, 20, 30, 0))
        field = field.shift(self.rational_box(Fraction(1, 2), 0, 1, 1), (20, -40, 300, 0))
        saved = field.to_source()
        loaded = ResolutionField.from_source(saved)
        self.assertEqual(loaded.to_source(), saved)
        self.assertTrue(all(isinstance(tile, Tile) for tile in loaded.tiles))
        for width, height in ((7, 5), (13, 11)):
            rendered = loaded.render(width, height)
            # フィールドの標本関数を期待値に流用せず、編集契約から直接計算する。
            for y in range(height):
                for x in range(width):
                    px, py = Fraction(2 * x + 1, 2 * width), Fraction(2 * y + 1, 2 * height)
                    color = source.getpixel((int(px * 4), int(py * 3)))
                    if box[0] <= px < box[2] and box[1] <= py < box[3]:
                        color = (240, 20, 30, 0)
                    if px >= Fraction(1, 2):
                        color = tuple(value + delta for value, delta in zip(color, (20, -40, 300, 0)))
                    self.assertEqual(loaded.sample_raw(px, py), color, (width, height, x, y))
                    expected = tuple(max(0, min(255, value)) for value in color)
                    self.assertEqual(rendered.getpixel((x, y)), expected, (width, height, x, y))
        self.assertEqual(original.to_source(), before)

    # {
    #   責務: [test_detail_detection_handles_empty_single_and_touching_patches: 細部判定が空・単一・境界接触を区別することを確認する]
    #   処理: [被覆なし・単色・細かい元画素・境界接触だけの照会結果を比較する]
    #   引数: [self: テストケース]
    #   戻り値: [なし、パッチ数や細かさの判定が変化すればテスト失敗]
    # }
    def test_detail_detection_handles_empty_single_and_touching_patches(self):
        self.assertFalse(ResolutionField(()).has_detail(FULL))
        self.assertFalse(ResolutionField().has_detail(FULL))
        field = ResolutionField.from_image(Image.new("RGBA", (2, 1)))
        self.assertTrue(field.has_detail(FULL))
        # 隣のパッチと辺が接するだけなら、重なるパッチを2つと数えない。
        field = ResolutionField().replace(self.rational_box(0, 0, Fraction(1, 2), 1), (1, 2, 3, 255))
        self.assertFalse(field.has_detail(self.rational_box(Fraction(1, 2), 0, Fraction(3, 4), 1)))
        self.assertTrue(field.has_detail(FULL))

    # {
    #   責務: [test_detail_detection_stops_after_two_overlaps: 重なるパッチが2件見つかった時点で探索を終えることを確認する]
    #   処理: [3パッチ全体を照会し、交差判定が2回で終了することを検証する]
    #   引数: [self: テストケース]
    #   戻り値: [なし、不要な全件走査があればテスト失敗]
    # }
    def test_detail_detection_stops_after_two_overlaps(self):
        image = Image.new("RGBA", (1, 1))
        tiles = []
        for x in range(3):
            box = self.rational_box(Fraction(x, 3), 0, Fraction(x + 1, 3), 1)
            tiles.append(Tile(box, box, image, ZERO))
        # 結果だけでなく、早期終了という変更の目的も回帰検証する。
        with patch("resolution_field.intersection", wraps=resolution_field.intersection) as intersect:
            self.assertTrue(ResolutionField(tuple(tiles)).has_detail(FULL))
        self.assertEqual(intersect.call_count, 2)

    # {
    #   責務: [test_compaction_and_budget_errors_preserve_named_records: 予算超過時の無損失集約と拒否でも名前付き記録と元状態を保つことを確認する]
    #   処理: [複数パッチを1件へ集約して描画を比較し、非ゼロ差分と過大差分の拒否後に元状態を比較する]
    #   引数: [self: テストケース]
    #   戻り値: [なし、集約の色・記録型・失敗時の状態が異なればテスト失敗]
    # }
    def test_compaction_and_budget_errors_preserve_named_records(self):
        field = ResolutionField().replace(self.rational_box(Fraction(1, 4), 0, Fraction(3, 4), 1), (20, 30, 40, 255))
        before = field.to_source()
        expected = field.render(4, 1).tobytes()
        with patch("resolution_field.MAX_TILES", 1):
            compacted = ResolutionField._checked(list(field.tiles))
        self.assertEqual(len(compacted.tiles), 1)
        self.assertIsInstance(compacted.tiles[0], Tile)
        self.assertEqual(compacted.render(4, 1).tobytes(), expected)
        shifted = field.shift(FULL, (1, 0, 0, 0))
        # 差分付きパッチの強制集約は不可。過大差分も元状態を変更せず拒否する。
        with patch("resolution_field.MAX_TILES", 1):
            with self.assertRaises(ValueError):
                ResolutionField._checked(list(shifted.tiles))
        with self.assertRaises(ValueError):
            field.shift(FULL, (1_000_001, 0, 0, 0))
        self.assertEqual(field.to_source(), before)
