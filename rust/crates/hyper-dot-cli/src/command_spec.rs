//! Declarative description of one command: its words, arguments, flags and handler.

use std::path::PathBuf;

use hyper_dot_core::layered_canvas::LayeredCanvas;
use serde_json::Value;

use crate::cli_error::CliError;
use crate::parsed_command::ParsedCommand;

/// {
///   責務: [FlagSpec: コマンド固有のオプション1つの書式を表す]
///   フィールド: [
///     name: `--`付きの長い名前
///     short: `-`付きの短い名前。なければNone
///     values: オプションの後ろに続く値の個数
///     summary: ヘルプに出す1行の説明
///   ]
/// }
#[derive(Debug)]
pub struct FlagSpec {
    pub name: &'static str,
    pub short: Option<&'static str>,
    pub values: usize,
    pub summary: &'static str,
}

/// {
///   責務: [ExportPlan: 書き出すファイルの場所と内容、結果の要約を表す]
///   フィールド: [
///     path: 書き出し先のパス
///     bytes: 書き出すバイト列
///     result: 標準出力へ載せる結果
///   ]
/// }
#[derive(Debug)]
pub struct ExportPlan {
    pub path: PathBuf,
    pub bytes: Vec<u8>,
    pub result: Value,
}

/// 編集の結果。結果のJSON値と、作品が変わったかの真偽。
pub type EditResult = Result<(Value, bool), CliError>;
/// 選択中のレイヤーを編集するハンドラ。
pub type EditHandler = fn(&ParsedCommand, &mut LayeredCanvas) -> EditResult;

/// {
///   責務: [Handler: コマンドがプロジェクトへ行う操作の種類と実装を結びつける]
///   フィールド: [
///     Create: 新しいプロジェクトを作る。保存先は共通オプションの--project
///     Read: プロジェクトを読み取るだけ。保存しない
///     Edit: プロジェクトを変更する。変更があれば保存する。戻り値の真偽は変更の有無
///     Export: プロジェクトから別のファイルを書き出す。プロジェクト自体は保存しない
///   ]
/// }
#[derive(Debug)]
pub enum Handler {
    Create(fn(&ParsedCommand) -> Result<(LayeredCanvas, Value), CliError>),
    Read(fn(&ParsedCommand, &LayeredCanvas) -> Result<Value, CliError>),
    Edit(EditHandler),
    Export(fn(&ParsedCommand, &LayeredCanvas) -> Result<ExportPlan, CliError>),
}

/// {
///   責務: [CommandSpec: コマンド名・引数・オプション・実装を1件にまとめる]
///   フィールド: [
///     path: コマンドを表す語の並び（例: ["pixel", "paint"]）
///     summary: ヘルプに出す1行の説明
///     positionals: 位置引数の名前を順に並べたもの
///     flags: 受け付けるオプション
///     handler: 実行する操作
///   ]
/// }
#[derive(Debug)]
pub struct CommandSpec {
    pub path: &'static [&'static str],
    pub summary: &'static str,
    pub positionals: &'static [&'static str],
    pub flags: &'static [FlagSpec],
    pub handler: Handler,
}

impl CommandSpec {
    /// {
    ///   責務: [operation: JSONの`operation`に使う名前を作る]
    ///   処理: [
    ///     1: コマンドの語をピリオドで連結する
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///   ]
    ///   戻り値: [`pixel.paint`のような操作名]
    /// }
    pub fn operation(&self) -> String {
        self.path.join(".")
    }
}
