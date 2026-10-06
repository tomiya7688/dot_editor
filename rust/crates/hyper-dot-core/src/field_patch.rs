use std::sync::Arc;

use crate::field_bounds::FieldBounds;
use crate::raster::{Color, Raster, RasterError};
use crate::rational_coordinate::RationalCoordinate as Coordinate;
use crate::resolution::Resolution;

/// {
///   責務: [PatchSource: パッチの未補正色と元の画素境界を保持する]
///   フィールド: [
///     Raster.raster: 共有する切り出し画像
///     Raster.origin_x・origin_y: 元画像上の切り出し開始位置
///     Raster.extent: 元画像の空間範囲
///     Raster.original_size: 元画像の寸法
///     Solid: 単色RGBA
///   ]
/// }
#[derive(Clone, Debug, Eq, PartialEq)]
enum PatchSource {
    Raster {
        raster: Arc<Raster>,
        origin_x: u32,
        origin_y: u32,
        extent: FieldBounds,
        original_size: Resolution,
    },
    Solid(Color),
}

/// {
///   責務: [FieldPatch: 局所領域の元色・標本密度・未飽和の色差分を保持する]
///   フィールド: [
///     bounds: 表示対象の切り出し範囲
///     grid: 保持解像度の要約
///     offset: RGBA各成分の未飽和差分
///     source: 単色または元画像
///   ]
/// }
#[derive(Clone, Debug, Eq, PartialEq)]
pub(crate) struct FieldPatch {
    pub(crate) bounds: FieldBounds,
    pub(crate) grid: Resolution,
    pub(crate) offset: [i64; 4],
    source: PatchSource,
}

impl FieldPatch {
    /// Stored source extent, before clipping, with unshifted source pixels.
    /// {
    ///   責務: [source_data: 元画素と切り取り前の正確な画像範囲を公開する]
    ///   処理: [
    ///     1: 単色なら現在領域と色を返す
    ///     2: ラスタなら元範囲から保存画素の端を補間する
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///   ]
    ///   戻り値: [元画像範囲・ラスタ参照・単色色]
    /// }
    pub(crate) fn source_data(&self) -> (FieldBounds, Option<&Raster>, Color) {
        match &self.source {
            PatchSource::Solid(color) => (self.bounds, None, *color),
            PatchSource::Raster {
                raster,
                origin_x,
                origin_y,
                extent,
                original_size,
            } => {
                let size = raster.resolution();
                let extent = FieldBounds {
                    left: Coordinate::interpolate(
                        extent.left,
                        extent.right,
                        *origin_x,
                        original_size.width(),
                    ),
                    top: Coordinate::interpolate(
                        extent.top,
                        extent.bottom,
                        *origin_y,
                        original_size.height(),
                    ),
                    right: Coordinate::interpolate(
                        extent.left,
                        extent.right,
                        origin_x + size.width(),
                        original_size.width(),
                    ),
                    bottom: Coordinate::interpolate(
                        extent.top,
                        extent.bottom,
                        origin_y + size.height(),
                        original_size.height(),
                    ),
                };
                (extent, Some(raster), [0; 4])
            }
        }
    }

    /// {
    ///   責務: [from_raster: Canvas全体を覆うラスタパッチを作る]
    ///   処理: [
    ///     1: 元の画像寸法と単位領域を保存する
    ///     2: 色差分と切り取り原点を0にする
    ///   ]
    ///   引数: [
    ///     source: 保持する元RGBAラスタ
    ///   ]
    ///   戻り値: [新しい保持パッチ]
    /// }
    pub(crate) fn from_raster(source: Raster) -> Self {
        let original_size = source.resolution();
        Self {
            bounds: FieldBounds::full(),
            grid: source.resolution(),
            offset: [0; 4],
            source: PatchSource::Raster {
                raster: Arc::new(source),
                origin_x: 0,
                origin_y: 0,
                extent: FieldBounds::full(),
                original_size,
            },
        }
    }

    /// {
    ///   責務: [from_source: 検証済みJSONの元範囲・画素・色差分を復元する]
    ///   処理: [
    ///     1: 範囲内の画素密度から要約解像度を求める
    ///     2: 元画像範囲とサイズを保持してラスタを共有する
    ///   ]
    ///   引数: [
    ///     bounds: 処理する正規化長方形
    ///     extent: 元画像に対応する空間範囲
    ///     raster: 元となるRGBAラスタ
    ///     offset: RGBA成分の未飽和差分
    ///   ]
    ///   戻り値: [復元した保持パッチ]
    /// }
    pub(crate) fn from_source(
        bounds: FieldBounds,
        extent: FieldBounds,
        raster: Raster,
        offset: [i64; 4],
    ) -> Self {
        let original_size = raster.resolution();
        let grid = Resolution::new(
            Coordinate::density(extent.left, extent.right, original_size.width()),
            Coordinate::density(extent.top, extent.bottom, original_size.height()),
        )
        .expect("positive source extent and dimensions");
        Self {
            bounds,
            grid,
            offset,
            source: PatchSource::Raster {
                raster: Arc::new(raster),
                origin_x: 0,
                origin_y: 0,
                extent,
                original_size,
            },
        }
    }

    /// {
    ///   責務: [solid: 局所領域を単色で保持するパッチを作る]
    ///   処理: [
    ///     1: 領域・解像度と単色を格納する
    ///     2: 色差分を0にする
    ///   ]
    ///   引数: [
    ///     bounds: 処理する正規化長方形
    ///     grid: 座標を解釈するグリッド
    ///     color: 適用するRGBA色
    ///   ]
    ///   戻り値: [単色保持パッチ]
    /// }
    pub(crate) fn solid(bounds: FieldBounds, grid: Resolution, color: Color) -> Self {
        Self {
            bounds,
            grid,
            offset: [0; 4],
            source: PatchSource::Solid(color),
        }
    }

    /// {
    ///   責務: [sample_raw: パッチ内の元色と未飽和の色差分を読む]
    ///   処理: [
    ///     1: 単色または元画像範囲に対応する画素を取得する
    ///     2: 各色成分へ保持差分を足す
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///     x: 横座標
    ///     y: 縦座標
    ///   ]
    ///   戻り値: [範囲制限前のRGBA成分]
    /// }
    pub(crate) fn sample_raw(&self, x: Coordinate, y: Coordinate) -> [i64; 4] {
        let color = match &self.source {
            PatchSource::Solid(color) => *color,
            PatchSource::Raster {
                raster,
                origin_x,
                origin_y,
                extent,
                original_size,
            } => raster
                .sample(
                    x.relative_floor(extent.left, extent.right, original_size.width()) - origin_x,
                    y.relative_floor(extent.top, extent.bottom, original_size.height()) - origin_y,
                )
                .expect("patch clip lies inside the cropped source"),
        };
        std::array::from_fn(|channel| i64::from(color[channel]) + self.offset[channel])
    }

    /// {
    ///   責務: [stored_pixels: パッチが保持する元画素数を求める]
    ///   処理: [
    ///     1: 単色は1、ラスタは保存画像の縦横積を数える
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///   ]
    ///   戻り値: [保持画素数]
    /// }
    pub(crate) fn stored_pixels(&self) -> usize {
        match &self.source {
            PatchSource::Solid(_) => 1,
            PatchSource::Raster { raster, .. } => {
                let size = raster.resolution();
                size.width() as usize * size.height() as usize
            }
        }
    }

    /// Removes inaccessible source pixels without moving their spatial boundaries.
    /// {
    ///   責務: [cropped: 画素境界を動かさず不要な元画素を除く]
    ///   処理: [
    ///     1: 元範囲から切り取りの画素端を求める
    ///     2: 必要なら元画像を切り取る
    ///     3: 元の座標系と色差分を引き継ぐ
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///     bounds: 処理する正規化長方形
    ///   ]
    ///   戻り値: [切り取り済みパッチまたはラスタ確保エラー]
    /// }
    pub(crate) fn cropped(&self, bounds: FieldBounds) -> Result<Self, RasterError> {
        let source = match &self.source {
            PatchSource::Solid(color) => PatchSource::Solid(*color),
            PatchSource::Raster {
                raster,
                origin_x,
                origin_y,
                extent,
                original_size,
            } => {
                let x0 =
                    bounds
                        .left
                        .relative_floor(extent.left, extent.right, original_size.width());
                let y0 =
                    bounds
                        .top
                        .relative_floor(extent.top, extent.bottom, original_size.height());
                let x1 =
                    bounds
                        .right
                        .relative_ceil(extent.left, extent.right, original_size.width());
                let y1 =
                    bounds
                        .bottom
                        .relative_ceil(extent.top, extent.bottom, original_size.height());
                let size = raster.resolution();
                if x0 == *origin_x
                    && y0 == *origin_y
                    && x1 == origin_x + size.width()
                    && y1 == origin_y + size.height()
                {
                    self.source.clone()
                } else {
                    let size = Resolution::new(x1 - x0, y1 - y0)
                        .expect("positive patch bounds retain at least one source pixel");
                    let mut crop = Raster::new(size)?;
                    for y in 0..size.height() {
                        for x in 0..size.width() {
                            crop.paint(x, y, raster.sample(x0 + x - origin_x, y0 + y - origin_y)?);
                        }
                    }
                    PatchSource::Raster {
                        raster: Arc::new(crop),
                        origin_x: x0,
                        origin_y: y0,
                        extent: *extent,
                        original_size: *original_size,
                    }
                }
            }
        };
        Ok(Self {
            bounds,
            grid: self.grid,
            offset: self.offset,
            source,
        })
    }
}
