from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from pixel_backend import ChildCoordinate, Color, DetailPolicy, PixelCanvas
from pixel_layers import LayeredPixelCanvas

Canvas = PixelCanvas | LayeredPixelCanvas


# {
#   責務: [canvas_from_source: JSON由来の辞書から適切な作品モデルを復元する]
#   処理: [
#     1: ルートが辞書であることを検証する
#     2: layersキーの有無に応じて単一またはレイヤー付きモデルを復元する
#   ]
#   引数: [source: 読み込んだプロジェクトのルート値]
#   戻り値: [復元したPixelCanvasまたはLayeredPixelCanvas]
# }
def canvas_from_source(source: object) -> Canvas:
    if not isinstance(source, dict):
        raise ValueError("project root must be a JSON object")
    if "layers" in source:
        return LayeredPixelCanvas.from_source(source)
    return PixelCanvas.from_source(source)


# {
#   責務: [unique_json_object: JSONオブジェクト内の重複キーを拒否する]
#   処理: [
#     1: キーと値の組を辞書へ順に格納する
#     2: 既に現れたキーはValueErrorにする
#   ]
#   引数: [pairs: JSONパーサーが読み取ったキーと値の組]
#   戻り値: [重複のない辞書]
# }
def unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """Reject ambiguous JSON instead of silently using the last value."""
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


# {
#   責務: [reject_json_constant: JSON標準外の数値定数を拒否する]
#   処理: [NaNやInfinityなどの定数名を含むValueErrorを送出する]
#   引数: [value: JSONパーサーが検出した定数名]
#   戻り値: [なし。常にValueErrorになる]
# }
def reject_json_constant(value: str) -> None:
    raise ValueError(f"non-standard JSON constant: {value}")


# {
#   責務: [validate_json_depth: JSON値のコンテナ入れ子深度を制限する]
#   処理: [
#     1: 明示的なスタックで辞書・配列を反復走査する
#     2: 深さ128を超えるコンテナをValueErrorにする
#   ]
#   引数: [source: 深度を検査するJSON由来の値]
#   戻り値: [なし。上限を超えた場合はValueErrorになる]
# }
def validate_json_depth(source: object) -> None:
    """Apply the same 128-container limit across Python JSON implementations."""
    pending = [(source, 1)]
    while pending:
        value, depth = pending.pop()
        if not isinstance(value, (dict, list)):
            continue
        if depth > 128:
            raise ValueError("JSON nesting is too deep (maximum 128 containers)")
        children = value.values() if isinstance(value, dict) else value
        pending.extend((child, depth + 1) for child in children)


# {
#   責務: [load_project: JSONプロジェクトを厳密に検証して作品モデルへ読み込む]
#   処理: [
#     1: UTF-8 JSONを重複キー・非標準定数拒否付きで解析する
#     2: コンテナ深度を検証し、作品モデルを復元する
#     3: 読込・解析エラーを文脈付きValueErrorへ変換する
#   ]
#   引数: [path: 読み込むJSONプロジェクトのパス]
#   戻り値: [復元したPixelCanvasまたはLayeredPixelCanvas]
# }
def load_project(path: str | Path) -> Canvas:
    target = Path(path)
    try:
        source = json.loads(
            target.read_text(encoding="utf-8"),
            object_pairs_hook=unique_json_object,
            parse_constant=reject_json_constant,
        )
        validate_json_depth(source)
    except RecursionError as error:
        raise ValueError("failed to read project: JSON nesting is too deep") from error
    except (OSError, UnicodeError, ValueError) as error:
        raise ValueError(f"failed to read project: {error}") from error
    return canvas_from_source(source)


# {
#   責務: [save_project: 作品をJSONファイルへ原子的に保存する]
#   処理: [
#     1: 作品データを整形済みUTF-8 JSONへ変換する
#     2: 同じディレクトリの一時ファイルへ書き込み同期する
#     3: 既存ファイルの権限を保ち、一時ファイルを置換して後始末する
#   ]
#   引数: [canvas: 保存する作品モデル, path: 保存先ファイルのパス]
#   戻り値: [なし。I/O失敗時は例外を送出する]
# }
def save_project(canvas: Canvas, path: str | Path) -> None:
    """Atomically publish a complete project JSON file."""
    target = Path(path).resolve()
    content = json.dumps(canvas.to_source(), ensure_ascii=False, indent=2) + "\n"
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="\n", dir=target.parent,
            prefix=f".{target.name}.", suffix=".tmp", delete=False,
        ) as stream:
            temporary = Path(stream.name)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        if target.exists():
            temporary.chmod(target.stat().st_mode & 0o777)
        os.replace(temporary, target)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


# {
#   責務: [PixelCommandAPI: GUI・CLI・自動化で共有する作品操作APIを提供する]
#   フィールド: [canvas: すべての操作が直接委譲するPixelCanvasまたはLayeredPixelCanvas]
# }
class PixelCommandAPI:
    """Shared command surface for GUI, CUI, automation and game developer tools.

    The class owns no duplicate artwork state. Every command delegates to the
    supplied PixelCanvas/LayeredPixelCanvas and applies the same validation
    regardless of caller.
    """

    # {
    #   責務: [__init__: 操作対象の作品モデルを保持する]
    #   処理: [対応するCanvas型だけを受け入れ、それ以外はTypeErrorにする]
    #   引数: [canvas: 操作対象のPixelCanvasまたはLayeredPixelCanvas]
    #   戻り値: [なし。検証済みモデルをself.canvasへ設定する]
    # }
    def __init__(self, canvas: Canvas) -> None:
        if not isinstance(canvas, (PixelCanvas, LayeredPixelCanvas)):
            raise TypeError("canvas must be PixelCanvas or LayeredPixelCanvas")
        self.canvas = canvas

    # {
    #   責務: [new: 指定解像度の新規作品と共有APIを作成する]
    #   処理: [
    #     1: layeredに応じてPixelCanvasかLayeredPixelCanvasを生成する
    #     2: 生成したモデルをclsでラップして返す
    #   ]
    #   引数: [
    #     cls: PixelCommandAPI型
    #     width: 横解像度
    #     height: 縦解像度またはNone
    #     layered: レイヤー付き作品を作るか
    #   ]
    #   戻り値: [新規作品を操作するPixelCommandAPI]
    # }
    @classmethod
    def new(
        cls, width: int = 16, height: int | None = None, *, layered: bool = False
    ) -> "PixelCommandAPI":
        model: Canvas = (
            LayeredPixelCanvas(width, height) if layered else PixelCanvas(width, height)
        )
        return cls(model)

    # {
    #   責務: [load: 保存済みプロジェクトから共有APIを作成する]
    #   処理: [厳密な読込処理で作品を復元し、clsでラップする]
    #   引数: [cls: PixelCommandAPI型, path: JSONプロジェクトのパス]
    #   戻り値: [読み込んだ作品を操作するPixelCommandAPI]
    # }
    @classmethod
    def load(cls, path: str | Path) -> "PixelCommandAPI":
        return cls(load_project(path))

    # {
    #   責務: [resolution: 作品の論理解像度を公開する]
    #   処理: [バックエンドの現在解像度を取得する]
    #   引数: []
    #   戻り値: [横幅と縦幅の組]
    # }
    @property
    def resolution(self) -> tuple[int, int]:
        return self.canvas.resolution

    # {
    #   責務: [_point: 現在の作品上で論理画素座標を検証する]
    #   処理: [現在の作品の解像度に対して座標の型と範囲を検証する]
    #   引数: [x: 横座標, y: 縦座標]
    #   戻り値: [検証済み整数座標]
    # }
    def _point(self, x: object, y: object) -> tuple[int, int]:
        # 編集と読み取りで異なる座標変換を行わず、同じ検証へ集約する。
        return self._point_for(self.canvas, x, y)

    # {
    #   責務: [_require_integer: 値が組み込みの整数型か検証する]
    #   処理: [typeがintと完全一致しない値をValueErrorにし、適合値を返す]
    #   引数: [value: 検証対象, label: エラー文に使う値の説明]
    #   戻り値: [検証済み整数]
    # }
    @staticmethod
    def _require_integer(value: object, label: str) -> int:
        # boolはintの派生型なので、isinstanceでは座標への混入を防げない。
        if type(value) is not int:
            raise ValueError(f"{label} must be integers")
        return value

    # {
    #   責務: [_point_for: 指定した作品モデルの論理画素座標を検証する]
    #   処理: [
    #     1: xとyが整数座標として有効か検証する
    #     2: モデルの幅・高さの範囲内かを確認する
    #   ]
    #   引数: [canvas: 座標の対象作品, x: 横座標, y: 縦座標]
    #   戻り値: [検証済み整数座標]
    # }
    @staticmethod
    def _point_for(canvas: Canvas, x: object, y: object) -> tuple[int, int]:
        # 暗黙変換による切り捨てを避け、範囲比較の前に両座標の型を確定する。
        px = PixelCommandAPI._require_integer(x, "pixel coordinates")
        py = PixelCommandAPI._require_integer(y, "pixel coordinates")
        if not (0 <= px < canvas.width and 0 <= py < canvas.height):
            raise ValueError(
                f"pixel coordinate ({px}, {py}) outside "
                f"{canvas.width}x{canvas.height}"
            )
        return px, py

    # {
    #   責務: [_child: 子画素座標を検証して正規化する]
    #   処理: [
    #     1: Noneは子画素指定なしとして返す
    #     2: 整数の子座標2つと0または1の範囲を検証する
    #   ]
    #   引数: [child: 省略可能な子画素の横・縦座標]
    #   戻り値: [検証済み子画素座標またはNone]
    # }
    def _child(self, child: Sequence[object] | None) -> ChildCoordinate | None:
        if child is None:
            return None
        if len(child) != 2:
            raise ValueError("child coordinate requires CHILD_X CHILD_Y")
        # 親座標と同じ整数契約を適用してから、子セルの二値範囲を検証する。
        values = tuple(self._require_integer(value, "child coordinates") for value in child)
        if values[0] not in (0, 1) or values[1] not in (0, 1):
            raise ValueError("child coordinate must be 0 or 1")
        return values[0], values[1]

    # {
    #   責務: [_region: キャンバス内の矩形領域を検証する]
    #   処理: [
    #     1: 左上座標と幅・高さを整数・範囲検証する
    #     2: 寸法が正で、矩形全体がキャンバスに収まることを確認する
    #   ]
    #   引数: [x: 左上の横座標, y: 左上の縦座標, width: 領域幅, height: 領域高さ]
    #   戻り値: [検証済みx・y・幅・高さの組]
    # }
    def _region(
        self, x: object, y: object, width: object = 1, height: object = 1
    ) -> tuple[int, int, int, int]:
        px, py = self._point(x, y)
        # 幅・高さも切り捨てず検証し、編集を開始する前に矩形全体を確定する。
        region_width = self._require_integer(width, "region dimensions")
        region_height = self._require_integer(height, "region dimensions")
        if region_width <= 0 or region_height <= 0:
            raise ValueError("region width and height must be positive")
        if px + region_width > self.canvas.width or py + region_height > self.canvas.height:
            raise ValueError("region must fit entirely inside the canvas")
        return px, py, region_width, region_height

    # {
    #   責務: [_color: 色成分列をバックエンドのRGBA形式へ正規化する]
    #   処理: [入力列をタプル化しPixelCanvas共通の色検証へ渡す]
    #   引数: [color: 正規化する色成分列]
    #   戻り値: [検証済みRGBA色]
    # }
    @staticmethod
    def _color(color: Sequence[int]) -> Color:
        return PixelCanvas._normalize_color(tuple(color))

    # {
    #   責務: [set_resolution: 作品の論理解像度を変更する]
    #   処理: [検証と細部方針の適用をバックエンドへ委譲する]
    #   引数: [width: 横解像度, height: 縦解像度またはNone, detail_policy: 細部の保持・破棄方針]
    #   戻り値: [解像度が変化した場合はTrue、それ以外はFalse]
    # }
    def set_resolution(
        self, width: int, height: int | None = None,
        detail_policy: DetailPolicy = "preserve",
    ) -> bool:
        return self.canvas.set_resolution(width, height, detail_policy=detail_policy)

    # {
    #   責務: [upscale: 現在の論理解像度を縦横2倍にする]
    #   処理: [現在寸法の2倍と細部方針をバックエンドの解像度変更へ渡す]
    #   引数: [detail_policy: 拡大時の細部保持・破棄方針]
    #   戻り値: [解像度が変化した場合はTrue、それ以外はFalse]
    # }
    def upscale(self, detail_policy: DetailPolicy = "preserve") -> bool:
        return self.canvas.set_resolution(
            self.canvas.width * 2,
            self.canvas.height * 2,
            detail_policy=detail_policy,
        )

    # {
    #   責務: [is_split: 指定セルが4分割済みかを調べる]
    #   処理: [座標を検証してバックエンドへ分割状態を問い合わせる]
    #   引数: [x: 横座標, y: 縦座標]
    #   戻り値: [分割済みならTrue、それ以外はFalse]
    # }
    def is_split(self, x: object, y: object) -> bool:
        px, py = self._point(x, y)
        return self.canvas.is_split(px, py)

    # {
    #   責務: [split: 指定した論理セルを4分割する]
    #   処理: [座標を検証してバックエンドの単一セル分割を実行する]
    #   引数: [x: 横座標, y: 縦座標]
    #   戻り値: [セルが変化した場合はTrue、それ以外はFalse]
    # }
    def split(self, x: object, y: object) -> bool:
        px, py = self._point(x, y)
        return self.canvas.split_cell(px, py)

    # {
    #   責務: [split_region: 矩形内のセルをまとめて4分割する]
    #   処理: [領域全体を検証し、バックエンドで全体を1回の履歴操作として分割する]
    #   引数: [x: 左上の横座標, y: 左上の縦座標, width: 領域幅, height: 領域高さ]
    #   戻り値: [分割されたセル数]
    # }
    def split_region(
        self, x: object, y: object, width: object, height: object
    ) -> int:
        px, py, region_width, region_height = self._region(x, y, width, height)
        # 共有APIでセルごとに確定せず、バックエンドの一括更新へ委譲する。
        return self.canvas.split_region(px, py, region_width, region_height)

    # {
    #   責務: [collapse: 指定した分割セルを折りたたむ]
    #   処理: [座標と細部方針を検証し、discard指定時だけ細部破棄を有効にする]
    #   引数: [x: 横座標, y: 縦座標, detail_policy: 折りたたみ時の細部保持・破棄方針]
    #   戻り値: [セルが変化した場合はTrue、それ以外はFalse]
    # }
    def collapse(
        self, x: object, y: object, detail_policy: DetailPolicy = "preserve"
    ) -> bool:
        px, py = self._point(x, y)
        PixelCanvas._validate_detail_policy(detail_policy)
        return self.canvas.collapse_cell(
            px, py, discard_detail=detail_policy == "discard"
        )

    # {
    #   責務: [paint: 親画素または指定した子画素に色を描く]
    #   処理: [
    #     1: 親座標と色を検証・正規化する
    #     2: 任意の子座標と細部方針をバックエンドへ渡す
    #   ]
    #   引数: [x: 横座標, y: 縦座標, color: 描画色, child: 任意の子画素座標, detail_policy: 細部の保持・破棄方針]
    #   戻り値: [画素が変化した場合はTrue、それ以外はFalse]
    # }
    def paint(
        self, x: object, y: object, color: Sequence[int], *,
        child: Sequence[object] | None = None,
        detail_policy: DetailPolicy = "preserve",
    ) -> bool:
        px, py = self._point(x, y)
        return self.canvas.paint(
            px, py, self._color(color), child=self._child(child),
            detail_policy=detail_policy,
        )

    # {
    #   責務: [erase: 親画素または指定した子画素を透明色にする]
    #   処理: [
    #     1: 親座標を検証する
    #     2: 透明RGBA色と消去指定、子座標、細部方針を描画APIへ渡す
    #   ]
    #   引数: [x: 横座標, y: 縦座標, child: 任意の子画素座標, detail_policy: 細部の保持・破棄方針]
    #   戻り値: [画素が変化した場合はTrue、それ以外はFalse]
    # }
    def erase(
        self, x: object, y: object, *,
        child: Sequence[object] | None = None,
        detail_policy: DetailPolicy = "preserve",
    ) -> bool:
        px, py = self._point(x, y)
        return self.canvas.paint(
            px, py, (0, 0, 0, 0), erase=True, child=self._child(child),
            detail_policy=detail_policy,
        )

    # {
    #   責務: [fill: 接続領域を指定色で塗りつぶす]
    #   処理: [座標と色を検証し、細部方針を添えてバックエンドの塗りつぶしを実行する]
    #   引数: [x: 起点の横座標, y: 起点の縦座標, color: 塗りつぶし色, detail_policy: 細部の保持・破棄方針]
    #   戻り値: [変更された画素数]
    # }
    def fill(
        self, x: object, y: object, color: Sequence[int], *,
        detail_policy: DetailPolicy = "preserve",
    ) -> int:
        px, py = self._point(x, y)
        return self.canvas.fill(
            px, py, self._color(color), detail_policy=detail_policy
        )

    # {
    #   責務: [sample: 指定位置の色を作品または特定レイヤーから取得する]
    #   処理: [
    #     1: layer指定時はレイヤー付き作品と存在する名前を検証する
    #     2: 座標と子座標を検証して対象モデルから色を読む
    #   ]
    #   引数: [x: 横座標, y: 縦座標, child: 任意の子画素座標, layer: 任意の対象レイヤー名]
    #   戻り値: [取得したRGBA色]
    # }
    def sample(
        self, x: object, y: object, *,
        child: Sequence[object] | None = None,
        layer: str | None = None,
    ) -> Color:
        target: Canvas = self.canvas
        if layer is not None:
            if not isinstance(self.canvas, LayeredPixelCanvas):
                raise ValueError("layer selection requires a layered project")
            if layer not in self.canvas.layers:
                raise ValueError(f"layer does not exist: {layer}")
            target = self.canvas.layers[layer]
        px, py = self._point_for(target, x, y)
        return target.sample(px, py, self._child(child))

    # {
    #   責務: [discard_detail: 矩形領域が保持する細部を破棄する]
    #   処理: [領域寸法と境界を検証し、バックエンドへ一括破棄を委譲する]
    #   引数: [x: 左上の横座標, y: 左上の縦座標, width: 領域幅, height: 領域高さ]
    #   戻り値: [細部を破棄したセル数]
    # }
    def discard_detail(
        self, x: object, y: object, width: object = 1, height: object = 1
    ) -> int:
        region = self._region(x, y, width, height)
        return self.canvas.discard_detail(*region)

    # {
    #   責務: [import_image: 画像ファイルをアクティブな作品へ読み込む]
    #   処理: [
    #     1: レイヤー付き作品ならアクティブレイヤーを対象にする
    #     2: 単一作品なら自身を対象にして画像を読み込む
    #   ]
    #   引数: [source: 読み込む画像ファイルのパス]
    #   戻り値: [読込成功時はTrue。失敗時はバックエンド例外を送出する]
    # }
    def import_image(self, source: str | Path) -> bool:
        target = (
            self.canvas.active
            if isinstance(self.canvas, LayeredPixelCanvas)
            else self.canvas
        )
        target.import_image(source)
        return True

    # {
    #   責務: [add_layer: レイヤー付き作品へ新しいレイヤーを追加する]
    #   処理: [レイヤー対応モデルを検証し、追加処理をバックエンドへ委譲する]
    #   引数: [name: 追加するレイヤー名]
    #   戻り値: [追加成功時はTrue。非レイヤー作品ではValueErrorになる]
    # }
    def add_layer(self, name: str) -> bool:
        if not isinstance(self.canvas, LayeredPixelCanvas):
            raise ValueError("layer operations require a layered project")
        self.canvas.add_layer(name)
        return True

    # {
    #   責務: [select_layer: 指定レイヤーをアクティブにする]
    #   処理: [レイヤー対応モデルを検証し、選択前後の名前を比較して切替を行う]
    #   引数: [name: 選択するレイヤー名]
    #   戻り値: [アクティブレイヤーが変化した場合はTrue、それ以外はFalse]
    # }
    def select_layer(self, name: str) -> bool:
        if not isinstance(self.canvas, LayeredPixelCanvas):
            raise ValueError("layer operations require a layered project")
        changed = name != self.canvas.active_layer
        self.canvas.select_layer(name)
        return changed

    # {
    #   責務: [remove_layer: レイヤー付き作品から指定または選択中の層を削除する]
    #   処理: [レイヤー対応モデルを検証し、削除処理をバックエンドへ委譲する]
    #   引数: [name: 削除するレイヤー名。Noneならバックエンドの既定対象]
    #   戻り値: [削除成功時はTrue。非レイヤー作品ではValueErrorになる]
    # }
    def remove_layer(self, name: str | None = None) -> bool:
        if not isinstance(self.canvas, LayeredPixelCanvas):
            raise ValueError("layer operations require a layered project")
        self.canvas.remove_layer(name)
        return True

    # {
    #   責務: [rename_layer: 指定または選択中のレイヤー名を変更する]
    #   処理: [レイヤー対応モデルを検証し、新旧の名前をバックエンドへ渡す]
    #   引数: [new_name: 変更後の名前, name: 変更対象の現在名。Noneなら既定対象]
    #   戻り値: [バックエンドが返す変更有無]
    # }
    def rename_layer(self, new_name: str, name: str | None = None) -> bool:
        if not isinstance(self.canvas, LayeredPixelCanvas):
            raise ValueError("layer operations require a layered project")
        return self.canvas.rename_layer(new_name, name)

    # {
    #   責務: [move_layer: 指定または選択中のレイヤーを並べ替える]
    #   処理: [レイヤー対応モデルを検証し、方向と対象名をバックエンドへ渡す]
    #   引数: [direction: 移動方向, name: 移動対象のレイヤー名。Noneなら既定対象]
    #   戻り値: [バックエンドが返す変更有無]
    # }
    def move_layer(self, direction: str, name: str | None = None) -> bool:
        if not isinstance(self.canvas, LayeredPixelCanvas):
            raise ValueError("layer operations require a layered project")
        return self.canvas.move_layer(direction, name)

    # {
    #   責務: [set_layer_visibility: 指定または選択中のレイヤー表示を設定する]
    #   処理: [レイヤー対応モデルを検証し、可視状態と対象名をバックエンドへ渡す]
    #   引数: [visible: 表示するか, name: 対象レイヤー名。Noneなら既定対象]
    #   戻り値: [バックエンドが返す変更有無]
    # }
    def set_layer_visibility(self, visible: bool, name: str | None = None) -> bool:
        if not isinstance(self.canvas, LayeredPixelCanvas):
            raise ValueError("layer operations require a layered project")
        return self.canvas.set_layer_visibility(visible, name)

    # {
    #   責務: [inspect: 作品と各レイヤーの解像度・細部状態を要約する]
    #   処理: [
    #     1: 単一作品または全レイヤーのモデルを列挙する
    #     2: 各層の可視状態、保持・展開セル、保持解像度とパッチ数を集計する
    #     3: 作品種別、解像度、アクティブ層、細部有無を含む辞書を構成する
    #   ]
    #   引数: []
    #   戻り値: [作品状態を表すJSON互換辞書]
    # }
    def inspect(self) -> dict[str, Any]:
        entries = (
            self.canvas.layers.items()
            if isinstance(self.canvas, LayeredPixelCanvas)
            else [(None, self.canvas)]
        )
        layers = []
        for name, layer in entries:
            cells = layer.detail_cells()
            expanded = sum(bool(cell["expanded"]) for cell in cells)
            layers.append({
                "name": name,
                "visible": (
                    self.canvas.layer_visibility.get(name, True)
                    if isinstance(self.canvas, LayeredPixelCanvas)
                    else True
                ),
                "retained_detail_cells": len(cells),
                "expanded_cells": expanded,
                "collapsed_detail_cells": len(cells) - expanded,
                "detail_cells": cells,
                "retained_resolution": list(layer.retained_resolution),
                "retained_patch_count": layer.retained_patch_count,
            })
        return {
            "schema_version": 1,
            "project_type": (
                "layered" if isinstance(self.canvas, LayeredPixelCanvas) else "flat"
            ),
            "resolution": list(self.canvas.resolution),
            "native_resolution": list(self.canvas.native_resolution),
            "retained_resolution": list(self.canvas.retained_resolution),
            "active_layer": (
                self.canvas.active_layer
                if isinstance(self.canvas, LayeredPixelCanvas)
                else None
            ),
            "has_detail": self.canvas.has_detail,
            "has_refinements": self.canvas.has_refinements,
            "layers": layers,
        }

    # {
    #   責務: [inspect_sample: 作品の状態要約へ指定位置の採色結果を加える]
    #   処理: [
    #     1: 作品状態を取得して対象作品または指定レイヤーを選ぶ
    #     2: 座標と色を検証し、親または子画素のRGBA値を読む
    #     3: 座標・子画素・対象層・色をsample項目として要約へ追加する
    #   ]
    #   引数: [x: 横座標, y: 縦座標, child: 任意の子画素座標, layer: 任意の対象レイヤー名]
    #   戻り値: [作品状態と採色結果を含むJSON互換辞書]
    # }
    def inspect_sample(
        self, x: object, y: object, *,
        child: Sequence[object] | None = None,
        layer: str | None = None,
    ) -> dict[str, Any]:
        report = self.inspect()
        if layer is not None:
            if not isinstance(self.canvas, LayeredPixelCanvas):
                raise ValueError("layer selection requires a layered project")
            if layer not in self.canvas.layers:
                raise ValueError(f"layer does not exist: {layer}")
            sample_canvas: Canvas = self.canvas.layers[layer]
        else:
            sample_canvas = self.canvas
        px, py = self._point_for(sample_canvas, x, y)
        layer_name = (
            layer if layer is not None
            else self.canvas.active_layer
            if isinstance(self.canvas, LayeredPixelCanvas)
            else None
        )
        color = self.sample(px, py, child=child, layer=layer)
        report["sample"] = {
            "x": px, "y": py,
            "child": list(child) if child is not None else None,
            "layer": layer_name,
            "rgba": list(color),
        }
        return report

    # {
    #   責務: [save: 現在の作品をJSONプロジェクトとして保存する]
    #   処理: [保存処理を共有ファイル関数へ委譲する]
    #   引数: [path: 保存先ファイルのパス]
    #   戻り値: [なし。保存失敗時は例外を送出する]
    # }
    def save(self, path: str | Path) -> None:
        save_project(self.canvas, path)

    # {
    #   責務: [export_png: 現在の作品をPNG画像として書き出す]
    #   処理: [保存先と任意の出力寸法をバックエンドのPNG出力へ渡す]
    #   引数: [
    #     path: PNG保存先
    #     export_size: 任意の正方形出力サイズ
    #     output_resolution: 任意の横幅・縦幅の出力寸法
    #   ]
    #   戻り値: [なし。出力失敗時は例外を送出する]
    # }
    def export_png(
        self, path: str | Path, export_size: int | None = None, *,
        output_resolution: tuple[int, int] | None = None,
    ) -> None:
        self.canvas.save_png(
            path, export_size, output_resolution=output_resolution
        )

    # {
    #   責務: [execute: 名前で指定された操作を自動化向けに実行する]
    #   処理: [
    #     1: サポートする操作名とメソッドの対応表を作る
    #     2: 未知の名前はValueErrorにし、対応操作へ名前付き引数を渡す
    #   ]
    #   引数: [command: 実行する操作名, parameters: 操作メソッドに渡す名前付き引数]
    #   戻り値: [呼び出した操作メソッドの戻り値]
    # }
    def execute(self, command: str, /, **parameters: Any) -> Any:
        """Execute one named command for automation/AI callers."""
        commands = {
            "set_resolution": self.set_resolution,
            "upscale": self.upscale,
            "split": self.split,
            "split_region": self.split_region,
            "collapse": self.collapse,
            "paint": self.paint,
            "erase": self.erase,
            "fill": self.fill,
            "sample": self.sample,
            "discard_detail": self.discard_detail,
            "import_image": self.import_image,
            "add_layer": self.add_layer,
            "select_layer": self.select_layer,
            "remove_layer": self.remove_layer,
            "rename_layer": self.rename_layer,
            "move_layer": self.move_layer,
            "set_layer_visibility": self.set_layer_visibility,
            "inspect": self.inspect,
            "inspect_sample": self.inspect_sample,
            "save": self.save,
            "export_png": self.export_png,
        }
        try:
            operation = commands[command]
        except KeyError as error:
            raise ValueError(f"unknown command: {command}") from error
        return operation(**parameters)
