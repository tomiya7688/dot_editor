//! Failures raised by layer structure edits and document-wide history.

use std::error::Error;
use std::fmt::{Display, Formatter};

use crate::canvas::CanvasError;
use crate::raster::RasterError;

/// {
///   責務: [LayerError: レイヤー構成の編集と合成で検出した失敗を分類する]
///   フィールド: [
///     Canvas: 選択中レイヤーの編集で起きたCanvasエラー
///     EmptyName: 空白だけのレイヤー名
///     DuplicateName: 既に存在するレイヤー名
///     NoSuchLayer: 存在しないレイヤー名
///     TooManyLayers: レイヤー数の上限超過
///     LastLayer: 最後の1層を削除しようとした失敗
///     HistoryAllocationFailed: 作品履歴の確保失敗
///     ExportSmallerThanNative: 自然な解像度より小さい書き出しサイズ
///   ]
/// }
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum LayerError {
    Canvas(CanvasError),
    EmptyName,
    DuplicateName(String),
    NoSuchLayer(String),
    TooManyLayers,
    LastLayer,
    HistoryAllocationFailed,
    ExportSmallerThanNative,
}

impl From<CanvasError> for LayerError {
    /// {
    ///   責務: [from: Canvasエラーをレイヤーエラーへ包む]
    ///   処理: [
    ///     1: Canvas種別として保持する
    ///   ]
    ///   引数: [
    ///     error: 包むCanvasエラー
    ///   ]
    ///   戻り値: [LayerError]
    /// }
    fn from(error: CanvasError) -> Self {
        Self::Canvas(error)
    }
}

impl From<RasterError> for LayerError {
    /// {
    ///   責務: [from: ラスタエラーをレイヤーエラーへ包む]
    ///   処理: [
    ///     1: Canvas経由のラスタエラーとして保持する
    ///   ]
    ///   引数: [
    ///     error: 包むラスタエラー
    ///   ]
    ///   戻り値: [LayerError]
    /// }
    fn from(error: RasterError) -> Self {
        Self::Canvas(CanvasError::Raster(error))
    }
}

impl Display for LayerError {
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
            Self::Canvas(error) => Display::fmt(error, formatter),
            Self::EmptyName => formatter.write_str("layer name must not be empty"),
            Self::DuplicateName(name) => write!(formatter, "layer already exists: {name}"),
            Self::NoSuchLayer(name) => write!(formatter, "layer does not exist: {name}"),
            Self::TooManyLayers => formatter.write_str("too many layers"),
            Self::LastLayer => formatter.write_str("at least one layer is required"),
            Self::HistoryAllocationFailed => {
                formatter.write_str("unable to allocate document history")
            }
            Self::ExportSmallerThanNative => {
                formatter.write_str("export size cannot be smaller than the native canvas size")
            }
        }
    }
}

impl Error for LayerError {
    /// {
    ///   責務: [source: 連鎖する内部エラーを取得する]
    ///   処理: [
    ///     1: Canvasエラーを持つ種別なら参照を返し、それ以外はNoneを返す
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///   ]
    ///   戻り値: [内部エラーの参照またはNone]
    /// }
    fn source(&self) -> Option<&(dyn Error + 'static)> {
        match self {
            Self::Canvas(error) => Some(error),
            _ => None,
        }
    }
}
