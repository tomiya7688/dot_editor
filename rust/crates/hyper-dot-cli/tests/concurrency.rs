//! Concurrent-edit protection: revisions, locking and non-clobbering creation, via real processes.

use std::fs::{self, OpenOptions};
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::thread;
use std::time::Duration;

use serde_json::Value;

/// {
///   責務: [cli: 標準入力を閉じた状態でpixel-cliを実行し、終了値と標準出力のJSONを返す]
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
    let path = Path::new(env!("CARGO_TARGET_TMPDIR")).join(format!("concurrency-{name}"));
    let _ = fs::remove_dir_all(&path);
    fs::create_dir_all(&path).unwrap();
    path
}

/// {
///   責務: [new_project: 新しい16x16のプロジェクトを作り、パスを返す]
///   処理: [
///     1: project newを実行して成功を確認する
///   ]
///   引数: [
///     folder: 作業フォルダ
///   ]
///   戻り値: [プロジェクトのパス]
/// }
fn new_project(folder: &Path) -> String {
    let project = folder.join("art.json").to_string_lossy().into_owned();
    let (code, _) = cli(&["--json", "-p", &project, "project", "new", "--size", "16"]);
    assert_eq!(code, 0);
    project
}

/// {
///   責務: [revision_of_status: statusが返すrevisionを取り出す]
///   処理: [
///     1: status --jsonを実行し、resultのrevisionを読む
///   ]
///   引数: [
///     project: プロジェクトのパス
///   ]
///   戻り値: [revisionの文字列]
/// }
fn revision_of_status(project: &str) -> String {
    let (code, json) = cli(&["--json", "-p", project, "status"]);
    assert_eq!(code, 0);
    json["result"]["revision"]
        .as_str()
        .expect("revision")
        .to_owned()
}

/// {
///   責務: [status_reports_revision_and_edits_change_it: revisionの形と、編集で変わることを検証する]
///   処理: [
///     1: statusとproject infoが同じ書式のrevisionを返すことを確認する
///     2: 塗ると保存後のrevisionが結果とstatusの両方で新しい値になることを確認する
///   ]
///   引数: []
///   戻り値: [なし、不一致ならテストを失敗させる]
/// }
#[test]
fn status_reports_revision_and_edits_change_it() {
    let project = new_project(&workspace("revision"));
    let before = revision_of_status(&project);
    assert!(before.starts_with("sha256:") && before.len() == 71);
    let (_, info) = cli(&["--json", "-p", &project, "project", "info"]);
    assert_eq!(info["result"]["revision"], before.as_str());
    let (code, painted) = cli(&[
        "--json", "-p", &project, "pixel", "paint", "1", "1", "#FF0000",
    ]);
    assert_eq!(code, 0);
    let after = revision_of_status(&project);
    assert_ne!(after, before);
    assert_eq!(painted["result"]["revision"], after.as_str());
}

/// {
///   責務: [stale_revision_conflicts_and_saves_nothing: 古いrevisionでは編集も保存もされないことを検証する]
///   処理: [
///     1: 別の編集で作品を進めた後、古いrevisionを付けた編集を実行する
///     2: revision_conflictで失敗し、ファイルが変わっていないことを確認する
///     3: 現在のrevisionを付けた編集は成功することを確認する
///   ]
///   引数: []
///   戻り値: [なし、不一致ならテストを失敗させる]
/// }
#[test]
fn stale_revision_conflicts_and_saves_nothing() {
    let project = new_project(&workspace("stale"));
    let stale = revision_of_status(&project);
    cli(&["-p", &project, "pixel", "paint", "0", "0", "#00FF00"]);
    let bytes = fs::read(&project).unwrap();
    let (code, json) = cli(&[
        "--json",
        "-p",
        &project,
        "--if-revision",
        &stale,
        "pixel",
        "paint",
        "2",
        "2",
        "#0000FF",
    ]);
    assert_eq!(code, 1);
    assert_eq!(json["error"], "revision_conflict");
    assert_eq!(fs::read(&project).unwrap(), bytes);
    let current = revision_of_status(&project);
    let (code, _) = cli(&[
        "--json",
        "-p",
        &project,
        "--if-revision",
        &current,
        "pixel",
        "paint",
        "2",
        "2",
        "#0000FF",
    ]);
    assert_eq!(code, 0);
}

/// {
///   責務: [bad_or_missing_revision_cases: 不正な表記は使い方の誤り、存在しないファイルへの期待は競合になることを検証する]
///   処理: [
///     1: 形式の誤ったrevisionと範囲外のロック待ちが終了値2になることを確認する
///     2: 存在しない作品に既存のrevisionを要求するとrevision_conflictになることを確認する
///   ]
///   引数: []
///   戻り値: [なし、不一致ならテストを失敗させる]
/// }
#[test]
fn bad_or_missing_revision_cases() {
    let folder = workspace("bad");
    let project = new_project(&folder);
    let (code, _) = cli(&[
        "--json",
        "-p",
        &project,
        "--if-revision",
        "sha256:xyz",
        "status",
    ]);
    assert_eq!(code, 2);
    let (code, _) = cli(&[
        "--json",
        "-p",
        &project,
        "--lock-timeout-ms",
        "60001",
        "status",
    ]);
    assert_eq!(code, 2);
    let missing = folder.join("missing.json").to_string_lossy().into_owned();
    let revision = revision_of_status(&project);
    let (code, json) = cli(&[
        "--json",
        "-p",
        &missing,
        "--if-revision",
        &revision,
        "pixel",
        "paint",
        "0",
        "0",
        "#FF0000",
    ]);
    assert_eq!(code, 1);
    assert_eq!(json["error"], "revision_conflict");
}

/// {
///   責務: [parallel_edits_are_all_applied: 同時に起動した編集がどれも失われないことを検証する]
///   処理: [
///     1: 16個のプロセスが別々の画素を同時に塗る
///     2: すべて成功し、16画素すべてが塗られていることを確認する
///     3: 一時ファイルが残っていないことを確認する
///   ]
///   引数: []
///   戻り値: [なし、不一致ならテストを失敗させる]
/// }
#[test]
fn parallel_edits_are_all_applied() {
    let folder = workspace("parallel");
    let project = new_project(&folder);
    let handles: Vec<_> = (0..16)
        .map(|x| {
            let project = project.clone();
            thread::spawn(move || {
                cli(&[
                    "-p",
                    &project,
                    "pixel",
                    "paint",
                    &x.to_string(),
                    "0",
                    "#FF0000",
                ])
                .0
            })
        })
        .collect();
    for handle in handles {
        assert_eq!(handle.join().unwrap(), 0);
    }
    for x in 0..16 {
        let (_, json) = cli(&[
            "--json",
            "-p",
            &project,
            "pixel",
            "sample",
            &x.to_string(),
            "0",
        ]);
        assert!(
            json.to_string().to_lowercase().contains("ff0000"),
            "pixel {x} was lost: {json}"
        );
    }
    let leftovers: Vec<_> = fs::read_dir(&folder)
        .unwrap()
        .map(|entry| entry.unwrap().file_name().to_string_lossy().into_owned())
        .filter(|name| name.ends_with(".tmp"))
        .collect();
    assert!(leftovers.is_empty(), "{leftovers:?}");
}

/// {
///   責務: [concurrent_new_never_replaces: 同時の新規作成でちょうど1つだけが成功することを検証する]
///   処理: [
///     1: 8個のプロセスが同じ名前で--forceなしのproject newを同時に実行する
///     2: 成功が1件、残りがfile_existsであることを確認する
///   ]
///   引数: []
///   戻り値: [なし、不一致ならテストを失敗させる]
/// }
#[test]
fn concurrent_new_never_replaces() {
    let folder = workspace("race-new");
    let project = folder.join("art.json").to_string_lossy().into_owned();
    let handles: Vec<_> = (0..8)
        .map(|_| {
            let project = project.clone();
            thread::spawn(move || cli(&["--json", "-p", &project, "project", "new", "--size", "4"]))
        })
        .collect();
    let results: Vec<_> = handles
        .into_iter()
        .map(|handle| handle.join().unwrap())
        .collect();
    assert_eq!(results.iter().filter(|(code, _)| *code == 0).count(), 1);
    for (code, json) in &results {
        if *code != 0 {
            assert_eq!(json["error"], "file_exists");
        }
    }
}

/// {
///   責務: [busy_lock_and_dry_run: 他者がロック中なら待って失敗し、dry-runは何も作らないことを検証する]
///   処理: [
///     1: テスト自身がsidecarのロックを握り、短い待ち時間の編集がproject_busyになることを確認する
///     2: ロックを握ったままでもdry-runは成功し、作品を変えないことを確認する
///     3: ロックを離すと編集が成功することを確認する
///     4: ロックのないフォルダでdry-runがsidecarや一時ファイルを作らないことを確認する
///   ]
///   引数: []
///   戻り値: [なし、不一致ならテストを失敗させる]
/// }
#[test]
fn busy_lock_and_dry_run() {
    let folder = workspace("busy");
    let project = new_project(&folder);
    let sidecar = fs::canonicalize(&folder).unwrap().join(".art.json.lock");
    let holder = OpenOptions::new()
        .create(true)
        .write(true)
        .truncate(false)
        .open(&sidecar)
        .unwrap();
    holder.lock().unwrap();
    let bytes = fs::read(&project).unwrap();
    let (code, json) = cli(&[
        "--json",
        "-p",
        &project,
        "--lock-timeout-ms",
        "100",
        "pixel",
        "paint",
        "0",
        "0",
        "#FF0000",
    ]);
    assert_eq!((code, json["error"].as_str()), (1, Some("project_busy")));
    let (code, _) = cli(&[
        "--json",
        "-p",
        &project,
        "--dry-run",
        "pixel",
        "paint",
        "0",
        "0",
        "#FF0000",
    ]);
    assert_eq!(code, 0);
    assert_eq!(fs::read(&project).unwrap(), bytes);
    drop(holder);
    thread::sleep(Duration::from_millis(50));
    let (code, _) = cli(&[
        "--json", "-p", &project, "pixel", "paint", "0", "0", "#FF0000",
    ]);
    assert_eq!(code, 0);

    let quiet = workspace("quiet");
    let project = new_project(&quiet);
    let before: Vec<_> = fs::read_dir(&quiet)
        .unwrap()
        .map(|e| e.unwrap().file_name())
        .collect();
    cli(&[
        "--json",
        "-p",
        &project,
        "--dry-run",
        "pixel",
        "paint",
        "1",
        "1",
        "#FF0000",
    ]);
    let mut after: Vec<_> = fs::read_dir(&quiet)
        .unwrap()
        .map(|e| e.unwrap().file_name())
        .collect();
    let mut expected = before;
    expected.sort();
    after.sort();
    assert_eq!(after, expected);
}

/// {
///   責務: [export_to_an_alias_of_the_project_is_rejected: 別の書き方で同じ作品ファイルへの書き出しを拒否することを検証する]
///   処理: [
///     1: ./を含む別名のパスへPNGを書き出そうとする
///     2: invalid_outputで失敗し、作品が変わっていないことを確認する
///   ]
///   引数: []
///   戻り値: [なし、不一致ならテストを失敗させる]
/// }
#[test]
fn export_to_an_alias_of_the_project_is_rejected() {
    let folder = workspace("alias");
    let project = new_project(&folder);
    let bytes = fs::read(&project).unwrap();
    let alias = folder
        .join(".")
        .join("art.json")
        .to_string_lossy()
        .into_owned();
    let (code, json) = cli(&["--json", "-p", &project, "export", "render", "-o", &alias]);
    assert_eq!((code, json["error"].as_str()), (1, Some("invalid_output")));
    assert_eq!(fs::read(&project).unwrap(), bytes);
}
