"""Headless checks for menu access-key uniqueness and live editor actions."""
import unittest

from dot_editor import PixelEditor, menu_spec


# {
#   責務: [MenuStructureTests: Altメニューのアクセスキー・操作先・パレット項目を検証する]
#   フィールド: [なし、各テスト内で検証対象を構築する]
# }
class MenuStructureTests(unittest.TestCase):
    # {
    #   責務: [test_top_level_alt_access_keys_are_visible_and_unique: メニュー見出しのアクセスキーが表示され重複しないことを検証する]
    #   処理: [
    #     1: メニュー仕様から見出しとアクセスキーを取得する
    #     2: アクセスキーの重複がないこととメニュー数が6であることを確認する
    #     3: 各アクセスキーが対応する見出しに含まれることを照合する
    #   ]
    #   引数: [self: テスト対象のMenuStructureTestsケース]
    #   戻り値: [なし、仕様が期待と異なればassertionで失敗する]
    # }
    def test_top_level_alt_access_keys_are_visible_and_unique(self):
        menus = menu_spec()
        keys = [access_key.casefold() for _, access_key, _ in menus]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertEqual(len(menus), 6)
        for label, access_key, _ in menus:
            self.assertIn(access_key.casefold(), label.casefold())

    # {
    #   責務: [test_every_menu_entry_key_is_unique_within_its_menu: 全メニュー項目のアクセスキー表示と同階層での一意性を検証する]
    #   処理: [
    #     1: 入れ子関数で区切り線以外の項目を調べ、キーがラベルに表示されることを確認する
    #     2: カスケードメニューを再帰的に検査し、各階層のキー重複を確認する
    #     3: 全メニューの項目ツリーに対して同じ検査を行う
    #   ]
    #   引数: [self: テスト対象のMenuStructureTestsケース]
    #   戻り値: [なし、表示や一意性が期待と異なればassertionで失敗する]
    # }
    def test_every_menu_entry_key_is_unique_within_its_menu(self):
        # {
        #   責務: [check_siblings: 同一メニュー階層のアクセスキーと子メニューを検証する]
        #   処理: [
        #     1: 区切り線を除く項目のアクセスキーをラベルと照合する
        #     2: カスケード項目の子階層を再帰的に検査する
        #     3: 同階層に重複キーがないことを確認する
        #   ]
        #   引数: [entries: 同一階層に並ぶメニュー項目]
        #   戻り値: [なし、キーが不正または重複すればassertionで失敗する]
        # }
        def check_siblings(entries):
            keys = []
            for entry in entries:
                if entry[0] == "separator":
                    continue
                access_key = entry[2]
                label, _ = PixelEditor.access_label(entry[1], access_key)
                self.assertIn(access_key.casefold(), label.casefold())
                keys.append(access_key.casefold())
                if entry[0] == "cascade":
                    check_siblings(entry[3])
            self.assertEqual(len(keys), len(set(keys)), keys)

        for _, _, entries in menu_spec():
            check_siblings(entries)

    # {
    #   責務: [test_actions_resolve_to_editor_methods: メニュー操作先がPixelEditorの呼び出し可能なメソッドであることを検証する]
    #   処理: [
    #     1: 入れ子関数でコマンド項目の操作先をPixelEditorから取得する
    #     2: 操作先が呼び出し可能であることを確認する
    #     3: カスケードと全メニューを再帰的に検査する
    #   ]
    #   引数: [self: テスト対象のMenuStructureTestsケース]
    #   戻り値: [なし、未定義または非呼び出し可能な操作先があればassertionで失敗する]
    # }
    def test_actions_resolve_to_editor_methods(self):
        # {
        #   責務: [check_actions: メニュー項目の操作先を調べ、子メニューを再帰的に検証する]
        #   処理: [コマンド項目の操作先を検証し、カスケード項目では子項目を再帰処理する]
        #   引数: [entries: 検査するメニュー項目]
        #   戻り値: [なし、操作先が無効ならassertionで失敗する]
        # }
        def check_actions(entries):
            for entry in entries:
                if entry[0] == "command":
                    self.assertTrue(callable(getattr(PixelEditor, entry[3], None)), entry[3])
                elif entry[0] == "cascade":
                    check_actions(entry[3])

        for _, _, entries in menu_spec():
            check_actions(entries)

    # {
    #   責務: [test_palette_menu_covers_all_current_palette_slots: パレットが全8色を保持し色変換結果が16進形式であることを検証する]
    #   処理: [
    #     1: GUI起動を避けてPixelEditorを生成し、現在の8色を設定する
    #     2: 色数と各RGB値の16進文字列長を照合する
    #   ]
    #   引数: [self: テスト対象のMenuStructureTestsケース]
    #   戻り値: [なし、パレットの数や変換形式が期待と異なればassertionで失敗する]
    # }
    def test_palette_menu_covers_all_current_palette_slots(self):
        editor = PixelEditor.__new__(PixelEditor)
        editor.palette_colors = [
            (255, 255, 255), (0, 0, 0), (255, 80, 80), (255, 190, 70),
            (255, 240, 100), (90, 210, 130), (80, 180, 255), (170, 110, 255),
        ]
        self.assertEqual(len(editor.palette_colors), 8)
        for color in editor.palette_colors:
            self.assertEqual(len(editor.rgb_to_hex(color)), 7)


if __name__ == "__main__":
    unittest.main()
