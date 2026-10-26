//! Help output generated from the command table.

use crate::command_spec::CommandSpec;
use crate::command_table::COMMANDS;

/// {
///   責務: [overview: すべてのコマンドと共通オプションの一覧を作る]
///   処理: [
///     1: 使い方と共通オプションを書く
///     2: コマンド表の順に、語・位置引数・説明を1行ずつ並べる
///   ]
///   引数: []
///   戻り値: [ヘルプの文章]
/// }
pub fn overview() -> String {
    let mut text = String::from(
        "pixel-cli - shell-first editor for Hyper Dot projects\n\n\
         usage: pixel-cli [options] <command> [arguments]\n\n\
         options (accepted anywhere):\n\
         \x20 -p, --project PATH  project file to read or write\n\
         \x20 --json              print only one JSON object on stdout\n\
         \x20 --dry-run           evaluate without saving or writing files\n\
         \x20 -h, --help          show help (also `<command> --help`)\n\
         \x20 -V, --version       show the version\n\n\
         commands:\n",
    );
    for spec in COMMANDS.iter() {
        text.push_str(&format!("  {:<28}{}\n", usage_line(spec), spec.summary));
    }
    text.push_str("\nexit status: 0 success, 1 runtime/project failure, 2 usage error\n");
    text
}

/// {
///   責務: [usage_line: コマンドの語と位置引数を1行の書式にする]
///   処理: [
///     1: コマンドの語を並べ、位置引数を山括弧で続ける
///   ]
///   引数: [
///     spec: コマンドの定義
///   ]
///   戻り値: [`pixel paint <x> <y> <color>`のような書式]
/// }
fn usage_line(spec: &CommandSpec) -> String {
    let mut line = spec.path.join(" ");
    for name in spec.positionals {
        line.push_str(&format!(" <{name}>"));
    }
    line
}

/// {
///   責務: [for_command: 1つのコマンドの書式とオプションの説明を作る]
///   処理: [
///     1: 書式と説明を書く
///     2: オプションがあれば長い名前・短い名前・値の個数・説明を並べる
///   ]
///   引数: [
///     spec: コマンドの定義
///   ]
///   戻り値: [ヘルプの文章]
/// }
pub fn for_command(spec: &CommandSpec) -> String {
    let mut text = format!(
        "usage: pixel-cli [options] {}\n{}\n",
        usage_line(spec),
        spec.summary
    );
    if !spec.flags.is_empty() {
        text.push_str("\ncommand options:\n");
    }
    for flag in spec.flags {
        let short = flag
            .short
            .map(|name| format!("{name}, "))
            .unwrap_or_default();
        let values = " <v>".repeat(flag.values);
        text.push_str(&format!(
            "  {short}{}{values}  {}\n",
            flag.name, flag.summary
        ));
    }
    text
}
