import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog
from tkinter.colorchooser import askcolor

from PIL import Image, ImageTk

from pixel_backend import PixelCanvas
from pixel_commands import PixelCommandAPI
from pixel_layers import LayeredPixelCanvas
from resolution_field import resolution


class PixelEditor:
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
        self.canvas = tk.Canvas(master, bg="#111820", highlightthickness=1, highlightbackground="#3b4654")
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.canvas.bind("<Configure>", self.on_canvas_configure, add="+")
        self.canvas.bind("<Control-MouseWheel>", self.zoom_with_wheel)
        self.build_sidebar()
        self.update_canvas_size()
        self.refresh_layer_list()
        self.canvas.bind("<Button-1>", self.paint_pixel)
        self.canvas.bind("<B1-Motion>", self.paint_pixel)
        self.master.bind("<Control-z>", lambda event: self.undo())
        self.master.bind("<Control-y>", lambda event: self.redo())
        self.canvas.bind("<ButtonPress-2>", self.begin_pan)
        self.canvas.bind("<B2-Motion>", self.pan_canvas)

    def build_sidebar(self):
        # Scrollable so the resolution/detail controls do not hide file actions.
        frame = tk.Frame(self.master, bg="#0b0f14")
        frame.grid(row=0, column=1, padx=10, pady=10, sticky="ns")
        viewport = tk.Canvas(frame, bg="#0b0f14", width=240, height=640, highlightthickness=0)
        scrollbar = tk.Scrollbar(frame, orient="vertical", command=viewport.yview)
        viewport.configure(yscrollcommand=scrollbar.set)
        viewport.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        sidebar = tk.Frame(viewport, bg="#0b0f14")
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
            button.grid(row=index // 4, column=index % 4, padx=1, pady=1)
            self.palette_buttons.append(button)
        layer_group = self.create_toolbar_group(sidebar, "レイヤー")
        self.layer_list = tk.Listbox(layer_group, height=4, width=20, bg="#111820", fg="#f0f3f6",
                                    selectbackground="#3f6685", highlightthickness=0, exportselection=False)
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
            tk.Radiobutton(view_group, text=title, variable=self.detail_policy, value=value,
                           bg="#101820", fg="#f0f3f6", selectcolor="#17212b", anchor="w").pack(fill="x")
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

    def create_toolbar_group(self, parent, title):
        group = tk.LabelFrame(parent, text=title, bg="#101820", fg="#cbd5df", bd=1,
                              relief="solid", padx=2, pady=4)
        group.pack(fill="x", pady=(0, 8))
        return group

    def make_toolbar_button(self, parent, text, command, use_pack=True):
        button = tk.Button(parent, text=text, command=command, bg="#17212b", fg="#f0f3f6",
                           activebackground="#263747", activeforeground="#ffffff", relief="flat")
        if use_pack:
            button.pack(fill="x", padx=6, pady=2)
        return button

    def set_tool(self, tool):
        if tool not in {"brush", "fill", "eraser", "picker"}:
            raise ValueError(f"unknown tool: {tool}")
        self.tool = tool
        self.refresh_tool_state()

    def refresh_tool_state(self):
        names = {"brush": "ブラシ", "fill": "塗りつぶし", "eraser": "消しゴム", "picker": "スポイト"}
        for name, button in getattr(self, "tool_buttons", {}).items():
            selected = name == self.tool
            button.configure(bg="#3f6685" if selected else "#17212b", relief="sunken" if selected else "flat")
        label = getattr(self, "tool_status_label", None)
        if label is not None:
            label.configure(text=f"現在: {names[self.tool]}")

    def current_detail_policy(self):
        variable = getattr(self, "detail_policy", None)
        return variable.get() if variable is not None else "preserve"

    @property
    def commands(self):
        """Return the shared command surface for the current backend."""
        return PixelCommandAPI(self.backend)

    def report_error(self, error):
        if hasattr(self, "master"):
            messagebox.showerror("操作できません", str(error), parent=self.master)

    def refresh_composite(self):
        self.image = self.backend.composite().resize((self.canvas_width, self.canvas_height), Image.Resampling.NEAREST)

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

    def _finish_edit(self, before):
        self.history.append(before)
        del self.history[:-100]
        self.future.clear()
        self.num_pixels_x, self.num_pixels_y = self.backend.resolution
        self.refresh_layer_list()
        self.update_canvas_size()

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

    def remove_layer(self):
        before = self.make_snapshot()
        try:
            changed = self.commands.remove_layer()
        except (KeyError, ValueError) as error:
            self.report_error(error)
            return
        if changed:
            self._finish_edit(before)

    def rename_layer(self):
        current = self.backend.active_layer
        new_name = simpledialog.askstring(
            "レイヤー名称変更", "新しいレイヤー名", initialvalue=current, parent=self.master
        )
        if new_name is not None:
            self.perform_edit(self.commands.rename_layer, new_name)

    def move_layer(self, direction):
        self.perform_edit(self.commands.move_layer, direction)

    def toggle_layer_visibility(self):
        current = self.backend.is_layer_visible()
        self.perform_edit(self.commands.set_layer_visibility, not current)

    def select_layer(self, _event=None):
        selection = self.layer_list.curselection()
        if selection:
            self.commands.select_layer(self._layer_names[selection[0]])
            self.refresh_composite()
            self.create_grid()
            self.update_canvas()

    @staticmethod
    def image_origin(viewport_width, viewport_height, image_width, image_height):
        """Center an image when it fits; keep its origin at zero when it overflows."""
        return (
            max(0, (viewport_width - image_width) // 2),
            max(0, (viewport_height - image_height) // 2),
        )

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

    def zoom_with_wheel(self, event):
        if event.delta > 0:
            self.zoom_in()
        elif event.delta < 0:
            self.zoom_out()
        return "break"

    def update_canvas_size(self):
        """Only update display geometry; never reset the document or its history."""
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

    def set_display_size(self, width, height):
        if type(width) is not int or type(height) is not int or width <= 0 or height <= 0:
            raise ValueError("display size must be positive integers")
        self.canvas_width, self.canvas_height = width, height
        self.update_canvas_size()

    def reset_canvas_model(self, size=None, height=None):
        shape = self.backend.resolution if size is None else resolution(size, height)
        self.backend = PixelCommandAPI.new(*shape, layered=True).canvas
        self.num_pixels_x, self.num_pixels_y = shape
        self.selected_cell = None
        self.history.clear()
        self.future.clear()
        self.refresh_layer_list()
        self.update_canvas_size()

    def resize_logical_canvas(self, size, height=None, detail_policy="preserve"):
        target = resolution(size, height)
        changed = self.perform_edit(self.commands.set_resolution, *target, detail_policy=detail_policy)
        if changed:
            self.selected_cell = None
        return changed

    def create_grid(self):
        self.canvas.delete("grid")
        width = max(1, round(self.canvas_width * self.zoom_factor))
        height = max(1, round(self.canvas_height * self.zoom_factor))
        # Skip subpixel-spaced lines; pointer mapping still uses exact ratios.
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

    def set_zoom(self, factor):
        self.zoom_factor = max(0.5, min(4.0, float(factor)))
        self.update_canvas_size()

    def zoom_in(self):
        self.set_zoom(self.zoom_factor * 1.25)

    def zoom_out(self):
        self.set_zoom(self.zoom_factor / 1.25)

    def choose_color(self):
        color = askcolor()[1]
        if color:
            self.current_color = self.hex_to_rgb(color)

    def rgb_to_hex(self, color):
        return "#%02x%02x%02x" % tuple(color[:3])

    def set_palette_color(self, color):
        self.current_color = color
        self.set_tool("brush")

    def activate_fill(self):
        self.set_tool("fill")

    def hex_to_rgb(self, hex_color):
        hex_color = hex_color.lstrip("#")
        return tuple(int(hex_color[i:i + 2], 16) for i in (0, 2, 4))

    def begin_pan(self, event):
        self.canvas.scan_mark(event.x, event.y)

    def pan_canvas(self, event):
        self.canvas.scan_dragto(event.x, event.y, gain=1)

    def _child_coordinate(self, x, y, image_x, image_y):
        if not self.commands.is_split(x, y):
            return None
        cx = int(2 * (image_x * self.num_pixels_x / self.canvas_width - x))
        cy = int(2 * (image_y * self.num_pixels_y / self.canvas_height - y))
        return min(1, max(0, cx)), min(1, max(0, cy))

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

    def activate_eyedropper(self):
        self.set_tool("picker")

    def activate_eraser(self):
        self.set_tool("eraser")

    def make_snapshot(self):
        return self.backend.to_source(), self.num_pixels_x, self.num_pixels_y

    def push_history(self):
        self.history.append(self.make_snapshot())
        del self.history[:-100]
        self.future.clear()

    def restore_snapshot(self, snapshot):
        source, self.num_pixels_x, self.num_pixels_y = snapshot
        self.backend = LayeredPixelCanvas.from_source(source)
        self.selected_cell = None
        self.refresh_layer_list()
        self.update_canvas_size()

    def undo(self):
        if self.history:
            self.future.append(self.make_snapshot())
            self.restore_snapshot(self.history.pop())

    def redo(self):
        if self.future:
            self.history.append(self.make_snapshot())
            self.restore_snapshot(self.future.pop())

    def update_canvas(self):
        shape = max(1, round(self.canvas_width * self.zoom_factor)), max(1, round(self.canvas_height * self.zoom_factor))
        self.photo = ImageTk.PhotoImage(self.image.resize(shape, Image.Resampling.NEAREST))
        viewport_width, viewport_height = self.viewport_size()
        origin = self.image_origin(viewport_width, viewport_height, *shape)
        self.canvas.delete("artwork")
        self.canvas.create_image(*origin, anchor="nw", image=self.photo, tags="artwork")
        self.canvas.tag_lower("artwork")
        self.canvas.image = self.photo

    def import_image(self):
        path = filedialog.askopenfilename(filetypes=[("画像ファイル", "*.png;*.jpg;*.jpeg;*.bmp"), ("すべて", "*.*")])
        if not path:
            return
        self.perform_edit(self.commands.import_image, path)

    def save_project(self):
        path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON project", "*.json")])
        if path:
            try:
                self.commands.save(Path(path))
            except (OSError, ValueError) as error:
                self.report_error(error)

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

    def save_image(self):
        path = filedialog.asksaveasfilename(defaultextension=".png", filetypes=[("PNG files", "*.png")])
        if path:
            try:
                self.commands.export_png(path)
            except (OSError, ValueError) as error:
                self.report_error(error)

    def reset_canvas(self):
        self.reset_canvas_model()

    def upscale_resolution(self):
        try:
            changed = self.perform_edit(
                self.commands.upscale, detail_policy=self.current_detail_policy()
            )
            if changed:
                self.selected_cell = None
        except ValueError as error:
            self.report_error(error)

    def split_selected_cell(self):
        if self.selected_cell is not None:
            self.perform_edit(self.commands.split, *self.selected_cell)

    def collapse_selected_cell(self):
        if self.selected_cell is not None:
            self.perform_edit(
                self.commands.collapse, *self.selected_cell,
                detail_policy=self.current_detail_policy(),
            )

    def discard_selected_detail(self):
        if self.selected_cell is not None:
            self.perform_edit(self.commands.discard_detail, *self.selected_cell)

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

    def change_canvas_size(self):
        width = simpledialog.askinteger("キャンバス幅", "表示の横幅（ピクセル）", minvalue=100, maxvalue=5000)
        if width is None:
            return
        height = simpledialog.askinteger("キャンバス高さ", "表示の縦幅（ピクセル）", minvalue=100, maxvalue=5000)
        if height is not None:
            self.set_display_size(width, height)


if __name__ == "__main__":
    root = tk.Tk()
    editor = PixelEditor(root)
    root.mainloop()
