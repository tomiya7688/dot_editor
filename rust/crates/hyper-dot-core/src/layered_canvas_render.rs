//! Flattening of visible layers into one RGBA raster.

use crate::alpha_composite::composite_over;
use crate::layer_error::LayerError;
use crate::layered_canvas::LayeredCanvas;
use crate::raster::{Raster, RasterError};
use crate::resolution::Resolution;

/// {
///   責務: [scale_nearest: 整数倍の最近傍拡大でラスタを目標解像度へ合わせる]
///   処理: [
///     1: 解像度が同じならそのまま返す
///     2: 出力画素ごとに、比率で対応する元画素の色を読む
///   ]
///   引数: [
///     source: 拡大するラスタ
///     target: 出力する解像度。元以上の大きさであること
///   ]
///   戻り値: [目標解像度のラスタまたは描画予算エラー]
/// }
fn scale_nearest(source: Raster, target: Resolution) -> Result<Raster, RasterError> {
    let from = source.resolution();
    if from == target {
        return Ok(source);
    }
    let mut output = Raster::new(target)?;
    for y in 0..target.height() {
        for x in 0..target.width() {
            // 整数比の拡大では、出力画素の左上が属する元画素へ切り捨てて対応する。
            let source_x = u64::from(x) * u64::from(from.width()) / u64::from(target.width());
            let source_y = u64::from(y) * u64::from(from.height()) / u64::from(target.height());
            let color = source.sample(source_x as u32, source_y as u32)?;
            output.paint(x, y, color);
        }
    }
    Ok(output)
}

impl LayeredCanvas {
    /// {
    ///   責務: [native_resolution: 展開セルを含めた作品の自然な出力解像度を求める]
    ///   処理: [
    ///     1: 全レイヤーの自然な解像度を調べる
    ///     2: いずれかが論理解像度と違えば、その2倍の解像度を返す
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///   ]
    ///   戻り値: [出力解像度または子解像度の予算エラー]
    /// }
    pub fn native_resolution(&self) -> Result<Resolution, LayerError> {
        let logical = self.resolution();
        for entry in &self.layers {
            let native = entry.canvas.native_resolution()?;
            if native != logical {
                return Ok(native);
            }
        }
        Ok(logical)
    }

    /// {
    ///   責務: [composite: 表示中のレイヤーを自然な出力解像度で合成する]
    ///   処理: [
    ///     1: 透明なラスタを出力解像度で確保する
    ///     2: 表示中の層を下から順に、展開セルを含めて描画する
    ///     3: 出力より小さい層を最近傍拡大して重ねる
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///   ]
    ///   戻り値: [合成したラスタ、失敗なら描画予算などのエラー]
    /// }
    pub fn composite(&self) -> Result<Raster, LayerError> {
        let target = self.native_resolution()?;
        let mut result = Raster::new(target)?;
        for entry in self.layers.iter().filter(|entry| entry.visible) {
            let layer = scale_nearest(entry.canvas.render_native()?, target)?;
            composite_over(&mut result, &layer)?;
        }
        Ok(result)
    }

    /// {
    ///   責務: [render_at: 各レイヤーの保持細部を指定解像度で合成する]
    ///   処理: [
    ///     1: 透明なラスタを指定解像度で確保する
    ///     2: 表示中の層を下から順に保持フィールドから直接描画して重ねる
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///     resolution: 出力する解像度
    ///   ]
    ///   戻り値: [合成したラスタ、失敗なら描画予算などのエラー]
    /// }
    pub fn render_at(&self, resolution: Resolution) -> Result<Raster, LayerError> {
        let mut result = Raster::new(resolution)?;
        for entry in self.layers.iter().filter(|entry| entry.visible) {
            composite_over(&mut result, &entry.canvas.render_at(resolution)?)?;
        }
        Ok(result)
    }
}
