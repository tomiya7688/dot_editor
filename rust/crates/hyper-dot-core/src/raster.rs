//! Bounded RGBA raster storage for one logical resolution.

use std::error::Error;
use std::fmt::{Display, Formatter};

use crate::resolution::Resolution;

pub const MAX_DIMENSION: u32 = 4096;
pub const MAX_PIXELS: usize = 4_194_304;

pub type Color = [u8; 4];

const TRANSPARENT: Color = [0, 0, 0, 0];

/// A row-major raster. Resolution changes and retained-detail behavior live above
/// this storage primitive; this type never resamples its own pixels.
/// {
///   責務: [Raster: 固定解像度のRGBA画素を行優先で保持する]
///   フィールド: [
///     resolution: 正の画像寸法
///     pixels: 行優先のRGBA配列
///   ]
/// }
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct Raster {
    resolution: Resolution,
    pixels: Vec<Color>,
}

/// {
///   責務: [RasterError: ラスタ確保・座標検査の失敗を分類する]
///   フィールド: [
///     DimensionLimitExceeded: 上限を超えたwidth・height
///     PixelBudgetExceeded: 画素数上限
///     AllocationFailed: 保存領域の確保失敗
///     CoordinateOutOfBounds: 範囲外のx・y
///   ]
/// }
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum RasterError {
    DimensionLimitExceeded { width: u32, height: u32 },
    PixelBudgetExceeded,
    AllocationFailed,
    CoordinateOutOfBounds { x: u32, y: u32 },
}

impl Raster {
    /// {
    ///   責務: [new: 上限内の透明RGBAラスタを確保する]
    ///   処理: [
    ///     1: 辺長と画素数を検証する
    ///     2: 必要な画素容量を確保する
    ///     3: 全画素を透明黒にする
    ///   ]
    ///   引数: [
    ///     resolution: 対象の解像度
    ///   ]
    ///   戻り値: [ラスタまたは確保・予算エラー]
    /// }
    pub fn new(resolution: Resolution) -> Result<Self, RasterError> {
        let width = resolution.width();
        let height = resolution.height();
        if width > MAX_DIMENSION || height > MAX_DIMENSION {
            return Err(RasterError::DimensionLimitExceeded { width, height });
        }

        let pixel_count = usize::try_from(width)
            .ok()
            .and_then(|width| {
                usize::try_from(height)
                    .ok()
                    .and_then(|height| width.checked_mul(height))
            })
            .filter(|count| *count <= MAX_PIXELS)
            .ok_or(RasterError::PixelBudgetExceeded)?;

        let mut pixels = Vec::new();
        pixels
            .try_reserve_exact(pixel_count)
            .map_err(|_| RasterError::AllocationFailed)?;
        pixels.resize(pixel_count, TRANSPARENT);

        Ok(Self { resolution, pixels })
    }

    /// {
    ///   責務: [resolution: ラスタの解像度を取得する]
    ///   処理: [
    ///     1: 保存した縦横の値を返す
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///   ]
    ///   戻り値: [ラスタ解像度]
    /// }
    pub const fn resolution(&self) -> Resolution {
        self.resolution
    }

    /// {
    ///   責務: [sample: 指定座標のRGBAを読む]
    ///   処理: [
    ///     1: 座標を配列位置へ検証・変換する
    ///     2: 対応する色を返す
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///     x: 横座標
    ///     y: 縦座標
    ///   ]
    ///   戻り値: [RGBAまたは座標エラー]
    /// }
    pub fn sample(&self, x: u32, y: u32) -> Result<Color, RasterError> {
        let index = self
            .index(x, y)
            .ok_or(RasterError::CoordinateOutOfBounds { x, y })?;
        Ok(self.pixels[index])
    }

    /// Writes a pixel and reports whether its value changed. Out-of-range writes
    /// are ignored, matching the editor's paint operation.
    /// {
    ///   責務: [paint: 指定画素を描いて変更有無を報告する]
    ///   処理: [
    ///     1: 範囲外と同色を変更なしにする
    ///     2: 画素を置き換える
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///     x: 横座標
    ///     y: 縦座標
    ///     color: 適用するRGBA色
    ///   ]
    ///   戻り値: [変更した場合true]
    /// }
    pub fn paint(&mut self, x: u32, y: u32, color: Color) -> bool {
        let Some(index) = self.index(x, y) else {
            return false;
        };
        if self.pixels[index] == color {
            return false;
        }
        self.pixels[index] = color;
        true
    }

    /// {
    ///   責務: [erase: 指定画素を透明黒へ戻す]
    ///   処理: [
    ///     1: 透明色で画素描画へ委譲する
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///     x: 横座標
    ///     y: 縦座標
    ///   ]
    ///   戻り値: [変更した場合true]
    /// }
    pub fn erase(&mut self, x: u32, y: u32) -> bool {
        self.paint(x, y, TRANSPARENT)
    }

    /// Fills the four-connected region matching the seed pixel's exact RGBA value.
    /// Returns the number of changed pixels, or zero for an out-of-range seed or
    /// an unchanged color. Allocation failure leaves the raster unchanged.
    /// {
    ///   責務: [fill: 同じRGBAの4近傍領域を塗る]
    ///   処理: [
    ///     1: 範囲外・同色を変更なしにする
    ///     2: 探索領域を確保して隣接画素を探索する
    ///     3: 訪問時に色を変更して個数を数える
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///     x: 横座標
    ///     y: 縦座標
    ///     color: 適用するRGBA色
    ///   ]
    ///   戻り値: [変更画素数または確保エラー]
    /// }
    pub fn fill(&mut self, x: u32, y: u32, color: Color) -> Result<usize, RasterError> {
        let Some(seed) = self.index(x, y) else {
            return Ok(0);
        };
        let original = self.pixels[seed];
        if original == color {
            return Ok(0);
        }

        // Each pixel can enter the work list once: recoloring it when queued
        // prevents revisits. Reserve the upper bound before any mutation.
        let mut pending = Vec::new();
        pending
            .try_reserve_exact(self.pixels.len())
            .map_err(|_| RasterError::AllocationFailed)?;
        pending.push(seed);
        self.pixels[seed] = color;
        let mut changed = 1;
        let width = self.resolution.width() as usize;

        while let Some(index) = pending.pop() {
            let column = index % width;
            let neighbors = [
                if column > 0 { Some(index - 1) } else { None },
                if column + 1 < width {
                    Some(index + 1)
                } else {
                    None
                },
                index.checked_sub(width),
                index
                    .checked_add(width)
                    .filter(|next| *next < self.pixels.len()),
            ];
            for next in neighbors.into_iter().flatten() {
                if self.pixels[next] == original {
                    self.pixels[next] = color;
                    pending.push(next);
                    changed += 1;
                }
            }
        }
        Ok(changed)
    }

    /// {
    ///   責務: [index: 画素座標を範囲内の行優先配列位置へ変換する]
    ///   処理: [
    ///     1: 縦横の範囲を確認する
    ///     2: 行の開始位置に列を足す
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///     x: 横座標
    ///     y: 縦座標
    ///   ]
    ///   戻り値: [配列位置、範囲外ならNone]
    /// }
    fn index(&self, x: u32, y: u32) -> Option<usize> {
        let width = self.resolution.width();
        let height = self.resolution.height();
        if x >= width || y >= height {
            return None;
        }
        usize::try_from(y)
            .ok()?
            .checked_mul(usize::try_from(width).ok()?)?
            .checked_add(usize::try_from(x).ok()?)
    }
}

impl Display for RasterError {
    /// {
    ///   責務: [fmt: エラー種別に対応する診断文を出力する]
    ///   処理: [
    ///     1: 種別を判定し内部エラーまたは説明文をformatterへ書く
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///     formatter: 診断文の出力先
    ///   ]
    ///   戻り値: [書き込み結果、出力に失敗するとfmt::Error]
    /// }
    fn fmt(&self, formatter: &mut Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::DimensionLimitExceeded { width, height } => write!(
                formatter,
                "raster dimensions {width}x{height} exceed the {MAX_DIMENSION} limit"
            ),
            Self::PixelBudgetExceeded => {
                write!(formatter, "raster exceeds the {MAX_PIXELS}-pixel budget")
            }
            Self::AllocationFailed => formatter.write_str("unable to allocate raster storage"),
            Self::CoordinateOutOfBounds { x, y } => {
                write!(formatter, "pixel coordinate ({x}, {y}) is out of bounds")
            }
        }
    }
}

impl Error for RasterError {}

#[cfg(test)]
mod tests {
    use super::{Color, MAX_DIMENSION, Raster, RasterError};
    use crate::resolution::Resolution;

    /// {
    ///   責務: [raster: テスト用の透明ラスタを確保する]
    ///   処理: [
    ///     1: 正の解像度を作りラスタを確保する
    ///   ]
    ///   引数: [
    ///     width: 対象領域の幅
    ///     height: 対象領域の高さ
    ///   ]
    ///   戻り値: [透明ラスタ、確保失敗ならテストを失敗させる]
    /// }
    fn raster(width: u32, height: u32) -> Raster {
        Raster::new(Resolution::new(width, height).expect("test dimensions are positive"))
            .expect("test raster is within the storage budget")
    }

    /// {
    ///   責務: [starts_transparent_at_non_square_resolution: 非正方形画像を透明色で初期化することを回帰検証する]
    ///   処理: [
    ///     1: 対象の画像・状態を用意する
    ///     2: 非正方形画像を透明色で初期化する操作を実行し期待結果をassertで比較する
    ///   ]
    ///   引数: []
    ///   戻り値: [なし、不一致ならテストを失敗させる]
    /// }
    #[test]
    fn starts_transparent_at_non_square_resolution() {
        let raster = raster(23, 17);

        assert_eq!(raster.resolution(), Resolution::new(23, 17).unwrap());
        assert_eq!(raster.sample(22, 16), Ok([0, 0, 0, 0]));
    }

    /// {
    ///   責務: [paint_and_sample_preserve_rgba_and_do_not_alias_neighbors: RGBAを保持し隣接画素へ変更を漏らさないことを回帰検証する]
    ///   処理: [
    ///     1: 対象の画像・状態を用意する
    ///     2: RGBAを保持し隣接画素へ変更を漏らさない操作を実行し期待結果をassertで比較する
    ///   ]
    ///   引数: []
    ///   戻り値: [なし、不一致ならテストを失敗させる]
    /// }
    #[test]
    fn paint_and_sample_preserve_rgba_and_do_not_alias_neighbors() {
        let mut raster = raster(3, 2);
        let color: Color = [12, 34, 56, 78];

        assert!(raster.paint(2, 1, color));
        assert_eq!(raster.sample(2, 1), Ok(color));
        assert_eq!(raster.sample(1, 1), Ok([0, 0, 0, 0]));
    }

    /// {
    ///   責務: [painting_the_existing_color_is_a_no_op: 同色描画を変更なしとすることを回帰検証する]
    ///   処理: [
    ///     1: 対象の画像・状態を用意する
    ///     2: 同色描画を変更なしとする操作を実行し期待結果をassertで比較する
    ///   ]
    ///   引数: []
    ///   戻り値: [なし、不一致ならテストを失敗させる]
    /// }
    #[test]
    fn painting_the_existing_color_is_a_no_op() {
        let mut raster = raster(1, 1);
        let color = [1, 2, 3, 255];

        assert!(raster.paint(0, 0, color));
        assert!(!raster.paint(0, 0, color));
    }

    /// {
    ///   責務: [erase_restores_transparency_and_is_idempotent: 消去で透明に戻り再消去を変更なしとすることを回帰検証する]
    ///   処理: [
    ///     1: 対象の画像・状態を用意する
    ///     2: 消去で透明に戻り再消去を変更なしとする操作を実行し期待結果をassertで比較する
    ///   ]
    ///   引数: []
    ///   戻り値: [なし、不一致ならテストを失敗させる]
    /// }
    #[test]
    fn erase_restores_transparency_and_is_idempotent() {
        let mut raster = raster(1, 1);
        raster.paint(0, 0, [255, 0, 0, 255]);

        assert!(raster.erase(0, 0));
        assert_eq!(raster.sample(0, 0), Ok([0, 0, 0, 0]));
        assert!(!raster.erase(0, 0));
    }

    /// {
    ///   責務: [paint_outside_resolution_is_ignored: 範囲外描画を無視することを回帰検証する]
    ///   処理: [
    ///     1: 対象の画像・状態を用意する
    ///     2: 範囲外描画を無視する操作を実行し期待結果をassertで比較する
    ///   ]
    ///   引数: []
    ///   戻り値: [なし、不一致ならテストを失敗させる]
    /// }
    #[test]
    fn paint_outside_resolution_is_ignored() {
        let mut raster = raster(2, 3);

        assert!(!raster.paint(2, 0, [1, 2, 3, 255]));
        assert!(!raster.paint(0, 3, [1, 2, 3, 255]));
    }

    /// {
    ///   責務: [sample_outside_resolution_returns_an_error: 範囲外標本をエラーにすることを回帰検証する]
    ///   処理: [
    ///     1: 対象の画像・状態を用意する
    ///     2: 範囲外標本をエラーにする操作を実行し期待結果をassertで比較する
    ///   ]
    ///   引数: []
    ///   戻り値: [なし、不一致ならテストを失敗させる]
    /// }
    #[test]
    fn sample_outside_resolution_returns_an_error() {
        let raster = raster(2, 3);

        assert_eq!(
            raster.sample(2, 0),
            Err(RasterError::CoordinateOutOfBounds { x: 2, y: 0 })
        );
    }

    /// {
    ///   責務: [rejects_dimensions_above_the_storage_limit: 保存可能な寸法上限を超える画像を拒否することを回帰検証する]
    ///   処理: [
    ///     1: 対象の画像・状態を用意する
    ///     2: 保存可能な寸法上限を超える画像を拒否する操作を実行し期待結果をassertで比較する
    ///   ]
    ///   引数: []
    ///   戻り値: [なし、不一致ならテストを失敗させる]
    /// }
    #[test]
    fn rejects_dimensions_above_the_storage_limit() {
        let resolution = Resolution::new(MAX_DIMENSION + 1, 1).unwrap();

        assert_eq!(
            Raster::new(resolution),
            Err(RasterError::DimensionLimitExceeded {
                width: MAX_DIMENSION + 1,
                height: 1
            })
        );
    }

    /// {
    ///   責務: [rejects_pixel_count_above_the_storage_budget: 保存画素数の予算超過を拒否することを回帰検証する]
    ///   処理: [
    ///     1: 対象の画像・状態を用意する
    ///     2: 保存画素数の予算超過を拒否する操作を実行し期待結果をassertで比較する
    ///   ]
    ///   引数: []
    ///   戻り値: [なし、不一致ならテストを失敗させる]
    /// }
    #[test]
    fn rejects_pixel_count_above_the_storage_budget() {
        let resolution = Resolution::new(MAX_DIMENSION, MAX_DIMENSION).unwrap();

        assert_eq!(
            Raster::new(resolution),
            Err(RasterError::PixelBudgetExceeded)
        );
    }
}
