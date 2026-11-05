"""Keyboard cell cursor: pure position logic and geometry helpers (no Tk, no document data)."""


# {
#   責務: [CanvasCursor: キーボードで動かすセル位置と子セルのモードを保持する]
#   フィールド: [x, y: 論理セルの座標, child: 子セルのモード中なら(cx, cy)、そうでなければNone]
# }
class CanvasCursor:
    # {
    #   責務: [__init__: 指定位置に子セルのモードなしでカーソルを置く]
    #   処理: [座標を保存し、子セルのモードを解除する]
    #   引数: [x: 横の論理セル, y: 縦の論理セル]
    #   戻り値: [なし]
    # }
    def __init__(self, x=0, y=0):
        self.x = x
        self.y = y
        self.child = None

    # {
    #   責務: [place: 親セルの位置へ置き、子セルのモードを解除する]
    #   処理: [座標を更新して子セルのモードをNoneにする]
    #   引数: [x: 横の論理セル, y: 縦の論理セル]
    #   戻り値: [なし]
    # }
    def place(self, x, y):
        self.x = x
        self.y = y
        self.child = None

    # {
    #   責務: [place_keeping_child: 親セルの位置だけを合わせ、子セルのモードは保つ]
    #   処理: [座標を更新し、子セルの状態は変えない]
    #   引数: [x: 横の論理セル, y: 縦の論理セル]
    #   戻り値: [なし]
    # }
    def place_keeping_child(self, x, y):
        self.x = x
        self.y = y

    # {
    #   責務: [move: 矢印キー1回分カーソルを動かす]
    #   処理: [
    #     1: 子セルのモード中は2x2の範囲内で動かす
    #     2: 範囲の外へ出るときは子セルのモードを抜けて隣の親セルへ移る
    #     3: 親セルは端で止め、回り込まない
    #   ]
    #   引数: [dx: 横の移動量, dy: 縦の移動量, width: 横のセル数, height: 縦のセル数]
    #   戻り値: [位置または子セルが変わったら真]
    # }
    def move(self, dx, dy, width, height):
        before = (self.x, self.y, self.child)
        if self.child is not None:
            cx, cy = self.child[0] + dx, self.child[1] + dy
            if 0 <= cx <= 1 and 0 <= cy <= 1:
                self.child = (cx, cy)
                return True
            self.child = None
        self.x = min(max(self.x + dx, 0), width - 1)
        self.y = min(max(self.y + dy, 0), height - 1)
        return (self.x, self.y, self.child) != before

    # {
    #   責務: [enter_child: 分割済みのセルで子セルのモードに入る]
    #   処理: [分割済みなら子セルの左上から入り、そうでなければ何もしない]
    #   引数: [is_split: (x, y)が分割済みかを返す関数]
    #   戻り値: [入れたら真]
    # }
    def enter_child(self, is_split):
        if self.child is None and is_split(self.x, self.y):
            self.child = (0, 0)
            return True
        return False

    # {
    #   責務: [leave_child: 子セルのモードを抜けて親セルへ戻る]
    #   処理: [子セルのモード中なら解除する]
    #   引数: []
    #   戻り値: [抜けたら真]
    # }
    def leave_child(self):
        if self.child is None:
            return False
        self.child = None
        return True

    # {
    #   責務: [clamp: 解像度や分割状態が変わった後に範囲内へ補正する]
    #   処理: [
    #     1: 座標を現在のセル数の範囲へ収める
    #     2: 親セルが分割済みでなくなった場合は子セルのモードを解除する
    #   ]
    #   引数: [width: 横のセル数, height: 縦のセル数, is_split: 分割済みかを返す関数]
    #   戻り値: [なし]
    # }
    def clamp(self, width, height, is_split):
        self.x = min(max(self.x, 0), width - 1)
        self.y = min(max(self.y, 0), height - 1)
        if self.child is not None and not is_split(self.x, self.y):
            self.child = None


# {
#   責務: [cell_bounds: セルまたは子セルの表示上の外枠を求める]
#   処理: [
#     1: 画像全体をセル数で等分したセルの左上と大きさを求める
#     2: 子セルが指定されたら、そのセルの半分の大きさの区画に絞る
#   ]
#   引数: [origin: 画像の左上, size: 画像の表示寸法, cells: 縦横のセル数, x, y: セル, child: 子セルまたはNone]
#   戻り値: [左, 上, 右, 下の組]
# }
def cell_bounds(origin, size, cells, x, y, child=None):
    cell_w = size[0] / cells[0]
    cell_h = size[1] / cells[1]
    left = origin[0] + x * cell_w
    top = origin[1] + y * cell_h
    if child is None:
        return left, top, left + cell_w, top + cell_h
    half_w, half_h = cell_w / 2, cell_h / 2
    left += child[0] * half_w
    top += child[1] * half_h
    return left, top, left + half_w, top + half_h


# {
#   責務: [scroll_offset: 対象が表示範囲に入るための新しい左端（または上端）を求める]
#   処理: [
#     1: 対象が表示範囲に収まっていればスクロールしない
#     2: はみ出す側へ最小量だけ動かし、対象が表示範囲より大きければ先頭を合わせる
#   ]
#   引数: [low: 対象の始端, high: 対象の終端, view_low: 表示範囲の始端, view_high: 表示範囲の終端]
#   戻り値: [新しい表示範囲の始端。動かす必要がなければNone]
# }
def scroll_offset(low, high, view_low, view_high):
    if low >= view_low and high <= view_high:
        return None
    if high - low >= view_high - view_low or low < view_low:
        return low
    return high - (view_high - view_low)
