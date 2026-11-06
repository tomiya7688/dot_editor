//! `batch apply`: equivalence with one-at-a-time edits, all-or-nothing saving and strict input checks.

use std::fs;
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};

use serde_json::Value;

/// {
///   責務: [cli: 標準入力を閉じてpixel-cliを実行し、終了値と標準出力のJSONを返す]
///   処理: [
///     1: ビルド済みのバイナリを指定の引数で起動する
///     2: 標準出力をJSONとして読む。読めなければnullにする
///   ]
///   引数: [
///     arguments: コマンド行の語
///   ]
///   戻り値: [終了値とJSON]
/// }
fn cli(arguments: &[&str]) -> (i32, Value) {
    let output = Command::new(env!("CARGO_BIN_EXE_pixel-cli"))
        .args(arguments)
        .stdin(Stdio::null())
        .output()
        .expect("pixel-cli starts");
    let json = serde_json::from_slice(&output.stdout).unwrap_or(Value::Null);
    (output.status.code().expect("exit code"), json)
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
    let path = Path::new(env!("CARGO_TARGET_TMPDIR")).join(format!("batch-{name}"));
    let _ = fs::remove_dir_all(&path);
    fs::create_dir_all(&path).unwrap();
    path
}

/// {
///   責務: [new_project: 指定の名前で8x8の新しいプロジェクトを作る]
///   処理: [
///     1: project newを実行して成功を確認する
///   ]
///   引数: [
///     folder: 作業フォルダ
///     name: ファイル名
///   ]
///   戻り値: [プロジェクトのパス]
/// }
fn new_project(folder: &Path, name: &str) -> String {
    let project = folder.join(name).to_string_lossy().into_owned();
    let (code, _) = cli(&["--json", "-p", &project, "project", "new", "--size", "8"]);
    assert_eq!(code, 0);
    project
}

/// {
///   責務: [write_batch: バッチファイルを書いてパスを返す]
///   処理: [
///     1: 内容をそのままUTF-8で書く
///   ]
///   引数: [
///     folder: 作業フォルダ
///     text: ファイルの内容
///   ]
///   戻り値: [バッチファイルのパス]
/// }
fn write_batch(folder: &Path, text: &str) -> String {
    let path = folder.join("operations.json");
    fs::write(&path, text).unwrap();
    path.to_string_lossy().into_owned()
}

/// ひととおりの編集を含むバッチ。単独の呼び出しとの一致検査に使う。
const SAMPLE: &str = r##"{"version":1,"operations":[
  {"op":"pixel.paint","x":3,"y":4,"color":"#FF8800"},
  {"op":"detail.split","x":3,"y":4},
  {"op":"pixel.paint","x":3,"y":4,"child":[1,0],"color":"#0000FF"},
  {"op":"layer.add","name":"shadow"},
  {"op":"pixel.fill","x":0,"y":0,"color":"#102030"},
  {"op":"layer.visibility","visible":false},
  {"op":"pixel.erase","x":3,"y":4,"discard_detail":true},
  {"op":"layer.rename","new_name":"light","layer":"shadow"},
  {"op":"layer.move","direction":"down"},
  {"op":"detail.split-region","x":0,"y":0,"width":2,"height":2},
  {"op":"canvas.resolution.set","width":10,"height":10}
]}"##;

/// {
///   責務: [batch_matches_one_at_a_time_edits: バッチの結果が単独の呼び出しの連続と同じ作品・PNGになることを検証する]
///   処理: [
///     1: 同じ内容の2つの作品を用意し、片方へバッチ、もう片方へ同じ編集を1つずつ適用する
///     2: 保存されたJSONのバイト列と書き出したPNGのバイト列が一致することを確認する
///     3: 保存が1回で、結果にrevision_beforeとrevision_afterがあることを確認する
///   ]
///   引数: []
///   戻り値: [なし、不一致ならテストを失敗させる]
/// }
#[test]
fn batch_matches_one_at_a_time_edits() {
    let folder = workspace("equivalence");
    let batched = new_project(&folder, "batched.json");
    let stepped = new_project(&folder, "stepped.json");
    let batch = write_batch(&folder, SAMPLE);
    let (code, json) = cli(&["--json", "-p", &batched, "batch", "apply", "--file", &batch]);
    assert_eq!(code, 0, "{json}");
    assert_eq!(json["operation"], "batch.apply");
    assert_eq!(json["saved"], true);
    assert_eq!(json["result"]["operation_count"], 11);
    assert!(
        json["result"]["revision_before"]
            .as_str()
            .unwrap()
            .starts_with("sha256:")
    );
    assert_ne!(
        json["result"]["revision_before"],
        json["result"]["revision_after"]
    );

    let steps: Vec<Vec<&str>> = vec![
        vec!["pixel", "paint", "3", "4", "#FF8800"],
        vec!["detail", "split", "3", "4"],
        vec!["pixel", "paint", "3", "4", "--child", "1", "0", "#0000FF"],
        vec!["layer", "add", "shadow"],
        vec!["pixel", "fill", "0", "0", "#102030"],
        vec!["layer", "visibility", "off"],
        vec!["pixel", "erase", "3", "4", "--discard-detail"],
        vec!["layer", "rename", "light", "--layer", "shadow"],
        vec!["layer", "move", "down"],
        vec!["detail", "split-region", "0", "0", "2", "2"],
        vec!["canvas", "resolution", "set", "10", "10"],
    ];
    for step in &steps {
        let mut arguments = vec!["-p", stepped.as_str()];
        arguments.extend(step);
        assert_eq!(cli(&arguments).0, 0, "{step:?}");
    }
    // 保存JSONのバイト列は、単独実行が毎回再読込する分だけ表記の順序が変わりうるため、意味（層・画素・細部）で比べる。
    for arguments in [["layer", "list"], ["canvas", "info"]] {
        let (_, a) = cli(&["--json", "-p", &batched, arguments[0], arguments[1]]);
        let (_, b) = cli(&["--json", "-p", &stepped, arguments[0], arguments[1]]);
        assert!(a["result"] == b["result"], "{arguments:?} differs");
    }
    for (index, size) in [["--size", "20"], ["--size", "40"]].iter().enumerate() {
        let png_a = folder
            .join(format!("a{index}.png"))
            .to_string_lossy()
            .into_owned();
        let png_b = folder
            .join(format!("b{index}.png"))
            .to_string_lossy()
            .into_owned();
        let (code_a, _) = cli(&[
            "-p", &batched, "export", "render", "-o", &png_a, size[0], size[1],
        ]);
        let (code_b, _) = cli(&[
            "-p", &stepped, "export", "render", "-o", &png_b, size[0], size[1],
        ]);
        assert_eq!((code_a, code_b), (0, 0));
        assert!(
            fs::read(&png_a).unwrap() == fs::read(&png_b).unwrap(),
            "PNG {size:?} differs"
        );
    }
    for (x, y) in [(3, 4), (0, 0), (1, 1)] {
        let (x, y) = (x.to_string(), y.to_string());
        let (_, a) = cli(&["--json", "-p", &batched, "pixel", "sample", &x, &y]);
        let (_, b) = cli(&["--json", "-p", &stepped, "pixel", "sample", &x, &y]);
        assert!(a["result"] == b["result"], "sample {x},{y} differs");
    }
}

/// {
///   責務: [failure_saves_nothing_and_reports_the_index: 途中で失敗したら何も保存せず、失敗した操作を報告することを検証する]
///   処理: [
///     1: 2件目が範囲外になるバッチを実行する
///     2: 終了値1、元のエラー種別、details.failed_indexとopを確認する
///     3: プロジェクトのバイト列が変わっていないことを確認する
///   ]
///   引数: []
///   戻り値: [なし、不一致ならテストを失敗させる]
/// }
#[test]
fn failure_saves_nothing_and_reports_the_index() {
    let folder = workspace("atomic");
    let project = new_project(&folder, "art.json");
    let before = fs::read(&project).unwrap();
    let batch = write_batch(
        &folder,
        r##"{"version":1,"operations":[
          {"op":"pixel.paint","x":1,"y":1,"color":"#FF0000"},
          {"op":"pixel.paint","x":99,"y":1,"color":"#FF0000"},
          {"op":"pixel.paint","x":2,"y":2,"color":"#FF0000"}]}"##,
    );
    let (code, json) = cli(&["--json", "-p", &project, "batch", "apply", "--file", &batch]);
    assert_eq!(code, 1);
    assert_eq!(json["error"], "out_of_bounds");
    assert_eq!(json["details"]["failed_index"], 1);
    assert_eq!(json["details"]["op"], "pixel.paint");
    assert_eq!(fs::read(&project).unwrap(), before);
}

/// {
///   責務: [rejects_malformed_batches: 不正なバッチがすべてinvalid_batchで拒否され、何も保存されないことを検証する]
///   処理: [
///     1: 重複キー・未知のop・未知のフィールド・版違い・負数や小数の座標・型違い・未知のトップレベルを順に試す
///     2: いずれも終了値1、invalid_batch、プロジェクト不変であることを確認する
///   ]
///   引数: []
///   戻り値: [なし、不一致ならテストを失敗させる]
/// }
#[test]
fn rejects_malformed_batches() {
    let folder = workspace("strict");
    let project = new_project(&folder, "art.json");
    let before = fs::read(&project).unwrap();
    let cases = [
        r##"{"version":1,"operations":[],"operations":[]}"##,
        r##"{"version":1,"operations":[{"op":"pixel.paint","x":1,"y":1,"color":"#FF0000","x":2}]}"##,
        r##"{"version":1,"operations":[{"op":"pixel.sample","x":1,"y":1}]}"##,
        r##"{"version":1,"operations":[{"op":"batch.apply","file":"x"}]}"##,
        r##"{"version":1,"operations":[{"op":"project.new"}]}"##,
        r##"{"version":1,"operations":[{"op":"pixel.paint","x":1,"y":1,"color":"#FF0000","extra":1}]}"##,
        r##"{"version":2,"operations":[]}"##,
        r##"{"version":1,"operations":[],"note":"x"}"##,
        r##"{"version":1,"operations":[{"op":"pixel.paint","x":-1,"y":1,"color":"#FF0000"}]}"##,
        r##"{"version":1,"operations":[{"op":"pixel.paint","x":1.5,"y":1,"color":"#FF0000"}]}"##,
        r##"{"version":1,"operations":[{"op":"pixel.paint","x":"1","y":1,"color":"#FF0000"}]}"##,
        r##"{"version":1,"operations":[{"op":"pixel.paint","x":1,"y":1}]}"##,
        r##"{"version":1,"operations":[{"op":"pixel.paint","x":1,"y":1,"color":"red"}]}"##,
        r##"{"version":1,"operations":[{"op":"pixel.paint","x":1,"y":1,"color":"#FF0000","child":[0]}]}"##,
        r##"{"version":1,"operations":[{"op":"layer.visibility","visible":"on"}]}"##,
        r##"{"version":1,"operations":[1]}"##,
        r##"[1]"##,
        r##"not json"##,
        r##"{"version":1,"operations":[]} trailing"##,
    ];
    for text in cases {
        let batch = write_batch(&folder, text);
        let (code, json) = cli(&["--json", "-p", &project, "batch", "apply", "--file", &batch]);
        assert_eq!(code, 1, "{text}: {json}");
        assert_eq!(json["error"], "invalid_batch", "{text}: {json}");
        assert_eq!(fs::read(&project).unwrap(), before, "{text}");
    }
    let located = write_batch(
        &folder,
        r##"{"version":1,"operations":[
          {"op":"pixel.paint","x":1,"y":1,"color":"#FF0000"},
          {"op":"pixel.paint","x":-1,"y":1,"color":"#FF0000"}]}"##,
    );
    let (_, json) = cli(&[
        "--json", "-p", &project, "batch", "apply", "--file", &located,
    ]);
    assert_eq!(json["details"]["failed_index"], 1);
    assert_eq!(json["details"]["op"], "pixel.paint");
    let (code, json) = cli(&["--json", "-p", &project, "batch", "apply"]);
    assert_eq!((code, json["error"].as_str()), (2, Some("usage")));
    let (code, json) = cli(&[
        "--json",
        "-p",
        &project,
        "batch",
        "apply",
        "--file",
        "missing.json",
    ]);
    assert_eq!((code, json["error"].as_str()), (1, Some("file_not_found")));
}

/// {
///   責務: [empty_dry_run_limits_and_aliases: 0件・dry-run・件数と大きさの上限・同一ファイルの扱いを検証する]
///   処理: [
///     1: 0件は成功して保存しないことを確認する
///     2: dry-runは変更予定を報告しても保存しないことを確認する
///     3: 10000件は成功し、10001件と8MiB超はinvalid_batchになることを確認する
///     4: バッチファイルがプロジェクト自身なら拒否することを確認する
///   ]
///   引数: []
///   戻り値: [なし、不一致ならテストを失敗させる]
/// }
#[test]
fn empty_dry_run_limits_and_aliases() {
    let folder = workspace("limits");
    let project = new_project(&folder, "art.json");
    let before = fs::read(&project).unwrap();
    let batch = write_batch(&folder, r#"{"version":1,"operations":[]}"#);
    let (code, json) = cli(&["--json", "-p", &project, "batch", "apply", "--file", &batch]);
    assert_eq!(
        (code, &json["saved"], &json["result"]["changed"]),
        (0, &Value::Bool(false), &Value::Bool(false))
    );

    let paint = r##"{"op":"pixel.paint","x":1,"y":1,"color":"#FF0000"}"##;
    let batch = write_batch(
        &folder,
        &format!(r#"{{"version":1,"operations":[{paint}]}}"#),
    );
    let (code, json) = cli(&[
        "--json",
        "--dry-run",
        "-p",
        &project,
        "batch",
        "apply",
        "--file",
        &batch,
    ]);
    assert_eq!(
        (code, &json["saved"], &json["result"]["changed"]),
        (0, &Value::Bool(false), &Value::Bool(true))
    );
    assert!(json["result"].get("revision_after").is_none());
    assert_eq!(fs::read(&project).unwrap(), before);

    let many = vec![paint; 10_000].join(",");
    let batch = write_batch(
        &folder,
        &format!(r#"{{"version":1,"operations":[{many}]}}"#),
    );
    let (code, json) = cli(&["--json", "-p", &project, "batch", "apply", "--file", &batch]);
    assert_eq!(
        (code, &json["result"]["operation_count"]),
        (0, &Value::from(10_000))
    );
    let too_many = vec![paint; 10_001].join(",");
    let batch = write_batch(
        &folder,
        &format!(r#"{{"version":1,"operations":[{too_many}]}}"#),
    );
    let (code, json) = cli(&["--json", "-p", &project, "batch", "apply", "--file", &batch]);
    assert_eq!((code, json["error"].as_str()), (1, Some("invalid_batch")));

    let huge = format!(
        r#"{{"version":1,"operations":[],"pad":"{}"}}"#,
        "x".repeat(8 * 1024 * 1024)
    );
    let batch = write_batch(&folder, &huge);
    let (code, json) = cli(&["--json", "-p", &project, "batch", "apply", "--file", &batch]);
    assert_eq!((code, json["error"].as_str()), (1, Some("invalid_batch")));

    let alias = folder
        .join(".")
        .join("art.json")
        .to_string_lossy()
        .into_owned();
    let (code, json) = cli(&["--json", "-p", &project, "batch", "apply", "--file", &alias]);
    assert_eq!((code, json["error"].as_str()), (1, Some("invalid_batch")));
}

/// {
///   責務: [batch_respects_if_revision: 古いrevisionではバッチも保存されないことを検証する]
///   処理: [
///     1: 別の編集で作品を進めた後、古いrevisionつきでバッチを実行する
///     2: revision_conflictで失敗し、作品が変わっていないことを確認する
///   ]
///   引数: []
///   戻り値: [なし、不一致ならテストを失敗させる]
/// }
#[test]
fn batch_respects_if_revision() {
    let folder = workspace("revision");
    let project = new_project(&folder, "art.json");
    let (_, status) = cli(&["--json", "-p", &project, "status"]);
    let stale = status["result"]["revision"].as_str().unwrap().to_owned();
    cli(&["-p", &project, "pixel", "paint", "0", "0", "#00FF00"]);
    let before = fs::read(&project).unwrap();
    let batch = write_batch(
        &folder,
        r##"{"version":1,"operations":[{"op":"pixel.paint","x":1,"y":1,"color":"#FF0000"}]}"##,
    );
    let (code, json) = cli(&[
        "--json",
        "-p",
        &project,
        "--if-revision",
        &stale,
        "batch",
        "apply",
        "--file",
        &batch,
    ]);
    assert_eq!(
        (code, json["error"].as_str()),
        (1, Some("revision_conflict"))
    );
    assert_eq!(fs::read(&project).unwrap(), before);
}

/// {
///   責務: [failing_cases_keep_the_project_byte_identical: 存在しないレイヤー・無効な子セル・予算超過で全体が失敗し、作品が1バイトも変わらないことを検証する]
///   処理: [
///     1: 先頭の操作は有効で、後ろの操作が失敗するバッチを3種類実行する
///     2: 終了値1、期待するエラー種別、失敗位置、プロジェクトのバイト列不変を確認する
///   ]
///   引数: []
///   戻り値: [なし、不一致ならテストを失敗させる]
/// }
#[test]
fn failing_cases_keep_the_project_byte_identical() {
    let folder = workspace("failing");
    let project = new_project(&folder, "art.json");
    let before = fs::read(&project).unwrap();
    let ok = r##"{"op":"pixel.paint","x":1,"y":1,"color":"#FF0000"}"##;
    let cases = [
        (r#"{"op":"layer.select","name":"nope"}"#, "no_such_layer"),
        (
            r##"{"op":"pixel.paint","x":0,"y":0,"child":[1,1],"color":"#FF0000"}"##,
            "cell_not_split",
        ),
        (
            r#"{"op":"canvas.resolution.set","width":4096,"height":4096}"#,
            "resource_limit",
        ),
    ];
    for (bad, expected) in cases {
        let batch = write_batch(
            &folder,
            &format!(r#"{{"version":1,"operations":[{ok},{bad}]}}"#),
        );
        let (code, json) = cli(&["--json", "-p", &project, "batch", "apply", "--file", &batch]);
        assert_eq!(code, 1, "{bad}: {json}");
        assert_eq!(json["error"], expected, "{bad}: {json}");
        if expected != "resource_limit" {
            assert_eq!(json["details"]["failed_index"], 1, "{bad}");
        }
        assert_eq!(fs::read(&project).unwrap(), before, "{bad}");
    }
}

/// {
///   責務: [non_square_transparent_and_repeats_match_single_edits: 非正方形・透明色・同じセルの繰り返しが、単独の編集と同じ結果になることを検証する]
///   処理: [
///     1: 5x3の2つの作品へ、バッチと単独の編集で、同じセルへの塗りと透明色の塗りを繰り返す
///     2: 全セルの色が一致することを確認する
///   ]
///   引数: []
///   戻り値: [なし、不一致ならテストを失敗させる]
/// }
#[test]
fn non_square_transparent_and_repeats_match_single_edits() {
    let folder = workspace("shape");
    let make = |name: &str| {
        let project = folder.join(name).to_string_lossy().into_owned();
        let (code, _) = cli(&[
            "--json",
            "-p",
            &project,
            "project",
            "new",
            "--resolution",
            "5",
            "3",
        ]);
        assert_eq!(code, 0);
        project
    };
    let batched = make("batched.json");
    let stepped = make("stepped.json");
    let batch = write_batch(
        &folder,
        r##"{"version":1,"operations":[
          {"op":"pixel.paint","x":4,"y":2,"color":"#112233"},
          {"op":"pixel.paint","x":4,"y":2,"color":"#112233"},
          {"op":"pixel.paint","x":0,"y":0,"color":"#FF000000"},
          {"op":"pixel.paint","x":1,"y":1,"color":"#445566AA"},
          {"op":"pixel.fill","x":2,"y":0,"color":"#778899"}]}"##,
    );
    let (code, _) = cli(&["--json", "-p", &batched, "batch", "apply", "--file", &batch]);
    assert_eq!(code, 0);
    for step in [
        ["pixel", "paint", "4", "2", "#112233"],
        ["pixel", "paint", "4", "2", "#112233"],
        ["pixel", "paint", "0", "0", "#FF000000"],
        ["pixel", "paint", "1", "1", "#445566AA"],
        ["pixel", "fill", "2", "0", "#778899"],
    ] {
        let mut arguments = vec!["-p", stepped.as_str()];
        arguments.extend(step);
        assert_eq!(cli(&arguments).0, 0);
    }
    for x in 0..5 {
        for y in 0..3 {
            let (x, y) = (x.to_string(), y.to_string());
            let (code_a, a) = cli(&["--json", "-p", &batched, "pixel", "sample", &x, &y]);
            let (code_b, b) = cli(&["--json", "-p", &stepped, "pixel", "sample", &x, &y]);
            assert_eq!((code_a, code_b), (0, 0), "sample {x},{y}");
            assert!(a["result"] == b["result"], "cell {x},{y} differs");
        }
    }
}

/// {
///   責務: [every_edit_command_is_a_batch_operation: 編集コマンドがすべてバッチのopとして受け付けられ、dry-runがフォルダを変えないことを検証する]
///   処理: [
///     1: コマンド表から編集コマンドの一覧を取得する
///     2: 各idをopにしたバッチが「未知のop」で拒否されないことを確認する
///     3: dry-runの前後でフォルダの内容が同じで、sidecarや一時ファイルが増えないことを確認する
///   ]
///   引数: []
///   戻り値: [なし、不一致ならテストを失敗させる]
/// }
#[test]
fn every_edit_command_is_a_batch_operation() {
    let folder = workspace("coverage");
    let project = new_project(&folder, "art.json");
    let (_, catalog) = cli(&["--commands-json"]);
    let mut seen = 0;
    for command in catalog["commands"].as_array().unwrap() {
        if command["effect"] != "edit" || command["id"] == "batch.apply" {
            continue;
        }
        let id = command["id"].as_str().unwrap();
        let batch = write_batch(
            &folder,
            &format!(r#"{{"version":1,"operations":[{{"op":"{id}"}}]}}"#),
        );
        // 必須フィールドの無いopは、opとしては受理され、欠けたフィールドだけを理由に拒否される。
        let (code, json) = cli(&["--json", "-p", &project, "batch", "apply", "--file", &batch]);
        let message = json["message"].as_str().unwrap_or_default();
        let takes_no_fields = command["positionals"].as_array().unwrap().is_empty();
        if takes_no_fields {
            // 位置引数の無いop（layer.remove）は、そのまま有効に実行されうる。
            assert!(code == 0 || json["error"] == "last_layer", "{id}: {json}");
        } else {
            assert_eq!(
                (code, json["error"].as_str()),
                (1, Some("invalid_batch")),
                "{id}: {json}"
            );
            assert!(message.contains("needs"), "{id}: {message}");
        }
        assert!(!message.contains("unknown op"), "{id}: {message}");
        seen += 1;
    }
    assert_eq!(seen, 13);
    // 名前と大きさの一覧。dry-runの前後で同じであることを確認する。
    let names = |path: &Path| {
        let mut list: Vec<_> = fs::read_dir(path)
            .unwrap()
            .map(|entry| {
                let entry = entry.unwrap();
                (entry.file_name(), entry.metadata().unwrap().len())
            })
            .collect();
        list.sort();
        list
    };
    let batch = write_batch(
        &folder,
        r##"{"version":1,"operations":[{"op":"pixel.paint","x":1,"y":1,"color":"#FF0000"}]}"##,
    );
    let listed = names(&folder);
    let project_bytes = fs::read(&project).unwrap();
    let (code, _) = cli(&[
        "--json",
        "--dry-run",
        "-p",
        &project,
        "batch",
        "apply",
        "--file",
        &batch,
    ]);
    assert_eq!(code, 0);
    assert_eq!(names(&folder), listed);
    assert_eq!(fs::read(&project).unwrap(), project_bytes);
}
