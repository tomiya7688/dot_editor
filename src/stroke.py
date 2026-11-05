"""Keyboard stroke state and path interpolation (pure logic, no Tk, no document data)."""


# {
#   責務: [line_cells: 2つのセルの間を直線で結ぶセルの列を求める]
#   処理: [
#     1: ブレゼンハムの方法で始点から終点まで1セルずつ進む
#     2: 始点と終点を含め、範囲外には出ない
#   ]
#   引数: [start: 始点(x, y), end: 終点(x, y)]
#   戻り値: [始点から終点までのセルのリスト]
# }
def line_cells(start, end):
    x, y = start
    dx, dy = abs(end[0] - x), abs(end[1] - y)
    step_x = 1 if end[0] > x else -1
    step_y = 1 if end[1] > y else -1
    error = dx - dy
    cells = [(x, y)]
    while (x, y) != end:
        doubled = 2 * error
        if doubled > -dy:
            error -= dy
            x += step_x
        if doubled < dx:
            error += dx
            y += step_y
        cells.append((x, y))
    return cells


# {
#   責務: [StrokeSession: Spaceを押している間の描画の開始・延長・終了を管理する]
#   フィールド: [active: ストローク中か, last: 最後に描いたセル]
# }
class StrokeSession:
    # {
    #   責務: [__init__: 何も押していない状態で作る]
    #   処理: [ストロークなし、最後のセルなしにする]
    #   引数: []
    #   戻り値: [なし]
    # }
    def __init__(self):
        self.active = False
        self.last = None

    # {
    #   責務: [begin: ストロークを始め、最初に描くセルを返す]
    #   処理: [ストローク中にして最後のセルを記録する]
    #   引数: [cell: 現在のセル]
    #   戻り値: [描くセルのリスト（1件）]
    # }
    def begin(self, cell):
        self.active = True
        self.last = cell
        return [cell]

    # {
    #   責務: [extend: 新しいセルまで経路を補間し、まだ描いていないセルを返す]
    #   処理: [
    #     1: ストローク中でなければ何も返さない
    #     2: 最後のセルから新しいセルまでの直線を求め、最後のセルを除く
    #   ]
    #   引数: [cell: カーソルが移動した先のセル]
    #   戻り値: [新たに描くセルのリスト]
    # }
    def extend(self, cell):
        if not self.active or cell == self.last:
            return []
        cells = line_cells(self.last, cell)[1:]
        self.last = cell
        return cells

    # {
    #   責務: [end: ストロークを終了または取り消す]
    #   処理: [ストローク中なら解除して最後のセルを忘れる]
    #   引数: []
    #   戻り値: [ストローク中だったら真]
    # }
    def end(self):
        was_active = self.active
        self.active = False
        self.last = None
        return was_active
