//! Typed readers shared by command handlers: colors, cells, child cells and policies.

use hyper_dot_core::canvas::ChildCoordinate;
use hyper_dot_core::layered_canvas::LayeredCanvas;
use hyper_dot_core::raster::Color;
use hyper_dot_core::resolution::Resolution;
use hyper_dot_core::resolution_field::DetailPolicy;

use crate::cli_error::CliError;
use crate::parsed_command::{ParsedCommand, parse_unsigned};

/// {
///   責務: [parse_color: #RRGGBBまたは#RRGGBBAAの色をRGBAへ変換する]
///   処理: [
///     1: 先頭の#を任意として除き、6桁か8桁の16進数であることを確認する
///     2: 2桁ずつ読み、アルファが省略されたら255にする
///   ]
///   引数: [
///     text: 色の文字列
///   ]
///   戻り値: [RGBA色、形式が不正なら使い方の誤り]
/// }
pub fn parse_color(text: &str) -> Result<Color, CliError> {
    let digits = text.strip_prefix('#').unwrap_or(text);
    if !matches!(digits.len(), 6 | 8) || !digits.bytes().all(|byte| byte.is_ascii_hexdigit()) {
        return Err(CliError::usage(format!(
            "color must be #RRGGBB or #RRGGBBAA, got `{text}`"
        )));
    }
    let mut color = [0, 0, 0, 255];
    for (index, pair) in digits.as_bytes().chunks_exact(2).enumerate() {
        let pair = std::str::from_utf8(pair).expect("hex digits are ASCII");
        color[index] = u8::from_str_radix(pair, 16).expect("digits were checked");
    }
    Ok(color)
}

/// {
///   責務: [format_color: RGBAを#RRGGBBAAの文字列にする]
///   処理: [
///     1: 4成分を2桁の大文字16進で並べる
///   ]
///   引数: [
///     color: RGBA色
///   ]
///   戻り値: [色の文字列]
/// }
pub fn format_color(color: Color) -> String {
    format!(
        "#{:02X}{:02X}{:02X}{:02X}",
        color[0], color[1], color[2], color[3]
    )
}

/// {
///   責務: [resolution_of: 幅と高さの引数から解像度を作る]
///   処理: [
///     1: 0を拒否して正の解像度を構成する
///   ]
///   引数: [
///     width: 幅
///     height: 高さ
///   ]
///   戻り値: [解像度、0なら実行失敗]
/// }
pub fn resolution_of(width: u32, height: u32) -> Result<Resolution, CliError> {
    Resolution::new(width, height)
        .map_err(|error| CliError::failure("invalid_resolution", error.to_string()))
}

/// {
///   責務: [check_cell: 座標が作品の論理解像度の内側か確認する]
///   処理: [
///     1: x・yを幅・高さと比較する
///   ]
///   引数: [
///     document: 対象の作品
///     x: 横座標
///     y: 縦座標
///   ]
///   戻り値: [成功時は単位値、範囲外なら実行失敗]
/// }
pub fn check_cell(document: &LayeredCanvas, x: u32, y: u32) -> Result<(), CliError> {
    let resolution = document.resolution();
    if x >= resolution.width() || y >= resolution.height() {
        return Err(CliError::failure(
            "out_of_bounds",
            format!(
                "cell ({x}, {y}) is outside the {}x{} canvas",
                resolution.width(),
                resolution.height()
            ),
        ));
    }
    Ok(())
}

/// {
///   責務: [cell: 位置引数のx・yを読み、作品の範囲内か確認する]
///   処理: [
///     1: 整数として読む
///     2: 範囲内であることを確認する
///   ]
///   引数: [
///     command: 解析済みコマンド
///     document: 対象の作品
///   ]
///   戻り値: [座標の組、不正なら使い方の誤りまたは実行失敗]
/// }
pub fn cell(command: &ParsedCommand, document: &LayeredCanvas) -> Result<(u32, u32), CliError> {
    let (x, y) = (command.unsigned("x")?, command.unsigned("y")?);
    check_cell(document, x, y)?;
    Ok((x, y))
}

/// {
///   責務: [child: --child X Yの値を2×2内の子セル座標として読む]
///   処理: [
///     1: 指定がなければNoneを返す
///     2: 各値を0または1の整数として検証する
///   ]
///   引数: [
///     command: 解析済みコマンド
///   ]
///   戻り値: [子セル座標、範囲外や数字以外は使い方の誤り]
/// }
pub fn child(command: &ParsedCommand) -> Result<Option<ChildCoordinate>, CliError> {
    let Some(values) = command.flag_values("--child") else {
        return Ok(None);
    };
    let mut parts = [0u8; 2];
    for (part, text) in parts.iter_mut().zip(values) {
        *part = match parse_unsigned("--child", text)? {
            0 => 0,
            1 => 1,
            other => {
                return Err(CliError::usage(format!(
                    "--child values must be 0 or 1, got {other}"
                )));
            }
        };
    }
    Ok(Some((parts[0], parts[1])))
}

/// {
///   責務: [detail_policy: --discard-detailの有無から細部の方針を決める]
///   処理: [
///     1: 指定があれば破棄、なければ保持にする
///   ]
///   引数: [
///     command: 解析済みコマンド
///   ]
///   戻り値: [細部の保持・破棄の方針]
/// }
pub fn detail_policy(command: &ParsedCommand) -> DetailPolicy {
    if command.has_flag("--discard-detail") {
        DetailPolicy::Discard
    } else {
        DetailPolicy::Preserve
    }
}
