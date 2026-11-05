//! Options accepted before or after any command: `-p`, `--json`, `--dry-run`, help and version.

use crate::cli_error::CliError;

/// {
///   責務: [GlobalOptions: すべてのコマンドに共通するオプションを保持する]
///   フィールド: [
///     project: 対象のプロジェクトファイルのパス
///     json: 標準出力をJSONだけにするか
///     dry_run: 保存せずに結果だけを評価するか
///     help: ヘルプを表示するか
///     version: バージョンを表示するか
///     if_revision: 保存の前提とするrevision（sha256:付き）。違えば競合として失敗する
///     lock_timeout_ms: 作品のロックを待つ最長時間（ミリ秒）
///   ]
/// }
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct GlobalOptions {
    pub project: Option<String>,
    pub json: bool,
    pub dry_run: bool,
    pub help: bool,
    pub version: bool,
    pub if_revision: Option<String>,
    pub lock_timeout_ms: u64,
}

/// ロックを待つ既定の時間（ミリ秒）。
const DEFAULT_LOCK_TIMEOUT_MS: u64 = 5000;

/// ロックを待つ時間として指定できる上限（ミリ秒）。
const MAX_LOCK_TIMEOUT_MS: u64 = 60000;

impl Default for GlobalOptions {
    /// {
    ///   責務: [default: すべてのオプションが未指定の状態を作る]
    ///   処理: [
    ///     1: 真偽値を偽、値を空にし、ロック待ちを既定の時間にする
    ///   ]
    ///   引数: []
    ///   戻り値: [未指定の共通オプション]
    /// }
    fn default() -> Self {
        Self {
            project: None,
            json: false,
            dry_run: false,
            help: false,
            version: false,
            if_revision: None,
            lock_timeout_ms: DEFAULT_LOCK_TIMEOUT_MS,
        }
    }
}

impl GlobalOptions {
    /// {
    ///   責務: [extract: 引数の列から共通オプションを取り出し、残りを返す]
    ///   処理: [
    ///     1: 先頭から順に共通オプションを判定し、値を取るオプションは次の語を読む
    ///     2: 共通でない語は順序を保ったまま残りへ移す
    ///   ]
    ///   引数: [
    ///     arguments: プログラム名を除いたコマンド行の語
    ///   ]
    ///   戻り値: [共通オプションと残りの語、値の欠落や重複は使い方の誤り]
    /// }
    pub fn extract(arguments: &[String]) -> Result<(Self, Vec<String>), CliError> {
        let mut options = Self::default();
        let mut rest = Vec::new();
        let mut words = arguments.iter();
        while let Some(word) = words.next() {
            match word.as_str() {
                "--json" => options.json = true,
                "--dry-run" => options.dry_run = true,
                "--help" | "-h" => options.help = true,
                "--version" | "-V" => options.version = true,
                "--project" | "-p" => {
                    let value = words
                        .next()
                        .ok_or_else(|| CliError::usage(format!("{word} needs a path")))?;
                    options.set_project(value.clone())?;
                }
                "--if-revision" => {
                    let value = words
                        .next()
                        .ok_or_else(|| CliError::usage(format!("{word} needs a revision")))?;
                    options.set_if_revision(value)?;
                }
                "--lock-timeout-ms" => {
                    let value = words
                        .next()
                        .ok_or_else(|| CliError::usage(format!("{word} needs milliseconds")))?;
                    options.set_lock_timeout(value)?;
                }
                other => {
                    if let Some(value) = other.strip_prefix("--project=") {
                        options.set_project(value.to_owned())?;
                    } else if let Some(value) = other.strip_prefix("--if-revision=") {
                        options.set_if_revision(value)?;
                    } else if let Some(value) = other.strip_prefix("--lock-timeout-ms=") {
                        options.set_lock_timeout(value)?;
                    } else {
                        rest.push(word.clone());
                    }
                }
            }
        }
        Ok((options, rest))
    }

    /// {
    ///   責務: [set_if_revision: 期待するrevisionを1回だけ設定する]
    ///   処理: [
    ///     1: 表記が「sha256:」+小文字16進64文字であることを確認する
    ///     2: 二重指定を拒否して保存する
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///     value: 指定された文字列
    ///   ]
    ///   戻り値: [成功時は単位値、不正な表記や二重指定は使い方の誤り]
    /// }
    fn set_if_revision(&mut self, value: &str) -> Result<(), CliError> {
        if !crate::sha256::is_revision(value) {
            return Err(CliError::usage(
                "--if-revision needs sha256: followed by 64 lowercase hex digits",
            ));
        }
        if self.if_revision.is_some() {
            return Err(CliError::usage("--if-revision was given more than once"));
        }
        self.if_revision = Some(value.to_owned());
        Ok(())
    }

    /// {
    ///   責務: [set_lock_timeout: ロックを待つ最長時間を設定する]
    ///   処理: [
    ///     1: 0以上の整数で上限以内であることを確認して保存する
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///     value: 指定された文字列
    ///   ]
    ///   戻り値: [成功時は単位値、範囲外や整数でない値は使い方の誤り]
    /// }
    fn set_lock_timeout(&mut self, value: &str) -> Result<(), CliError> {
        match value.parse::<u64>() {
            Ok(milliseconds) if milliseconds <= MAX_LOCK_TIMEOUT_MS => {
                self.lock_timeout_ms = milliseconds;
                Ok(())
            }
            _ => Err(CliError::usage(format!(
                "--lock-timeout-ms needs an integer from 0 to {MAX_LOCK_TIMEOUT_MS}"
            ))),
        }
    }

    /// {
    ///   責務: [set_project: プロジェクトのパスを1回だけ設定する]
    ///   処理: [
    ///     1: 空のパスと二重指定を拒否する
    ///     2: パスを保存する
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///     path: 指定されたパス
    ///   ]
    ///   戻り値: [成功時は単位値、不正な指定は使い方の誤り]
    /// }
    fn set_project(&mut self, path: String) -> Result<(), CliError> {
        if path.is_empty() {
            return Err(CliError::usage("--project needs a non-empty path"));
        }
        if self.project.is_some() {
            return Err(CliError::usage("--project was given more than once"));
        }
        self.project = Some(path);
        Ok(())
    }
}
