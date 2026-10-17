"""共有APIの座標型と拒否時の履歴保護を検証する。"""
import unittest

from pixel_commands import PixelCommandAPI

RED = (255, 0, 0, 255)
BLUE = (0, 0, 255, 255)
INVALID_INTEGERS = (True, False, 0.5, 1.0, "1", None, float("inf"), float("nan"))


# {
#   責務: [CommandIntegerInputTests: 単一・レイヤー作品で整数以外の入力を拒否し画像と履歴を保護することを検証する]
#   フィールド: []
# }
class CommandIntegerInputTests(unittest.TestCase):
    # {
    #   責務: [new_api_with_history: 分割セルとUndo・Redoの両履歴を持つ小さな作品を作る]
    #   処理: [分割後に2画素を描き、最後の描画だけを取り消してRedo可能にする]
    #   引数: [self: テストケース, layered: レイヤー付き作品を使用するか]
    #   戻り値: [検証対象の共有API]
    # }
    def new_api_with_history(self, layered):
        # 型検証が編集・参照する作品に、保持細部と双方向の履歴を用意する。
        api = PixelCommandAPI.new(4, 3, layered=layered)
        api.split(0, 0)
        api.paint(2, 1, RED)
        api.paint(3, 2, BLUE)
        self.assertTrue(api.canvas.undo())
        return api

    # {
    #   責務: [assert_rejection_preserves_history: 不正なAPI操作の例外・保存表現・UndoとRedoの実行結果を確認する]
    #   処理: [
    #     1: 操作前の保存表現を記録してValueErrorを確認する
    #     2: 操作後の画像と分割状態が変わらないことを比較する
    #     3: Redo・Undoを実行し両方の履歴が残っていることを確認する
    #   ]
    #   引数: [self: テストケース, api: 履歴付き作品, method: 操作名, arguments: 位置引数, keywords: 任意のキーワード引数]
    #   戻り値: [なし、拒否や状態保護が期待と異なればテスト失敗]
    # }
    def assert_rejection_preserves_history(self, api, method, arguments, **keywords):
        before = api.canvas.to_source()
        with self.assertRaises(ValueError):
            getattr(api, method)(*arguments, **keywords)
        self.assertEqual(api.canvas.to_source(), before)
        # privateな履歴配列ではなく、公開Undo/Redoの結果を確認する。
        self.assertTrue(api.canvas.redo())
        self.assertEqual(api.sample(3, 2), BLUE)
        self.assertTrue(api.canvas.undo())
        self.assertEqual(api.canvas.to_source(), before)
        self.assertTrue(api.canvas.undo())
        self.assertEqual(api.sample(2, 1), (0, 0, 0, 0))
        self.assertTrue(api.canvas.redo())
        self.assertEqual(api.canvas.to_source(), before)

    # {
    #   責務: [test_parent_coordinates_reject_non_integers: 親座標を使う編集と照会で整数以外を拒否することを検証する]
    #   処理: [単一・レイヤー作品の各操作のxとyへ不正値を渡し、例外と状態保護を確認する]
    #   引数: [self: テストケース]
    #   戻り値: [なし、型の暗黙変換や履歴破損があればテスト失敗]
    # }
    def test_parent_coordinates_reject_non_integers(self):
        operations = (
            ("paint", (RED,)), ("fill", (BLUE,)), ("erase", ()),
            ("split", ()), ("collapse", ()), ("is_split", ()),
            ("sample", ()), ("inspect_sample", ()),
        )
        # 全公開経路が同じ親座標検証へ到達することを確認する。
        for layered in (False, True):
            for method, tail in operations:
                for index in (0, 1):
                    for invalid in INVALID_INTEGERS:
                        with self.subTest(layered=layered, method=method, index=index, value=invalid):
                            api = self.new_api_with_history(layered)
                            point = [0, 0]
                            point[index] = invalid
                            self.assert_rejection_preserves_history(api, method, (*point, *tail))

    # {
    #   責務: [test_child_coordinates_reject_non_integers: 子画素の編集と照会で整数以外を拒否することを検証する]
    #   処理: [各子座標へ不正値を渡し、分割済みセルと履歴が保護されることを確認する]
    #   引数: [self: テストケース]
    #   戻り値: [なし、子座標の暗黙変換や履歴破損があればテスト失敗]
    # }
    def test_child_coordinates_reject_non_integers(self):
        for layered in (False, True):
            for method, tail in (("paint", (RED,)), ("erase", ()), ("sample", ()), ("inspect_sample", ())):
                for index in (0, 1):
                    for invalid in INVALID_INTEGERS:
                        with self.subTest(layered=layered, method=method, index=index, value=invalid):
                            api = self.new_api_with_history(layered)
                            child = [0, 0]
                            child[index] = invalid
                            # 親座標は有効な分割セルを選び、子座標の拒否だけを検証する。
                            self.assert_rejection_preserves_history(api, method, (0, 0, *tail), child=child)

    # {
    #   責務: [test_region_coordinates_and_dimensions_reject_non_integers: 領域操作の左上座標と寸法で整数以外を拒否することを検証する]
    #   処理: [領域分割・細部破棄の4引数へ不正値を渡し、編集開始前の拒否と履歴保護を確認する]
    #   引数: [self: テストケース]
    #   戻り値: [なし、領域の暗黙変換や履歴破損があればテスト失敗]
    # }
    def test_region_coordinates_and_dimensions_reject_non_integers(self):
        for layered in (False, True):
            for method in ("split_region", "discard_detail"):
                for index in range(4):
                    for invalid in INVALID_INTEGERS:
                        with self.subTest(layered=layered, method=method, index=index, value=invalid):
                            api = self.new_api_with_history(layered)
                            region = [0, 0, 1, 1]
                            region[index] = invalid
                            # 寸法の検証も画像更新より先に行われる必要がある。
                            self.assert_rejection_preserves_history(api, method, region)

    # {
    #   責務: [test_explicit_layer_sampling_rejects_non_integer_coordinates: 名前で指定したレイヤーの読み取りにも整数契約を適用することを検証する]
    #   処理: [対象レイヤーを指定した照会に不正な横・縦座標を渡し、例外と状態保護を確認する]
    #   引数: [self: テストケース]
    #   戻り値: [なし、別レイヤー経路で暗黙変換された場合はテスト失敗]
    # }
    def test_explicit_layer_sampling_rejects_non_integer_coordinates(self):
        for index in (0, 1):
            for invalid in INVALID_INTEGERS:
                with self.subTest(index=index, value=invalid):
                    api = self.new_api_with_history(True)
                    point = [0, 0]
                    point[index] = invalid
                    # layer指定時は通常の_pointとは異なるモデルを参照する。
                    self.assert_rejection_preserves_history(
                        api, "sample", point, layer=api.canvas.active_layer,
                    )
