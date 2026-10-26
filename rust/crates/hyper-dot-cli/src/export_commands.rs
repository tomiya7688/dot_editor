//! `export` commands: render the visible layers to a PNG file.

use std::path::PathBuf;

use hyper_dot_core::layered_canvas::LayeredCanvas;
use serde_json::json;

use crate::cli_error::CliError;
use crate::command_input::resolution_of;
use crate::command_spec::ExportPlan;
use crate::document_summary::size;
use crate::parsed_command::{ParsedCommand, parse_unsigned};

/// {
///   責務: [render_png: 表示中のレイヤーを合成したPNGの書き出し内容を作る]
///   処理: [
///     1: --outputの有無と、--sizeと--resolutionの同時指定を検査する
///     2: 自然な解像度・指定解像度の保持細部・正方形への拡大のいずれかで合成する
///     3: PNGのバイト列と結果の概要を書き出し計画にまとめる
///   ]
///   引数: [
///     command: 解析済みコマンド
///     document: 読み込み済みの作品
///   ]
///   戻り値: [書き出し計画、指定の誤りや描画予算超過は失敗]
/// }
pub fn render_png(
    command: &ParsedCommand,
    document: &LayeredCanvas,
) -> Result<ExportPlan, CliError> {
    let output = command
        .flag_values("--output")
        .ok_or_else(|| CliError::usage("export render needs --output PATH"))?;
    let (raster, mode) = match (
        command.flag_values("--size"),
        command.flag_values("--resolution"),
    ) {
        (Some(_), Some(_)) => {
            return Err(CliError::usage("choose --size or --resolution, not both"));
        }
        (Some(values), None) => {
            let side = resolution_of(
                parse_unsigned("--size", &values[0])?,
                parse_unsigned("--size", &values[0])?,
            )?;
            (document.composite_scaled(side)?, "scaled")
        }
        (None, Some(values)) => {
            let target = resolution_of(
                parse_unsigned("--resolution width", &values[0])?,
                parse_unsigned("--resolution height", &values[1])?,
            )?;
            (document.render_at(target)?, "resolution")
        }
        (None, None) => (document.composite()?, "native"),
    };
    let bytes = raster.to_png()?;
    Ok(ExportPlan {
        path: PathBuf::from(&output[0]),
        result: json!({
            "output": output[0],
            "mode": mode,
            "size": size(raster.resolution()),
            "bytes": bytes.len(),
        }),
        bytes,
    })
}
