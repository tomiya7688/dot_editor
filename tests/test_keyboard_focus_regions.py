"""Headless checks for keyboard movement between the canvas and sidebar."""
import unittest
from unittest.mock import Mock

from dot_editor import PixelEditor


# {
#   責務: [FakeRoot: テスト用トップレベル窓のフォーカスとイベント登録状態を保持する]
#   フィールド: [
#     master: 親窓
#     is_toplevel: トップレベル窓の判定
#     focused: 現在のフォーカス対象
#     bindings: イベントとコールバックの対応
#   ]
# }
class FakeRoot:
    # {
    #   責務: [__init__: トップレベル窓の初期状態を用意する]
    #   処理: [親窓を保持し、フォーカスなし・トップレベル判定・イベント未登録で初期化する]
    #   引数: [master: 親窓、既定値は親を持たない状態]
    #   戻り値: [なし、各状態をインスタンスに設定する]
    # }
    def __init__(self, master=None):
        self.master = master
        self.is_toplevel = True
        self.focused = None
        self.bindings = {}

    # {
    #   責務: [focus_get: トップレベル窓の現在のフォーカス対象を返す]
    #   処理: [保持しているfocusedを取得する]
    #   引数: [なし]
    #   戻り値: [フォーカス対象、未設定ならNone]
    # }
    def focus_get(self):
        return self.focused

    # {
    #   責務: [after_idle: アイドル時処理を同期実行するテスト用代替を提供する]
    #   処理: [受け取ったコールバックを直ちに呼び出す]
    #   引数: [callback: 実行する処理]
    #   戻り値: [なし、コールバックの戻り値は使用しない]
    # }
    def after_idle(self, callback):
        callback()

    # {
    #   責務: [bind: イベントとコールバックをテスト用窓に登録する]
    #   処理: [sequenceに対応するcallbackとadd指定をbindingsへ保存する]
    #   引数: [sequence: イベント名、callback: 実行処理、add: 追加登録指定]
    #   戻り値: [なし、登録内容をbindingsに保持する]
    # }
    def bind(self, sequence, callback, add=None):
        self.bindings[sequence] = (callback, add)


# {
#   責務: [FakeWidget: GUI部品の状態・フォーカス・イベント登録をテスト内で模擬する]
#   フィールド: [
#     master: 親ウィジェット
#     state: 有効・無効状態
#     exists: ウィジェットの存在状態
#     class_name: GUI部品クラス名
#     focus_count: フォーカス設定回数
#     configured: configureで設定された属性
#     bindings: イベントとコールバックの対応
#   ]
# }
class FakeWidget:
    # {
    #   責務: [__init__: GUI部品の親・状態・設定記録を初期化する]
    #   処理: [引数を保持し、フォーカス回数・設定・イベント登録を空にする]
    #   引数: [master: 親部品、state: 有効状態、exists: 存在状態、class_name: 部品種別]
    #   戻り値: [なし、テスト用状態をインスタンスに設定する]
    # }
    def __init__(self, master=None, state="normal", exists=True, class_name="Button"):
        self.master = master
        self.state = state
        self.exists = exists
        self.class_name = class_name
        self.focus_count = 0
        self.configured = {}
        self.bindings = {}

    # {
    #   責務: [focus_set: この部品へフォーカスを移し、親窓に状態を反映する]
    #   処理: [フォーカス回数を増やし、親をたどってトップレベル窓のfocusedを更新する]
    #   引数: [なし]
    #   戻り値: [なし、親窓のフォーカス状態を更新する]
    # }
    def focus_set(self):
        self.focus_count += 1
        root = self
        while getattr(root, "master", None) is not None:
            root = root.master
        root.focused = self

    # {
    #   責務: [cget: GUI部品のstate属性を返す]
    #   処理: [state要求には現在値を返し、それ以外の属性名はKeyErrorにする]
    #   引数: [name: 取得する属性名]
    #   戻り値: [stateの値、未対応名では例外を送出する]
    # }
    def cget(self, name):
        if name == "state":
            return self.state
        raise KeyError(name)

    # {
    #   責務: [winfo_exists: GUI部品が存在するかを返す]
    #   処理: [初期化時に設定されたexistsを取得する]
    #   引数: [なし]
    #   戻り値: [存在状態を表す真偽値]
    # }
    def winfo_exists(self):
        return self.exists

    # {
    #   責務: [winfo_class: GUI部品のクラス名を返す]
    #   処理: [初期化時に設定されたclass_nameを取得する]
    #   引数: [なし]
    #   戻り値: [GUI部品クラス名]
    # }
    def winfo_class(self):
        return self.class_name

    # {
    #   責務: [winfo_toplevel: 親をたどってトップレベル窓を返す]
    #   処理: [is_toplevelが真になるまでmasterをたどり、該当窓を返す]
    #   引数: [なし]
    #   戻り値: [トップレベル窓、見つからない場合はNone]
    # }
    def winfo_toplevel(self):
        widget = self
        while widget is not None and not getattr(widget, "is_toplevel", False):
            widget = getattr(widget, "master", None)
        return widget

    # {
    #   責務: [configure: GUI部品の設定変更をテスト用記録に反映する]
    #   処理: [キーワード属性をconfigured辞書に追加または更新する]
    #   引数: [options: 設定する属性と値]
    #   戻り値: [なし、変更内容をconfiguredに保持する]
    # }
    def configure(self, **options):
        self.configured.update(options)

    # {
    #   責務: [bind: イベントとコールバックをGUI部品に登録する]
    #   処理: [sequenceに対応するcallbackとadd指定をbindingsへ保存する]
    #   引数: [sequence: イベント名、callback: 実行処理、add: 追加登録指定]
    #   戻り値: [なし、登録内容をbindingsに保持する]
    # }
    def bind(self, sequence, callback, add=None):
        self.bindings[sequence] = (callback, add)


# {
#   責務: [FakeViewport: サイドバー表示範囲とスクロール位置をテスト内で模擬する]
#   フィールド: [
#     root_y: 画面上の表示領域上端
#     height: 表示領域の高さ
#     scroll_offset: Canvas内の縦スクロール量
#     scroll_to: 最後に要求されたスクロール位置
#   ]
# }
class FakeViewport:
    # {
    #   責務: [__init__: 表示領域とスクロール状態を初期化する]
    #   処理: [画面位置・表示高さ・スクロール量を保持し、移動要求を未設定にする]
    #   引数: [root_y: 表示領域上端、height: 表示高さ、scroll_offset: 現在のスクロール量]
    #   戻り値: [なし、テスト用の表示状態を初期化する]
    # }
    def __init__(self, root_y=100, height=100, scroll_offset=0):
        self.root_y = root_y
        self.height = height
        self.scroll_offset = scroll_offset
        self.scroll_to = None

    # {
    #   責務: [bbox: スクロール領域全体の境界を返す]
    #   処理: [固定サイズのスクロール領域境界を返す]
    #   引数: [_tag: 呼び出し互換のため受け取るCanvasタグ]
    #   戻り値: [左・上・右・下の境界座標]
    # }
    def bbox(self, _tag):
        return (0, 0, 240, 500)

    # {
    #   責務: [winfo_rooty: 表示領域上端の画面座標を返す]
    #   処理: [root_yに保持した画面座標を取得する]
    #   引数: [なし]
    #   戻り値: [表示領域上端の画面座標]
    # }
    def winfo_rooty(self):
        return self.root_y

    # {
    #   責務: [winfo_height: 表示領域の高さを返す]
    #   処理: [heightに保持した表示高さを取得する]
    #   引数: [なし]
    #   戻り値: [表示領域の高さ]
    # }
    def winfo_height(self):
        return self.height

    # {
    #   責務: [canvasy: 画面内y座標をスクロール領域の座標へ変換する]
    #   処理: [画面内y座標に現在のスクロール量を加算する]
    #   引数: [y: 表示領域内のy座標]
    #   戻り値: [スクロール領域内のy座標]
    # }
    def canvasy(self, y):
        return y + self.scroll_offset

    # {
    #   責務: [yview_moveto: テスト用スクロール移動要求を記録する]
    #   処理: [指定された先頭位置の割合をscroll_toに保存する]
    #   引数: [fraction: スクロール領域に対する先頭位置の割合]
    #   戻り値: [なし、移動要求をscroll_toに保持する]
    # }
    def yview_moveto(self, fraction):
        self.scroll_to = fraction


# {
#   責務: [FocusableGeometry: フォーカス対象部品に画面位置と寸法を加えて模擬する]
#   フィールド: [
#     root_y: 部品上端の画面座標
#     height: 部品の高さ
#   ]
# }
class FocusableGeometry(FakeWidget):
    # {
    #   責務: [__init__: フォーカス可能部品の画面位置と寸法を初期化する]
    #   処理: [親クラスの標準状態を初期化し、画面上端と高さを保持する]
    #   引数: [root_y: 部品上端の画面座標、height: 部品の高さ]
    #   戻り値: [なし、GUI部品状態と位置情報を初期化する]
    # }
    def __init__(self, root_y, height=20):
        super().__init__()
        self.root_y = root_y
        self.height = height

    # {
    #   責務: [winfo_rooty: フォーカス対象部品上端の画面座標を返す]
    #   処理: [root_yに保持した画面座標を取得する]
    #   引数: [なし]
    #   戻り値: [部品上端の画面座標]
    # }
    def winfo_rooty(self):
        return self.root_y

    # {
    #   責務: [winfo_height: フォーカス対象部品の高さを返す]
    #   処理: [heightに保持した部品の高さを取得する]
    #   引数: [なし]
    #   戻り値: [部品の高さ]
    # }
    def winfo_height(self):
        return self.height


# {
#   責務: [KeyboardFocusRegionTests: Canvas・サイドバー間のキーボードフォーカス動作を検証する]
#   フィールド: [
#     editor: テスト対象のPixelEditor
#     first: サイドバーの先頭フォーカス対象
#     last: サイドバーの末尾フォーカス対象
#   ]
# }
class KeyboardFocusRegionTests(unittest.TestCase):
    # {
    #   責務: [setUp: 各テストで使うエディターとフォーカス対象を用意する]
    #   処理: [PixelEditorをGUI起動せず生成し、模擬窓・Canvas・サイドバー部品を接続する]
    #   引数: [self: テストケース]
    #   戻り値: [なし、各テスト用の初期状態をselfに設定する]
    # }
    def setUp(self):
        self.editor = PixelEditor.__new__(PixelEditor)
        self.editor.master = FakeRoot()
        self.editor.canvas = FakeWidget(self.editor.master)
        self.editor.sidebar_frame = FakeWidget(self.editor.master)
        self.editor.sidebar_focus_targets = []
        self.first = FakeWidget(self.editor.sidebar_frame)
        self.last = FakeWidget(self.editor.sidebar_frame)
        self.editor.sidebar_focus_targets.extend((self.first, self.last))

    # {
    #   責務: [test_f6_enters_sidebar_at_first_target_and_shift_f6_at_last: F6方向に応じてサイドバー先頭か末尾へ移ることを検証する]
    #   処理: [
    #     1: Canvasにフォーカスした状態でF6操作の戻り値と先頭対象への移動を確認する
    #     2: 同じ状態からShift+F6を操作し、末尾対象への移動を確認する
    #   ]
    #   引数: [self: テスト対象のKeyboardFocusRegionTestsケース]
    #   戻り値: [なし、操作結果が期待と異なればassertionで失敗する]
    # }
    def test_f6_enters_sidebar_at_first_target_and_shift_f6_at_last(self):
        self.editor.master.focused = self.editor.canvas

        self.assertEqual(self.editor.focus_adjacent_region(), "break")
        self.assertIs(self.editor.master.focused, self.first)

        self.editor.master.focused = self.editor.canvas
        self.assertEqual(self.editor.focus_adjacent_region(reverse=True), "break")
        self.assertIs(self.editor.master.focused, self.last)

    # {
    #   責務: [test_f6_from_any_nested_sidebar_control_returns_to_canvas: 入れ子のサイドバー部品からCanvasへ戻ることを検証する]
    #   処理: [
    #     1: サイドバー配下に入れ子部品を作り、現在のフォーカスに設定する
    #     2: F6操作後にCanvasへ移り、フォーカス設定が一度であることを確認する
    #   ]
    #   引数: [self: テスト対象のKeyboardFocusRegionTestsケース]
    #   戻り値: [なし、移動先や設定回数が期待と異なればassertionで失敗する]
    # }
    def test_f6_from_any_nested_sidebar_control_returns_to_canvas(self):
        nested = FakeWidget(FakeWidget(self.editor.sidebar_frame))
        self.editor.master.focused = nested

        self.editor.focus_adjacent_region()

        self.assertIs(self.editor.master.focused, self.editor.canvas)
        self.assertEqual(self.editor.canvas.focus_count, 1)

    # {
    #   責務: [test_sidebar_entry_skips_destroyed_and_disabled_controls: 無効な部品を飛ばして有効な部品にフォーカスすることを検証する]
    #   処理: [
    #     1: 存在しない部品・無効部品・有効部品の順に対象を設定する
    #     2: サイドバーへのフォーカス移動が成功し、有効部品を選ぶことを確認する
    #   ]
    #   引数: [self: テスト対象のKeyboardFocusRegionTestsケース]
    #   戻り値: [なし、移動結果が期待と異なればassertionで失敗する]
    # }
    def test_sidebar_entry_skips_destroyed_and_disabled_controls(self):
        destroyed = FakeWidget(self.editor.sidebar_frame, exists=False)
        disabled = FakeWidget(self.editor.sidebar_frame, state="disabled")
        self.editor.sidebar_focus_targets = [destroyed, disabled, self.last]

        self.assertTrue(self.editor.focus_sidebar())
        self.assertIs(self.editor.master.focused, self.last)

    # {
    #   責務: [test_registered_controls_receive_tabbable_focus_feedback: 登録部品にTab移動とフォーカス表示設定が与えられることを検証する]
    #   処理: [
    #     1: サイドバー部品をフォーカス対象として登録する
    #     2: Tab対象・強調表示・FocusInイベント・対象一覧への登録を照合する
    #   ]
    #   引数: [self: テスト対象のKeyboardFocusRegionTestsケース]
    #   戻り値: [なし、設定や登録内容が期待と異なればassertionで失敗する]
    # }
    def test_registered_controls_receive_tabbable_focus_feedback(self):
        widget = FakeWidget(self.editor.sidebar_frame)

        self.editor.register_sidebar_focus_target(widget)

        self.assertEqual(widget.configured["takefocus"], 1)
        self.assertEqual(widget.configured["highlightthickness"], 2)
        self.assertEqual(widget.configured["highlightcolor"], "#80d4ff")
        self.assertIn("<FocusIn>", widget.bindings)
        self.assertIn(widget, self.editor.sidebar_focus_targets)

    # {
    #   責務: [test_focus_outside_scrolls_sidebar_and_focus_inside_does_not: 表示範囲外のフォーカス対象だけを見える位置へスクロールすることを検証する]
    #   処理: [
    #     1: 表示領域より下の対象を可視化するスクロール割合を確認する
    #     2: 表示領域より上の対象を可視化するスクロール割合を確認する
    #     3: 表示範囲内の対象ではスクロール要求が発生しないことを確認する
    #   ]
    #   引数: [self: テスト対象のKeyboardFocusRegionTestsケース]
    #   戻り値: [なし、スクロール位置が期待と異なればassertionで失敗する]
    # }
    def test_focus_outside_scrolls_sidebar_and_focus_inside_does_not(self):
        self.editor.sidebar_viewport = FakeViewport()
        below = FocusableGeometry(root_y=260)
        self.editor.scroll_sidebar_focus_into_view(below)
        self.assertAlmostEqual(self.editor.sidebar_viewport.scroll_to, 0.16)

        self.editor.sidebar_viewport = FakeViewport(scroll_offset=200)
        above = FocusableGeometry(root_y=90)
        self.editor.scroll_sidebar_focus_into_view(above)
        self.assertAlmostEqual(self.editor.sidebar_viewport.scroll_to, 0.38)

        self.editor.sidebar_viewport = FakeViewport(scroll_offset=200)
        visible = FocusableGeometry(root_y=150)
        self.editor.scroll_sidebar_focus_into_view(visible)
        self.assertIsNone(self.editor.sidebar_viewport.scroll_to)

    # {
    #   責務: [test_history_shortcuts_run_only_in_editor_not_text_inputs_or_dialogs: Undo・Redoショートカットの有効範囲を検証する]
    #   処理: [
    #     1: グローバルショートカットを登録し、通常部品ではUndo・Redoを実行する
    #     2: Tkとttkの入力部品ではショートカットを横取りしないことを確認する
    #     3: 別ダイアログ内では実行せず、Undo・Redo呼び出し回数を照合する
    #   ]
    #   引数: [self: テスト対象のKeyboardFocusRegionTestsケース]
    #   戻り値: [なし、イベント処理や呼び出し回数が期待と異なればassertionで失敗する]
    # }
    def test_history_shortcuts_run_only_in_editor_not_text_inputs_or_dialogs(self):
        self.editor.undo = Mock()
        self.editor.redo = Mock()
        self.editor.bind_global_shortcuts()
        undo = self.editor.master.bindings["<Control-z>"][0]
        redo = self.editor.master.bindings["<Control-y>"][0]

        self.editor.master.focused = FakeWidget(self.editor.master)
        self.assertEqual(undo(None), "break")
        self.assertEqual(redo(None), "break")
        self.editor.undo.assert_called_once_with()
        self.editor.redo.assert_called_once_with()

        for widget_class in ("Entry", "Text", "Spinbox", "TEntry", "TSpinbox", "TCombobox"):
            with self.subTest(widget_class=widget_class):
                self.editor.master.focused = FakeWidget(
                    self.editor.master, class_name=widget_class
                )
                self.assertIsNone(undo(None))
                self.assertIsNone(redo(None))

        dialog = FakeRoot(master=self.editor.master)
        self.editor.master.focused = FakeWidget(dialog)
        self.assertIsNone(undo(None))
        self.assertIsNone(redo(None))
        self.assertEqual(self.editor.undo.call_count, 1)
        self.assertEqual(self.editor.redo.call_count, 1)

    # {
    #   責務: [test_f6_does_not_steal_focus_from_a_dialog: F6が別ダイアログ内のフォーカスを奪わないことを検証する]
    #   処理: [
    #     1: ダイアログ内の入力部品を現在のフォーカスにする
    #     2: F6処理が未処理を示し、入力部品のフォーカスを保つことを確認する
    #   ]
    #   引数: [self: テスト対象のKeyboardFocusRegionTestsケース]
    #   戻り値: [なし、イベント戻り値やフォーカス先が期待と異なればassertionで失敗する]
    # }
    def test_f6_does_not_steal_focus_from_a_dialog(self):
        dialog = FakeRoot(master=self.editor.master)
        dialog_entry = FakeWidget(dialog, class_name="Entry")
        self.editor.master.focused = dialog_entry

        self.assertIsNone(self.editor.focus_adjacent_region())
        self.assertIs(self.editor.master.focused, dialog_entry)


if __name__ == "__main__":
    unittest.main()
