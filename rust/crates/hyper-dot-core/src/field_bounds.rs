use crate::rational_coordinate::RationalCoordinate as Coordinate;
use crate::resolution::Resolution;

/// {
///   責務: [FieldBounds: 正規化した有理座標で半開の長方形を表す]
///   フィールド: [
///     left・top: 含む左上境界
///     right・bottom: 含まない右下境界
///   ]
/// }
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(crate) struct FieldBounds {
    pub(crate) left: Coordinate,
    pub(crate) top: Coordinate,
    pub(crate) right: Coordinate,
    pub(crate) bottom: Coordinate,
}

impl FieldBounds {
    /// {
    ///   責務: [full: 正規化されたCanvas全体の範囲を作る]
    ///   処理: [
    ///     1: 左右上下を0と1に設定する
    ///   ]
    ///   引数: []
    ///   戻り値: [単位正方形の範囲]
    /// }
    pub(crate) fn full() -> Self {
        Self {
            left: Coordinate::new(0, 1),
            top: Coordinate::new(0, 1),
            right: Coordinate::new(1, 1),
            bottom: Coordinate::new(1, 1),
        }
    }

    /// {
    ///   責務: [cell: セルに対応する正確な正規化範囲を求める]
    ///   処理: [
    ///     1: セル端を解像度で割った有理座標にする
    ///   ]
    ///   引数: [
    ///     grid: 座標を解釈するグリッド
    ///     x: 横座標
    ///     y: 縦座標
    ///   ]
    ///   戻り値: [セルの半開領域]
    /// }
    pub(crate) fn cell(grid: Resolution, x: u32, y: u32) -> Self {
        Self {
            left: Coordinate::new(u64::from(x), u64::from(grid.width())),
            top: Coordinate::new(u64::from(y), u64::from(grid.height())),
            right: Coordinate::new(u64::from(x) + 1, u64::from(grid.width())),
            bottom: Coordinate::new(u64::from(y) + 1, u64::from(grid.height())),
        }
    }

    /// {
    ///   責務: [contains: 正規化点が半開領域内か判定する]
    ///   処理: [
    ///     1: 左上を含み右下を除く範囲で比較する
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///     x: 横座標
    ///     y: 縦座標
    ///   ]
    ///   戻り値: [領域内ならtrue]
    /// }
    pub(crate) fn contains(self, x: Coordinate, y: Coordinate) -> bool {
        self.left <= x && x < self.right && self.top <= y && y < self.bottom
    }

    /// {
    ///   責務: [intersection: 二つの領域の共通部分を求める]
    ///   処理: [
    ///     1: 左上の最大値と右下の最小値を取る
    ///     2: 正の面積の有無を判定する
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///     other: 比較・交差の相手
    ///   ]
    ///   戻り値: [共通領域、交差しない場合はNone]
    /// }
    pub(crate) fn intersection(self, other: Self) -> Option<Self> {
        let overlap = Self {
            left: self.left.max(other.left),
            top: self.top.max(other.top),
            right: self.right.min(other.right),
            bottom: self.bottom.min(other.bottom),
        };
        (overlap.left < overlap.right && overlap.top < overlap.bottom).then_some(overlap)
    }

    /// Disjoint remainder strips. The cut must lie inside this rectangle.
    /// {
    ///   責務: [outside: 切り取る領域以外の互いに重ならない帯領域を求める]
    ///   処理: [
    ///     1: 上下左右の残り候補を作る
    ///     2: 面積0の候補を除く
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///     cut: 除外する長方形
    ///   ]
    ///   戻り値: [残り領域のイテレータ]
    /// }
    pub(crate) fn outside(self, cut: Self) -> impl Iterator<Item = Self> {
        [
            Self {
                bottom: cut.top,
                ..self
            },
            Self {
                top: cut.bottom,
                ..self
            },
            Self {
                top: cut.top,
                bottom: cut.bottom,
                right: cut.left,
                ..self
            },
            Self {
                top: cut.top,
                bottom: cut.bottom,
                left: cut.right,
                ..self
            },
        ]
        .into_iter()
        .filter(|piece| piece.left < piece.right && piece.top < piece.bottom)
    }
}
