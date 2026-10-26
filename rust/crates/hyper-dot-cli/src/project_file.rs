//! Reading and atomically replacing project and export files.

use std::fs;
use std::io::{ErrorKind, Write};
use std::path::{Path, PathBuf};

use hyper_dot_core::canvas::Canvas;
use hyper_dot_core::layered_canvas::LayeredCanvas;
use serde_json::Value;

use crate::cli_error::CliError;

/// Largest project file read into memory; the core enforces the same limit.
const MAX_PROJECT_BYTES: u64 = 256 * 1024 * 1024;

/// {
///   責務: [io_failure: ファイル操作の失敗をCLIの失敗へ変換する]
///   処理: [
///     1: 存在しないファイルとそれ以外の入出力の失敗を種別名で分ける
///   ]
///   引数: [
///     action: 何をしようとしたかの説明
///     path: 対象のパス
///     error: 標準ライブラリが返した入出力エラー
///   ]
///   戻り値: [CLIの実行失敗]
/// }
fn io_failure(action: &str, path: &Path, error: &std::io::Error) -> CliError {
    let code = if error.kind() == ErrorKind::NotFound {
        "file_not_found"
    } else {
        "io_error"
    };
    CliError::failure(code, format!("cannot {action} {}: {error}", path.display()))
}

/// {
///   責務: [load: プロジェクトファイルを読み込んで検証する]
///   処理: [
///     1: ファイルの大きさを確認して読み込む
///     2: レイヤー付きか単一Canvasかを判定する
///     3: コアの検証つき読み込みを行い、単一Canvasは背景1層にする
///   ]
///   引数: [
///     path: プロジェクトファイルのパス
///   ]
///   戻り値: [履歴のない作品、読み込めない・不正な文書は実行失敗]
/// }
pub fn load(path: &Path) -> Result<LayeredCanvas, CliError> {
    let metadata = fs::metadata(path).map_err(|error| io_failure("read", path, &error))?;
    if metadata.len() > MAX_PROJECT_BYTES {
        return Err(CliError::failure(
            "invalid_project",
            format!("{} exceeds the project size limit", path.display()),
        ));
    }
    let text = fs::read_to_string(path).map_err(|error| io_failure("read", path, &error))?;
    let probe: Value = serde_json::from_str(&text).map_err(|error| {
        CliError::failure("invalid_project", format!("not valid JSON: {error}"))
    })?;
    if probe.get("layers").is_some() {
        return Ok(LayeredCanvas::from_json(&text)?);
    }
    Ok(LayeredCanvas::from_canvas(Canvas::from_json(&text)?))
}

/// {
///   責務: [temporary_path: 同じフォルダに置く一時ファイルのパスを作る]
///   処理: [
///     1: 最終ファイル名の前にピリオド、後ろにプロセス番号と拡張子を付ける
///   ]
///   引数: [
///     path: 最終的なファイルのパス
///   ]
///   戻り値: [一時ファイルのパス]
/// }
fn temporary_path(path: &Path) -> PathBuf {
    let name = path
        .file_name()
        .map(|name| name.to_string_lossy().into_owned())
        .unwrap_or_default();
    path.with_file_name(format!(".{name}.{}.tmp", std::process::id()))
}

/// {
///   責務: [write_atomic: 途中で失敗しても元のファイルを壊さずに書き込む]
///   処理: [
///     1: 同じフォルダの一時ファイルへ全内容を書いてディスクへ同期する
///     2: 一時ファイルを最終ファイルへ置き換える
///     3: どこかで失敗したら一時ファイルを消して失敗を返す
///   ]
///   引数: [
///     path: 書き込み先のパス
///     bytes: 書き込む内容
///   ]
///   戻り値: [成功時は単位値、失敗時は元のファイルを変えずに実行失敗]
/// }
pub fn write_atomic(path: &Path, bytes: &[u8]) -> Result<(), CliError> {
    let temporary = temporary_path(path);
    let written = fs::File::create(&temporary).and_then(|mut file| {
        file.write_all(bytes)?;
        file.sync_all()
    });
    let replaced = written.and_then(|()| fs::rename(&temporary, path));
    if let Err(error) = replaced {
        // 失敗時に一時ファイルを残さない。消せなくても本来の失敗を優先して返す。
        let _ = fs::remove_file(&temporary);
        return Err(io_failure("write", path, &error));
    }
    Ok(())
}

/// {
///   責務: [save: 作品をレイヤー付きversion 2のJSONとして保存する]
///   処理: [
///     1: 作品をJSONへ直列化する
///     2: 原子的に置き換えて書き込む
///   ]
///   引数: [
///     path: 保存先のパス
///     document: 保存する作品
///   ]
///   戻り値: [成功時は単位値、失敗時は元のファイルを変えずに実行失敗]
/// }
pub fn save(path: &Path, document: &LayeredCanvas) -> Result<(), CliError> {
    write_atomic(path, document.to_json()?.as_bytes())
}
