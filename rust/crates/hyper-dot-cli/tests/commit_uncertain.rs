//! A real failure of the folder sync after the replace is reported as `commit_uncertain` (Unix only).

#![cfg(unix)]

use std::fs;
use std::os::unix::fs::PermissionsExt;
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
    let path = Path::new(env!("CARGO_TARGET_TMPDIR")).join(format!("commit-{name}"));
    let _ = fs::remove_dir_all(&path);
    fs::create_dir_all(&path).unwrap();
    path
}

/// {
///   責務: [set_mode: フォルダの権限を設定する]
///   処理: [
///     1: 指定のモードをUnixの権限として設定する
///   ]
///   引数: [
///     path: 対象のフォルダ
///     mode: 権限（8進数）
///   ]
///   戻り値: [なし]
/// }
fn set_mode(path: &Path, mode: u32) {
    fs::set_permissions(path, fs::Permissions::from_mode(mode)).unwrap();
}

/// {
///   責務: [failed_folder_sync_after_replace_is_commit_uncertain: 置換のあとのフォルダ同期の失敗が、実際にcommit_uncertainになることを検証する]
///   処理: [
///     1: 作品のあるフォルダを「書き込みと実行はできるが、読み取りはできない」権限にする
///     2: この状態の編集は、置換には成功し、フォルダの同期（読み取りで開く）だけが失敗する
///     3: 終了値1・commit_uncertainで、再読込の案内が出て、ファイルは実際に変わっていることを確認する
///     4: 権限が効かない環境（root）では、確認を省略する
///   ]
///   引数: []
///   戻り値: [なし、不一致ならテストを失敗させる]
/// }
#[test]
fn failed_folder_sync_after_replace_is_commit_uncertain() {
    let folder = workspace("sync");
    let project = folder.join("art.json").to_string_lossy().into_owned();
    let (code, _) = cli(&["--json", "-p", &project, "project", "new", "--size", "4"]);
    assert_eq!(code, 0);
    let before = fs::read(&project).unwrap();
    set_mode(&folder, 0o300);
    if fs::read_dir(&folder).is_ok() {
        set_mode(&folder, 0o700);
        eprintln!("directory permissions are not enforced here (root); skipping");
        return;
    }
    let (code, json) = cli(&[
        "--json", "-p", &project, "pixel", "paint", "0", "0", "#FF0000",
    ]);
    set_mode(&folder, 0o700);
    assert_eq!(code, 1, "{json}");
    assert_eq!(json["error"], "commit_uncertain", "{json}");
    assert!(
        json["message"].as_str().unwrap().contains("read it again"),
        "{json}"
    );
    // 置換は済んでいるため、旧状態の維持は約束されず、ファイルは実際に変わっている。
    assert_ne!(fs::read(&project).unwrap(), before);
    let (code, json) = cli(&["--json", "-p", &project, "status"]);
    assert_eq!(code, 0);
    assert_eq!(json["result"]["layers"].as_array().map(Vec::len), Some(1));
}
