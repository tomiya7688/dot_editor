//! A command line resolved against the command table, with typed argument access.

use std::collections::HashMap;

use crate::cli_error::CliError;
use crate::command_spec::{CommandSpec, FlagSpec};

/// オプション名ごとの値の並び。
type FlagValues = HashMap<&'static str, Vec<String>>;

/// {
///   責務: [ParsedCommand: 表に照合したコマンドと、その引数・オプションの値を保持する]
///   フィールド: [
///     spec: 一致したコマンドの定義
///     positionals: 位置引数の値。定義と同じ順序
///     flags: 指定されたオプションの名前ごとの値
///   ]
/// }
#[derive(Debug)]
pub struct ParsedCommand {
    pub spec: &'static CommandSpec,
    positionals: Vec<String>,
    flags: FlagValues,
}

impl ParsedCommand {
    /// {
    ///   責務: [parse: 共通オプションを除いた語をコマンド表に照合する]
    ///   処理: [
    ///     1: 先頭の語の並びが一致するコマンドのうち最も長いものを選ぶ
    ///     2: 残りの語をオプションと位置引数に分ける
    ///     3: 位置引数の個数を定義と照合する
    ///   ]
    ///   引数: [
    ///     table: 受け付けるコマンドの表
    ///     words: 共通オプションを除いた語
    ///   ]
    ///   戻り値: [解析済みコマンド、未知のコマンドや引数の誤りは使い方の誤り]
    /// }
    pub fn parse(table: &'static [CommandSpec], words: &[String]) -> Result<Self, CliError> {
        let spec = Self::resolve(table, words)?;
        let (positionals, flags) = Self::split_arguments(spec, &words[spec.path.len()..])?;
        if positionals.len() != spec.positionals.len() {
            return Err(CliError::usage(format!(
                "`{}` expects {} (got {} argument(s))",
                spec.path.join(" "),
                if spec.positionals.is_empty() {
                    "no arguments".to_owned()
                } else {
                    spec.positionals.join(" ")
                },
                positionals.len()
            )));
        }
        Ok(Self {
            spec,
            positionals,
            flags,
        })
    }

    /// {
    ///   責務: [resolve: 語の先頭に一致する最も長いコマンドを探す]
    ///   処理: [
    ///     1: 各コマンドの語の並びが先頭と一致するか調べる
    ///     2: 一致したうち語数が最大のものを返す
    ///   ]
    ///   引数: [
    ///     table: 受け付けるコマンドの表
    ///     words: 共通オプションを除いた語
    ///   ]
    ///   戻り値: [コマンドの定義、一致がなければ使い方の誤り]
    /// }
    pub fn resolve(
        table: &'static [CommandSpec],
        words: &[String],
    ) -> Result<&'static CommandSpec, CliError> {
        table
            .iter()
            .filter(|spec| {
                words.len() >= spec.path.len()
                    && spec.path.iter().zip(words).all(|(name, word)| name == word)
            })
            .max_by_key(|spec| spec.path.len())
            .ok_or_else(|| {
                let shown: Vec<&str> = words.iter().take(2).map(String::as_str).collect();
                CliError::usage(format!("unknown command: {}", shown.join(" ")))
            })
    }

    /// {
    ///   責務: [split_arguments: コマンド名の後ろの語をオプションと位置引数に分ける]
    ///   処理: [
    ///     1: `-`で始まる語をオプションとして定義に照合し、必要な個数の値を読む
    ///     2: 同じオプションの重複と未知のオプションを拒否する
    ///     3: それ以外の語を位置引数として集める
    ///   ]
    ///   引数: [
    ///     spec: 一致したコマンドの定義
    ///     words: コマンド名の後ろの語
    ///   ]
    ///   戻り値: [位置引数とオプションの値、誤りは使い方の誤り]
    /// }
    fn split_arguments(
        spec: &'static CommandSpec,
        words: &[String],
    ) -> Result<(Vec<String>, FlagValues), CliError> {
        let mut positionals = Vec::new();
        let mut flags: HashMap<&'static str, Vec<String>> = HashMap::new();
        let mut index = 0;
        while index < words.len() {
            let word = &words[index];
            index += 1;
            if !word.starts_with('-') {
                positionals.push(word.clone());
                continue;
            }
            let flag = Self::find_flag(spec, word)?;
            let end = index + flag.values;
            if end > words.len() {
                return Err(CliError::usage(format!(
                    "{} needs {} value(s)",
                    flag.name, flag.values
                )));
            }
            if flags
                .insert(flag.name, words[index..end].to_vec())
                .is_some()
            {
                return Err(CliError::usage(format!(
                    "{} was given more than once",
                    flag.name
                )));
            }
            index = end;
        }
        Ok((positionals, flags))
    }

    /// {
    ///   責務: [find_flag: 語に対応するオプションの定義を探す]
    ///   処理: [
    ///     1: 長い名前または短い名前が一致する定義を返す
    ///   ]
    ///   引数: [
    ///     spec: 一致したコマンドの定義
    ///     word: `-`で始まる語
    ///   ]
    ///   戻り値: [オプションの定義、未知なら使い方の誤り]
    /// }
    fn find_flag(spec: &'static CommandSpec, word: &str) -> Result<&'static FlagSpec, CliError> {
        spec.flags
            .iter()
            .find(|flag| flag.name == word || flag.short == Some(word))
            .ok_or_else(|| {
                CliError::usage(format!(
                    "unknown option for `{}`: {word}",
                    spec.path.join(" ")
                ))
            })
    }

    /// {
    ///   責務: [has_flag: 値を取らないオプションが指定されたか調べる]
    ///   処理: [
    ///     1: 指定済みのオプション名に含まれるか確認する
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///     name: `--`付きのオプション名
    ///   ]
    ///   戻り値: [指定されていればtrue]
    /// }
    pub fn has_flag(&self, name: &str) -> bool {
        self.flags.contains_key(name)
    }

    /// {
    ///   責務: [flag_values: オプションに続く値を取り出す]
    ///   処理: [
    ///     1: 指定済みなら値の並びを返す
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///     name: `--`付きのオプション名
    ///   ]
    ///   戻り値: [値の並び。指定されていなければNone]
    /// }
    pub fn flag_values(&self, name: &str) -> Option<&[String]> {
        self.flags.get(name).map(Vec::as_slice)
    }

    /// {
    ///   責務: [text: 名前で指定した位置引数の文字列を取り出す]
    ///   処理: [
    ///     1: 定義から名前の位置を探して値を返す
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///     name: 位置引数の名前
    ///   ]
    ///   戻り値: [引数の文字列]
    /// }
    pub fn text(&self, name: &str) -> &str {
        let index = self
            .spec
            .positionals
            .iter()
            .position(|candidate| *candidate == name)
            .expect("handlers only ask for declared positionals");
        &self.positionals[index]
    }

    /// {
    ///   責務: [unsigned: 名前で指定した位置引数を符号なし整数として読む]
    ///   処理: [
    ///     1: 文字列を10進の整数として解釈する
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///     name: 位置引数の名前
    ///   ]
    ///   戻り値: [整数、小数・負数・数字以外は使い方の誤り]
    /// }
    pub fn unsigned(&self, name: &str) -> Result<u32, CliError> {
        parse_unsigned(name, self.text(name))
    }
}

/// {
///   責務: [parse_unsigned: 数字だけの文字列を符号なし整数へ変換する]
///   処理: [
///     1: 数字以外（符号・小数点・空）を含む文字列を拒否する
///     2: u32の範囲で変換する
///   ]
///   引数: [
///     label: エラー文に出す引数名
///     text: 変換する文字列
///   ]
///   戻り値: [整数、不正なら使い方の誤り]
/// }
pub fn parse_unsigned(label: &str, text: &str) -> Result<u32, CliError> {
    if text.is_empty() || !text.bytes().all(|byte| byte.is_ascii_digit()) {
        return Err(CliError::usage(format!(
            "{label} must be a whole number, got `{text}`"
        )));
    }
    text.parse::<u32>()
        .map_err(|_| CliError::usage(format!("{label} is too large: `{text}`")))
}
