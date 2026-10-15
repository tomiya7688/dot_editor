import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog
from tkinter.colorchooser import askcolor

from PIL import Image, ImageTk

from pixel_backend import PixelCanvas
from pixel_commands import PixelCommandAPI
from pixel_layers import LayeredPixelCanvas
from resolution_field import resolution


# {
#   責務: [menu_spec: メニューバーと各操作項目の構造を一元定義する]
#   処理: [ファイル・編集・描画・レイヤー・色・表示メニューをアクセスキーと操作名付きで返す]
#   引数: []
#   戻り値: [メニュー階層を表すタプル]
# }
def menu_spec():
    return (
        ("ファイル (F)", "F", (
            ("command", "画像を読み込む", "I", "import_image"),
            ("command", "プロジェクトを読み込む", "O", "load_project"),
            ("command", "プロジェクトを保存", "S", "save_project"),
            ("command", "PNGを保存", "P", "save_image"),
            ("separator",),
            ("command", "作品をリセット", "R", "reset_canvas"),
        )),
        ("編集 (E)", "E", (
            ("command", "元に戻す", "U", "undo", "Ctrl+Z"),
            ("command", "やり直す", "R", "redo", "Ctrl+Y"),
        )),
        ("描画 (T)", "T", (
            ("cascade", "描画ツール", "T", (
                ("command", "ブラシ (B)", "B", "activate_brush"),
                ("command", "塗りつぶし (F)", "F", "activate_fill"),
                ("command", "消しゴム (E)", "E", "activate_eraser"),
                ("command", "スポイト (P)", "P", "activate_eyedropper"),
            )),
            ("command", "選択セルを4分割", "S", "split_selected_cell"),
            ("command", "選択セルを折りたたむ", "C", "collapse_selected_cell"),
            ("command", "選択セルの細部を破棄", "D", "discard_selected_detail"),
        )),
        ("レイヤー (L)", "L", (
            ("layer-list", "レイヤーを選択", "S"),
            ("command", "追加", "A", "add_layer"),
            ("command", "削除", "R", "remove_layer"),
            ("command", "上へ移動", "U", "move_layer_up"),
            ("command", "下へ移動", "D", "move_layer_down"),
            ("command", "表示切替", "V", "toggle_layer_visibility"),
            ("command", "名称変更", "N", "rename_layer"),
        )),
        ("色 (C)", "C", (
            ("palette", "パレット色", "P"),
            ("command", "任意の色を選ぶ", "C", "choose_color"),
        )),
        ("表示 (V)", "V", (
            ("radio", "細部を保持", "P", "detail_policy", "preserve"),
            ("radio", "細部を破棄", "D", "detail_policy", "discard"),
            ("command", "論理解像度を変更", "R", "change_size"),
            ("command", "表示サイズを変更", "C", "change_canvas_size"),
            ("command", "解像度アップ", "U", "upscale_resolution"),
            ("command", "ズームイン", "I", "zoom_in"),
            ("command", "ズームアウト", "O", "zoom_out"),
        )),
    )


# {
#   責務: [PixelEditor: ドット絵編集画面とGUI操作を管理する]
#   フィールド: [
#     master: Tkメインウィンドウ
#     backend: レイヤー付き作品データ
#     canvas: 描画画像とグリッドを表示するキャンバス
#     canvas_width、canvas_height: 表示領域の幅と高さ
#     num_pixels_x、num_pixels_y: 論理解像度
#     current_color、tool、detail_policy: 描画色・選択ツール・細部処理方針
#     selected_cell: 選択中の論理セル
#     history、future: Undo/Redo用の作品スナップショット
#     zoom_factor: 表示倍率
#     pixel_size、pixel_size_y、display_pixel_size: 論理画素の表示寸法
#     sidebar_focus_targets、sidebar_frame、sidebar_viewport: スクロール可能なサイドバーとフォーカス対象
#     image、photo: 合成画像とTk表示用画像
#     menu_bar、editor_menus、layer_select_menu、palette_menu: メニュー部品
#     tool_buttons、brush_button、fill_button、eraser_button、eyedropper_button: 描画ツールUI
#     split_button、collapse_button、discard_button、tool_status_label: 分割操作とツール状態UI
#     color_button、palette_colors、palette_buttons: 色選択UI
#     layer_list、layer_menu_selection、_layer_names、add_layer_button、remove_layer_button: レイヤー一覧と追加・削除UI
#     move_layer_up_button、move_layer_down_button、layer_visibility_button、rename_layer_button: レイヤー操作UI
#     resolution_label、size_button、canvas_size_button、upscale_button: 解像度・表示寸法UI
#     zoom_in_button、zoom_out_button: 表示倍率UI
#     undo_button、redo_button、import_button、save_button、
#     save_project_button、load_project_button、reset_button: ファイル・履歴操作UI
#   ]
# }
class PixelEditor:
    # {
    #   責務: [__init__: 編集画面の初期状態とGUI部品を構築する]
    #   処理: [
    #     1: ウィンドウ・作品モデル・描画キャンバスを初期化する
    #     2: サイドバー、フォーカス移動、ショートカット、メニューを登録する
    #   ]
    #   引数: [master: 編集画面を配置するTkウィンドウ]
    #   戻り値: [なし。初期化済みインスタンスを構成する]
    # }
    def __init__(self, master):
        self.master = master
        self.master.title("ドット絵エディタ")
        self.master.configure(bg="#0b0f14")
        self.master.geometry("1040x740")
        self.master.minsize(900, 640)
        self.master.grid_columnconfigure(0, weight=1)
        self.master.grid_rowconfigure(0, weight=1)
        self.canvas_width = self.canvas_height = 640
        self.num_pixels_x = self.num_pixels_y = 2
        self.current_color = (255, 255, 255)
        self.selected_cell = None
        self.tool = "brush"
        self.palette_colors = [(255, 255, 255), (0, 0, 0), (255, 80, 80), (255, 190, 70),
                               (255, 240, 100), (90, 210, 130), (80, 180, 255), (170, 110, 255)]
        self.history, self.future = [], []
        self.backend = LayeredPixelCanvas(2)
        self.zoom_factor = 1.0
        self.detail_policy = tk.StringVar(master=master, value="preserve")
        self.layer_menu_selection = tk.StringVar(
            master=master, value=self.backend.active_layer
        )
        self.canvas = tk.Canvas(
            master,
            bg="#111820",
            highlightthickness=2,
            highlightbackground="#3b4654",
            highlightcolor="#80d4ff",
            takefocus=1,
        )
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.canvas.bind("<Configure>", self.on_canvas_configure, add="+")
        self.canvas.bind("<Control-MouseWheel>", self.zoom_with_wheel)
        self.build_sidebar()
        self.bind_focus_region_navigation()
        self.bind_global_shortcuts()
        self.build_menu_bar()

    # {
    #   責務: [access_label: メニュー表示名へアクセスキーと下線位置を反映する]
    #   処理: [
    #     1: 表示名から大文字小文字を区別せずキー位置を探す
    #     2: 見つからなければ括弧付きキーを追加して位置を求める
    #   ]
    #   引数: [label: メニュー項目名, access_key: アクセスキー]
    #   戻り値: [表示名と下線位置の組]
    # }
    @staticmethod
    def access_label(label, access_key):
        position = label.casefold().find(access_key.casefold())
        if position < 0:
            label = f"{label} ({access_key.upper()})"
            position = label.casefold().rfind(access_key.casefold())
        return label, position

    # {
    #   責務: [add_access_key: アクセスキー付きのコマンド項目をメニューへ追加する]
    #   処理: [表示名と下線位置を求め、追加オプションとともにcommand項目へ渡す]
    #   引数: [cls: PixelEditor型, menu: 追加先メニュー, label: 項目名, access_key: アクセスキー, options: Tkメニューへ渡す追加設定]
    #   戻り値: [なし。指定メニューを更新する]
    # }
    @classmethod
    def add_access_key(cls, menu, label, access_key, **options):
        label, position = cls.access_label(label, access_key)
        menu.add_command(label=label, underline=position, **options)

    # {
    #   責務: [build_menu_bar: 定義済み構造からメニューバーを構築する]
    #   処理: [
    #     1: メニュー状態と遅延生成メニューの参照を初期化する
    #     2: menu_specの各階層をTkメニューに変換してウィンドウへ設定する
    #   ]
    #   引数: []
    #   戻り値: [なし。selfのメニュー部品を初期化する]
    # }
    def build_menu_bar(self):
        self.menu_bar = tk.Menu(self.master, tearoff=False)
        self.editor_menus = {}
        self.layer_select_menu = None
        self.palette_menu = None
        for label, access_key, entries in menu_spec():
            visible_label, underline = self.access_label(label, access_key)
            menu = tk.Menu(self.menu_bar, tearoff=False)
            self.populate_menu(menu, entries)
            self.editor_menus[label] = menu
            self.menu_bar.add_cascade(
                label=visible_label,
                menu=menu,
                underline=underline,
                postcommand=self.update_menu_state,
            )
        self.master.configure(menu=self.menu_bar)

    # {
    #   責務: [populate_menu: メニュー定義の各項目をTkメニューへ展開する]
    #   処理: [
    #     1: separator、command、cascade、radio項目を種類別に生成する
    #     2: レイヤー・パレット項目は選択時に内容を更新するコールバックを結ぶ
    #     3: 未知の項目種類はValueErrorで拒否する
    #   ]
    #   引数: [menu: 項目を追加するTkメニュー, entries: 展開するメニュー定義]
    #   戻り値: [なし。指定メニューと遅延生成メニュー参照を更新する]
    # }
    def populate_menu(self, menu, entries):
        for entry in entries:
            kind = entry[0]
            if kind == "separator":
                menu.add_separator()
            elif kind == "command":
                _, label, access_key, action, *accelerator = entry
                self.add_access_key(
                    menu,
                    label,
                    access_key,
                    command=getattr(self, action),
                    accelerator=accelerator[0] if accelerator else "",
                )
            elif kind == "cascade":
                _, label, access_key, children = entry
                submenu = tk.Menu(menu, tearoff=False)
                self.populate_menu(submenu, children)
                visible_label, underline = self.access_label(label, access_key)
                menu.add_cascade(
                    label=visible_label,
                    underline=underline,
                    menu=submenu,
                    postcommand=self.update_menu_state,
                )
            elif kind == "radio":
                _, label, access_key, variable_name, value = entry
                variable = getattr(self, variable_name)
                visible_label, underline = self.access_label(label, access_key)
                menu.add_radiobutton(
                    label=visible_label,
                    underline=underline,
                    variable=variable,
                    value=value,
                )
            elif kind == "layer-list":
                _, label, access_key = entry
                submenu = tk.Menu(menu, tearoff=False)
                visible_label, underline = self.access_label(label, access_key)
                menu.add_cascade(
                    label=visible_label,
                    underline=underline,
                    menu=submenu,
                    postcommand=lambda target=submenu: self.populate_layer_menu(target),
                )
                self.layer_select_menu = submenu
            elif kind == "palette":
                _, label, access_key = entry
                submenu = tk.Menu(menu, tearoff=False)
                visible_label, underline = self.access_label(label, access_key)
                menu.add_cascade(
                    label=visible_label,
                    underline=underline,
                    menu=submenu,
                    postcommand=lambda target=submenu: self.populate_palette_menu(target),
                )
                self.palette_menu = submenu
            else:
                raise ValueError(f"unknown menu entry type: {kind}")

    # {
    #   責務: [update_menu_state: 操作対象がないメニュー項目を無効化する]
    #   処理: [Undo/Redo履歴とレイヤー数を確認して編集・レイヤー操作の状態を設定する]
    #   引数: []
    #   戻り値: [なし。既存メニューの有効状態を更新する]
    # }
    def update_menu_state(self):
        edit = self.editor_menus.get("編集 (E)")
        if edit is not None:
            edit.entryconfigure(0, state="normal" if self.history else "disabled")
            edit.entryconfigure(1, state="normal" if self.future else "disabled")
        layers = self.editor_menus.get("レイヤー (L)")
        if layers is not None:
            layers.entryconfigure(
                2,
                state="normal" if len(self.backend.layers) > 1 else "disabled",
            )

    # {
    #   責務: [populate_layer_menu: 現在のレイヤー一覧を選択メニューへ反映する]
    #   処理: [
    #     1: 古い項目を消して各レイヤーのラジオ項目を追加する
    #     2: 選択時のレイヤー切り替え処理を登録する
    #     3: 選択値をバックエンドのアクティブレイヤーに同期する
    #   ]
    #   引数: [menu: レイヤー項目を表示するTkメニュー]
    #   戻り値: [なし。メニュー内容と選択値を更新する]
    # }
    def populate_layer_menu(self, menu):
        menu.delete(0, tk.END)
        for name in self.backend.layers:
            menu.add_radiobutton(
                label=name,
                variable=self.layer_menu_selection,
                value=name,
                command=lambda selected=name: self.select_layer_from_menu(selected),
            )
        self.layer_menu_selection.set(self.backend.active_layer)

    # {
    #   責務: [select_layer_from_menu: メニューで指定したレイヤーを選択する]
    #   処理: [
    #     1: 存在しないレイヤー名を無視する
    #     2: 共有Command APIで選択し、一覧・合成画像・グリッドを更新する
    #   ]
    #   引数: [name: 選択するレイヤー名]
    #   戻り値: [なし。選択と画面表示を更新する]
    # }
    def select_layer_from_menu(self, name):
        if name not in self.backend.layers:
            return
        self.commands.select_layer(name)
        self.refresh_layer_list()
        self.refresh_composite()
        self.create_grid()
        self.update_canvas()

    # {
    #   責務: [populate_palette_menu: 色パレットを数字キー付きメニューに展開する]
    #   処理: [各色の番号と16進色を表示し、選択時にその色へ切り替える]
    #   引数: [menu: パレット項目を表示するTkメニュー]
    #   戻り値: [なし。メニュー内容を更新する]
    # }
    def populate_palette_menu(self, menu):
        menu.delete(0, tk.END)
        for index, color in enumerate(self.palette_colors, start=1):
            label = f"Color {index} (#{self.rgb_to_hex(color)[1:]})"
            self.add_access_key(
                menu,
                label,
                str(index),
                command=lambda selected=color: self.set_palette_color(selected),
            )
        self.update_canvas_size()
        self.refresh_layer_list()
        self.canvas.bind("<Button-1>", self.paint_pixel)
        self.canvas.bind("<B1-Motion>", self.paint_pixel)
        self.canvas.bind("<ButtonPress-2>", self.begin_pan)
        self.canvas.bind("<B2-Motion>", self.pan_canvas)

    # {
    #   責務: [build_sidebar: 描画・色・レイヤー・表示・ファイル操作欄を作る]
    #   処理: [
    #     1: スクロール可能なサイドバーとフォーカス対象一覧を用意する
    #     2: ツール・パレット・レイヤー・解像度・ファイル操作UIを配置する
    #     3: UI状態を作品モデルに同期する
    #   ]
    #   引数: []
    #   戻り値: [なし。サイドバー部品をselfへ登録する]
    # }
    def build_sidebar(self):
        # 解像度や細部の操作欄がファイル操作を隠さないようスクロール可能にする。
        self.sidebar_focus_targets = []
        frame = tk.Frame(self.master, bg="#0b0f14")
        frame.grid(row=0, column=1, padx=10, pady=10, sticky="ns")
        viewport = tk.Canvas(frame, bg="#0b0f14", width=240, height=640, highlightthickness=0)
        self.sidebar_viewport = viewport
        scrollbar = tk.Scrollbar(frame, orient="vertical", command=viewport.yview)
        viewport.configure(yscrollcommand=scrollbar.set)
        viewport.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        sidebar = tk.Frame(viewport, bg="#0b0f14")
        self.sidebar_frame = sidebar
        window = viewport.create_window((0, 0), window=sidebar, anchor="nw", width=240)
        sidebar.bind("<Configure>", lambda event: viewport.configure(scrollregion=viewport.bbox("all")))
        viewport.bind("<Configure>", lambda event: viewport.itemconfigure(window, width=event.width))
        tool_group = self.create_toolbar_group(sidebar, "描画ツール")
        tool_grid = tk.Frame(tool_group, bg="#101820")
        tool_grid.pack(fill="x", padx=6, pady=(0, 6))
        self.tool_buttons = {}
        tools = [("brush", "ブラシ", "brush_button"), ("fill", "塗りつぶし", "fill_button"),
                 ("eraser", "消しゴム", "eraser_button"), ("picker", "スポイト", "eyedropper_button")]
        for index, (name, title, attr) in enumerate(tools):
            button = self.make_toolbar_button(tool_grid, title, lambda name=name: self.set_tool(name), False)
            button.grid(row=index // 2, column=index % 2, padx=2, pady=2, sticky="ew")
            tool_grid.grid_columnconfigure(index % 2, weight=1)
            self.tool_buttons[name] = button
            setattr(self, attr, button)
        self.split_button = self.make_toolbar_button(tool_group, "選択セルを4分割", self.split_selected_cell)
        self.collapse_button = self.make_toolbar_button(tool_group, "選択セルを折りたたむ", self.collapse_selected_cell)
        self.discard_button = self.make_toolbar_button(tool_group, "選択セルの細部を破棄", self.discard_selected_detail)
        self.tool_status_label = tk.Label(tool_group, bg="#101820", fg="#a9c7df", anchor="w")
        self.tool_status_label.pack(fill="x", padx=8, pady=(2, 6))
        color_group = self.create_toolbar_group(sidebar, "色")
        self.color_button = self.make_toolbar_button(color_group, "色を選ぶ", self.choose_color)
        palette = tk.Frame(color_group, bg="#101820")
        palette.pack(padx=6, pady=(0, 6))
        self.palette_buttons = []
        for index, color in enumerate(self.palette_colors):
            button = tk.Button(palette, width=2, height=1, bg=self.rgb_to_hex(color), relief="flat",
                               command=lambda color=color: self.set_palette_color(color))
            self.register_sidebar_focus_target(button)
            button.grid(row=index // 4, column=index % 4, padx=1, pady=1)
            self.palette_buttons.append(button)
        layer_group = self.create_toolbar_group(sidebar, "レイヤー")
        self.layer_list = tk.Listbox(layer_group, height=4, width=20, bg="#111820", fg="#f0f3f6",
                                    selectbackground="#3f6685", highlightthickness=0, exportselection=False)
        self.register_sidebar_focus_target(self.layer_list)
        self.layer_list.pack(fill="x", padx=6, pady=(0, 4))
        self.layer_list.bind("<<ListboxSelect>>", self.select_layer)
        self.add_layer_button = self.make_toolbar_button(layer_group, "追加", self.add_layer)
        self.remove_layer_button = self.make_toolbar_button(layer_group, "削除", self.remove_layer)
        self.move_layer_up_button = self.make_toolbar_button(
            layer_group, "上へ", lambda: self.move_layer("up")
        )
        self.move_layer_down_button = self.make_toolbar_button(
            layer_group, "下へ", lambda: self.move_layer("down")
        )
        self.layer_visibility_button = self.make_toolbar_button(
            layer_group, "表示切替", self.toggle_layer_visibility
        )
        self.rename_layer_button = self.make_toolbar_button(
            layer_group, "名称変更", self.rename_layer
        )
        view_group = self.create_toolbar_group(sidebar, "表示・解像度")
        self.resolution_label = tk.Label(view_group, bg="#101820", fg="#a9c7df", anchor="w")
        self.resolution_label.pack(fill="x", padx=8)
        for value, title in (("preserve", "細部を保持（既定）"), ("discard", "細部を破棄して編集")):
            button = tk.Radiobutton(
                view_group,
                text=title,
                variable=self.detail_policy,
                value=value,
                bg="#101820",
                fg="#f0f3f6",
                selectcolor="#17212b",
                anchor="w",
            )
            self.register_sidebar_focus_target(button)
            button.pack(fill="x")
        self.size_button = self.make_toolbar_button(view_group, "論理解像度を変更", self.change_size)
        self.canvas_size_button = self.make_toolbar_button(view_group, "表示サイズを変更", self.change_canvas_size)
        self.upscale_button = self.make_toolbar_button(view_group, "解像度アップ", self.upscale_resolution)
        self.zoom_out_button = self.make_toolbar_button(view_group, "ズーム−", self.zoom_out)
        self.zoom_in_button = self.make_toolbar_button(view_group, "ズーム＋", self.zoom_in)
        file_group = self.create_toolbar_group(sidebar, "ファイル・編集")
        buttons = [("undo_button", "元に戻す", self.undo), ("redo_button", "やり直す", self.redo),
                   ("import_button", "画像を読み込む", self.import_image), ("save_button", "PNG保存", self.save_image),
                   ("save_project_button", "プロジェクト保存", self.save_project),
                   ("load_project_button", "プロジェクト読込", self.load_project),
                   ("reset_button", "作品をリセット", self.reset_canvas)]
        for attr, title, command in buttons:
            setattr(self, attr, self.make_toolbar_button(file_group, title, command))
        self.refresh_tool_state()

    # {
    #   責務: [create_toolbar_group: 見出し付きのツールバー区画を作成する]
    #   処理: [指定タイトルのLabelFrameを生成して親へ配置する]
    #   引数: [parent: 区画の親ウィジェット, title: 区画見出し]
    #   戻り値: [生成した区画ウィジェット]
    # }
    def create_toolbar_group(self, parent, title):
        group = tk.LabelFrame(parent, text=title, bg="#101820", fg="#cbd5df", bd=1,
                              relief="solid", padx=2, pady=4)
        group.pack(fill="x", pady=(0, 8))
        return group

    # {
    #   責務: [make_toolbar_button: サイドバー用ボタンを作成して配置する]
    #   処理: [
    #     1: 配色と操作コマンドを指定したボタンを作成する
    #     2: キーボードフォーカス対象へ登録し、必要ならpack配置する
    #   ]
    #   引数: [parent: ボタンの親ウィジェット, text: 表示文字列, command: 実行コールバック, use_pack: pack配置するか]
    #   戻り値: [作成したボタンウィジェット]
    # }
    def make_toolbar_button(self, parent, text, command, use_pack=True):
        button = tk.Button(parent, text=text, command=command, bg="#17212b", fg="#f0f3f6",
                           activebackground="#263747", activeforeground="#ffffff", relief="flat")
        self.register_sidebar_focus_target(button)
        if use_pack:
            button.pack(fill="x", padx=6, pady=2)
        return button

    # {
    #   責務: [register_sidebar_focus_target: サイドバー部品をキーボード操作対象に登録する]
    #   処理: [
    #     1: Tab移動と視認できるフォーカス枠を設定する
    #     2: フォーカス時のスクロール処理を追加して対象一覧へ保存する
    #   ]
    #   引数: [widget: 登録するサイドバー部品]
    #   戻り値: [登録した同じウィジェット]
    # }
    def register_sidebar_focus_target(self, widget):
        widget.configure(
            takefocus=1,
            highlightthickness=2,
            highlightbackground="#253443",
            highlightcolor="#80d4ff",
        )
        widget.bind(
            "<FocusIn>",
            lambda _event, target=widget: self.on_sidebar_focus(target),
            add="+",
        )
        self.sidebar_focus_targets.append(widget)
        return widget

    # {
    #   責務: [bind_focus_region_navigation: キャンバスとサイドバー間のフォーカス移動を結ぶ]
    #   処理: [F6とShift+F6を順方向・逆方向の領域移動コールバックへ割り当てる]
    #   引数: []
    #   戻り値: [なし。メインウィンドウへイベントを登録する]
    # }
    def bind_focus_region_navigation(self):
        self.master.bind(
            "<F6>",
            lambda event: self.focus_adjacent_region(event, reverse=False),
            add="+",
        )
        self.master.bind(
            "<Shift-F6>",
            lambda event: self.focus_adjacent_region(event, reverse=True),
            add="+",
        )

    # {
    #   責務: [bind_global_shortcuts: Undo/Redoのグローバルショートカットを登録する]
    #   処理: [Ctrl+ZとCtrl+Yをフォーカス状態を考慮するハンドラーへ結び付ける]
    #   引数: []
    #   戻り値: [なし。メインウィンドウへイベントを登録する]
    # }
    def bind_global_shortcuts(self):
        self.master.bind("<Control-z>", self.handle_undo_shortcut, add="+")
        self.master.bind("<Control-y>", self.handle_redo_shortcut, add="+")

    # {
    #   責務: [is_main_window_widget: ウィジェットが編集ウィンドウ配下か判定する]
    #   処理: [トップレベル取得を試み、破棄済み・非Tk対象の例外はFalseにする]
    #   引数: [widget: 所属を調べるウィジェットまたはNone]
    #   戻り値: [編集ウィンドウ配下ならTrue、それ以外はFalse]
    # }
    def is_main_window_widget(self, widget):
        if widget is None:
            return False
        try:
            return widget.winfo_toplevel() is self.master
        except (AttributeError, tk.TclError):
            return False

    # {
    #   責務: [is_text_input_widget: ウィジェットが文字入力部品か判定する]
    #   処理: [
    #     1: Noneやウィジェット情報取得エラーをFalseにする
    #     2: 入力欄として扱うTkクラス名の一覧と照合する
    #   ]
    #   引数: [widget: 種類を調べるウィジェットまたはNone]
    #   戻り値: [文字入力部品ならTrue、それ以外はFalse]
    # }
    @staticmethod
    def is_text_input_widget(widget):
        if widget is None:
            return False
        try:
            widget_class = widget.winfo_class().casefold()
        except (AttributeError, tk.TclError):
            return False
        return widget_class in {
            "entry",
            "text",
            "spinbox",
            "tentry",
            "tspinbox",
            "tcombobox",
        }

    # {
    #   責務: [handle_undo_shortcut: Ctrl+Zを安全なフォーカス領域で実行する]
    #   処理: [
    #     1: 入力欄や別ウィンドウのフォーカス中は何もしない
    #     2: 編集画面内ならUndoを実行してTkの既定処理を止める
    #   ]
    #   引数: [_event: Tkイベント。未指定でも呼び出せる]
    #   戻り値: [イベント抑止時は"break"、対象外ならNone]
    # }
    def handle_undo_shortcut(self, _event=None):
        focused = self.master.focus_get()
        if not self.is_main_window_widget(focused) or self.is_text_input_widget(focused):
            return None
        self.undo()
        return "break"

    # {
    #   責務: [handle_redo_shortcut: Ctrl+Yを安全なフォーカス領域で実行する]
    #   処理: [
    #     1: 入力欄や別ウィンドウのフォーカス中は何もしない
    #     2: 編集画面内ならRedoを実行してTkの既定処理を止める
    #   ]
    #   引数: [_event: Tkイベント。未指定でも呼び出せる]
    #   戻り値: [イベント抑止時は"break"、対象外ならNone]
    # }
    def handle_redo_shortcut(self, _event=None):
        focused = self.master.focus_get()
        if not self.is_main_window_widget(focused) or self.is_text_input_widget(focused):
            return None
        self.redo()
        return "break"

    # {
    #   責務: [is_sidebar_widget: ウィジェットがサイドバー配下か判定する]
    #   処理: [親ウィジェットをたどり、サイドバーフレームとの同一性を確認する]
    #   引数: [widget: 所属を調べるウィジェットまたはNone]
    #   戻り値: [サイドバー配下ならTrue、それ以外はFalse]
    # }
    def is_sidebar_widget(self, widget):
        while widget is not None:
            if widget is self.sidebar_frame:
                return True
            widget = getattr(widget, "master", None)
        return False

    # {
    #   責務: [focus_adjacent_region: キャンバスとサイドバーの間でフォーカスを移す]
    #   処理: [
    #     1: 編集ウィンドウ以外にフォーカスがあればイベントを処理しない
    #     2: 現在領域に応じてキャンバスまたはサイドバーへ移動する
    #   ]
    #   引数: [_event: Tkイベント, reverse: サイドバーを逆順に検索するか]
    #   戻り値: [移動を処理した場合は"break"、対象外ならNone]
    # }
    def focus_adjacent_region(self, _event=None, reverse=False):
        focused = self.master.focus_get()
        if not self.is_main_window_widget(focused):
            return None
        if self.is_sidebar_widget(focused):
            self.canvas.focus_set()
        else:
            self.focus_sidebar(reverse=reverse)
        return "break"

    # {
    #   責務: [focus_sidebar: 使用可能なサイドバー部品へフォーカスする]
    #   処理: [
    #     1: 指定方向でフォーカス対象を順に確認する
    #     2: 存在し無効化されていない最初の対象へフォーカスを設定する
    #   ]
    #   引数: [reverse: 逆順で対象を探すか]
    #   戻り値: [対象へ移動できた場合はTrue、候補がなければFalse]
    # }
    def focus_sidebar(self, reverse=False):
        targets = reversed(self.sidebar_focus_targets) if reverse else self.sidebar_focus_targets
        for widget in targets:
            if widget.winfo_exists() and widget.cget("state") != tk.DISABLED:
                widget.focus_set()
                return True
        return False

    # {
    #   責務: [on_sidebar_focus: フォーカス対象を表示範囲へ収める処理を予約する]
    #   処理: [Tkのアイドル処理後に対象ウィジェットのスクロール調整を呼び出す]
    #   引数: [widget: フォーカスを受けたサイドバー部品]
    #   戻り値: [なし。Tkのアイドルコールバックを登録する]
    # }
    def on_sidebar_focus(self, widget):
        self.master.after_idle(lambda target=widget: self.scroll_sidebar_focus_into_view(target))

    # {
    #   責務: [scroll_sidebar_focus_into_view: フォーカス対象が見えるようサイドバーをスクロールする]
    #   処理: [
    #     1: 対象と表示領域の座標・高さを取得する
    #     2: 対象が表示外なら必要な位置へ移動する
    #     3: 遅延処理中に部品が破棄された場合は安全に終了する
    #   ]
    #   引数: [widget: 表示範囲へ収める対象部品]
    #   戻り値: [なし。必要な場合のみ表示領域を更新する]
    # }
    def scroll_sidebar_focus_into_view(self, widget):
        viewport = self.sidebar_viewport
        try:
            region = viewport.bbox("all")
            if region is None:
                return
            region_top, region_bottom = region[1], region[3]
            content_height = max(1, region_bottom - region_top)
            viewport_height = viewport.winfo_height()
            view_top = viewport.canvasy(0)
            view_bottom = viewport.canvasy(viewport_height)
            widget_y = widget.winfo_rooty() - viewport.winfo_rooty()
            widget_top = viewport.canvasy(widget_y)
            widget_bottom = widget_top + widget.winfo_height()
            if widget_top < view_top:
                target_top = widget_top
            elif widget_bottom > view_bottom:
                target_top = max(region_top, widget_bottom - viewport_height)
            else:
                return
            fraction = (target_top - region_top) / content_height
            viewport.yview_moveto(max(0.0, min(1.0, fraction)))
        except tk.TclError:
            # 遅延FocusInコールバックの実行前に対象部品が破棄される場合がある。
            return

    # {
    #   責務: [set_tool: 描画ツールを検証して選択する]
    #   処理: [許可されたツール名だけを受け入れ、選択状態を表示へ反映する]
    #   引数: [tool: brush・fill・eraser・pickerのいずれか]
    #   戻り値: [なし。無効な名前はValueErrorになる]
    # }
    def set_tool(self, tool):
        if tool not in {"brush", "fill", "eraser", "picker"}:
            raise ValueError(f"unknown tool: {tool}")
        self.tool = tool
        self.refresh_tool_state()

    # {
    #   責務: [activate_brush: ブラシツールを選択する]
    #   処理: [共通ツール切替処理へbrushを渡す]
    #   引数: []
    #   戻り値: [なし。ツール状態とボタン表示を更新する]
    # }
    def activate_brush(self):
        self.set_tool("brush")

    # {
    #   責務: [move_layer_up: 選択レイヤーを上へ移動する]
    #   処理: [共通レイヤー移動処理へup方向を渡す]
    #   引数: []
    #   戻り値: [なし。編集結果は共通編集処理で反映する]
    # }
    def move_layer_up(self):
        self.move_layer("up")

    # {
    #   責務: [move_layer_down: 選択レイヤーを下へ移動する]
    #   処理: [共通レイヤー移動処理へdown方向を渡す]
    #   引数: []
    #   戻り値: [なし。編集結果は共通編集処理で反映する]
    # }
    def move_layer_down(self):
        self.move_layer("down")

    # {
    #   責務: [refresh_tool_state: 選択ツールと状態表示を画面へ反映する]
    #   処理: [各ツールボタンの配色・押下状態と、現在ツール名を設定する]
    #   引数: []
    #   戻り値: [なし。存在するツールUIだけを更新する]
    # }
    def refresh_tool_state(self):
        names = {"brush": "ブラシ", "fill": "塗りつぶし", "eraser": "消しゴム", "picker": "スポイト"}
        for name, button in getattr(self, "tool_buttons", {}).items():
            selected = name == self.tool
            button.configure(bg="#3f6685" if selected else "#17212b", relief="sunken" if selected else "flat")
        label = getattr(self, "tool_status_label", None)
        if label is not None:
            label.configure(text=f"現在: {names[self.tool]}")

    # {
    #   責務: [current_detail_policy: 現在選択されている細部処理方針を取得する]
    #   処理: [方針変数があれば値を読み、未初期化なら既定のpreserveを返す]
    #   引数: []
    #   戻り値: [preserveまたはdiscard]
    # }
    def current_detail_policy(self):
        variable = getattr(self, "detail_policy", None)
        return variable.get() if variable is not None else "preserve"

    # {
    #   責務: [commands: 現在の作品バックエンドを操作する共有APIを返す]
    #   処理: [現在のLayeredPixelCanvasを包むPixelCommandAPIを生成する]
    #   引数: []
    #   戻り値: [バックエンドを共有するPixelCommandAPI]
    # }
    @property
    def commands(self):
        return PixelCommandAPI(self.backend)

    # {
    #   責務: [report_error: 操作失敗を利用者へ通知する]
    #   処理: [メインウィンドウが初期化済みの場合にエラーダイアログを表示する]
    #   引数: [error: 表示する例外またはエラー内容]
    #   戻り値: [なし。ウィンドウ未初期化時は何もしない]
    # }
    def report_error(self, error):
        if hasattr(self, "master"):
            messagebox.showerror("操作できません", str(error), parent=self.master)

    # {
    #   責務: [refresh_composite: レイヤー合成結果から表示用画像を作り直す]
    #   処理: [バックエンドの合成画像を表示キャンバス寸法へ最近傍拡大する]
    #   引数: []
    #   戻り値: [なし。self.imageを更新する]
    # }
    def refresh_composite(self):
        self.image = self.backend.composite().resize((self.canvas_width, self.canvas_height), Image.Resampling.NEAREST)

    # {
    #   責務: [refresh_layer_list: レイヤー一覧と選択状態を画面へ反映する]
    #   処理: [
    #     1: 一覧ウィジェット未作成なら終了する
    #     2: 表示状態付きの名前一覧を作り、アクティブレイヤーを選択する
    #   ]
    #   引数: []
    #   戻り値: [なし。リストと内部表示名一覧を更新する]
    # }
    def refresh_layer_list(self):
        if not hasattr(self, "layer_list"):
            return
        self.layer_list.delete(0, tk.END)
        names = list(self.backend.layers)
        self._layer_names = names
        for name in names:
            marker = "表示" if self.backend.layer_visibility.get(name, True) else "非表示"
            self.layer_list.insert(tk.END, f"[{marker}] {name}")
        if self.backend.active_layer in names:
            self.layer_list.selection_set(names.index(self.backend.active_layer))

    # {
    #   責務: [_finish_edit: 成功した編集をUndo履歴へ確定する]
    #   処理: [
    #     1: 編集前状態を最大100件のUndo履歴へ追加しRedo履歴を消す
    #     2: 論理解像度、レイヤー一覧、表示キャンバスを再同期する
    #   ]
    #   引数: [before: 編集前の作品スナップショット]
    #   戻り値: [なし。履歴と画面状態を更新する]
    # }
    def _finish_edit(self, before):
        self.history.append(before)
        del self.history[:-100]
        self.future.clear()
        self.num_pixels_x, self.num_pixels_y = self.backend.resolution
        self.refresh_layer_list()
        self.update_canvas_size()

    # {
    #   責務: [perform_edit: 編集コマンドを実行し成功時だけ履歴へ記録する]
    #   処理: [
    #     1: 実行前スナップショットを取得する
    #     2: 編集エラーを通知して失敗として返す
    #     3: 状態が変わった場合に編集を確定する
    #   ]
    #   引数: [command: 呼び出す編集操作, args: 操作の位置引数, kwargs: 操作の名前付き引数]
    #   戻り値: [作品が変化した場合はTrue、それ以外はFalse]
    # }
    def perform_edit(self, command, *args, **kwargs):
        before = self.make_snapshot()
        try:
            changed = command(*args, **kwargs)
        except (ValueError, IndexError, KeyError, OSError) as error:
            self.report_error(error)
            return False
        if changed:
            self._finish_edit(before)
        return bool(changed)

    # {
    #   責務: [add_layer: 利用者が指定した名前でレイヤーを追加する]
    #   処理: [
    #     1: レイヤー名入力を求め、キャンセルや空欄なら終了する
    #     2: 共有APIで追加し、入力不正を通知する
    #     3: 追加できた場合にUndo可能な編集として確定する
    #   ]
    #   引数: []
    #   戻り値: [なし。成功時は作品・履歴・表示を更新する]
    # }
    def add_layer(self):
        name = simpledialog.askstring("レイヤー追加", "レイヤー名")
        if not name:
            return
        before = self.make_snapshot()
        try:
            changed = self.commands.add_layer(name)
        except ValueError as error:
            self.report_error(error)
            return
        if changed:
            self._finish_edit(before)

    # {
    #   責務: [remove_layer: アクティブレイヤーを削除する]
    #   処理: [スナップショットを保持して削除し、失敗を通知、成功時は編集を確定する]
    #   引数: []
    #   戻り値: [なし。削除可能な場合に作品と画面を更新する]
    # }
    def remove_layer(self):
        before = self.make_snapshot()
        try:
            changed = self.commands.remove_layer()
        except (KeyError, ValueError) as error:
            self.report_error(error)
            return
        if changed:
            self._finish_edit(before)

    # {
    #   責務: [rename_layer: アクティブレイヤーの名称を変更する]
    #   処理: [現在名を初期値として入力を求め、キャンセル以外を共通編集処理へ渡す]
    #   引数: []
    #   戻り値: [なし。成功時はUndo可能な編集として反映する]
    # }
    def rename_layer(self):
        current = self.backend.active_layer
        new_name = simpledialog.askstring(
            "レイヤー名称変更", "新しいレイヤー名", initialvalue=current, parent=self.master
        )
        if new_name is not None:
            self.perform_edit(self.commands.rename_layer, new_name)

    # {
    #   責務: [move_layer: アクティブレイヤーを指定方向へ移動する]
    #   処理: [共有Command APIのレイヤー移動を共通編集処理経由で実行する]
    #   引数: [direction: upまたはdownの移動方向]
    #   戻り値: [なし。成功時は履歴と表示を更新する]
    # }
    def move_layer(self, direction):
        self.perform_edit(self.commands.move_layer, direction)

    # {
    #   責務: [toggle_layer_visibility: アクティブレイヤーの表示状態を切り替える]
    #   処理: [現在値を反転して共通編集処理から可視状態変更を実行する]
    #   引数: []
    #   戻り値: [なし。成功時は履歴と合成表示を更新する]
    # }
    def toggle_layer_visibility(self):
        current = self.backend.is_layer_visible()
        self.perform_edit(self.commands.set_layer_visibility, not current)

    # {
    #   責務: [select_layer: リスト選択をバックエンドのアクティブレイヤーへ反映する]
    #   処理: [選択行があれば名前を共有APIへ渡し、合成画像・グリッドを描き直す]
    #   引数: [_event: Tkの選択変更イベント。未指定でも呼び出せる]
    #   戻り値: [なし。選択がある場合に作品表示を更新する]
    # }
    def select_layer(self, _event=None):
        selection = self.layer_list.curselection()
        if selection:
            self.commands.select_layer(self._layer_names[selection[0]])
            self.refresh_composite()
            self.create_grid()
            self.update_canvas()

    # {
    #   責務: [image_origin: 表示領域内における画像の左上位置を求める]
    #   処理: [画像が収まる軸は中央寄せし、はみ出す軸は原点を0にする]
    #   引数: [viewport_width: 表示領域幅, viewport_height: 表示領域高さ, image_width: 画像幅, image_height: 画像高さ]
    #   戻り値: [画像左上のx・y座標]
    # }
    @staticmethod
    def image_origin(viewport_width, viewport_height, image_width, image_height):
        return (
            max(0, (viewport_width - image_width) // 2),
            max(0, (viewport_height - image_height) // 2),
        )

    # {
    #   責務: [viewport_size: キャンバスの実表示領域寸法を取得する]
    #   処理: [
    #     1: 表示寸法の代替値を現在の表示キャンバスと倍率から求める
    #     2: Tkの実寸を安全に取得し、未確定・不正値は代替値にする
    #   ]
    #   引数: []
    #   戻り値: [幅と高さの組。各値は1以上]
    # }
    def viewport_size(self):
        requested = (
            max(1, min(self.canvas_width, round(self.canvas_width * self.zoom_factor))),
            max(1, min(self.canvas_height, round(self.canvas_height * self.zoom_factor))),
        )
        measure = getattr(self.canvas, "winfo_width", None)
        try:
            width = int(measure()) if callable(measure) else 0
        except (TypeError, ValueError):
            width = 0
        measure = getattr(self.canvas, "winfo_height", None)
        try:
            height = int(measure()) if callable(measure) else 0
        except (TypeError, ValueError):
            height = 0
        return (
            width if width and width > 1 else requested[0],
            height if height and height > 1 else requested[1],
        )

    # {
    #   責務: [on_canvas_configure: キャンバス寸法変更後の表示領域を再計算する]
    #   処理: [画像が存在する場合にスクロール範囲を更新し、グリッドと画像を描き直す]
    #   引数: [_event: TkのConfigureイベント。未指定でも呼び出せる]
    #   戻り値: [なし。画像未生成時は何もしない]
    # }
    def on_canvas_configure(self, _event=None):
        if not hasattr(self, "image"):
            return
        viewport_width, viewport_height = self.viewport_size()
        content_width = max(1, round(self.canvas_width * self.zoom_factor))
        content_height = max(1, round(self.canvas_height * self.zoom_factor))
        self.canvas.configure(
            scrollregion=(
                0, 0, max(viewport_width, content_width),
                max(viewport_height, content_height),
            )
        )
        self.create_grid()
        self.update_canvas()

    # {
    #   責務: [zoom_with_wheel: Ctrl+マウスホイールで表示倍率を変更する]
    #   処理: [ホイール方向に応じて拡大または縮小する]
    #   引数: [event: ホイール移動量を持つTkイベント]
    #   戻り値: [Tkの既定処理を抑止する"break"]
    # }
    def zoom_with_wheel(self, event):
        if event.delta > 0:
            self.zoom_in()
        elif event.delta < 0:
            self.zoom_out()
        return "break"

    # {
    #   責務: [update_canvas_size: 作品を維持したまま表示寸法と画像を更新する]
    #   処理: [
    #     1: 論理解像度と倍率から表示画素寸法を計算する
    #     2: キャンバス寸法・スクロール領域・解像度ラベルを更新する
    #     3: 合成画像・グリッド・描画画像を再生成する
    #   ]
    #   引数: []
    #   戻り値: [なし。作品データとUndo/Redo履歴は変更しない]
    # }
    def update_canvas_size(self):
        self.pixel_size = self.canvas_width / self.num_pixels_x
        self.pixel_size_y = self.canvas_height / self.num_pixels_y
        self.display_pixel_size = self.pixel_size * self.zoom_factor
        width = max(1, round(self.canvas_width * self.zoom_factor))
        height = max(1, round(self.canvas_height * self.zoom_factor))
        self.canvas.config(width=min(self.canvas_width, width), height=min(self.canvas_height, height))
        viewport_width, viewport_height = self.viewport_size()
        self.canvas.configure(
            scrollregion=(
                0, 0, max(viewport_width, width), max(viewport_height, height)
            )
        )
        label = getattr(self, "resolution_label", None)
        if label is not None:
            label.configure(
                text=f"解像度: {self.num_pixels_x} × {self.num_pixels_y}"
                f"　表示: {round(self.zoom_factor * 100)}%"
            )
        self.refresh_composite()
        self.create_grid()
        self.update_canvas()

    # {
    #   責務: [set_display_size: 表示領域の幅と高さを検証して変更する]
    #   処理: [正の整数だけを受け入れ、寸法を設定後に表示を更新する]
    #   引数: [width: 表示領域幅, height: 表示領域高さ]
    #   戻り値: [なし。不正値はValueErrorになる]
    # }
    def set_display_size(self, width, height):
        if type(width) is not int or type(height) is not int or width <= 0 or height <= 0:
            raise ValueError("display size must be positive integers")
        self.canvas_width, self.canvas_height = width, height
        self.update_canvas_size()

    # {
    #   責務: [reset_canvas_model: 空のレイヤー付き作品へ初期化する]
    #   処理: [
    #     1: 省略時は現在解像度を使い、指定値は正規化する
    #     2: 新しい作品を作り、選択セルとUndo/Redo履歴を消去する
    #     3: レイヤー一覧と表示を更新する
    #   ]
    #   引数: [size: 横幅または解像度指定, height: 任意の縦幅]
    #   戻り値: [なし。作品モデルを新規作成する]
    # }
    def reset_canvas_model(self, size=None, height=None):
        shape = self.backend.resolution if size is None else resolution(size, height)
        self.backend = PixelCommandAPI.new(*shape, layered=True).canvas
        self.num_pixels_x, self.num_pixels_y = shape
        self.selected_cell = None
        self.history.clear()
        self.future.clear()
        self.refresh_layer_list()
        self.update_canvas_size()

    # {
    #   責務: [resize_logical_canvas: 作品の論理解像度を変更する]
    #   処理: [解像度を正規化し、指定方針で共通編集処理へ渡して必要ならセル選択を解除する]
    #   引数: [size: 横幅または解像度指定, height: 任意の縦幅, detail_policy: 細部の保持・破棄方針]
    #   戻り値: [解像度が変更された場合はTrue、それ以外はFalse]
    # }
    def resize_logical_canvas(self, size, height=None, detail_policy="preserve"):
        target = resolution(size, height)
        changed = self.perform_edit(self.commands.set_resolution, *target, detail_policy=detail_policy)
        if changed:
            self.selected_cell = None
        return changed

    # {
    #   責務: [create_grid: 表示倍率と論理解像度に合わせた格子線を描く]
    #   処理: [
    #     1: 既存グリッドを消して表示寸法と原点を求める
    #     2: 表示間隔が2画素以上の縦線・横線だけをキャンバスへ描く
    #   ]
    #   引数: []
    #   戻り値: [なし。キャンバス上のgrid項目を更新する]
    # }
    def create_grid(self):
        self.canvas.delete("grid")
        width = max(1, round(self.canvas_width * self.zoom_factor))
        height = max(1, round(self.canvas_height * self.zoom_factor))
        # 画面上で2表示画素未満になる格子線は省き、ポインター座標は正確な比率で換算する。
        viewport_width, viewport_height = self.viewport_size()
        origin_x, origin_y = self.image_origin(
            viewport_width, viewport_height, width, height
        )
        if width / self.num_pixels_x >= 2:
            for x in range(self.num_pixels_x + 1):
                px = origin_x + x * width / self.num_pixels_x
                self.canvas.create_line(
                    px, origin_y, px, origin_y + height,
                    fill="#303945", tags="grid",
                )
        if height / self.num_pixels_y >= 2:
            for y in range(self.num_pixels_y + 1):
                py = origin_y + y * height / self.num_pixels_y
                self.canvas.create_line(
                    origin_x, py, origin_x + width, py,
                    fill="#303945", tags="grid",
                )

    # {
    #   責務: [set_zoom: 表示倍率を許可範囲へ収めて設定する]
    #   処理: [倍率を0.5〜4.0に制限し、表示寸法と画像を更新する]
    #   引数: [factor: 設定する表示倍率]
    #   戻り値: [なし。self.zoom_factorとキャンバス表示を更新する]
    # }
    def set_zoom(self, factor):
        self.zoom_factor = max(0.5, min(4.0, float(factor)))
        self.update_canvas_size()

    # {
    #   責務: [zoom_in: 表示倍率を1.25倍にする]
    #   処理: [現在倍率を拡大率として共通倍率設定へ渡す]
    #   引数: []
    #   戻り値: [なし。上限を超える場合はset_zoomが制限する]
    # }
    def zoom_in(self):
        self.set_zoom(self.zoom_factor * 1.25)

    # {
    #   責務: [zoom_out: 表示倍率を1.25分の1にする]
    #   処理: [現在倍率を縮小率として共通倍率設定へ渡す]
    #   引数: []
    #   戻り値: [なし。下限を下回る場合はset_zoomが制限する]
    # }
    def zoom_out(self):
        self.set_zoom(self.zoom_factor / 1.25)

    # {
    #   責務: [choose_color: 色選択ダイアログから現在色を設定する]
    #   処理: [選択結果がある場合のみ16進色をRGBへ変換して保存する]
    #   引数: []
    #   戻り値: [なし。キャンセル時は現在色を維持する]
    # }
    def choose_color(self):
        color = askcolor()[1]
        if color:
            self.current_color = self.hex_to_rgb(color)

    # {
    #   責務: [rgb_to_hex: RGB色をHTML形式の16進表記へ変換する]
    #   処理: [先頭3成分を2桁ずつの16進数として連結する]
    #   引数: [color: RGBまたはRGBA色]
    #   戻り値: [#rrggbb形式の文字列]
    # }
    def rgb_to_hex(self, color):
        return "#%02x%02x%02x" % tuple(color[:3])

    # {
    #   責務: [set_palette_color: パレット色を選んでブラシへ切り替える]
    #   処理: [現在色を指定値に設定し、ブラシツールを選択する]
    #   引数: [color: パレットから選ばれたRGB色]
    #   戻り値: [なし。色とツール状態を更新する]
    # }
    def set_palette_color(self, color):
        self.current_color = color
        self.set_tool("brush")

    # {
    #   責務: [activate_fill: 塗りつぶしツールを選択する]
    #   処理: [共通ツール切替処理へfillを渡す]
    #   引数: []
    #   戻り値: [なし。ツール状態とボタン表示を更新する]
    # }
    def activate_fill(self):
        self.set_tool("fill")

    # {
    #   責務: [hex_to_rgb: 16進色表記をRGB成分へ変換する]
    #   処理: [先頭の#を除き、2桁ずつ整数として読み取る]
    #   引数: [hex_color: rrggbbまたは#rrggbb形式の色]
    #   戻り値: [赤・緑・青の整数タプル]
    # }
    def hex_to_rgb(self, hex_color):
        hex_color = hex_color.lstrip("#")
        return tuple(int(hex_color[i:i + 2], 16) for i in (0, 2, 4))

    # {
    #   責務: [begin_pan: キャンバスのパン操作開始位置を記録する]
    #   処理: [マウス位置をTkキャンバスのscan基準として記録する]
    #   引数: [event: パン開始位置を持つTkイベント]
    #   戻り値: [なし。キャンバスの走査基準を更新する]
    # }
    def begin_pan(self, event):
        self.canvas.scan_mark(event.x, event.y)

    # {
    #   責務: [pan_canvas: ドラッグ量に応じてキャンバスを移動する]
    #   処理: [Tkキャンバスのscan_dragtoへ現在ポインター位置を渡す]
    #   引数: [event: ドラッグ中のポインター位置を持つTkイベント]
    #   戻り値: [なし。キャンバスの表示位置を更新する]
    # }
    def pan_canvas(self, event):
        self.canvas.scan_dragto(event.x, event.y, gain=1)

    # {
    #   責務: [_child_coordinate: 分割セル内の子画素座標を求める]
    #   処理: [
    #     1: 指定親セルが分割済みか共有APIで確認する
    #     2: 表示位置と論理解像度から子座標を算出し0〜1へ制限する
    #   ]
    #   引数: [x: 親セルの横位置, y: 親セルの縦位置, image_x: 画像内の横座標, image_y: 画像内の縦座標]
    #   戻り値: [子画素のx・y座標。未分割ならNone]
    # }
    def _child_coordinate(self, x, y, image_x, image_y):
        if not self.commands.is_split(x, y):
            return None
        cx = int(2 * (image_x * self.num_pixels_x / self.canvas_width - x))
        cy = int(2 * (image_y * self.num_pixels_y / self.canvas_height - y))
        return min(1, max(0, cx)), min(1, max(0, cy))

    # {
    #   責務: [paint_pixel: ポインター位置に応じて選択・採色・編集を行う]
    #   処理: [
    #     1: 表示領域と倍率から画像内位置・論理セル・子画素を求める
    #     2: 画像外なら終了し、画像内なら選択セルを更新する
    #     3: スポイト・塗りつぶし・消しゴム・ブラシを選択状態に応じて実行する
    #   ]
    #   引数: [event: ポインター座標を持つTkイベント]
    #   戻り値: [なし。選択色または作品データと表示を更新する]
    # }
    def paint_pixel(self, event):
        viewport_width, viewport_height = self.viewport_size()
        shape = (
            round(self.canvas_width * self.zoom_factor),
            round(self.canvas_height * self.zoom_factor),
        )
        origin_x, origin_y = self.image_origin(
            viewport_width, viewport_height, *shape
        )
        image_x = (self.canvas.canvasx(event.x) - origin_x) / self.zoom_factor
        image_y = (self.canvas.canvasy(event.y) - origin_y) / self.zoom_factor
        if not (0 <= image_x < self.canvas_width and 0 <= image_y < self.canvas_height):
            return
        x = int(image_x * self.num_pixels_x / self.canvas_width)
        y = int(image_y * self.num_pixels_y / self.canvas_height)
        self.selected_cell = (x, y)
        child = self._child_coordinate(x, y, image_x, image_y)
        if self.tool == "picker":
            self.current_color = self.commands.sample(x, y, child=child)[:3]
            self.set_tool("brush")
            return
        color = tuple(self.current_color[:3]) + (255,)
        policy = self.current_detail_policy()
        if self.tool == "fill":
            self.perform_edit(self.commands.fill, x, y, color, detail_policy=policy)
            self.set_tool("brush")
        else:
            command = self.commands.erase if self.tool == "eraser" else self.commands.paint
            self.perform_edit(command, x, y, **(
                {"child": child, "detail_policy": policy}
                if self.tool == "eraser"
                else {"color": color, "child": child, "detail_policy": policy}
            ))

    # {
    #   責務: [activate_eyedropper: スポイトツールを選択する]
    #   処理: [共通ツール切替処理へpickerを渡す]
    #   引数: []
    #   戻り値: [なし。ツール状態とボタン表示を更新する]
    # }
    def activate_eyedropper(self):
        self.set_tool("picker")

    # {
    #   責務: [activate_eraser: 消しゴムツールを選択する]
    #   処理: [共通ツール切替処理へeraserを渡す]
    #   引数: []
    #   戻り値: [なし。ツール状態とボタン表示を更新する]
    # }
    def activate_eraser(self):
        self.set_tool("eraser")

    # {
    #   責務: [make_snapshot: Undo/Redo用に現在の作品状態を保存形式で取得する]
    #   処理: [バックエンドのJSON互換データと現在の論理解像度を組にする]
    #   引数: []
    #   戻り値: [作品データ・横解像度・縦解像度のタプル]
    # }
    def make_snapshot(self):
        return self.backend.to_source(), self.num_pixels_x, self.num_pixels_y

    # {
    #   責務: [push_history: 現在状態をUndo履歴へ追加する]
    #   処理: [スナップショットを最大100件保持し、Redo履歴を消去する]
    #   引数: []
    #   戻り値: [なし。Undo/Redo履歴を更新する]
    # }
    def push_history(self):
        self.history.append(self.make_snapshot())
        del self.history[:-100]
        self.future.clear()

    # {
    #   責務: [restore_snapshot: 保存済みスナップショットから作品を復元する]
    #   処理: [
    #     1: 作品データと論理解像度を読み出してレイヤーバックエンドを再生成する
    #     2: 選択セルを解除し、レイヤー一覧と表示を更新する
    #   ]
    #   引数: [snapshot: 作品データと解像度を含むスナップショット]
    #   戻り値: [なし。作品モデルとGUI表示を復元する]
    # }
    def restore_snapshot(self, snapshot):
        source, self.num_pixels_x, self.num_pixels_y = snapshot
        self.backend = LayeredPixelCanvas.from_source(source)
        self.selected_cell = None
        self.refresh_layer_list()
        self.update_canvas_size()

    # {
    #   責務: [undo: 直前の編集を取り消す]
    #   処理: [Undo履歴があれば現状態をRedoへ退避し、直前状態を復元する]
    #   引数: []
    #   戻り値: [なし。履歴がない場合は何もしない]
    # }
    def undo(self):
        if self.history:
            self.future.append(self.make_snapshot())
            self.restore_snapshot(self.history.pop())

    # {
    #   責務: [redo: 取り消した編集を再適用する]
    #   処理: [Redo履歴があれば現状態をUndoへ退避し、次状態を復元する]
    #   引数: []
    #   戻り値: [なし。履歴がない場合は何もしない]
    # }
    def redo(self):
        if self.future:
            self.history.append(self.make_snapshot())
            self.restore_snapshot(self.future.pop())

    # {
    #   責務: [update_canvas: 合成画像を倍率付きでキャンバスへ描画する]
    #   処理: [
    #     1: 最近傍補間で表示倍率の画像を生成する
    #     2: 中央寄せ位置に画像項目を再作成し、グリッドより背面へ置く
    #   ]
    #   引数: []
    #   戻り値: [なし。Tk画像参照を保持して表示を更新する]
    # }
    def update_canvas(self):
        shape = max(1, round(self.canvas_width * self.zoom_factor)), max(1, round(self.canvas_height * self.zoom_factor))
        self.photo = ImageTk.PhotoImage(self.image.resize(shape, Image.Resampling.NEAREST))
        viewport_width, viewport_height = self.viewport_size()
        origin = self.image_origin(viewport_width, viewport_height, *shape)
        self.canvas.delete("artwork")
        self.canvas.create_image(*origin, anchor="nw", image=self.photo, tags="artwork")
        self.canvas.tag_lower("artwork")
        self.canvas.image = self.photo

    # {
    #   責務: [import_image: 画像ファイルを選んで作品へ読み込む]
    #   処理: [
    #     1: 対応画像ファイルの選択ダイアログを開く
    #     2: 選択された場合に共有APIの画像読み込みを編集処理として実行する
    #   ]
    #   引数: []
    #   戻り値: [なし。キャンセル時は作品を変更しない]
    # }
    def import_image(self):
        path = filedialog.askopenfilename(filetypes=[("画像ファイル", "*.png;*.jpg;*.jpeg;*.bmp"), ("すべて", "*.*")])
        if not path:
            return
        self.perform_edit(self.commands.import_image, path)

    # {
    #   責務: [save_project: 現在の作品をJSONプロジェクトとして保存する]
    #   処理: [
    #     1: JSON保存先を選択する
    #     2: 選択された場合に共有APIで保存し、I/O・形式エラーを通知する
    #   ]
    #   引数: []
    #   戻り値: [なし。ダイアログをキャンセルした場合は保存しない]
    # }
    def save_project(self):
        path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON project", "*.json")])
        if path:
            try:
                self.commands.save(Path(path))
            except (OSError, ValueError) as error:
                self.report_error(error)

    # {
    #   責務: [load_project: JSONプロジェクトを検証後に作品へ読み込む]
    #   処理: [
    #     1: 読込先を選び、共有APIで一時的にプロジェクトを読み込む
    #     2: 単一キャンバス形式は背景レイヤーへ包む
    #     3: 失敗時は既存状態を保って通知し、成功後に作品・履歴・表示を置き換える
    #   ]
    #   引数: []
    #   戻り値: [なし。キャンセルまたは検証失敗時は既存作品を維持する]
    # }
    def load_project(self):
        path = filedialog.askopenfilename(filetypes=[("JSON project", "*.json"), ("All files", "*.*")])
        if not path:
            return
        try:
            loaded = PixelCommandAPI.load(Path(path)).canvas
            if isinstance(loaded, PixelCanvas):
                layered = LayeredPixelCanvas(*loaded.resolution)
                layered.layers = {"背景": loaded}
                loaded = layered
        except (OSError, UnicodeError, ValueError, TypeError, KeyError) as error:
            self.report_error(error)
            return
        self.backend = loaded
        self.num_pixels_x, self.num_pixels_y = loaded.resolution
        self.selected_cell = None
        self.history.clear()
        self.future.clear()
        self.refresh_layer_list()
        self.update_canvas_size()

    # {
    #   責務: [save_image: 現在の合成画像をPNGで書き出す]
    #   処理: [
    #     1: PNG保存先を選択する
    #     2: 選択された場合に共有APIで出力し、I/Oエラーを通知する
    #   ]
    #   引数: []
    #   戻り値: [なし。ダイアログをキャンセルした場合は出力しない]
    # }
    def save_image(self):
        path = filedialog.asksaveasfilename(defaultextension=".png", filetypes=[("PNG files", "*.png")])
        if path:
            try:
                self.commands.export_png(path)
            except (OSError, ValueError) as error:
                self.report_error(error)

    # {
    #   責務: [reset_canvas: 確認後に作品と編集履歴をリセットする]
    #   処理: [元に戻せないことを確認し、承認された場合だけ空の作品へ初期化する]
    #   引数: []
    #   戻り値: [なし。拒否・キャンセル時は現在状態を維持する]
    # }
    def reset_canvas(self):
        if not messagebox.askyesno(
            "作品をリセット",
            "すべてのレイヤー・描画・Undo/Redo履歴を消去します。\n"
            "この操作は元に戻せません。リセットしますか？",
            default=messagebox.NO,
        ):
            return
        self.reset_canvas_model()

    # {
    #   責務: [upscale_resolution: 細部処理方針を適用して論理解像度を上げる]
    #   処理: [
    #     1: 現在の保持・破棄方針で共有APIの解像度アップを実行する
    #     2: 成功時に選択セルを解除し、値エラーを利用者へ通知する
    #   ]
    #   引数: []
    #   戻り値: [なし。作品が変化した場合は編集履歴と表示を更新する]
    # }
    def upscale_resolution(self):
        try:
            changed = self.perform_edit(
                self.commands.upscale, detail_policy=self.current_detail_policy()
            )
            if changed:
                self.selected_cell = None
        except ValueError as error:
            self.report_error(error)

    # {
    #   責務: [split_selected_cell: 選択中の論理セルを4分割する]
    #   処理: [選択セルがある場合に共通編集処理で分割コマンドを実行する]
    #   引数: []
    #   戻り値: [なし。選択セルがない場合は何もしない]
    # }
    def split_selected_cell(self):
        if self.selected_cell is not None:
            self.perform_edit(self.commands.split, *self.selected_cell)

    # {
    #   責務: [collapse_selected_cell: 選択中の分割セルを折りたたむ]
    #   処理: [選択セルがある場合に細部方針を付けて共通編集処理を実行する]
    #   引数: []
    #   戻り値: [なし。選択セルがない場合は何もしない]
    # }
    def collapse_selected_cell(self):
        if self.selected_cell is not None:
            self.perform_edit(
                self.commands.collapse, *self.selected_cell,
                detail_policy=self.current_detail_policy(),
            )

    # {
    #   責務: [discard_selected_detail: 選択中のセルが保持する細部を破棄する]
    #   処理: [選択セルがある場合に細部破棄を共通編集処理から実行する]
    #   引数: []
    #   戻り値: [なし。選択セルがない場合は何もしない]
    # }
    def discard_selected_detail(self):
        if self.selected_cell is not None:
            self.perform_edit(self.commands.discard_detail, *self.selected_cell)

    # {
    #   責務: [change_size: 利用者入力に基づいて作品の論理解像度を変更する]
    #   処理: [
    #     1: 横幅と高さを上限付きで入力させ、キャンセル時は終了する
    #     2: 細部破棄を選んだ場合は全レイヤーへの適用を確認する
    #     3: 共通解像度変更処理を実行し、値エラーを通知する
    #   ]
    #   引数: []
    #   戻り値: [なし。確認拒否や入力キャンセル時は作品を変更しない]
    # }
    def change_size(self):
        width = simpledialog.askinteger("論理解像度", "横のセル数", initialvalue=self.backend.width,
                                        minvalue=1, maxvalue=PixelCanvas.MAX_DIMENSION)
        if width is None:
            return
        height = simpledialog.askinteger("論理解像度", "縦のセル数", initialvalue=self.backend.height,
                                         minvalue=1, maxvalue=PixelCanvas.MAX_DIMENSION)
        if height is None:
            return
        policy = self.current_detail_policy()
        if policy == "discard" and not messagebox.askyesno("細部を破棄", "全レイヤーの細部を新しい解像度に統合しますか？"):
            return
        try:
            self.resize_logical_canvas(width, height, policy)
        except ValueError as error:
            self.report_error(error)

    # {
    #   責務: [change_canvas_size: 表示キャンバスの幅と高さを変更する]
    #   処理: [幅・高さを個別に入力させ、揃った場合に表示寸法だけを更新する]
    #   引数: []
    #   戻り値: [なし。作品モデルと編集履歴は変更しない]
    # }
    def change_canvas_size(self):
        width = simpledialog.askinteger("キャンバス幅", "表示の横幅（ピクセル）", minvalue=100, maxvalue=5000)
        if width is None:
            return
        height = simpledialog.askinteger("キャンバス高さ", "表示の縦幅（ピクセル）", minvalue=100, maxvalue=5000)
        if height is not None:
            self.set_display_size(width, height)


# {
#   責務: [main: GUIエディターを起動するかヘッドレス起動確認を実行する]
#   処理: [
#     1: --smoke-test指定時はTkインタープリターとバックエンドの最低限の処理を確認する
#     2: 通常時はTkウィンドウを作成してPixelEditorを実行する
#   ]
#   引数: []
#   戻り値: [正常終了コード0]
# }
def main():
    import sys

    if sys.argv[1:] == ["--smoke-test"]:
        # GUIウィンドウを作らず、同梱Tclとバックエンドの基本処理を確認する。
        interpreter = tk.Tcl()
        assert interpreter.eval("expr {2 + 2}") == "4"
        model = LayeredPixelCanvas(2)
        model.paint(0, 0, (255, 0, 0, 255))
        assert model.sample(0, 0) == (255, 0, 0, 255)
        return 0
    root = tk.Tk()
    editor = PixelEditor(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
