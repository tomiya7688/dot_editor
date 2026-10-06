//! Logical canvas dimensions shared by project data and rendering operations.

use std::error::Error;
use std::fmt::{Display, Formatter};

/// A positive logical width and height. This value does not allocate a pixel buffer.
/// {
///   責務: [Resolution: バッファを確保せず正の論理寸法を表す]
///   フィールド: [
///     width: 正の幅
///     height: 正の高さ
///   ]
/// }
#[derive(Clone, Copy, Debug, Eq, Hash, PartialEq)]
pub struct Resolution {
    width: u32,
    height: u32,
}

/// {
///   責務: [ResolutionError: 解像度のゼロ寸法を区別する]
///   フィールド: [
///     ZeroWidth: 幅がゼロ
///     ZeroHeight: 高さがゼロ
///   ]
/// }
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum ResolutionError {
    ZeroWidth,
    ZeroHeight,
}

impl Resolution {
    /// {
    ///   責務: [new: 正の論理解像度を構成する]
    ///   処理: [
    ///     1: 幅と高さが0でないことを確認する
    ///     2: 縦横を格納する
    ///   ]
    ///   引数: [
    ///     width: 対象領域の幅
    ///     height: 対象領域の高さ
    ///   ]
    ///   戻り値: [解像度または幅・高さ0のエラー]
    /// }
    pub const fn new(width: u32, height: u32) -> Result<Self, ResolutionError> {
        if width == 0 {
            return Err(ResolutionError::ZeroWidth);
        }
        if height == 0 {
            return Err(ResolutionError::ZeroHeight);
        }
        Ok(Self { width, height })
    }

    /// {
    ///   責務: [width: 解像度の幅を取得する]
    ///   処理: [
    ///     1: 保存した幅を返す
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///   ]
    ///   戻り値: [幅]
    /// }
    pub const fn width(self) -> u32 {
        self.width
    }

    /// {
    ///   責務: [height: 解像度の高さを取得する]
    ///   処理: [
    ///     1: 保存した高さを返す
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///   ]
    ///   戻り値: [高さ]
    /// }
    pub const fn height(self) -> u32 {
        self.height
    }
}

impl Display for ResolutionError {
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
            Self::ZeroWidth => formatter.write_str("resolution width must be greater than zero"),
            Self::ZeroHeight => formatter.write_str("resolution height must be greater than zero"),
        }
    }
}

impl Error for ResolutionError {}

#[cfg(test)]
mod tests {
    use super::{Resolution, ResolutionError};

    /// {
    ///   責務: [accepts_non_square_resolution: 非正方形の解像度を許可することを回帰検証する]
    ///   処理: [
    ///     1: 対象の画像・状態を用意する
    ///     2: 非正方形の解像度を許可する操作を実行し期待結果をassertで比較する
    ///   ]
    ///   引数: []
    ///   戻り値: [なし、不一致ならテストを失敗させる]
    /// }
    #[test]
    fn accepts_non_square_resolution() {
        let resolution = Resolution::new(23, 17).expect("positive dimensions are valid");

        assert_eq!(resolution.width(), 23);
        assert_eq!(resolution.height(), 17);
    }

    /// {
    ///   責務: [accepts_single_pixel_resolution: 1画素の解像度を許可することを回帰検証する]
    ///   処理: [
    ///     1: 対象の画像・状態を用意する
    ///     2: 1画素の解像度を許可する操作を実行し期待結果をassertで比較する
    ///   ]
    ///   引数: []
    ///   戻り値: [なし、不一致ならテストを失敗させる]
    /// }
    #[test]
    fn accepts_single_pixel_resolution() {
        assert_eq!(Resolution::new(1, 1).unwrap().width(), 1);
    }

    /// {
    ///   責務: [rejects_zero_width: 幅ゼロを拒否することを回帰検証する]
    ///   処理: [
    ///     1: 対象の画像・状態を用意する
    ///     2: 幅ゼロを拒否する操作を実行し期待結果をassertで比較する
    ///   ]
    ///   引数: []
    ///   戻り値: [なし、不一致ならテストを失敗させる]
    /// }
    #[test]
    fn rejects_zero_width() {
        assert_eq!(Resolution::new(0, 17), Err(ResolutionError::ZeroWidth));
    }

    /// {
    ///   責務: [rejects_zero_height: 高さゼロを拒否することを回帰検証する]
    ///   処理: [
    ///     1: 対象の画像・状態を用意する
    ///     2: 高さゼロを拒否する操作を実行し期待結果をassertで比較する
    ///   ]
    ///   引数: []
    ///   戻り値: [なし、不一致ならテストを失敗させる]
    /// }
    #[test]
    fn rejects_zero_height() {
        assert_eq!(Resolution::new(23, 0), Err(ResolutionError::ZeroHeight));
    }
}
