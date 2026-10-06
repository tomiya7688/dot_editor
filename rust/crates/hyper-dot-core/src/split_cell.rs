use crate::field_bounds::FieldBounds;
use crate::raster::Color;
use crate::resolution::Resolution;

/// {
///   責務: [SplitCell: 特定グリッドの分割セルの親色と展開状態を保持する]
///   フィールド: [
///     resolution: 記録した親グリッド
///     x・y: 親セル座標
///     base: 独立した親RGBA
///     expanded: 子を展開表示するか
///   ]
/// }
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(crate) struct SplitCell {
    pub(crate) resolution: Resolution,
    pub(crate) x: u32,
    pub(crate) y: u32,
    pub(crate) base: Color,
    pub(crate) expanded: bool,
}

impl SplitCell {
    /// {
    ///   責務: [bounds: 保存した分割セルの正規化領域を求める]
    ///   処理: [
    ///     1: 保存解像度と親座標からセル範囲を計算する
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///   ]
    ///   戻り値: [分割親セルの領域]
    /// }
    pub(crate) fn bounds(self) -> FieldBounds {
        FieldBounds::cell(self.resolution, self.x, self.y)
    }

    /// {
    ///   責務: [matches: 保存分割が指定解像度・親座標と一致するか判定する]
    ///   処理: [
    ///     1: 解像度・x・yを比較する
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///     resolution: 対象の解像度
    ///     x: 横座標
    ///     y: 縦座標
    ///   ]
    ///   戻り値: [すべて一致した場合true]
    /// }
    pub(crate) fn matches(self, resolution: Resolution, x: u32, y: u32) -> bool {
        self.resolution == resolution && self.x == x && self.y == y
    }
}
