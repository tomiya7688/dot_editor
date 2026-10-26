//! Failures reported by the command line, with stable machine-readable codes.

use hyper_dot_core::canvas::CanvasError;
use hyper_dot_core::layer_error::LayerError;
use hyper_dot_core::project_json::ProjectJsonError;
use hyper_dot_core::raster::RasterError;

/// Exit status for a runtime or project failure.
pub const EXIT_FAILURE: u8 = 1;
/// Exit status for a usage or argument error.
pub const EXIT_USAGE: u8 = 2;

/// {
///   責務: [CliError: 終了値・機械可読な種別・人が読む説明を持つ失敗を表す]
///   フィールド: [
///     exit_code: プロセスの終了値。1は実行失敗、2は使い方の誤り
///     code: 変わらない英小文字の種別名
///     message: 利用者向けの説明
///   ]
/// }
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct CliError {
    pub exit_code: u8,
    pub code: &'static str,
    pub message: String,
}

impl CliError {
    /// {
    ///   責務: [usage: コマンドの使い方の誤りを作る]
    ///   処理: [
    ///     1: 終了値2とusage種別で失敗を構成する
    ///   ]
    ///   引数: [
    ///     message: 何が誤りかの説明
    ///   ]
    ///   戻り値: [使い方の誤り]
    /// }
    pub fn usage(message: impl Into<String>) -> Self {
        Self {
            exit_code: EXIT_USAGE,
            code: "usage",
            message: message.into(),
        }
    }

    /// {
    ///   責務: [failure: 実行時またはプロジェクトの失敗を作る]
    ///   処理: [
    ///     1: 終了値1と指定した種別で失敗を構成する
    ///   ]
    ///   引数: [
    ///     code: 機械可読な種別名
    ///     message: 何が失敗したかの説明
    ///   ]
    ///   戻り値: [実行失敗]
    /// }
    pub fn failure(code: &'static str, message: impl Into<String>) -> Self {
        Self {
            exit_code: EXIT_FAILURE,
            code,
            message: message.into(),
        }
    }
}

/// {
///   責務: [raster_code: ラスタ・座標の失敗を種別名へ対応づける]
///   処理: [
///     1: 範囲外の座標とそれ以外の予算・確保の失敗を分ける
///   ]
///   引数: [
///     error: コアが返したラスタエラー
///   ]
///   戻り値: [種別名]
/// }
fn raster_code(error: &RasterError) -> &'static str {
    match error {
        RasterError::CoordinateOutOfBounds { .. } => "out_of_bounds",
        _ => "resource_limit",
    }
}

/// {
///   責務: [canvas_code: Canvasの失敗を種別名へ対応づける]
///   処理: [
///     1: 座標・領域・分割状態・予算の失敗をそれぞれの種別名にする
///   ]
///   引数: [
///     error: コアが返したCanvasエラー
///   ]
///   戻り値: [種別名]
/// }
fn canvas_code(error: &CanvasError) -> &'static str {
    match error {
        CanvasError::Raster(raster) => raster_code(raster),
        CanvasError::InvalidRegionSize | CanvasError::RegionOutOfBounds { .. } => "invalid_region",
        CanvasError::ChildCoordinateOutOfBounds { .. } => "invalid_child",
        CanvasError::CellNotSplit { .. } | CanvasError::CellNotExpanded { .. } => "cell_not_split",
        CanvasError::SplitLimitExceeded
        | CanvasError::SplitResolutionOverflow
        | CanvasError::AllocationFailed
        | CanvasError::HistoryAllocationFailed
        | CanvasError::Field(_) => "resource_limit",
    }
}

impl From<LayerError> for CliError {
    /// {
    ///   責務: [from: レイヤー作品の失敗をCLIの失敗へ変換する]
    ///   処理: [
    ///     1: 種別ごとに安定した種別名を選び、コアの説明文を添える
    ///   ]
    ///   引数: [
    ///     error: コアが返したレイヤーエラー
    ///   ]
    ///   戻り値: [CLIの実行失敗]
    /// }
    fn from(error: LayerError) -> Self {
        let code = match &error {
            LayerError::Canvas(canvas) => canvas_code(canvas),
            LayerError::EmptyName => "invalid_layer_name",
            LayerError::DuplicateName(_) => "duplicate_layer",
            LayerError::NoSuchLayer(_) => "no_such_layer",
            LayerError::TooManyLayers => "too_many_layers",
            LayerError::LastLayer => "last_layer",
            LayerError::HistoryAllocationFailed => "resource_limit",
            LayerError::ExportSmallerThanNative => "invalid_export_size",
        };
        Self::failure(code, error.to_string())
    }
}

impl From<CanvasError> for CliError {
    /// {
    ///   責務: [from: Canvasの失敗をCLIの失敗へ変換する]
    ///   処理: [
    ///     1: 種別名を選び、コアの説明文を添える
    ///   ]
    ///   引数: [
    ///     error: コアが返したCanvasエラー
    ///   ]
    ///   戻り値: [CLIの実行失敗]
    /// }
    fn from(error: CanvasError) -> Self {
        Self::failure(canvas_code(&error), error.to_string())
    }
}

impl From<RasterError> for CliError {
    /// {
    ///   責務: [from: ラスタの失敗をCLIの失敗へ変換する]
    ///   処理: [
    ///     1: 種別名を選び、コアの説明文を添える
    ///   ]
    ///   引数: [
    ///     error: コアが返したラスタエラー
    ///   ]
    ///   戻り値: [CLIの実行失敗]
    /// }
    fn from(error: RasterError) -> Self {
        Self::failure(raster_code(&error), error.to_string())
    }
}

impl From<ProjectJsonError> for CliError {
    /// {
    ///   責務: [from: プロジェクトJSONの失敗をCLIの失敗へ変換する]
    ///   処理: [
    ///     1: 文書の不正はinvalid_projectにし、残りは予算・直列化の失敗にする
    ///   ]
    ///   引数: [
    ///     error: コアが返したJSONエラー
    ///   ]
    ///   戻り値: [CLIの実行失敗]
    /// }
    fn from(error: ProjectJsonError) -> Self {
        let message = error.to_string();
        match error {
            ProjectJsonError::Raster(raster) => Self::from(raster),
            ProjectJsonError::Canvas(canvas) => Self::from(canvas),
            _ => Self::failure("invalid_project", message),
        }
    }
}
