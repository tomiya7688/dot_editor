//! Shell-contract tests: every case spawns the real `pixel-cli` binary.

use std::fs;
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};

use serde_json::Value;

/// {
///   責務: [Run: 1回のプロセス実行の終了値と出力を保持する]
///   フィールド: [
///     code: 終了値
///     stdout: 標準出力
///     stderr: 標準エラー
///   ]
/// }
struct Run {
    code: i32,
    stdout: String,
    stderr: String,
}

impl Run {
    /// {
    ///   責務: [json: 標準出力が1つのJSONだけであることを確認して読む]
    ///   処理: [
    ///     1: 標準出力全体をJSONとして解析する
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///   ]
    ///   戻り値: [JSON値、解析できなければテストを失敗させる]
    /// }
    fn json(&self) -> Value {
        serde_json::from_str(&self.stdout).unwrap_or_else(|error| {
            panic!("stdout is not one JSON value ({error}): {}", self.stdout)
        })
    }
}

/// {
///   責務: [cli: 標準入力を閉じた状態でpixel-cliを実行する]
///   処理: [
///     1: ビルド済みのバイナリを指定の引数で起動する
///     2: 終了値と両方の出力を集める
///   ]
///   引数: [
///     arguments: コマンド行の語
///   ]
///   戻り値: [実行結果]
/// }
fn cli(arguments: &[&str]) -> Run {
    let output = Command::new(env!("CARGO_BIN_EXE_pixel-cli"))
        .args(arguments)
        .stdin(Stdio::null())
        .output()
        .expect("pixel-cli starts");
    Run {
        code: output.status.code().expect("exit code"),
        stdout: String::from_utf8(output.stdout).unwrap(),
        stderr: String::from_utf8(output.stderr).unwrap(),
    }
}

/// {
///   責務: [workspace: テストごとに空の作業フォルダを作る]
///   処理: [
///     1: ターゲットの一時領域の下にテスト名のフォルダを作り直す
///   ]
///   引数: [
///     name: テスト名
///   ]
///   戻り値: [作業フォルダのパス]
/// }
fn workspace(name: &str) -> PathBuf {
    let path = Path::new(env!("CARGO_TARGET_TMPDIR")).join(format!("cli-{name}"));
    let _ = fs::remove_dir_all(&path);
    fs::create_dir_all(&path).unwrap();
    path
}

/// {
///   責務: [project_in: 作業フォルダ内のプロジェクトのパス文字列を返す]
///   処理: [
///     1: フォルダと固定のファイル名を連結する
///   ]
///   引数: [
///     folder: 作業フォルダ
///   ]
///   戻り値: [プロジェクトのパス]
/// }
fn project_in(folder: &Path) -> String {
    folder.join("art.json").to_string_lossy().into_owned()
}

/// {
///   責務: [new_project: 指定の大きさの新しいプロジェクトを作る]
///   処理: [
///     1: project newを実行して成功を確認する
///   ]
///   引数: [
///     folder: 作業フォルダ
///     size: 正方形の一辺
///   ]
///   戻り値: [プロジェクトのパス]
/// }
fn new_project(folder: &Path, size: &str) -> String {
    let project = project_in(folder);
    let run = cli(&["-p", &project, "project", "new", "--size", size]);
    assert_eq!(run.code, 0, "{}", run.stderr);
    project
}

/// {
///   責務: [new_project_can_be_inspected_in_json: 新規作成と各種の読み取りがJSON契約に従うことを回帰検証する]
///   処理: [
///     1: 新規作成し、project info・canvas info・statusを--jsonで読む
///     2: status・operation・resultの形と、標準エラーが空であることを確認する
///   ]
///   引数: []
///   戻り値: [なし、不一致ならテストを失敗させる]
/// }
#[test]
fn new_project_can_be_inspected_in_json() {
    let folder = workspace("inspect");
    let project = new_project(&folder, "4");
    for (words, operation) in [
        (vec!["project", "info"], "project.info"),
        (vec!["canvas", "info"], "canvas.info"),
        (vec!["status"], "status"),
    ] {
        let mut arguments = vec!["--json", "-p", project.as_str()];
        arguments.extend(words);
        let run = cli(&arguments);
        assert_eq!(run.code, 0);
        assert_eq!(run.stderr, "");
        let document = run.json();
        assert_eq!(document["status"], "ok");
        assert_eq!(document["operation"], operation);
        assert_eq!(document["project"], project.as_str());
        assert_eq!(document["result"]["resolution"]["width"], 4);
        assert_eq!(document["result"]["active_layer"], "背景");
    }
}

/// {
///   責務: [edits_persist_between_separate_processes: 別々のプロセスで行った編集が保存されて読み戻せることを回帰検証する]
///   処理: [
///     1: paint・fill・eraseを別々に実行する
///     2: sampleで色が保存されていることを確認する
///   ]
///   引数: []
///   戻り値: [なし、不一致ならテストを失敗させる]
/// }
#[test]
fn edits_persist_between_separate_processes() {
    let folder = workspace("persist");
    let project = new_project(&folder, "3");
    assert_eq!(
        cli(&["-p", &project, "pixel", "paint", "1", "1", "#336699"]).code,
        0
    );
    let fill = cli(&[
        "--json",
        "-p",
        &project,
        "pixel",
        "fill",
        "0",
        "0",
        "#FF000080",
    ]);
    assert_eq!(fill.json()["result"]["cells"], 8);
    assert_eq!(cli(&["-p", &project, "pixel", "erase", "2", "2"]).code, 0);
    let color = |x: &str, y: &str| {
        cli(&["--json", "-p", &project, "pixel", "sample", x, y]).json()["result"]["color"].clone()
    };
    assert_eq!(color("1", "1"), "#336699FF");
    assert_eq!(color("0", "0"), "#FF000080");
    assert_eq!(color("2", "2"), "#00000000");
}

/// {
///   責務: [dry_run_never_writes: --dry-runがファイルを作らず変更もしないことを回帰検証する]
///   処理: [
///     1: 新規作成と編集を--dry-runで実行する
///     2: ファイルが作られない・編集前後でバイト列が同じことと、結果にdry_runが載ることを確認する
///   ]
///   引数: []
///   戻り値: [なし、不一致ならテストを失敗させる]
/// }
#[test]
fn dry_run_never_writes() {
    let folder = workspace("dry-run");
    let project = project_in(&folder);
    let planned = cli(&[
        "--json",
        "--dry-run",
        "-p",
        &project,
        "project",
        "new",
        "--size",
        "2",
    ]);
    assert_eq!(planned.code, 0);
    assert_eq!(planned.json()["dry_run"], true);
    assert_eq!(planned.json()["saved"], false);
    assert!(!Path::new(&project).exists());
    new_project(&folder, "2");
    let before = fs::read(&project).unwrap();
    let edit = cli(&[
        "--json",
        "--dry-run",
        "-p",
        &project,
        "pixel",
        "paint",
        "0",
        "0",
        "#112233",
    ]);
    assert_eq!(edit.code, 0);
    assert_eq!(edit.json()["result"]["changed"], true);
    assert_eq!(edit.json()["saved"], false);
    assert_eq!(fs::read(&project).unwrap(), before);
    let output = folder.join("out.png");
    let export = cli(&[
        "--dry-run",
        "-p",
        &project,
        "export",
        "render",
        "-o",
        output.to_str().unwrap(),
    ]);
    assert_eq!(export.code, 0);
    assert!(!output.exists());
}

/// {
///   責務: [usage_errors_exit_two_with_a_json_error: 使い方の誤りが終了値2とJSONエラーになることを回帰検証する]
///   処理: [
///     1: 未知のコマンド・プロジェクト未指定・数字以外・不正な色・引数不足を実行する
///     2: 終了値2、標準出力のエラーJSON、標準エラーの説明を確認する
///   ]
///   引数: []
///   戻り値: [なし、不一致ならテストを失敗させる]
/// }
#[test]
fn usage_errors_exit_two_with_a_json_error() {
    let folder = workspace("usage");
    let project = new_project(&folder, "2");
    let cases: [Vec<&str>; 6] = [
        vec!["--json", "-p", &project, "frobnicate"],
        vec!["--json", "status"],
        vec![
            "--json", "-p", &project, "pixel", "paint", "x", "0", "#000000",
        ],
        vec!["--json", "-p", &project, "pixel", "paint", "0", "0", "red"],
        vec!["--json", "-p", &project, "pixel", "paint", "0", "0"],
        vec![
            "--json", "-p", &project, "pixel", "paint", "0", "0", "#000000", "--bogus",
        ],
    ];
    for arguments in cases {
        let run = cli(&arguments);
        assert_eq!(run.code, 2, "{arguments:?}");
        let document = run.json();
        assert_eq!(document["status"], "error", "{arguments:?}");
        assert_eq!(document["error"], "usage", "{arguments:?}");
        assert!(run.stderr.starts_with("error: "), "{arguments:?}");
    }
    assert_eq!(cli(&[]).code, 2);
}

/// {
///   責務: [runtime_failures_exit_one_and_keep_the_project: 実行時の失敗が終了値1になりプロジェクトを変えないことを回帰検証する]
///   処理: [
///     1: 範囲外の座標・存在しないファイル・壊れたファイル・重複名・最後の層の削除を実行する
///     2: 終了値1と種別名、失敗した編集の前後でファイルが同じことを確認する
///   ]
///   引数: []
///   戻り値: [なし、不一致ならテストを失敗させる]
/// }
#[test]
fn runtime_failures_exit_one_and_keep_the_project() {
    let folder = workspace("failures");
    let project = new_project(&folder, "2");
    let before = fs::read(&project).unwrap();
    let broken = folder.join("broken.json");
    fs::write(&broken, "{ not json").unwrap();
    let missing = folder.join("missing.json");
    let cases: [(Vec<&str>, &str); 5] = [
        (
            vec!["-p", &project, "pixel", "paint", "5", "0", "#000000"],
            "out_of_bounds",
        ),
        (
            vec!["-p", missing.to_str().unwrap(), "status"],
            "file_not_found",
        ),
        (
            vec!["-p", broken.to_str().unwrap(), "status"],
            "invalid_project",
        ),
        (
            vec!["-p", &project, "layer", "add", "背景"],
            "duplicate_layer",
        ),
        (vec!["-p", &project, "layer", "remove"], "last_layer"),
    ];
    for (arguments, code) in cases {
        let mut full = vec!["--json"];
        full.extend(&arguments);
        let run = cli(&full);
        assert_eq!(run.code, 1, "{arguments:?}");
        assert_eq!(run.json()["error"], code, "{arguments:?}");
    }
    assert_eq!(fs::read(&project).unwrap(), before);
}

/// {
///   責務: [new_refuses_to_overwrite_without_force: 既存ファイルを--forceなしで上書きしないことを回帰検証する]
///   処理: [
///     1: 既存のプロジェクトへproject newを実行する
///     2: 拒否と内容の不変、--forceでの置き換えを確認する
///   ]
///   引数: []
///   戻り値: [なし、不一致ならテストを失敗させる]
/// }
#[test]
fn new_refuses_to_overwrite_without_force() {
    let folder = workspace("overwrite");
    let project = new_project(&folder, "2");
    let before = fs::read(&project).unwrap();
    let refused = cli(&["--json", "-p", &project, "project", "new", "--size", "9"]);
    assert_eq!(refused.code, 1);
    assert_eq!(refused.json()["error"], "file_exists");
    assert_eq!(fs::read(&project).unwrap(), before);
    let forced = cli(&["-p", &project, "project", "new", "--size", "9", "--force"]);
    assert_eq!(forced.code, 0);
    let info = cli(&["--json", "-p", &project, "canvas", "info"]);
    assert_eq!(info.json()["result"]["resolution"]["width"], 9);
}

/// {
///   責務: [layers_and_detail_flow_works_from_the_shell: レイヤーと細部の操作がシェルから通しで使えることを回帰検証する]
///   処理: [
///     1: 層の追加・名前変更・移動・表示切替・選択を実行する
///     2: 領域分割・子セル塗り・子セル読み取り・細部情報を実行する
///   ]
///   引数: []
///   戻り値: [なし、不一致ならテストを失敗させる]
/// }
#[test]
fn layers_and_detail_flow_works_from_the_shell() {
    let folder = workspace("layers");
    let project = new_project(&folder, "4");
    let run = |words: &[&str]| {
        let mut arguments = vec!["--json", "-p", project.as_str()];
        arguments.extend(words);
        let outcome = cli(&arguments);
        assert_eq!(outcome.code, 0, "{words:?}: {}", outcome.stderr);
        outcome.json()
    };
    run(&["layer", "add", "線画"]);
    run(&["layer", "rename", "ペン", "--layer", "線画"]);
    run(&["layer", "move", "down"]);
    run(&["layer", "visibility", "off", "--layer", "背景"]);
    let listed = run(&["layer", "list"]);
    let names: Vec<&str> = listed["result"]["layers"]
        .as_array()
        .unwrap()
        .iter()
        .map(|layer| layer["name"].as_str().unwrap())
        .collect();
    assert_eq!(names, ["ペン", "背景"]);
    assert_eq!(listed["result"]["layers"][1]["visible"], false);
    run(&["layer", "select", "背景"]);
    assert_eq!(run(&["status"])["result"]["active_layer"], "背景");
    assert_eq!(
        run(&["detail", "split-region", "0", "0", "2", "2"])["result"]["expanded"],
        4
    );
    run(&["pixel", "paint", "1", "1", "#00FF00", "--child", "1", "0"]);
    let child = run(&["pixel", "sample", "1", "1", "--child", "1", "0"]);
    assert_eq!(child["result"]["color"], "#00FF00FF");
    assert_eq!(run(&["detail", "info", "1", "1"])["result"]["split"], true);
    assert_eq!(
        run(&["canvas", "info"])["result"]["native_resolution"]["width"],
        8
    );
    assert_eq!(run(&["detail", "info", "3", "3"])["result"]["split"], false);
}

/// {
///   責務: [png_size: PNGの先頭から幅と高さを読む]
///   処理: [
///     1: 署名とIHDRの位置から幅・高さを取り出す
///   ]
///   引数: [
///     path: PNGファイルのパス
///   ]
///   戻り値: [幅と高さ、PNGでなければテストを失敗させる]
/// }
fn png_size(path: &Path) -> (u32, u32) {
    let bytes = fs::read(path).unwrap();
    assert_eq!(
        &bytes[..8],
        &[0x89, b'P', b'N', b'G', 0x0D, 0x0A, 0x1A, 0x0A]
    );
    let number = |at: usize| u32::from_be_bytes(bytes[at..at + 4].try_into().unwrap());
    (number(16), number(20))
}

/// {
///   責務: [export_writes_a_png_in_each_mode: 書き出しが自然・拡大・解像度指定の各方式でPNGを作ることを回帰検証する]
///   処理: [
///     1: 分割した作品を3方式で書き出し、寸法を確認する
///     2: 小さすぎる拡大・プロジェクト自身への出力・両方式の同時指定を拒否することを確認する
///   ]
///   引数: []
///   戻り値: [なし、不一致ならテストを失敗させる]
/// }
#[test]
fn export_writes_a_png_in_each_mode() {
    let folder = workspace("export");
    let project = new_project(&folder, "2");
    assert_eq!(cli(&["-p", &project, "detail", "split", "0", "0"]).code, 0);
    let render = |extra: &[&str], name: &str| {
        let output = folder.join(name);
        let mut arguments = vec!["--json", "-p", project.as_str(), "export", "render", "-o"];
        arguments.push(output.to_str().unwrap());
        arguments.extend(extra);
        (cli(&arguments), output)
    };
    let (native, path) = render(&[], "native.png");
    assert_eq!(native.code, 0, "{}", native.stderr);
    assert_eq!(png_size(&path), (4, 4));
    let (scaled, path) = render(&["--size", "9"], "scaled.png");
    assert_eq!(scaled.code, 0);
    assert_eq!(png_size(&path), (9, 9));
    let (detail, path) = render(&["--resolution", "6", "3"], "detail.png");
    assert_eq!(detail.code, 0);
    assert_eq!(png_size(&path), (6, 3));
    assert_eq!(
        render(&["--size", "3"], "small.png").0.json()["error"],
        "invalid_export_size"
    );
    assert_eq!(
        render(&["--size", "9", "--resolution", "2", "2"], "both.png")
            .0
            .code,
        2
    );
    let same = cli(&["--json", "-p", &project, "export", "render", "-o", &project]);
    assert_eq!(same.json()["error"], "invalid_output");
}

/// {
///   責務: [single_canvas_projects_load_and_are_saved_as_layered: 単一Canvasの旧文書を1層として読み、保存時にレイヤー付きにすることを回帰検証する]
///   処理: [
///     1: 共有フィクスチャの単一Canvas文書をコピーして読む
///     2: 編集後にレイヤー付きversion 2で保存され、元の画素が残ることを確認する
///   ]
///   引数: []
///   戻り値: [なし、不一致ならテストを失敗させる]
/// }
#[test]
fn single_canvas_projects_load_and_are_saved_as_layered() {
    let folder = workspace("flat");
    let project = project_in(&folder);
    let flat =
        include_str!("../../../../tests/fixtures/project_json/transparent_rectangular_v2.json");
    fs::write(&project, flat).unwrap();
    let status = cli(&["--json", "-p", &project, "status"]);
    assert_eq!(status.code, 0, "{}", status.stderr);
    assert_eq!(status.json()["result"]["layer_count"], 1);
    let sample = || {
        cli(&["--json", "-p", &project, "pixel", "sample", "0", "0"]).json()["result"]["rgba"]
            .clone()
    };
    let before = sample();
    assert_eq!(cli(&["-p", &project, "layer", "add", "上"]).code, 0);
    let saved: Value = serde_json::from_str(&fs::read_to_string(&project).unwrap()).unwrap();
    assert_eq!(saved["version"], 2);
    assert_eq!(saved["layers"].as_array().unwrap().len(), 2);
    // 新しい層は空なので、背景を選び直すと元の画素がそのまま読める。
    assert_eq!(cli(&["-p", &project, "layer", "select", "背景"]).code, 0);
    assert_eq!(sample(), before);
}

/// {
///   責務: [help_and_version_succeed: ヘルプとバージョンが成功し標準出力へ出ることを回帰検証する]
///   処理: [
///     1: --help・コマンド別--help・--version・--version --jsonを実行する
///   ]
///   引数: []
///   戻り値: [なし、不一致ならテストを失敗させる]
/// }
#[test]
fn help_and_version_succeed() {
    let help = cli(&["--help"]);
    assert_eq!(help.code, 0);
    assert!(help.stdout.contains("pixel paint"));
    assert!(help.stdout.contains("layer visibility"));
    let command = cli(&["pixel", "paint", "--help"]);
    assert!(command.stdout.contains("--child"));
    assert_eq!(
        cli(&["--version"]).stdout,
        format!("pixel-cli {}\n", env!("CARGO_PKG_VERSION"))
    );
    let json = cli(&["--json", "--version"]).json();
    assert_eq!(json["result"]["version"], env!("CARGO_PKG_VERSION"));
}
