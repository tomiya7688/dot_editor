//! One invocation of `pixel-cli`: parse, load, apply, save and report.

use std::path::Path;
use std::time::Duration;

use hyper_dot_core::layered_canvas::LayeredCanvas;
use serde_json::{Value, json};

use crate::cli_error::CliError;
use crate::command_spec::{EditHandler, ExportPlan, Handler};
use crate::command_table::COMMANDS;
use crate::global_options::GlobalOptions;
use crate::help_text;
use crate::parsed_command::ParsedCommand;
use crate::project_file::{self, ProjectLock, Snapshot};
use crate::report::{self, Outcome};

/// コマンドを特定できないときの`operation`。
const UNRESOLVED_OPERATION: &str = "usage";

/// {
///   責務: [project_path: 共通オプションのプロジェクトパスを取り出す]
///   処理: [
///     1: 指定がなければ使い方の誤りにする
///   ]
///   引数: [
///     options: 共通オプション
///   ]
///   戻り値: [プロジェクトのパス]
/// }
fn project_path(options: &GlobalOptions) -> Result<&str, CliError> {
    options
        .project
        .as_deref()
        .ok_or_else(|| CliError::usage("--project/-p PATH is required for this command"))
}

/// {
///   責務: [create: 新しいプロジェクトを作って保存する]
///   処理: [
///     1: ハンドラで作品を作り、既存ファイルを--forceなしでは上書きしない
///     2: --dry-runでなければ原子的に保存する
///   ]
///   引数: [
///     options: 共通オプション
///     command: 解析済みコマンド
///     build: 作品を作るハンドラ
///   ]
///   戻り値: [結果の出力、既存ファイルや保存の失敗はエラー]
/// }
fn create(
    options: &GlobalOptions,
    command: &ParsedCommand,
    build: fn(&ParsedCommand) -> Result<(LayeredCanvas, Value), CliError>,
) -> Result<Outcome, CliError> {
    let path = project_path(options)?;
    let target = Path::new(path);
    let (document, result) = build(command)?;
    let _lock = lock_for(options, path)?;
    let current = project_file::current_revision(target)?;
    if options.if_revision.is_some() {
        check_revision(options, path, current.as_deref())?;
    }
    let force = command.has_flag("--force");
    if current.is_some() && !force {
        return Err(CliError::failure(
            "file_exists",
            format!("{path} already exists; use --force to replace it"),
        ));
    }
    let mut result = result;
    if !options.dry_run {
        let revision = if current.is_some() {
            project_file::save(target, &document)?
        } else {
            project_file::save_new(target, &document)?
        };
        result = with_revision(result, &revision);
    }
    Ok(finish(
        options,
        command,
        Some(path),
        !options.dry_run,
        result,
    ))
}

/// {
///   責務: [lock_for: 変更を伴う実行のために作品のロックを取る]
///   処理: [
///     1: --dry-runではロックもsidecarも作らない
///     2: それ以外は指定の時間までロックを待つ
///   ]
///   引数: [
///     options: 共通オプション
///     path: プロジェクトのパス
///   ]
///   戻り値: [ロック（dry-runではNone）、取得できなければ実行失敗]
/// }
fn lock_for(options: &GlobalOptions, path: &str) -> Result<Option<ProjectLock>, CliError> {
    if options.dry_run {
        return Ok(None);
    }
    let timeout = Duration::from_millis(options.lock_timeout_ms);
    ProjectLock::acquire(Path::new(path), timeout).map(Some)
}

/// {
///   責務: [check_revision: 期待したrevisionと現在のrevisionが一致するか確かめる]
///   処理: [
///     1: --if-revisionが無ければ何もしない
///     2: 現在のrevisionが無い、または違えば競合として失敗する
///   ]
///   引数: [
///     options: 共通オプション
///     path: プロジェクトのパス
///     actual: 現在のrevision（ファイルが無ければNone）
///   ]
///   戻り値: [一致すれば単位値、違えばrevision_conflict]
/// }
fn check_revision(
    options: &GlobalOptions,
    path: &str,
    actual: Option<&str>,
) -> Result<(), CliError> {
    match &options.if_revision {
        Some(expected) if actual != Some(expected.as_str()) => Err(CliError::failure(
            "revision_conflict",
            format!(
                "{path} is at {} but --if-revision expected {expected}; nothing was saved",
                actual.unwrap_or("no file")
            ),
        )),
        _ => Ok(()),
    }
}

/// {
///   責務: [load_checked: 作品を読み、--if-revisionがあれば一致を確かめる]
///   処理: [
///     1: スナップショットを読む。ファイルが無く期待があれば競合にする
///     2: 読んだrevisionを期待と照合する
///   ]
///   引数: [
///     options: 共通オプション
///     path: プロジェクトのパス
///   ]
///   戻り値: [作品とrevision、競合や読み込みの失敗はエラー]
/// }
fn load_checked(options: &GlobalOptions, path: &str) -> Result<Snapshot, CliError> {
    match project_file::load_snapshot(Path::new(path)) {
        Ok(snapshot) => {
            check_revision(options, path, Some(&snapshot.revision))?;
            Ok(snapshot)
        }
        Err(error) if error.code == "file_not_found" && options.if_revision.is_some() => {
            check_revision(options, path, None)?;
            Err(error)
        }
        Err(error) => Err(error),
    }
}

/// {
///   責務: [with_revision: 結果の連想配列にrevisionを加える]
///   処理: [
///     1: 結果が連想配列のときだけ「revision」を追加する
///   ]
///   引数: [
///     result: コマンド固有の結果
///     revision: 加えるrevision
///   ]
///   戻り値: [revisionを加えた結果]
/// }
fn with_revision(mut result: Value, revision: &str) -> Value {
    if let Value::Object(map) = &mut result {
        map.insert("revision".to_owned(), json!(revision));
    }
    result
}

/// {
///   責務: [read: プロジェクトを読み込み、変更せずに結果を返す]
///   処理: [
///     1: プロジェクトを読み込む
///     2: ハンドラで結果を作る。ファイルには何も書かない
///   ]
///   引数: [
///     options: 共通オプション
///     command: 解析済みコマンド
///     query: 結果を作るハンドラ
///   ]
///   戻り値: [結果の出力]
/// }
fn read(
    options: &GlobalOptions,
    command: &ParsedCommand,
    query: fn(&ParsedCommand, &LayeredCanvas) -> Result<Value, CliError>,
) -> Result<Outcome, CliError> {
    let path = project_path(options)?;
    let snapshot = project_file::load_snapshot(Path::new(path))?;
    let mut result = query(command, &snapshot.canvas)?;
    if matches!(command.spec.operation().as_str(), "status" | "project.info") {
        result = with_revision(result, &snapshot.revision);
    }
    Ok(finish(options, command, Some(path), false, result))
}

/// {
///   責務: [edit: プロジェクトを編集し、変更があれば保存する]
///   処理: [
///     1: プロジェクトを読み込む
///     2: ハンドラで編集する。失敗時は何も保存しない
///     3: 変更があり--dry-runでなければ原子的に保存する
///   ]
///   引数: [
///     options: 共通オプション
///     command: 解析済みコマンド
///     apply: 編集するハンドラ
///   ]
///   戻り値: [結果の出力、編集や保存の失敗はエラー]
/// }
fn edit(
    options: &GlobalOptions,
    command: &ParsedCommand,
    apply: EditHandler,
) -> Result<Outcome, CliError> {
    let path = project_path(options)?;
    let _lock = lock_for(options, path)?;
    let mut snapshot = load_checked(options, path)?;
    let (result, changed) = apply(command, &mut snapshot.canvas)?;
    let saved = changed && !options.dry_run;
    let revision = if saved {
        project_file::save(Path::new(path), &snapshot.canvas)?
    } else {
        snapshot.revision
    };
    let result = with_revision(result, &revision);
    Ok(finish(options, command, Some(path), saved, result))
}

/// {
///   責務: [export: プロジェクトから別のファイルを書き出す]
///   処理: [
///     1: プロジェクトを読み込み、ハンドラで書き出し計画を作る
///     2: 書き出し先がプロジェクト自身なら拒否する
///     3: --dry-runでなければ原子的に書き出す
///   ]
///   引数: [
///     options: 共通オプション
///     command: 解析済みコマンド
///     plan: 書き出し計画を作るハンドラ
///   ]
///   戻り値: [結果の出力、書き出しの失敗はエラー。プロジェクトは変更しない]
/// }
fn export(
    options: &GlobalOptions,
    command: &ParsedCommand,
    plan: fn(&ParsedCommand, &LayeredCanvas) -> Result<ExportPlan, CliError>,
) -> Result<Outcome, CliError> {
    let path = project_path(options)?;
    let document = project_file::load_snapshot(Path::new(path))?.canvas;
    let planned = plan(command, &document)?;
    if project_file::same_target(&planned.path, Path::new(path)) {
        return Err(CliError::failure(
            "invalid_output",
            "the output file must differ from the project file",
        ));
    }
    if !options.dry_run {
        project_file::write_atomic(&planned.path, &planned.bytes)?;
    }
    Ok(finish(
        options,
        command,
        Some(path),
        !options.dry_run,
        planned.result,
    ))
}

/// {
///   責務: [finish: 成功結果にdry_runとsavedを添えて出力にする]
///   処理: [
///     1: --dry-runのときだけdry_runを真で記録する
///     2: 書き込みを行ったかをsavedとして記録する
///   ]
///   引数: [
///     options: 共通オプション
///     command: 解析済みコマンド
///     project: プロジェクトのパス
///     saved: ファイルへ書き込んだか
///     result: コマンド固有の結果
///   ]
///   戻り値: [成功の出力]
/// }
fn finish(
    options: &GlobalOptions,
    command: &ParsedCommand,
    project: Option<&str>,
    saved: bool,
    result: Value,
) -> Outcome {
    let extras = [("dry_run", json!(options.dry_run)), ("saved", json!(saved))];
    report::success(
        options.json,
        &command.spec.operation(),
        project,
        &extras,
        result,
    )
}

/// {
///   責務: [execute: コマンドの種類に応じた実行手順を呼び分ける]
///   処理: [
///     1: ハンドラの種類を判定し、作成・読み取り・編集・書き出しの手順へ渡す
///   ]
///   引数: [
///     options: 共通オプション
///     command: 解析済みコマンド
///   ]
///   戻り値: [結果の出力またはエラー]
/// }
fn execute(options: &GlobalOptions, command: &ParsedCommand) -> Result<Outcome, CliError> {
    match &command.spec.handler {
        Handler::Create(build) => create(options, command, *build),
        Handler::Read(query) => read(options, command, *query),
        Handler::Edit(apply) => edit(options, command, *apply),
        Handler::Export(plan) => export(options, command, *plan),
    }
}

/// {
///   責務: [show_help: ヘルプの要求に、全体または指定コマンドの説明を返す]
///   処理: [
///     1: 語がコマンドに一致すればそのコマンドの説明、なければ全体の一覧を返す
///   ]
///   引数: [
///     words: 共通オプションを除いた語
///   ]
///   戻り値: [終了値0の出力]
/// }
fn show_help(words: &[String]) -> Outcome {
    match ParsedCommand::resolve(&COMMANDS, words) {
        Ok(spec) => report::text(help_text::for_command(spec)),
        Err(_) => report::text(help_text::overview()),
    }
}

/// {
///   責務: [show_version: バージョンを表示する]
///   処理: [
///     1: --jsonなら結果のJSON、そうでなければ1行の文章にする
///   ]
///   引数: [
///     json: JSON出力か
///   ]
///   戻り値: [終了値0の出力]
/// }
fn show_version(json: bool) -> Outcome {
    let version = env!("CARGO_PKG_VERSION");
    if json {
        report::success(true, "version", None, &[], json!({"version": version}))
    } else {
        report::text(format!("pixel-cli {version}\n"))
    }
}

/// {
///   責務: [run: コマンド行1回分を実行して出力と終了値を返す]
///   処理: [
///     1: 共通オプションを取り出し、ヘルプ・バージョンを処理する
///     2: コマンドを表に照合して実行する
///     3: 失敗は、--jsonの有無に応じたエラー出力と終了値にする
///   ]
///   引数: [
///     arguments: プログラム名を除いたコマンド行の語
///   ]
///   戻り値: [標準出力・標準エラー・終了値]
/// }
pub fn run(arguments: &[String]) -> Outcome {
    let json_hint = arguments.iter().any(|word| word == "--json");
    let (options, words) = match GlobalOptions::extract(arguments) {
        Ok(parsed) => parsed,
        Err(error) => return report::failure(json_hint, UNRESOLVED_OPERATION, &error),
    };
    if options.version {
        return show_version(options.json);
    }
    if options.help {
        return show_help(&words);
    }
    if words.is_empty() {
        let error = CliError::usage("no command given; run `pixel-cli --help`");
        return report::failure(options.json, UNRESOLVED_OPERATION, &error);
    }
    let command = match ParsedCommand::parse(&COMMANDS, &words) {
        Ok(command) => command,
        Err(error) => return report::failure(options.json, UNRESOLVED_OPERATION, &error),
    };
    match execute(&options, &command) {
        Ok(outcome) => outcome,
        Err(error) => report::failure(options.json, &command.spec.operation(), &error),
    }
}
