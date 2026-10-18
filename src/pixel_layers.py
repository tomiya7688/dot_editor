from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image

from pixel_backend import CanvasState, ChildCoordinate, DetailPolicy, PixelCanvas
from resolution_field import resolution

LayerState = tuple[list[tuple[str, CanvasState, bool]], str]


# {
#   責務: [LayeredPixelCanvas: レイヤー構成・表示合成・作品単位の編集履歴を管理する]
#   フィールド: [
#     layers: 下層から上層の順に画素キャンバスを保持する名前付き辞書,
#     layer_visibility: レイヤー名ごとの表示状態,
#     active_layer: 編集対象のレイヤー名,
#     _history: Undo用の全レイヤー状態,
#     _future: Redo用の全レイヤー状態
#   ]
# }
class LayeredPixelCanvas:
    """Layer-aware composition and atomic document-wide resolution changes."""

    HISTORY_LIMIT = 50
    MAX_LAYERS = 256

    # {
    #   責務: [__init__: 背景レイヤーを持つ空の作品を初期化する]
    #   処理: [指定解像度の背景を作り、表示状態・選択・作品履歴を初期化する]
    #   引数: [size: 横幅, height: 縦幅。省略時は横幅と同じ]
    #   戻り値: [なし。背景が選択された作品になる]
    # }
    def __init__(self, size: int = 16, height: int | None = None) -> None:
        self.layers: dict[str, PixelCanvas] = {"背景": PixelCanvas(size, height)}
        self.layer_visibility: dict[str, bool] = {"背景": True}
        self.active_layer = "背景"
        self._history: list[LayerState] = []
        self._future: list[LayerState] = []

    # {
    #   責務: [size: 旧API向けに作品の横幅を返す]
    #   処理: [widthプロパティへ委譲する]
    #   引数: []
    #   戻り値: [論理画素の横幅]
    # }
    @property
    def size(self) -> int:
        return self.width

    # {
    #   責務: [width: 作品の論理画素の横幅を返す]
    #   処理: [選択中レイヤーの横幅を取得する]
    #   引数: []
    #   戻り値: [全レイヤーで共通の横幅]
    # }
    @property
    def width(self) -> int:
        return self.active.width

    # {
    #   責務: [height: 作品の論理画素の縦幅を返す]
    #   処理: [選択中レイヤーの縦幅を取得する]
    #   引数: []
    #   戻り値: [全レイヤーで共通の縦幅]
    # }
    @property
    def height(self) -> int:
        return self.active.height

    # {
    #   責務: [resolution: 作品の現在の論理解像度を返す]
    #   処理: [選択中レイヤーの解像度を取得する]
    #   引数: []
    #   戻り値: [全レイヤーで共通の横幅と縦幅]
    # }
    @property
    def resolution(self) -> tuple[int, int]:
        return self.active.resolution

    # {
    #   責務: [active: 現在の編集対象キャンバスを返す]
    #   処理: [選択中の名前でレイヤー辞書を参照する]
    #   引数: []
    #   戻り値: [選択中のPixelCanvas]
    # }
    @property
    def active(self) -> PixelCanvas:
        return self.layers[self.active_layer]

    # {
    #   責務: [has_refinements: 展開済みの細分画素が作品内にあるか調べる]
    #   処理: [非表示を含む全レイヤーの展開状態を確認する]
    #   引数: []
    #   戻り値: [いずれかのレイヤーに展開済みセルがあればTrue]
    # }
    @property
    def has_refinements(self) -> bool:
        return any(layer.has_refinements for layer in self.layers.values())

    # {
    #   責務: [has_detail: 保持中の細部が作品内にあるか調べる]
    #   処理: [非表示を含む全レイヤーの細部状態を確認する]
    #   引数: []
    #   戻り値: [いずれかのレイヤーに細部があればTrue]
    # }
    @property
    def has_detail(self) -> bool:
        return any(layer.has_detail for layer in self.layers.values())

    # {
    #   責務: [retained_resolution: 全レイヤーが保持する解像度の上限を要約する]
    #   処理: [各層の保持解像度から横幅と縦幅それぞれの最大値を求める]
    #   引数: []
    #   戻り値: [保持解像度の横幅・縦幅の最大値]
    # }
    @property
    def retained_resolution(self) -> tuple[int, int]:
        shapes = [layer.retained_resolution for layer in self.layers.values()]
        return max(w for w, _ in shapes), max(h for _, h in shapes)

    # {
    #   責務: [native_resolution: 作品の分割表示に必要な自然な出力解像度を返す]
    #   処理: [非表示を含むいずれかの層に展開済みセルがあれば論理解像度を縦横2倍する]
    #   引数: []
    #   戻り値: [自然な出力の横幅と縦幅]
    # }
    @property
    def native_resolution(self) -> tuple[int, int]:
        return (self.width * 2, self.height * 2) if self.has_refinements else self.resolution

    # {
    #   責務: [native_size: 旧API向けに自然な出力の横幅を返す]
    #   処理: [native_resolutionから横幅を取得する]
    #   引数: []
    #   戻り値: [自然な出力の横幅]
    # }
    @property
    def native_size(self) -> int:
        return self.native_resolution[0]

    # {
    #   責務: [_state: 全レイヤーと選択状態のスナップショットを作る]
    #   処理: [各層の名前・画素状態・可視状態を合成順に列挙し、選択名と組み合わせる]
    #   引数: []
    #   戻り値: [レイヤー状態の一覧と選択名の組]
    # }
    def _state(self) -> LayerState:
        entries = [
            (name, layer._state(), self.layer_visibility.get(name, True))
            for name, layer in self.layers.items()
        ]
        return entries, self.active_layer

    # {
    #   責務: [_record: 作品編集前の状態をUndo履歴へ記録する]
    #   処理: [状態を追加し、履歴上限を適用してRedo履歴を消去する]
    #   引数: [state: 記録する編集前の作品状態]
    #   戻り値: [なし。作品履歴が更新される]
    # }
    def _record(self, state: LayerState) -> None:
        self._history.append(state)
        del self._history[:-self.HISTORY_LIMIT]
        self._future.clear()

    # {
    #   責務: [_restore: 作品履歴から全レイヤーと選択を復元する]
    #   処理: [各層のキャンバスを再構成し、順序・可視状態・選択名を戻す]
    #   引数: [state: 復元する作品状態]
    #   戻り値: [なし。現在のレイヤー構成が置き換わる]
    # }
    def _restore(self, state: LayerState) -> None:
        entries, active = state
        # 各層を作り直し、作品履歴に保存した順序と可視状態を復元する。
        self.layers = {}
        self.layer_visibility = {}
        for name, canvas_state, visible in entries:
            canvas = PixelCanvas(*canvas_state[0])
            canvas._restore_state(canvas_state)
            self.layers[name] = canvas
            self.layer_visibility[name] = visible
        self.active_layer = active

    # {
    #   責務: [_edit_active: 選択中レイヤーの編集を作品単位の履歴へ接続する]
    #   処理: [編集前状態を保存して操作を呼び出し、結果が真の場合だけ作品履歴へ記録する]
    #   引数: [operation: 呼び出す編集メソッド名, args: 位置引数, kwargs: キーワード引数]
    #   戻り値: [委譲した編集操作の戻り値]
    # }
    def _edit_active(self, operation: str, *args: Any, **kwargs: Any) -> Any:
        # 変更なしの操作は作品履歴とRedoを維持するため、結果を見て記録する。
        before = self._state()
        result = getattr(self.active, operation)(*args, **kwargs)
        if result:
            self._record(before)
        return result

    # {
    #   責務: [add_layer: 新しい空のレイヤーを最上層へ追加して選択する]
    #   処理: [名前と層数上限を検証し、現在解像度の層を追加して編集前状態を記録する]
    #   引数: [name: 前後の空白を除いて使用する新レイヤー名]
    #   戻り値: [なし。追加した層が表示・選択される]
    # }
    def add_layer(self, name: str) -> None:
        # 空名・重複・上限超過を拒否してからレイヤー構成を変更する。
        if not isinstance(name, str) or not name.strip():
            raise ValueError("layer name must not be empty")
        clean = name.strip()
        if clean in self.layers:
            raise ValueError(f"layer already exists: {clean}")
        if len(self.layers) >= self.MAX_LAYERS:
            raise ValueError("too many layers")
        # 全層で解像度を揃え、新しい層を合成順の末尾へ追加する。
        before = self._state()
        self.layers[clean] = PixelCanvas(*self.resolution)
        self.layer_visibility[clean] = True
        self.active_layer = clean
        self._record(before)

    # {
    #   責務: [select_layer: 既存レイヤーを編集対象にする]
    #   処理: [指定名の存在を確認して選択名を変更する。選択だけでは履歴を記録しない]
    #   引数: [name: 選択する既存レイヤー名]
    #   戻り値: [なし。編集対象が切り替わる]
    # }
    def select_layer(self, name: str) -> None:
        if name not in self.layers:
            raise KeyError(name)
        self.active_layer = name

    # {
    #   責務: [remove_layer: 少なくとも1層を残して対象レイヤーを削除する]
    #   処理: [対象と残存層数を検証し、削除・選択の補正・作品履歴の記録を行う]
    #   引数: [name: 削除名。省略時は選択中のレイヤー]
    #   戻り値: [なし。対象レイヤーが削除される]
    # }
    def remove_layer(self, name: str | None = None) -> None:
        target = self.active_layer if name is None else name
        if target not in self.layers:
            raise KeyError(target)
        if len(self.layers) == 1:
            raise ValueError("at least one layer is required")
        # 選択中の層を削除した場合も、編集先が必ず存在する状態を保つ。
        before = self._state()
        del self.layers[target]
        self.layer_visibility.pop(target, None)
        if target == self.active_layer:
            self.active_layer = next(iter(self.layers))
        self._record(before)

    # {
    #   責務: [is_layer_visible: 対象レイヤーの可視状態を返す]
    #   処理: [対象の存在を確認し、可視状態が未登録なら表示として扱う]
    #   引数: [name: 確認する名前。省略時は選択中のレイヤー]
    #   戻り値: [表示ならTrue、非表示ならFalse]
    # }
    def is_layer_visible(self, name: str | None = None) -> bool:
        target = self.active_layer if name is None else name
        if target not in self.layers:
            raise KeyError(target)
        return self.layer_visibility.get(target, True)

    # {
    #   責務: [set_layer_visibility: 対象レイヤーの表示・非表示を切り替える]
    #   処理: [真偽値と対象を検証し、可視状態が変わる場合だけ変更前状態を記録する]
    #   引数: [visible: 新しい可視状態, name: 対象名。省略時は選択中のレイヤー]
    #   戻り値: [状態が変わればTrue、既に同じ状態ならFalse]
    # }
    def set_layer_visibility(self, visible: bool, name: str | None = None) -> bool:
        if type(visible) is not bool:
            raise ValueError("layer visibility must be a boolean")
        target = self.active_layer if name is None else name
        if target not in self.layers:
            raise KeyError(target)
        if self.layer_visibility.get(target, True) == visible:
            return False
        # 表示変更も描画編集と同じ作品履歴で戻せるようにする。
        before = self._state()
        self.layer_visibility[target] = visible
        self._record(before)
        return True

    # {
    #   責務: [rename_layer: 合成順と選択状態を維持してレイヤー名を変更する]
    #   処理: [名前を検証し、画素と可視状態の辞書キーを同じ位置で置き換えて記録する]
    #   引数: [new_name: 前後の空白を除いて使用する変更後の名前, name: 対象名。省略時は選択中の層]
    #   戻り値: [変更した場合はTrue、同じ名前ならFalse]
    # }
    def rename_layer(self, new_name: str, name: str | None = None) -> bool:
        target = self.active_layer if name is None else name
        if target not in self.layers:
            raise KeyError(target)
        if not isinstance(new_name, str) or not new_name.strip():
            raise ValueError("layer name must not be empty")
        clean = new_name.strip()
        if clean == target:
            return False
        if clean in self.layers:
            raise ValueError(f"layer already exists: {clean}")
        before = self._state()
        # 辞書への削除・再追加では合成順が変わるため、元の位置で名前だけを置き換える。
        self.layers = {
            clean if layer_name == target else layer_name: layer
            for layer_name, layer in self.layers.items()
        }
        self.layer_visibility = {
            clean if layer_name == target else layer_name: visible
            for layer_name, visible in self.layer_visibility.items()
        }
        if target == self.active_layer:
            self.active_layer = clean
        self._record(before)
        return True

    # {
    #   責務: [move_layer: 対象レイヤーを合成順で1段上下へ移動する]
    #   処理: [方向と対象を検証し、範囲内なら順序を入れ替えて作品履歴へ記録する]
    #   引数: [direction: upで上層側、downで下層側, name: 対象名。省略時は選択中の層]
    #   戻り値: [移動した場合はTrue、既に端にある場合はFalse]
    # }
    def move_layer(self, direction: str, name: str | None = None) -> bool:
        """Move one layer in compositing order; the last item is topmost."""
        if direction not in ("up", "down"):
            raise ValueError("direction must be 'up' or 'down'")
        target = self.active_layer if name is None else name
        if target not in self.layers:
            raise KeyError(target)
        entries = list(self.layers.items())
        index = next(i for i, (layer_name, _) in enumerate(entries) if layer_name == target)
        destination = index + (1 if direction == "up" else -1)
        if destination < 0 or destination >= len(entries):
            return False
        # 辞書の末尾ほど上に合成されるため、並び順を移動先へ組み替える。
        before = self._state()
        entry = entries.pop(index)
        entries.insert(destination, entry)
        self.layers = dict(entries)
        self._record(before)
        return True

    # {
    #   責務: [is_split: 選択中レイヤーの画素が分割済みか調べる]
    #   処理: [座標を選択中キャンバスの分割判定へ渡す]
    #   引数: [x: 横座標, y: 縦座標]
    #   戻り値: [分割済みならTrue]
    # }
    def is_split(self, x: int, y: int) -> bool:
        return self.active.is_split(x, y)

    # {
    #   責務: [split_cell: 選択中レイヤーの画素を4分割する]
    #   処理: [分割を実行し、変更があれば作品単位の履歴へ記録する]
    #   引数: [x: 横座標, y: 縦座標]
    #   戻り値: [分割状態が変わればTrue]
    # }
    def split_cell(self, x: int, y: int) -> bool:
        return self._edit_active("split_cell", x, y)

    # {
    #   責務: [split_region: 選択中レイヤーの矩形領域をまとめて4分割する]
    #   処理: [領域分割を委譲し、変更があれば1回の作品履歴へ記録する]
    #   引数: [x: 左上の横座標, y: 左上の縦座標, width: 領域幅, height: 領域高さ]
    #   戻り値: [新たに分割した画素数]
    # }
    def split_region(self, x: int, y: int, width: int, height: int) -> int:
        # 選択中の層だけを編集し、戻り値が正なら作品履歴へ1回記録する。
        return self._edit_active("split_region", x, y, width, height)

    # {
    #   責務: [collapse_cell: 選択中レイヤーの分割画素を折りたたむ]
    #   処理: [細部の破棄指定を添えて委譲し、変更があれば作品履歴へ記録する]
    #   引数: [x: 横座標, y: 縦座標, discard_detail: 保持細部も破棄するか]
    #   戻り値: [状態が変わればTrue]
    # }
    def collapse_cell(self, x: int, y: int, discard_detail: bool = False) -> bool:
        return self._edit_active("collapse_cell", x, y, discard_detail=discard_detail)

    # {
    #   責務: [has_detail_at: 選択中レイヤーの指定画素に保持細部があるか調べる]
    #   処理: [座標を選択中キャンバスの細部判定へ渡す]
    #   引数: [x: 横座標, y: 縦座標]
    #   戻り値: [保持細部があればTrue]
    # }
    def has_detail_at(self, x: int, y: int) -> bool:
        return self.active.has_detail_at(x, y)

    # {
    #   責務: [paint: 選択中レイヤーの親画素または子画素へ描画する]
    #   処理: [描画条件を委譲し、変更があれば作品履歴へ記録する]
    #   引数: [x: 横座標, y: 縦座標, color: 描画色, erase: 透明色で消すか, child: 任意の子座標, detail_policy: 細部方針]
    #   戻り値: [画素状態が変わればTrue]
    # }
    def paint(self, x: int, y: int, color: tuple[int, ...], erase: bool = False,
              child: ChildCoordinate | None = None, detail_policy: DetailPolicy = "preserve") -> bool:
        return self._edit_active("paint", x, y, color, erase=erase, child=child, detail_policy=detail_policy)

    # {
    #   責務: [sample: 選択中レイヤーの親画素または子画素の色を取得する]
    #   処理: [座標と任意の子画素指定を選択中キャンバスへ渡す]
    #   引数: [x: 横座標, y: 縦座標, child: 任意の子画素座標]
    #   戻り値: [取得したRGBA色]
    # }
    def sample(self, x: int, y: int, child: ChildCoordinate | None = None) -> tuple[int, int, int, int]:
        return self.active.sample(x, y, child)

    # {
    #   責務: [fill: 選択中レイヤーの連結した同色領域を塗りつぶす]
    #   処理: [塗りつぶし条件を委譲し、変更があれば作品履歴へ記録する]
    #   引数: [x: 起点の横座標, y: 起点の縦座標, color: 塗りつぶし色, erase: 透明色で消すか, detail_policy: 細部方針]
    #   戻り値: [変更した画素数]
    # }
    def fill(self, x: int, y: int, color: tuple[int, ...], erase: bool = False,
             detail_policy: DetailPolicy = "preserve") -> int:
        return self._edit_active("fill", x, y, color, erase=erase, detail_policy=detail_policy)

    # {
    #   責務: [discard_detail: 選択中レイヤーの矩形領域から細部を破棄する]
    #   処理: [領域の検証と細部破棄を委譲し、変更があれば作品履歴へ記録する]
    #   引数: [x: 左上の横座標, y: 左上の縦座標, width: 領域幅, height: 領域高さ]
    #   戻り値: [細部を破棄した画素数]
    # }
    def discard_detail(self, x: int, y: int, width: int = 1, height: int = 1) -> int:
        return self._edit_active("discard_detail", x, y, width, height)

    # {
    #   責務: [set_resolution: 全レイヤーの論理解像度を一括変更する]
    #   処理: [
    #     1: 解像度と細部方針を検証し、変更不要なら終了する,
    #     2: 全層の変更結果を別キャンバス上で作る,
    #     3: 全層の処理成功後に作品を置き換え、履歴へ記録する
    #   ]
    #   引数: [width: 新しい横幅, height: 新しい縦幅, detail_policy: 細部の保持・破棄方針]
    #   戻り値: [解像度または細部状態が変わればTrue]
    # }
    def set_resolution(self, width: int, height: int | None = None,
                       detail_policy: DetailPolicy = "preserve") -> bool:
        target = resolution(width, height)
        PixelCanvas._validate_detail_policy(detail_policy)
        if target == self.resolution and detail_policy == "preserve":
            return False
        # Stage every layer first. Validation/allocation failure leaves the
        # original layers, document history and selection unchanged.
        candidates = {}
        for name, layer in self.layers.items():
            candidate = PixelCanvas(*layer.resolution)
            candidate._restore_state(layer._state())
            candidate.set_resolution(*target, detail_policy=detail_policy)
            candidates[name] = candidate
        # 全層が揃ってから作品を置換し、一部の層だけ解像度が変わる状態を防ぐ。
        before = self._state()
        self.layers = candidates
        self._record(before)
        return True

    # {
    #   責務: [resize: 旧APIとの互換性を保って全レイヤーの解像度を変更する]
    #   処理: [引数をset_resolutionへ委譲する]
    #   引数: [target: 新しい横幅, height: 新しい縦幅, detail_policy: 細部方針]
    #   戻り値: [解像度または細部状態が変わればTrue]
    # }
    def resize(self, target: int, height: int | None = None,
               detail_policy: DetailPolicy = "preserve") -> bool:
        return self.set_resolution(target, height, detail_policy)

    # {
    #   責務: [upscale: 全レイヤーの論理解像度を縦横2倍にする]
    #   処理: [2倍の寸法を検証し、上限内なら全層の解像度変更へ委譲する]
    #   引数: []
    #   戻り値: [変更した場合はTrue、寸法が上限を超える場合はFalse]
    # }
    def upscale(self) -> bool:
        try:
            target = resolution(self.width * 2, self.height * 2)
        except ValueError:
            return False
        return self.set_resolution(*target)

    # {
    #   責務: [undo: 全レイヤーと選択状態を直前の作品履歴へ戻す]
    #   処理: [現在状態をRedo用に保存し、直前のUndo状態を復元する]
    #   引数: []
    #   戻り値: [復元した場合はTrue、履歴がなければFalse]
    # }
    def undo(self) -> bool:
        if not self._history:
            return False
        self._future.append(self._state())
        self._restore(self._history.pop())
        return True

    # {
    #   責務: [redo: Undoで戻した全レイヤーと選択状態を再適用する]
    #   処理: [現在状態を上限付きUndo履歴へ保存し、Redo状態を復元する]
    #   引数: []
    #   戻り値: [復元した場合はTrue、履歴がなければFalse]
    # }
    def redo(self) -> bool:
        if not self._future:
            return False
        self._history.append(self._state())
        del self._history[:-self.HISTORY_LIMIT]
        self._restore(self._future.pop())
        return True

    # {
    #   責務: [composite: 表示中のレイヤーを自然な出力解像度で合成する]
    #   処理: [透明画像を作り、表示中の各層を下から順にアルファ合成する]
    #   引数: []
    #   戻り値: [分割表示を含む合成済みRGBA画像]
    # }
    def composite(self) -> Image.Image:
        target = self.native_resolution
        result = Image.new("RGBA", target)
        # 辞書の挿入順が下層から上層の合成順となり、非表示の層は描画しない。
        for name, layer in self.layers.items():
            if self.layer_visibility.get(name, True):
                result.alpha_composite(layer.render(target))
        return result

    # {
    #   責務: [render_resolution: 各レイヤーの保持細部を指定解像度で合成する]
    #   処理: [出力寸法を検証し、表示中の各層を同じ寸法で描画して順に合成する]
    #   引数: [width: 出力横幅, height: 出力縦幅。省略時は横幅と同じ]
    #   戻り値: [指定解像度の合成済みRGBA画像]
    # }
    def render_resolution(self, width: int, height: int | None = None) -> Image.Image:
        target = resolution(width, height)
        result = Image.new("RGBA", target)
        for name, layer in self.layers.items():
            if self.layer_visibility.get(name, True):
                result.alpha_composite(layer.render_resolution(*target))
        return result

    # {
    #   責務: [save_png: 表示中のレイヤーを合成してPNGへ保存する]
    #   処理: [
    #     1: 出力サイズの指定が重複していないか確認する,
    #     2: 指定解像度の合成画像、または自然な合成画像を必要に応じて最近傍拡大する,
    #     3: 合成画像をPNG形式で保存する
    #   ]
    #   引数: [path: 保存先, export_size: 任意の正方形サイズ, output_resolution: 任意の横幅・縦幅]
    #   戻り値: [なし。指定の重複・縮小指定・保存失敗時は例外になる]
    # }
    def save_png(self, path: str | Path, export_size: int | None = None,
                 *, output_resolution: tuple[int, int] | None = None) -> None:
        if export_size is not None and output_resolution is not None:
            raise ValueError("choose export size or output resolution, not both")
        # 明示した解像度では保持フィールドを直接描画し、省略時は分割表示を含む画像を使う。
        if output_resolution is not None:
            output = self.render_resolution(*output_resolution)
        else:
            output = self.composite()
            if export_size is not None:
                target = resolution(export_size)
                if export_size < max(output.size):
                    raise ValueError("export size cannot be smaller than native canvas size")
                output = output.resize(target, Image.Resampling.NEAREST)
        output.save(path, "PNG")

    # {
    #   責務: [to_source: レイヤー構成をversion 2のJSON互換辞書へ変換する]
    #   処理: [解像度・選択名と、全層の名前・可視状態・画素状態を合成順に書き出す]
    #   引数: []
    #   戻り値: [非表示層も含む保存用の作品辞書。編集履歴は含めない]
    # }
    def to_source(self) -> dict[str, Any]:
        return {
            "version": 2, "canvas_size": self.width, "resolution": list(self.resolution),
            "active_layer": self.active_layer,
            "layers": [
                {
                    "name": name,
                    "visible": self.layer_visibility.get(name, True),
                    "source": canvas.to_source(),
                }
                for name, canvas in self.layers.items()
            ],
        }

    # {
    #   責務: [from_source: version 1または2の辞書からレイヤー付き作品を復元する]
    #   処理: [
    #     1: 形式と層数を検証する,
    #     2: 各層の名前・可視状態・画素状態を検証し、共通解像度を確認する,
    #     3: 作品の寸法と選択名を確認して、履歴の空の作品へ復元する
    #   ]
    #   引数: [cls: LayeredPixelCanvas型, source: 復元元の作品辞書]
    #   戻り値: [復元したLayeredPixelCanvas。不正形式は例外になる]
    # }
    @classmethod
    def from_source(cls, source: dict[str, Any]) -> LayeredPixelCanvas:
        if not isinstance(source, dict):
            raise ValueError("layered project must be a JSON object")
        version = source.get("version", 1)
        if type(version) is not int or version not in (1, 2):
            raise ValueError("unsupported layered project version")
        entries = source.get("layers")
        if not isinstance(entries, list) or not (1 <= len(entries) <= cls.MAX_LAYERS):
            raise ValueError("layer source must contain 1..256 layers")
        # 検証済みの層を一時辞書へ集め、異なる解像度や重複名を持つ作品を拒否する。
        layers: dict[str, PixelCanvas] = {}
        visibility: dict[str, bool] = {}
        expected = None
        for entry in entries:
            if not isinstance(entry, dict):
                raise ValueError("invalid layer entry")
            name = entry.get("name")
            if not isinstance(name, str) or not name.strip():
                raise ValueError("layer name must not be empty")
            if name in layers:
                raise ValueError(f"duplicate layer name: {name}")
            visible = entry.get("visible", True)
            if type(visible) is not bool:
                raise ValueError("layer visible must be a boolean")
            layer = PixelCanvas.from_source(entry.get("source"))
            if expected is None:
                expected = layer.resolution
            elif layer.resolution != expected:
                raise ValueError("all layers must use the same canvas size and resolution")
            layers[name] = layer
            visibility[name] = visible
        # ルートの寸法と選択名を各層に照合し、整合した作品だけを返す。
        declared = source.get("canvas_size")
        if declared is not None and (type(declared) is not int or declared != expected[0]):
            raise ValueError("layered canvas_size does not match layer size")
        if version == 2:
            shape = source.get("resolution")
            if not isinstance(shape, list) or len(shape) != 2 or resolution(*shape) != expected:
                raise ValueError("layered resolution does not match layer resolution")
        active = source.get("active_layer", next(iter(layers)))
        if not isinstance(active, str) or active not in layers:
            raise ValueError("active_layer must reference an existing layer")
        model = cls(*expected)
        model.layers = layers
        model.layer_visibility = visibility
        model.active_layer = active
        return model
