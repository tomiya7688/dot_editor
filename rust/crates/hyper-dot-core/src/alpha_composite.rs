//! Straight-alpha "over" compositing that matches the Python reference.
//!
//! The integer arithmetic follows Pillow's `Image.alpha_composite` so that
//! flattened layers are byte-identical between the Rust core and the editor.

use crate::raster::{Color, Raster, RasterError};

const PRECISION_BITS: u32 = 7;

/// {
///   責務: [divide_by_255: 8bit精度の除算を丸め付きで近似する]
///   処理: [
///     1: 上位バイトを足して255で割った商に近い値を整数だけで求める
///   ]
///   引数: [
///     value: 255で割る前の値
///   ]
///   戻り値: [255で割った近似値]
/// }
const fn divide_by_255(value: u32) -> u32 {
    ((value >> 8) + value) >> 8
}

/// {
///   責務: [blend_channel: 1成分の色を重みで混ぜて8bitへ戻す]
///   処理: [
///     1: 上の層と下の層の成分を固定小数の重みで足す
///     2: 丸め項を足して255の除算と精度ビットの縮小を行う
///   ]
///   引数: [
///     source: 上の層の成分
///     destination: 下の層の成分
///     source_weight: 上の層の重み
///     destination_weight: 下の層の重み
///   ]
///   戻り値: [合成後の成分]
/// }
const fn blend_channel(
    source: u8,
    destination: u8,
    source_weight: u32,
    destination_weight: u32,
) -> u8 {
    let weighted = source as u32 * source_weight + destination as u32 * destination_weight;
    let rounded = weighted + (0x80 << PRECISION_BITS);
    (divide_by_255(rounded) >> PRECISION_BITS) as u8
}

/// {
///   責務: [blend_over: 非乗算済みRGBAの上の色を下の色へ重ねる]
///   処理: [
///     1: 上の色が完全透明なら下の色をそのまま返す
///     2: 出力アルファと上下の重みを求める
///     3: 各成分とアルファを混ぜる
///   ]
///   引数: [
///     source: 上に重ねるRGBA色
///     destination: 下にあるRGBA色
///   ]
///   戻り値: [合成後のRGBA色]
/// }
pub(crate) const fn blend_over(source: Color, destination: Color) -> Color {
    let source_alpha = source[3] as u32;
    if source_alpha == 0 {
        return destination;
    }
    // 下の層の不透明度を、上の層が隠した残りだけ寄与させる。
    let destination_alpha = destination[3] as u32;
    let output_alpha_255 = source_alpha * 255 + destination_alpha * (255 - source_alpha);
    let source_weight = source_alpha * 255 * 255 * (1 << PRECISION_BITS) / output_alpha_255;
    let destination_weight = 255 * (1 << PRECISION_BITS) - source_weight;
    [
        blend_channel(source[0], destination[0], source_weight, destination_weight),
        blend_channel(source[1], destination[1], source_weight, destination_weight),
        blend_channel(source[2], destination[2], source_weight, destination_weight),
        divide_by_255(output_alpha_255 + 0x80) as u8,
    ]
}

/// {
///   責務: [composite_over: 同じ解像度の上のラスタを下のラスタへ重ねる]
///   処理: [
///     1: 解像度が一致することを確認する
///     2: 全画素をblend_overで下のラスタへ書き込む
///   ]
///   引数: [
///     destination: 結果を受け取る下のラスタ
///     source: 上に重ねるラスタ
///   ]
///   戻り値: [成功時は単位値、解像度が違えば座標エラー]
/// }
pub(crate) fn composite_over(destination: &mut Raster, source: &Raster) -> Result<(), RasterError> {
    if destination.resolution() != source.resolution() {
        return Err(RasterError::CoordinateOutOfBounds {
            x: source.resolution().width(),
            y: source.resolution().height(),
        });
    }
    // 画素数は確保時の予算で制限済みなので、全画素を1回だけ走査する。
    for y in 0..source.resolution().height() {
        for x in 0..source.resolution().width() {
            let blended = blend_over(source.sample(x, y)?, destination.sample(x, y)?);
            destination.paint(x, y, blended);
        }
    }
    Ok(())
}
