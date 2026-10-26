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
///   ]
/// }
#[derive(Clone, Debug, Default, Eq, PartialEq)]
pub struct GlobalOptions {
    pub project: Option<String>,
    pub json: bool,
    pub dry_run: bool,
    pub help: bool,
    pub version: bool,
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
                other => match other.strip_prefix("--project=") {
                    Some(value) => options.set_project(value.to_owned())?,
                    None => rest.push(word.clone()),
                },
            }
        }
        Ok((options, rest))
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
