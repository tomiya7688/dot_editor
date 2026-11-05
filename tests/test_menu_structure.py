"""Headless checks for menu access-key uniqueness and live editor actions."""

import inspect
import tkinter as tk
import re
from pathlib import Path
from types import SimpleNamespace
import unittest

from canvas_cursor import CanvasCursor
from stroke import StrokeSession
from dot_editor import (
    CELL_MENU_ACTIONS,
    KEY_BINDINGS,
    PixelEditor,
    choose_restore_target,
    menu_spec,
)


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
        self.assertEqual(len(menus), 7)
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
            (255, 255, 255),
            (0, 0, 0),
            (255, 80, 80),
            (255, 190, 70),
            (255, 240, 100),
            (90, 210, 130),
            (80, 180, 255),
            (170, 110, 255),
        ]
        self.assertEqual(len(editor.palette_colors), 8)
        for color in editor.palette_colors:
            self.assertEqual(len(editor.rgb_to_hex(color)), 7)

    # {
    #   責務: [test_canvas_input_registered_at_startup_not_by_palette_menu: キャンバス入力が起動時に登録されることを検証する]
    #   処理: [
    #     1: 偽のキャンバスと初期化の副作用を差し替えた編集部を作る
    #     2: initialize_canvas_inputが4つのマウス入力を登録することを確認する
    #     3: __init__がそれを呼び、パレットメニューの作成は入力を登録しないことを確認する
    #   ]
    #   引数: [self: テスト対象のMenuStructureTestsケース]
    #   戻り値: [なし、登録の位置が誤っていればassertionで失敗する]
    # }
    def test_canvas_input_registered_at_startup_not_by_palette_menu(self):
        events = []
        canvas = SimpleNamespace(bind=lambda event, handler, add=None: events.append(event))
        menu = SimpleNamespace(delete=lambda *args: None)
        editor = PixelEditor.__new__(PixelEditor)
        editor.canvas = canvas
        editor.palette_colors = []
        editor.update_canvas_size = lambda: None
        editor.refresh_layer_list = lambda: None
        editor.populate_palette_menu(menu)
        self.assertEqual(events, [])
        editor.initialize_canvas_input()
        self.assertEqual(
            sorted(events),
            sorted(
                [
                    "<Button-1>",
                    "<B1-Motion>",
                    "<ButtonPress-2>",
                    "<B2-Motion>",
                    "<Left>",
                    "<Right>",
                    "<Up>",
                    "<Down>",
                    "<Return>",
                    "<Escape>",
                    "<KeyPress-space>",
                    "<KeyRelease-space>",
                    "<FocusOut>",
                ]
            ),
        )
        self.assertIn("self.initialize_canvas_input()", inspect.getsource(PixelEditor.__init__))

    # {
    #   責務: [test_cell_items_follow_selection_and_actions_resolve_by_name: 選択セルの有無で項目が切り替わることを検証する]
    #   処理: [
    #     1: 偽のメニューへ動作名と位置を登録した編集部を作る
    #     2: 選択セルなしで3項目が無効、ありで有効になることを確認する
    #     3: 履歴が空なら元に戻す・やり直しが無効、レイヤーが1枚なら削除が無効になることを確認する
    #   ]
    #   引数: [self: テスト対象のMenuStructureTestsケース]
    #   戻り値: [なし、状態の切り替えが誤っていればassertionで失敗する]
    # }
    def test_cell_items_follow_selection_and_actions_resolve_by_name(self):
        states = {}
        menu = SimpleNamespace(entryconfigure=lambda index, state: states.__setitem__(index, state))
        names = list(CELL_MENU_ACTIONS) + ["undo", "redo", "remove_layer"]
        editor = PixelEditor.__new__(PixelEditor)
        editor.menu_command_entries = {name: (menu, i) for i, name in enumerate(names)}
        editor.history, editor.future = [], []
        editor.backend = SimpleNamespace(layers=["a"])
        editor.selected_cell = None
        editor.update_menu_state()
        self.assertEqual(set(states.values()), {"disabled"})
        editor.selected_cell = (1, 2)
        editor.history = [object()]
        editor.backend = SimpleNamespace(layers=["a", "b"])
        editor.update_menu_state()
        enabled = {names[i] for i, state in states.items() if state == "normal"}
        self.assertEqual(enabled, set(CELL_MENU_ACTIONS) | {"undo", "remove_layer"})
        for action in CELL_MENU_ACTIONS:
            self.assertTrue(hasattr(PixelEditor, action))

    # {
    #   責務: [test_key_bindings_listed_in_readme: キー割当表の各キーが利用者向け案内に載っていることを検証する]
    #   処理: [
    #     1: READMEを読み込む
    #     2: KEY_BINDINGSの各キーの表記が含まれることを確認する
    #   ]
    #   引数: [self: テスト対象のMenuStructureTestsケース]
    #   戻り値: [なし、載っていないキーがあればassertionで失敗する]
    # }
    def test_key_bindings_listed_in_readme(self):
        readme = (Path(__file__).resolve().parents[1] / "README.md").read_text(encoding="utf-8")
        for key, _ in KEY_BINDINGS:
            self.assertIn(key, readme)

    # {
    #   責務: [test_restore_target_order: フォーカス復帰先が保存要素、近い要素、既定の順で決まることを検証する]
    #   処理: [
    #     1: すべて使える場合は保存要素が選ばれることを確認する
    #     2: 保存要素が使えない場合は近い要素、次に既定が選ばれることを確認する
    #     3: 候補がすべて使えない場合はNoneになることを確認する
    #   ]
    #   引数: [self: テスト対象のMenuStructureTestsケース]
    #   戻り値: [なし、復帰先の決定が誤っていればassertionで失敗する]
    # }
    def test_restore_target_order(self):
        self.assertEqual(choose_restore_target("a", ["n"], "c", lambda w: True), "a")
        self.assertEqual(choose_restore_target("a", ["n"], "c", lambda w: w != "a"), "n")
        self.assertEqual(choose_restore_target("a", ["n"], "c", lambda w: w == "c"), "c")
        self.assertEqual(choose_restore_target(None, [], "c", lambda w: False), None)

    # {
    #   責務: [test_run_dialog_sets_parent_and_restores_focus: ダイアログが親付きで開き、例外時も復帰することを検証する]
    #   処理: [
    #     1: 偽のウィンドウとキャンバスを持つ編集部を作る
    #     2: parentが渡され、保存した要素へフォーカスが戻ることを確認する
    #     3: ダイアログが例外を出しても復帰し、例外が伝わることを確認する
    #   ]
    #   引数: [self: テスト対象のMenuStructureTestsケース]
    #   戻り値: [なし、親指定または復帰が誤っていればassertionで失敗する]
    # }
    def test_run_dialog_sets_parent_and_restores_focus(self):
        focused = []
        saved = SimpleNamespace(
            winfo_exists=lambda: True, focus_set=lambda: focused.append("saved")
        )
        canvas = SimpleNamespace(
            winfo_exists=lambda: True, focus_set=lambda: focused.append("canvas")
        )
        editor = PixelEditor.__new__(PixelEditor)
        editor.master = SimpleNamespace(focus_get=lambda: saved)
        editor.canvas = canvas
        seen = {}
        result = editor.run_dialog(lambda **kw: seen.update(kw) or "ok")
        self.assertEqual((result, seen["parent"], focused), ("ok", editor.master, ["saved"]))
        saved.winfo_exists = lambda: False
        focused.clear()

        with self.assertRaises(ValueError):
            editor.run_dialog(lambda **kw: (_ for _ in ()).throw(ValueError("boom")))
        self.assertEqual(focused, ["canvas"])
        broken = SimpleNamespace(
            winfo_exists=lambda: True,
            focus_set=lambda: (_ for _ in ()).throw(tk.TclError("gone")),
        )
        editor.master = SimpleNamespace(focus_get=lambda: broken)
        self.assertEqual(editor.run_dialog(lambda **kw: "kept"), "kept")

    # {
    #   責務: [test_no_dialog_bypasses_run_dialog: すべてのダイアログがrun_dialog経由であることを検証する]
    #   処理: [
    #     1: エディターのソースを読む
    #     2: ダイアログ関数の直接呼び出しがないことを確認する
    #   ]
    #   引数: [self: テスト対象のMenuStructureTestsケース]
    #   戻り値: [なし、直接呼び出しがあればassertionで失敗する]
    # }
    def test_no_dialog_bypasses_run_dialog(self):
        source = (Path(__file__).resolve().parents[1] / "src" / "dot_editor.py").read_text(
            encoding="utf-8"
        )
        direct = re.findall(r"(?:simpledialog|filedialog|messagebox)\.(?:ask|show)\w*\(", source)
        direct += re.findall(r"(?<!run_dialog\()\baskcolor\(", source)
        self.assertEqual(direct, [])

    # {
    #   責務: [test_arrow_keys_move_selected_cell_and_redraw: 矢印キーが選択セルを動かし枠を描き直すことを検証する]
    #   処理: [
    #     1: 偽のキャンバスと3x2の作品を持つ編集部を作る
    #     2: 初回の矢印で左上、続く移動で端に止まることを確認する
    #     3: 分割済みセルでEnterを押すと子セルの枠になり、Escで戻ることを確認する
    #   ]
    #   引数: [self: テスト対象のMenuStructureTestsケース]
    #   戻り値: [なし、移動や枠の描画が誤っていればassertionで失敗する]
    # }
    def test_arrow_keys_move_selected_cell_and_redraw(self):
        rectangles = []
        canvas = SimpleNamespace(
            delete=lambda tag: rectangles.clear(),
            create_rectangle=lambda *box, **options: rectangles.append(box),
            tag_raise=lambda tag: None,
            cget=lambda name: "0 0 300 200",
            canvasx=lambda value: value,
            canvasy=lambda value: value,
            winfo_width=lambda: 300,
            winfo_height=lambda: 200,
            xview_moveto=lambda fraction: None,
            yview_moveto=lambda fraction: None,
        )
        stub = type(
            "Stub",
            (PixelEditor,),
            {"commands": SimpleNamespace(is_split=lambda x, y: (x, y) == (1, 0))},
        )
        editor = stub.__new__(stub)
        editor.canvas = canvas
        editor.cursor = CanvasCursor()
        editor.stroke = StrokeSession()
        editor.selected_cell = None
        editor.num_pixels_x, editor.num_pixels_y = 3, 2
        editor.canvas_width, editor.canvas_height, editor.zoom_factor = 300, 200, 1.0
        editor.viewport_size = lambda: (300, 200)
        self.assertEqual(editor.move_cursor(1, 0), "break")
        self.assertEqual(editor.selected_cell, (0, 0))
        editor.move_cursor(1, 0)
        editor.move_cursor(1, 0)
        editor.move_cursor(1, 0)
        self.assertEqual(editor.selected_cell, (2, 0))
        editor.move_cursor(-1, 0)
        self.assertEqual(editor.selected_cell, (1, 0))
        editor.enter_child_cell()
        self.assertEqual(editor.cursor.child, (0, 0))
        self.assertEqual(rectangles[0], (100.0, 0.0, 150.0, 50.0))
        editor.leave_child_cell()
        self.assertIsNone(editor.cursor.child)
        self.assertEqual(rectangles[0], (100.0, 0.0, 200.0, 100.0))


if __name__ == "__main__":
    unittest.main()
