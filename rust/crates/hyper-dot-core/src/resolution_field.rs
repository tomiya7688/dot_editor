//! Resolution-independent field with exact, locally clipped raster patches.

use std::error::Error;
use std::fmt::{Display, Formatter};
use std::sync::Arc;

use crate::field_bounds::FieldBounds;
use crate::field_patch::FieldPatch;
use crate::raster::{Color, Raster, RasterError};
use crate::rational_coordinate::RationalCoordinate as Coordinate;
use crate::resolution::Resolution;

const MAX_PATCHES: usize = 4096;
const MAX_STORED_PIXELS: usize = 16_777_216;
const MAX_OFFSET: i64 = 1_000_000;

/// {
///   責務: [DetailPolicy: 編集時の保持細部の扱いを選択する]
///   フィールド: [
///     Preserve: 元標本へ色差分を加えて細部を維持する
///     Discard: 編集セルを現在色で置き換えて細部を破棄する
///   ]
/// }
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum DetailPolicy {
    Preserve,
    Discard,
}

/// {
///   責務: [ResolutionFieldError: 局所保持フィールドの編集失敗を分類する]
///   フィールド: [
///     Raster: 描画・座標エラー
///     PatchBudgetExceeded: パッチ数上限
///     StoredPixelBudgetExceeded: 保持画素数上限
///     OffsetLimitExceeded: 未飽和色差分の絶対値上限
///   ]
/// }
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum ResolutionFieldError {
    Raster(RasterError),
    PatchBudgetExceeded,
    StoredPixelBudgetExceeded,
    OffsetLimitExceeded,
}

#[cfg(test)]
mod tests {
    use super::*;

    /// {
    ///   責務: [whole_canvas_discard_drops_old_raster_storage: 全面破棄で古いラスタの保存領域を解放することを回帰検証する]
    ///   処理: [
    ///     1: 対象の画像・状態を用意する
    ///     2: 全面破棄で古いラスタの保存領域を解放する操作を実行し期待結果をassertで比較する
    ///   ]
    ///   引数: []
    ///   戻り値: [なし、不一致ならテストを失敗させる]
    /// }
    #[test]
    fn whole_canvas_discard_drops_old_raster_storage() {
        let source = Raster::new(Resolution::new(16, 16).unwrap()).unwrap();
        let mut field = ResolutionField::from_raster(source);
        assert!(
            field
                .discard_detail(Resolution::new(1, 1).unwrap(), 0, 0)
                .unwrap()
        );
        assert_eq!(field.patches.len(), 1);
        assert_eq!(field.patches[0].stored_pixels(), 1);
        assert_eq!(field.retained_resolution(), Resolution::new(1, 1).unwrap());
    }

    /// {
    ///   責務: [patch_budget_failure_is_atomic: パッチ予算の失敗を原子的に扱うことを回帰検証する]
    ///   処理: [
    ///     1: 対象の画像・状態を用意する
    ///     2: パッチ予算の失敗を原子的に扱う操作を実行し期待結果をassertで比較する
    ///   ]
    ///   引数: []
    ///   戻り値: [なし、不一致ならテストを失敗させる]
    /// }
    #[test]
    fn patch_budget_failure_is_atomic() {
        let grid = Resolution::new(MAX_PATCHES as u32, 1).unwrap();
        let patches = (0..grid.width())
            .map(|x| FieldPatch::solid(FieldBounds::cell(grid, x, 0), grid, [0; 4]))
            .collect();
        let mut field = ResolutionField {
            patches: Arc::new(patches),
        };
        let before = field.clone();
        let finer = Resolution::new(2 * grid.width(), 1).unwrap();
        assert_eq!(
            field.paint(finer, 0, 0, [255; 4], DetailPolicy::Discard),
            Err(ResolutionFieldError::PatchBudgetExceeded)
        );
        assert_eq!(field, before);
        assert_eq!(field.sample(finer, 0, 0), Ok([0; 4]));
    }
}

impl From<RasterError> for ResolutionFieldError {
    /// {
    ///   責務: [from: 元のエラーをこの型の対応する種別へ変換する]
    ///   処理: [
    ///     1: 入力エラーを対応する列挙値に包む
    ///   ]
    ///   引数: [
    ///     error: 変換する元エラー
    ///   ]
    ///   戻り値: [変換後のエラー]
    /// }
    fn from(error: RasterError) -> Self {
        Self::Raster(error)
    }
}

impl Display for ResolutionFieldError {
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
            Self::Raster(error) => Display::fmt(error, formatter),
            Self::PatchBudgetExceeded => {
                formatter.write_str("retained field exceeds its patch budget")
            }
            Self::StoredPixelBudgetExceeded => {
                formatter.write_str("retained field exceeds its stored pixel budget")
            }
            Self::OffsetLimitExceeded => {
                formatter.write_str("retained color offset exceeds its safety limit")
            }
        }
    }
}

impl Error for ResolutionFieldError {
    /// {
    ///   責務: [source: 連鎖する内部エラーを取得する]
    ///   処理: [
    ///     1: 内部エラーを持つ種別なら参照を返し、それ以外はNoneを返す
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///   ]
    ///   戻り値: [内部エラーの参照またはNone]
    /// }
    fn source(&self) -> Option<&(dyn Error + 'static)> {
        match self {
            Self::Raster(error) => Some(error),
            _ => None,
        }
    }
}

/// A partition of retained samples independent of the logical display grid.
/// Clones share an immutable snapshot; an edit installs a new partition only
/// after all cropping, allocation and budget checks succeed.
/// {
///   責務: [ResolutionField: 単位領域を覆う共有パッチから任意解像度の色を読む]
///   フィールド: [
///     patches: 重複・欠落のない共有パッチ配列
///   ]
/// }
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ResolutionField {
    pub(crate) patches: Arc<Vec<FieldPatch>>,
}

impl ResolutionField {
    /// {
    ///   責務: [from_raster: ラスタをCanvas全体の保持フィールドにする]
    ///   処理: [
    ///     1: 全体ラスタパッチを一つ作る
    ///     2: 共有可能なパッチ配列へ格納する
    ///   ]
    ///   引数: [
    ///     source: 保持する元RGBAラスタ
    ///   ]
    ///   戻り値: [保持フィールド]
    /// }
    pub fn from_raster(source: Raster) -> Self {
        Self {
            patches: Arc::new(vec![FieldPatch::from_raster(source)]),
        }
    }

    /// {
    ///   責務: [retained_resolution: 保持パッチの最大密度を解像度として要約する]
    ///   処理: [
    ///     1: 各パッチの縦横の最大値を求める
    ///     2: 正の解像度を構成する
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///   ]
    ///   戻り値: [保持解像度の要約]
    /// }
    pub fn retained_resolution(&self) -> Resolution {
        let width = self.patches.iter().map(|p| p.grid.width()).max().unwrap();
        let height = self.patches.iter().map(|p| p.grid.height()).max().unwrap();
        Resolution::new(width, height).expect("a field always has nonempty positive patches")
    }

    /// Samples at the exact center of a cell on the requested logical grid.
    /// {
    ///   責務: [sample: 論理セル中心の保持色をRGBA範囲内へ変換する]
    ///   処理: [
    ///     1: 未飽和の保持色を読む
    ///     2: 各成分を0から255へ制限する
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///     resolution: 対象の解像度
    ///     x: 横座標
    ///     y: 縦座標
    ///   ]
    ///   戻り値: [RGBAまたは座標エラー]
    /// }
    pub fn sample(&self, resolution: Resolution, x: u32, y: u32) -> Result<Color, RasterError> {
        let raw = self.sample_raw(resolution, x, y)?;
        Ok(raw.map(|channel| channel.clamp(0, 255) as u8))
    }

    /// {
    ///   責務: [sample_raw: 論理セル中心に対応する未飽和保持色を読む]
    ///   処理: [
    ///     1: 座標を検証して正確な中心を計算する
    ///     2: 中心を含むパッチの元色と色差分を読む
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///     resolution: 対象の解像度
    ///     x: 横座標
    ///     y: 縦座標
    ///   ]
    ///   戻り値: [未飽和の色成分または座標エラー]
    /// }
    fn sample_raw(&self, resolution: Resolution, x: u32, y: u32) -> Result<[i64; 4], RasterError> {
        if x >= resolution.width() || y >= resolution.height() {
            return Err(RasterError::CoordinateOutOfBounds { x, y });
        }
        let cx = Coordinate::center(x, resolution.width());
        let cy = Coordinate::center(y, resolution.height());
        Ok(self
            .patches
            .iter()
            .find(|patch| patch.bounds.contains(cx, cy))
            .expect("retained patches partition the full canvas")
            .sample_raw(cx, cy))
    }

    /// {
    ///   責務: [sample_raw_cell: Canvas編集用にセルの未飽和色を取得する]
    ///   処理: [
    ///     1: 内部の未飽和サンプリングへ委譲する
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///     resolution: 対象の解像度
    ///     x: 横座標
    ///     y: 縦座標
    ///   ]
    ///   戻り値: [未飽和の色成分または座標エラー]
    /// }
    pub(crate) fn sample_raw_cell(
        &self,
        resolution: Resolution,
        x: u32,
        y: u32,
    ) -> Result<[i64; 4], RasterError> {
        self.sample_raw(resolution, x, y)
    }

    /// Builds a projected raster without replacing or resampling retained data.
    /// {
    ///   責務: [render: 保持情報を変更せず指定解像度へ投影する]
    ///   処理: [
    ///     1: 描画ラスタを確保する
    ///     2: 各画素中心で保持色を読んで描く
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///     resolution: 対象の解像度
    ///   ]
    ///   戻り値: [投影ラスタまたは描画エラー]
    /// }
    pub fn render(&self, resolution: Resolution) -> Result<Raster, RasterError> {
        let mut output = Raster::new(resolution)?;
        for y in 0..resolution.height() {
            for x in 0..resolution.width() {
                output.paint(x, y, self.sample(resolution, x, y)?);
            }
        }
        Ok(output)
    }

    /// {
    ///   責務: [has_detail_at: 指定セルより細かいパッチ情報があるか判定する]
    ///   処理: [
    ///     1: 座標を検証してセル範囲を求める
    ///     2: 交差パッチ数と画素密度を調べる
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///     grid: 座標を解釈するグリッド
    ///     x: 横座標
    ///     y: 縦座標
    ///   ]
    ///   戻り値: [細部があればtrue、範囲外ならエラー]
    /// }
    pub fn has_detail_at(&self, grid: Resolution, x: u32, y: u32) -> Result<bool, RasterError> {
        if x >= grid.width() || y >= grid.height() {
            return Err(RasterError::CoordinateOutOfBounds { x, y });
        }
        let bounds = FieldBounds::cell(grid, x, y);
        let mut overlapping = self
            .patches
            .iter()
            .filter(|p| p.bounds.intersection(bounds).is_some());
        let first = overlapping
            .next()
            .expect("retained patches cover every logical cell");
        Ok(overlapping.next().is_some()
            || first.grid.width() > grid.width()
            || first.grid.height() > grid.height())
    }

    /// Paints one logical cell. Preserve retains fine samples as reversible raw
    /// color offsets; discard crops old support and installs a solid patch.
    /// Out-of-range writes and unchanged preserve writes return false.
    /// {
    ///   責務: [paint: 保持方針に従って1セルの空間領域を編集する]
    ///   処理: [
    ///     1: 範囲と変更の必要性を検証する
    ///     2: 外側を切り出し、保持では色差分を付ける
    ///     3: 破棄では単色へ置換し予算内の候補を採用する
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///     grid: 座標を解釈するグリッド
    ///     x: 横座標
    ///     y: 縦座標
    ///     color: 適用するRGBA色
    ///     policy: 細部を保持または破棄する方針
    ///   ]
    ///   戻り値: [変更有無または保持予算・確保エラー]
    /// }
    pub fn paint(
        &mut self,
        grid: Resolution,
        x: u32,
        y: u32,
        color: Color,
        policy: DetailPolicy,
    ) -> Result<bool, ResolutionFieldError> {
        if x >= grid.width() || y >= grid.height() {
            return Ok(false);
        }
        let detail = self.has_detail_at(grid, x, y)?;
        if self.sample(grid, x, y)? == color && !(policy == DetailPolicy::Discard && detail) {
            return Ok(false);
        }
        let preserve = policy == DetailPolicy::Preserve && detail;
        let bounds = FieldBounds::cell(grid, x, y);
        let reference = self.sample_raw(grid, x, y)?;
        let delta: [i64; 4] = std::array::from_fn(|i| i64::from(color[i]) - reference[i]);
        let mut patches = Vec::new();
        patches
            .try_reserve_exact((self.patches.len() * 5 + 1).min(MAX_PATCHES))
            .map_err(|_| RasterError::AllocationFailed)?;
        let mut pixels = 0;
        for patch in self.patches.iter() {
            if let Some(overlap) = patch.bounds.intersection(bounds) {
                for remainder in patch.bounds.outside(overlap) {
                    Self::push_checked(&mut patches, &mut pixels, patch.cropped(remainder)?)?;
                }
                if preserve {
                    let mut shifted = patch.cropped(overlap)?;
                    for (offset, change) in shifted.offset.iter_mut().zip(delta) {
                        *offset += change;
                        if offset.abs() > MAX_OFFSET {
                            return Err(ResolutionFieldError::OffsetLimitExceeded);
                        }
                    }
                    Self::push_checked(&mut patches, &mut pixels, shifted)?;
                }
            } else {
                Self::push_checked(&mut patches, &mut pixels, patch.clone())?;
            }
        }
        if !preserve {
            Self::push_checked(
                &mut patches,
                &mut pixels,
                FieldPatch::solid(bounds, grid, color),
            )?;
        }
        self.patches = Arc::new(patches);
        Ok(true)
    }

    /// {
    ///   責務: [erase: 指定領域を透明色で編集する]
    ///   処理: [
    ///     1: 透明黒を使って局所描画へ委譲する
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///     grid: 座標を解釈するグリッド
    ///     x: 横座標
    ///     y: 縦座標
    ///     policy: 細部を保持または破棄する方針
    ///   ]
    ///   戻り値: [変更有無または局所編集エラー]
    /// }
    pub fn erase(
        &mut self,
        grid: Resolution,
        x: u32,
        y: u32,
        policy: DetailPolicy,
    ) -> Result<bool, ResolutionFieldError> {
        self.paint(grid, x, y, [0; 4], policy)
    }

    /// {
    ///   責務: [discard_detail: 表示色を維持してセルの細部だけを破棄する]
    ///   処理: [
    ///     1: 細部の存在を確認して表示色を取得する
    ///     2: 破棄方針で局所描画する
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///     grid: 座標を解釈するグリッド
    ///     x: 横座標
    ///     y: 縦座標
    ///   ]
    ///   戻り値: [変更有無または座標・編集エラー]
    /// }
    pub fn discard_detail(
        &mut self,
        grid: Resolution,
        x: u32,
        y: u32,
    ) -> Result<bool, ResolutionFieldError> {
        if !self.has_detail_at(grid, x, y)? {
            return Ok(false);
        }
        self.paint(grid, x, y, self.sample(grid, x, y)?, DetailPolicy::Discard)
    }

    /// {
    ///   責務: [push_checked: 保持予算を検査して候補パッチへ追加する]
    ///   処理: [
    ///     1: パッチ数と総保存画素数を検査する
    ///     2: 予算内なら候補配列へ追加する
    ///   ]
    ///   引数: [
    ///     patches: 追加先の候補パッチ配列
    ///     pixels: 追加済み保持画素数の累計
    ///     patch: 直列化する保持パッチ
    ///   ]
    ///   戻り値: [成功時は単位値、予算超過ならエラー]
    /// }
    fn push_checked(
        patches: &mut Vec<FieldPatch>,
        pixels: &mut usize,
        patch: FieldPatch,
    ) -> Result<(), ResolutionFieldError> {
        if patches.len() == MAX_PATCHES {
            return Err(ResolutionFieldError::PatchBudgetExceeded);
        }
        *pixels += patch.stored_pixels();
        if *pixels > MAX_STORED_PIXELS {
            return Err(ResolutionFieldError::StoredPixelBudgetExceeded);
        }
        patches.push(patch);
        Ok(())
    }
}
