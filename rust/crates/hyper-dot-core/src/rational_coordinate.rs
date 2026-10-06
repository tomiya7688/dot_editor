use std::cmp::Ordering;

/// Exact normalized coordinate in the closed unit interval.
/// {
///   責務: [RationalCoordinate: 単位区間内の位置を約分した有理数で表す]
///   フィールド: [
///     numerator: 分子
///     denominator: 正の分母
///   ]
/// }
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(crate) struct RationalCoordinate {
    numerator: u64,
    denominator: u64,
}

impl RationalCoordinate {
    /// Exact pixel position inside a source extent, independently of its origin.
    /// {
    ///   責務: [relative_floor: 元画像範囲内の位置を画素の下端へ丸める]
    ///   処理: [
    ///     1: 正確な相対比を求める
    ///     2: 整数除算で切り下げる
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///     start: 区間の開始境界
    ///     end: 区間の終了境界
    ///     pixels: 区間を分割する画素数
    ///   ]
    ///   戻り値: [元画像上の画素位置]
    /// }
    pub(crate) fn relative_floor(self, start: Self, end: Self, pixels: u32) -> u32 {
        let (numerator, denominator) = self.relative_ratio(start, end, pixels);
        (numerator / denominator) as u32
    }

    /// {
    ///   責務: [relative_ceil: 元画像範囲内の位置を画素の上端へ丸める]
    ///   処理: [
    ///     1: 正確な相対比を求める
    ///     2: 整数除算で切り上げる
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///     start: 区間の開始境界
    ///     end: 区間の終了境界
    ///     pixels: 区間を分割する画素数
    ///   ]
    ///   戻り値: [切り取り終端の画素位置]
    /// }
    pub(crate) fn relative_ceil(self, start: Self, end: Self, pixels: u32) -> u32 {
        let (numerator, denominator) = self.relative_ratio(start, end, pixels);
        numerator.div_ceil(denominator) as u32
    }

    /// {
    ///   責務: [relative_ratio: 正規化点の元画像範囲に対する正確な比を求める]
    ///   処理: [
    ///     1: 範囲の幅と始点からの距離を有理演算で求める
    ///     2: 画素数を掛けた分子・分母を作る
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///     start: 区間の開始境界
    ///     end: 区間の終了境界
    ///     pixels: 区間を分割する画素数
    ///   ]
    ///   戻り値: [相対画素位置の分子・分母]
    /// }
    fn relative_ratio(self, start: Self, end: Self, pixels: u32) -> (u128, u128) {
        let span = u128::from(end.numerator) * u128::from(start.denominator)
            - u128::from(start.numerator) * u128::from(end.denominator);
        let distance = u128::from(self.numerator) * u128::from(start.denominator)
            - u128::from(start.numerator) * u128::from(self.denominator);
        (
            distance * u128::from(end.denominator) * u128::from(pixels),
            u128::from(self.denominator) * span,
        )
    }

    /// {
    ///   責務: [interpolate: 元画像の画素端を正確な正規化座標に戻す]
    ///   処理: [
    ///     1: 元範囲と画素比を有理数で補間する
    ///     2: 分子・分母を約分する
    ///   ]
    ///   引数: [
    ///     start: 区間の開始境界
    ///     end: 区間の終了境界
    ///     position: 区間内の画素位置
    ///     pixels: 区間を分割する画素数
    ///   ]
    ///   戻り値: [補間した正規化座標]
    /// }
    pub(crate) fn interpolate(start: Self, end: Self, position: u32, pixels: u32) -> Self {
        let span = u128::from(end.numerator) * u128::from(start.denominator)
            - u128::from(start.numerator) * u128::from(end.denominator);
        let numerator =
            u128::from(start.numerator) * u128::from(end.denominator) * u128::from(pixels)
                + span * u128::from(position);
        let denominator =
            u128::from(start.denominator) * u128::from(end.denominator) * u128::from(pixels);
        let (mut a, mut b) = (numerator, denominator);
        while b != 0 {
            (a, b) = (b, a % b);
        }
        // Original extents are bounded JSON fractions or the unit rectangle;
        // origins always refer to that original extent, never interpolated ones.
        Self::new((numerator / a) as u64, (denominator / a) as u64)
    }

    /// {
    ///   責務: [density: 元画像範囲から保持解像度の要約を求める]
    ///   処理: [
    ///     1: 画素数を正確な範囲幅で割り切り上げる
    ///     2: u32の要約上限に収める
    ///   ]
    ///   引数: [
    ///     start: 区間の開始境界
    ///     end: 区間の終了境界
    ///     pixels: 区間を分割する画素数
    ///   ]
    ///   戻り値: [保持解像度の1辺の要約]
    /// }
    pub(crate) fn density(start: Self, end: Self, pixels: u32) -> u32 {
        let span = u128::from(end.numerator) * u128::from(start.denominator)
            - u128::from(start.numerator) * u128::from(end.denominator);
        let numerator =
            u128::from(pixels) * u128::from(start.denominator) * u128::from(end.denominator);
        // Retained resolution is a u32 summary; sampling still uses exact extents.
        numerator.div_ceil(span).min(u128::from(u32::MAX)) as u32
    }

    /// {
    ///   責務: [fraction: 正規化済み分子・分母を取り出す]
    ///   処理: [
    ///     1: 分子と分母を順に配列へ格納する
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///   ]
    ///   戻り値: [分子・分母の配列]
    /// }
    pub(crate) const fn fraction(self) -> [u64; 2] {
        [self.numerator, self.denominator]
    }

    /// {
    ///   責務: [new: 正の分母を持つ単位区間内の座標を約分する]
    ///   処理: [
    ///     1: 分子・分母の前提を確認する
    ///     2: 最大公約数で約分する
    ///   ]
    ///   引数: [
    ///     numerator: 有理数の分子
    ///     denominator: 有理数の正の分母
    ///   ]
    ///   戻り値: [正規化された有理座標]
    /// }
    pub(crate) fn new(numerator: u64, denominator: u64) -> Self {
        debug_assert!(denominator > 0 && numerator <= denominator);
        let (mut a, mut b) = (numerator, denominator);
        while b != 0 {
            (a, b) = (b, a % b);
        }
        Self {
            numerator: numerator / a,
            denominator: denominator / a,
        }
    }

    /// {
    ///   責務: [center: 論理セルの正確な中心位置を求める]
    ///   処理: [
    ///     1: セル番号の2倍に1を足す
    ///     2: 解像度の2倍を分母にして約分する
    ///   ]
    ///   引数: [
    ///     position: 区間内の画素位置
    ///     extent: 対象軸の正のセル数
    ///   ]
    ///   戻り値: [セル中心の有理座標]
    /// }
    pub(crate) fn center(position: u32, extent: u32) -> Self {
        Self::new(2 * u64::from(position) + 1, 2 * u64::from(extent))
    }
}

impl Ord for RationalCoordinate {
    /// {
    ///   責務: [cmp: 二つの有理座標の大小を比較する]
    ///   処理: [
    ///     1: u128で交差積を求めて比較する
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///     other: 比較・交差の相手
    ///   ]
    ///   戻り値: [大小・等値の順序]
    /// }
    fn cmp(&self, other: &Self) -> Ordering {
        (u128::from(self.numerator) * u128::from(other.denominator))
            .cmp(&(u128::from(other.numerator) * u128::from(self.denominator)))
    }
}

impl PartialOrd for RationalCoordinate {
    /// {
    ///   責務: [partial_cmp: 有理座標の全順序を部分順序として返す]
    ///   処理: [
    ///     1: 全順序比較をSomeで包む
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///     other: 比較・交差の相手
    ///   ]
    ///   戻り値: [Someに包んだ比較結果]
    /// }
    fn partial_cmp(&self, other: &Self) -> Option<Ordering> {
        Some(self.cmp(other))
    }
}
