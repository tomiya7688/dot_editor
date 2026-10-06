use std::error::Error;
use std::fmt::{Display, Formatter};

use crate::canvas::CanvasError;
use crate::raster::RasterError;

/// {
///   責務: [ProjectJsonError: 文書JSONの読み書き失敗を分類する]
///   フィールド: [
///     Raster: 描画エラー
///     Canvas: 編集状態のエラー
///     CoordinateLimitExceeded: 保存形式の有理座標上限
///     Json: JSON構文・直列化エラー
///     Invalid: 不正文書の理由
///   ]
/// }
#[derive(Debug)]
pub enum ProjectJsonError {
    Raster(RasterError),
    Canvas(CanvasError),
    CoordinateLimitExceeded,
    Json(serde_json::Error),
    Invalid(&'static str),
}

impl From<RasterError> for ProjectJsonError {
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

impl From<CanvasError> for ProjectJsonError {
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
    fn from(error: CanvasError) -> Self {
        Self::Canvas(error)
    }
}

impl From<serde_json::Error> for ProjectJsonError {
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
    fn from(error: serde_json::Error) -> Self {
        Self::Json(error)
    }
}

impl Display for ProjectJsonError {
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
            Self::Canvas(error) => Display::fmt(error, formatter),
            Self::CoordinateLimitExceeded => {
                formatter.write_str("patch coordinate exceeds the project JSON limit")
            }
            Self::Json(error) => Display::fmt(error, formatter),
            Self::Invalid(message) => formatter.write_str(message),
        }
    }
}

impl Error for ProjectJsonError {
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
            Self::Canvas(error) => Some(error),
            Self::Json(error) => Some(error),
            Self::CoordinateLimitExceeded => None,
            Self::Invalid(_) => None,
        }
    }
}
