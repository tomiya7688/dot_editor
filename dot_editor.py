import tkinter as tk
import json
from tkinter.colorchooser import askcolor
from PIL import Image, ImageDraw, ImageTk
import tkinter.simpledialog
from tkinter import filedialog
from pixel_backend import PixelCanvas

class PixelEditor:
    def __init__(self, master):
        self.master = master
        self.master.title("ドット絵エディタ")
        self.master.configure(bg="#0b0f14")

        # 初期設定
        self.canvas_width = 640  # 初期キャンバスの幅（640px）
        self.canvas_height = 640  # 初期キャンバスの高さ（640px）
        self.num_pixels_x = 2  # 初期ドット数（横方向）
        self.num_pixels_y = 2  # 初期ドット数（縦方向）

        self.pixel_size = self.canvas_width // self.num_pixels_x  # ドットのサイズ（初期設定）

        # current_colorの初期設定（デフォルトは黒）
        self.current_color = (255, 255, 255)
        self.refined_cells = set()
        self.child_pixels = {}
        self.selected_cell = None
        self.tool = "brush"
        self.palette_colors = [(255, 255, 255), (0, 0, 0), (255, 80, 80), (255, 190, 70), (255, 240, 100), (90, 210, 130), (80, 180, 255), (170, 110, 255)]
        self.history = []
        self.future = []
        self.backend = PixelCanvas(self.num_pixels_x)
        self.zoom_factor = 1.0
        self.display_pixel_size = self.pixel_size

        # キャンバスの作成
        self.canvas = tk.Canvas(self.master, bg="#111820", highlightthickness=1, highlightbackground="#3b4654")
        self.canvas.grid(row=0, column=0, rowspan=5)  # キャンバスをgridの左側に配置

        # ボタンを縦に並べるためのフレーム
        button_frame = tk.Frame(self.master, bg="#0b0f14")
        button_frame.grid(row=0, column=1, padx=10, pady=10)  # ボタンを右側に配置

        # 色選択ボタン
        self.color_button = tk.Button(button_frame, text="色を選ぶ", command=self.choose_color)
        self.color_button.grid(row=0, column=0, padx=5, pady=5)

        # ドットサイズ設定ボタン
        self.size_button = tk.Button(button_frame, text="サイズ変更", command=self.change_size)
        self.size_button.grid(row=1, column=0, padx=5, pady=5)

        # キャンバスサイズ設定ボタン
        self.canvas_size_button = tk.Button(button_frame, text="キャンバスサイズ変更", command=self.change_canvas_size)
        self.canvas_size_button.grid(row=2, column=0, padx=5, pady=5)

        # 保存ボタン
        self.save_button = tk.Button(button_frame, text="保存", command=self.save_image)
        self.save_button.grid(row=3, column=0, padx=5, pady=5)
        self.save_project_button = tk.Button(button_frame, text="プロジェクト保存", command=self.save_project)
        self.save_project_button.grid(row=16, column=0, padx=5, pady=5)
        self.load_project_button = tk.Button(button_frame, text="プロジェクト読込", command=self.load_project)
        self.load_project_button.grid(row=17, column=0, padx=5, pady=5)

        # リセットボタン
        self.reset_button = tk.Button(button_frame, text="リセット", command=self.reset_canvas)
        self.reset_button.grid(row=4, column=0, padx=5, pady=5)

        self.upscale_button = tk.Button(button_frame, text="解像度アップ", command=self.upscale_resolution)
        self.upscale_button.grid(row=5, column=0, padx=5, pady=5)

        self.split_button = tk.Button(button_frame, text="選択セルを4分割", command=self.split_selected_cell)
        self.split_button.grid(row=6, column=0, padx=5, pady=5)

        self.undo_button = tk.Button(button_frame, text="元に戻す", command=self.undo)
        self.undo_button.grid(row=7, column=0, padx=5, pady=5)
        self.redo_button = tk.Button(button_frame, text="やり直す", command=self.redo)
        self.redo_button.grid(row=8, column=0, padx=5, pady=5)
        self.eyedropper_button = tk.Button(button_frame, text="スポイト", command=self.activate_eyedropper)
        self.eyedropper_button.grid(row=9, column=0, padx=5, pady=5)
        self.eraser_button = tk.Button(button_frame, text="消しゴム", command=self.activate_eraser)
        self.eraser_button.grid(row=10, column=0, padx=5, pady=5)
        self.import_button = tk.Button(button_frame, text="画像を読み込む", command=self.import_image)
        self.import_button.grid(row=11, column=0, padx=5, pady=5)
        self.fill_button = tk.Button(button_frame, text="塗りつぶし", command=self.activate_fill)
        self.fill_button.grid(row=12, column=0, padx=5, pady=5)
        self.zoom_out_button = tk.Button(button_frame, text="表示ズーム−", command=self.zoom_out)
        self.zoom_out_button.grid(row=14, column=0, padx=5, pady=5)
        self.zoom_in_button = tk.Button(button_frame, text="表示ズーム＋", command=self.zoom_in)
        self.zoom_in_button.grid(row=15, column=0, padx=5, pady=5)
        palette_frame = tk.Frame(button_frame, bg="#0b0f14")
        palette_frame.grid(row=13, column=0, padx=5, pady=5)
        self.palette_buttons = []
        for index, palette_color in enumerate(self.palette_colors):
            palette_button = tk.Button(palette_frame, width=2, height=1, bg=self.rgb_to_hex(palette_color), command=lambda color=palette_color: self.set_palette_color(color))
            palette_button.grid(row=index // 4, column=index % 4, padx=1, pady=1)
            self.palette_buttons.append(palette_button)

        for button in (
            self.color_button, self.size_button, self.canvas_size_button,
            self.save_button, self.save_project_button, self.load_project_button, self.reset_button, self.upscale_button,
            self.split_button, self.undo_button, self.redo_button,
            self.eyedropper_button, self.eraser_button, self.import_button, self.fill_button,
        ):
            button.configure(bg="#17212b", fg="#f0f3f6", activebackground="#263747", activeforeground="#ffffff", relief="flat")

        # 初期キャンバスサイズを設定
        self.update_canvas_size()

        # ドット絵を描く
        self.canvas.bind("<Button-1>", self.paint_pixel)  # 左クリックで色を塗る
        self.master.bind("<Control-z>", lambda event: self.undo())
        self.master.bind("<Control-y>", lambda event: self.redo())
        self.canvas.bind("<B1-Motion>", self.paint_pixel)  # クリックしたまま移動した場合にも色を塗る
        self.canvas.bind("<ButtonPress-2>", self.begin_pan)
        self.canvas.bind("<B2-Motion>", self.pan_canvas)

    def update_canvas_size(self, preserve_image=False):
        """キャンバスのサイズを更新"""
        # ドットサイズの計算（キャンバス幅をドット数で割って計算）
        self.pixel_size = self.canvas_width // self.num_pixels_x  # ドットサイズはキャンバス幅 / ドット数（横）
        self.display_pixel_size = max(1, round(self.pixel_size * self.zoom_factor))
        
        # キャンバスのサイズを設定
        display_width = round(self.canvas_width * self.zoom_factor)
        display_height = round(self.canvas_height * self.zoom_factor)
        self.canvas.config(width=min(self.canvas_width, display_width), height=min(self.canvas_height, display_height))
        self.canvas.configure(scrollregion=(0, 0, display_width, display_height))

        old_image = getattr(self, "image", None)

        # 新しい画像を作成
        self.refined_cells.clear()
        self.child_pixels.clear()
        try:
            self.image = Image.new("RGBA", (self.canvas_width, self.canvas_height), (0, 0, 0, 0))
            if preserve_image and old_image is not None:
                resized = old_image.resize((self.canvas_width, self.canvas_height), Image.Resampling.NEAREST)
                self.image.paste(resized)
            self.draw = ImageDraw.Draw(self.image)
        except ValueError:
            print("無効なサイズが設定されました。")
            return

        # グリッドを再描画
        self.create_grid()
        self.update_canvas()

    def create_grid(self):
        """ズーム倍率に合わせてグリッドを描画"""
        self.canvas.delete("all")
        width = round(self.canvas_width * self.zoom_factor)
        height = round(self.canvas_height * self.zoom_factor)
        for x in range(0, width + 1, self.display_pixel_size):
            self.canvas.create_line(x, 0, x, height, fill="#303945")
        for y in range(0, height + 1, self.display_pixel_size):
            self.canvas.create_line(0, y, width, y, fill="#303945")

    def set_zoom(self, factor):
        self.zoom_factor = max(0.5, min(4.0, float(factor)))
        self.display_pixel_size = max(1, round(self.pixel_size * self.zoom_factor))
        self.canvas.config(
            width=round(self.canvas_width * self.zoom_factor),
            height=round(self.canvas_height * self.zoom_factor),
        )
        self.create_grid()
        self.update_canvas()

    def zoom_in(self):
        self.set_zoom(self.zoom_factor * 1.25)

    def zoom_out(self):
        self.set_zoom(self.zoom_factor / 1.25)

    def choose_color(self):
        """カラーパレットを開いて色を選択"""
        color = askcolor()[1]  # askcolorはRGBタプルを返す
        if color:
            self.current_color = self.hex_to_rgb(color)

    def rgb_to_hex(self, color):
        return "#%02x%02x%02x" % tuple(color)

    def set_palette_color(self, color):
        self.current_color = color
        self.tool = "brush"

    def activate_fill(self):
        self.tool = "fill"

    def hex_to_rgb(self, hex_color):
        """16進数の色コードをRGBタプルに変換"""
        hex_color = hex_color.lstrip('#')
        return tuple(int(hex_color[i:i + 2], 16) for i in (0, 2, 4))

    def begin_pan(self, event):
        self.canvas.scan_mark(event.x, event.y)

    def pan_canvas(self, event):
        self.canvas.scan_dragto(event.x, event.y, gain=1)

    def paint_pixel(self, event):
        """セルまたは細分化済みの子セルを塗る"""
        canvas_x = self.canvas.canvasx(event.x)
        canvas_y = self.canvas.canvasy(event.y)
        image_x = min(self.canvas_width - 1, max(0, int(canvas_x / self.zoom_factor)))
        image_y = min(self.canvas_height - 1, max(0, int(canvas_y / self.zoom_factor)))
        x = image_x // self.pixel_size
        y = image_y // self.pixel_size
        if not (0 <= x < self.num_pixels_x and 0 <= y < self.num_pixels_y):
            return
        if self.tool == "picker":
            self.current_color = self.image.getpixel((image_x, image_y))
            self.tool = "brush"
            return
        self.push_history()
        self.selected_cell = (x, y)
        paint_color = (0, 0, 0, 0) if self.tool == "eraser" else self.current_color
        if (x, y) in self.refined_cells:
            half = max(1, self.pixel_size // 2)
            child_x = min(1, max(0, (image_x - x * self.pixel_size) // half))
            child_y = min(1, max(0, (image_y - y * self.pixel_size) // half))
            self.child_pixels[(x, y)][child_y][child_x] = paint_color
            left = x * self.pixel_size + child_x * half
            top = y * self.pixel_size + child_y * half
            self.draw.rectangle([left, top, left + half, top + half], fill=paint_color)
        else:
            self.draw.rectangle([x * self.pixel_size, y * self.pixel_size,
                                 (x + 1) * self.pixel_size, (y + 1) * self.pixel_size],
                                fill=paint_color)
        self.update_canvas()

    def activate_eyedropper(self):
        """次のクリック位置の色を取得する"""
        self.tool = "picker"

    def activate_eraser(self):
        """白色で描く消しゴムを有効にする"""
        self.current_color = (255, 255, 255)
        self.tool = "eraser"

    def push_history(self):
        """現在の編集状態を履歴へ保存する"""
        children = {key: [row[:] for row in value] for key, value in self.child_pixels.items()}
        self.history.append((self.image.copy(), self.num_pixels_x, self.num_pixels_y, set(self.refined_cells), children))
        if len(self.history) > 100:
            self.history.pop(0)
        self.future.clear()

    def restore_snapshot(self, snapshot):
        self.image, self.num_pixels_x, self.num_pixels_y, refined, children = snapshot
        self.refined_cells = set(refined)
        self.child_pixels = {key: [row[:] for row in value] for key, value in children.items()}
        self.pixel_size = self.canvas_width // self.num_pixels_x
        display_width = round(self.canvas_width * self.zoom_factor)
        display_height = round(self.canvas_height * self.zoom_factor)
        self.canvas.config(width=min(self.canvas_width, display_width), height=min(self.canvas_height, display_height))
        self.canvas.configure(scrollregion=(0, 0, display_width, display_height))
        self.draw = ImageDraw.Draw(self.image)
        self.create_grid()
        self.update_canvas()

    def undo(self):
        if not self.history:
            return
        current = (self.image.copy(), self.num_pixels_x, self.num_pixels_y, set(self.refined_cells), {key: [row[:] for row in value] for key, value in self.child_pixels.items()})
        self.future.append(current)
        self.restore_snapshot(self.history.pop())

    def redo(self):
        if not self.future:
            return
        current = (self.image.copy(), self.num_pixels_x, self.num_pixels_y, set(self.refined_cells), {key: [row[:] for row in value] for key, value in self.child_pixels.items()})
        self.history.append(current)
        self.restore_snapshot(self.future.pop())

    def update_canvas(self):
        """キャンバスへ最近傍ズーム表示する"""
        display_size = (
            round(self.canvas_width * self.zoom_factor),
            round(self.canvas_height * self.zoom_factor),
        )
        display_image = self.image.resize(display_size, Image.Resampling.NEAREST)
        self.photo = ImageTk.PhotoImage(display_image)
        self.canvas.create_image(0, 0, anchor="nw", image=self.photo)
        self.canvas.image = self.photo

    def import_image(self):
        """画像をキャンバス内へ最近傍で収めて読み込む"""
        file_path = filedialog.askopenfilename(filetypes=[("画像ファイル", "*.png;*.jpg;*.jpeg;*.bmp"), ("すべて", "*.*")])
        if not file_path:
            return
        try:
            source = Image.open(file_path).convert("RGBA")
        except (OSError, ValueError):
            return
        self.push_history()
        fitted = Image.new("RGBA", (self.canvas_width, self.canvas_height), (0, 0, 0, 0))
        ratio = min(self.canvas_width / source.width, self.canvas_height / source.height)
        size = (max(1, round(source.width * ratio)), max(1, round(source.height * ratio)))
        resized = source.resize(size, Image.Resampling.NEAREST)
        fitted.alpha_composite(resized, ((self.canvas_width - size[0]) // 2, (self.canvas_height - size[1]) // 2))
        self.backend.import_image(source)
        self.image = self.backend.image.copy()
        self.draw = ImageDraw.Draw(self.image)
        self.update_canvas()

    def save_project(self):
        """バックエンド互換のJSONプロジェクトを保存する"""
        file_path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON project", "*.json"), ("All files", "*.*")],
        )
        if not file_path:
            return
        self.backend.image = self.image.copy()
        self.backend.size = self.num_pixels_x
        Path(file_path).write_text(
            json.dumps(self.backend.to_source(), ensure_ascii=False, indent=2) + "\\n",
            encoding="utf-8",
        )

    def load_project(self):
        """バックエンド互換のJSONプロジェクトを読み込む"""
        file_path = filedialog.askopenfilename(
            filetypes=[("JSON project", "*.json"), ("All files", "*.*")]
        )
        if not file_path:
            return
        try:
            source = json.loads(Path(file_path).read_text(encoding="utf-8"))
            self.backend = PixelCanvas.from_source(source)
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return
        self.num_pixels_x = self.backend.size
        self.num_pixels_y = self.backend.size
        self.image = self.backend.image.resize(
            (self.canvas_width, self.canvas_height),
            Image.Resampling.NEAREST,
        )
        self.draw = ImageDraw.Draw(self.image)
        self.refined_cells.clear()
        self.child_pixels.clear()
        self.history.clear()
        self.future.clear()
        self.pixel_size = self.canvas_width // self.num_pixels_x
        self.display_pixel_size = max(1, round(self.pixel_size * self.zoom_factor))
        self.create_grid()
        self.update_canvas()

    def save_image(self):
        """ドット絵を画像として保存"""
        # エクスプローラーを開き、保存先を選ばせる
        file_path = filedialog.asksaveasfilename(defaultextension=".png",
                                                 filetypes=[("PNG files", "*.png"),
                                                          ("JPEG files", "*.jpg"),
                                                          ("All files", "*.*")])
        if file_path:
            self.backend.image = self.image.copy()
            self.backend.size = self.num_pixels_x
            self.backend.save_png(file_path)

    def reset_canvas(self):
        """キャンバスをリセット"""
        self.update_canvas_size()

    def upscale_resolution(self):
        """ドット数を倍にし、既存の絵を最近傍拡大で引き継ぐ"""
        next_size = self.num_pixels_x * 2
        if next_size > 256:
            return
        self.backend.image = self.image.copy()
        self.backend.size = self.num_pixels_x
        if not self.backend.upscale():
            return
        self.num_pixels_x = self.backend.size
        self.num_pixels_y = self.backend.size
        self.image = self.backend.image.copy()
        self.draw = ImageDraw.Draw(self.image)
        self.pixel_size = self.canvas_width // self.num_pixels_x
        self.refined_cells.clear()
        self.child_pixels.clear()
        self.create_grid()
        self.update_canvas()

    def split_selected_cell(self):
        """選択中の親セルを2x2の子セルへ細分化する"""
        if self.selected_cell is None:
            return
        x, y = self.selected_cell
        if (x, y) in self.refined_cells:
            return
        base_color = self.image.getpixel((min(self.canvas_width - 1, x * self.pixel_size + self.pixel_size // 2), min(self.canvas_height - 1, y * self.pixel_size + self.pixel_size // 2)))
        self.push_history()
        self.refined_cells.add((x, y))
        self.child_pixels[(x, y)] = [[base_color, base_color], [base_color, base_color]]
        half = max(1, self.pixel_size // 2)
        for child_y in range(2):
            for child_x in range(2):
                left = x * self.pixel_size + child_x * half
                top = y * self.pixel_size + child_y * half
                self.draw.rectangle([left, top, left + half, top + half], fill=base_color)
        self.update_canvas()

    def change_size(self):
        """ドットサイズを変更"""
        size = tk.simpledialog.askinteger("サイズ変更", "サイズを選択してください（4, 8, 16, 32 など）",
                                          minvalue=2, maxvalue=256)
        if size not in PixelCanvas.SUPPORTED_SIZES:
            return
        if size:
            self.num_pixels_x = size  # ドット数を変更（横方向）
            self.num_pixels_y = size  # ドット数を変更（縦方向）
            self.update_canvas_size()

    def change_canvas_size(self):
        """キャンバスの大きさを変更"""
        while True:
            width = tk.simpledialog.askinteger("キャンバス幅", "キャンバスの横幅（ピクセル）を指定",
                                              minvalue=100, maxvalue=5000)
            height = tk.simpledialog.askinteger("キャンバス高さ", "キャンバスの縦幅（ピクセル）を指定",
                                               minvalue=100, maxvalue=5000)
            # 入力が無効でないか確認
            if width and height and width > 0 and height > 0:
                self.canvas_width = width
                self.canvas_height = height
                break
            else:
                print("無効なサイズが設定されました。")

        self.update_canvas_size()

if __name__ == "__main__":
    root = tk.Tk()
    editor = PixelEditor(root)
    root.mainloop()
