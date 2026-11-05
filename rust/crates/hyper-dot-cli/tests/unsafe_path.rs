//! Writes through symbolic links or shared hard links are refused with `unsafe_path`.

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
    let path = Path::new(env!("CARGO_TARGET_TMPDIR")).join(format!("unsafe-{name}"));
    let _ = fs::remove_dir_all(&path);
    fs::create_dir_all(&path).unwrap();
    path
}

/// {
///   責務: [new_project: 8x8の新しいプロジェクトを作ってパスを返す]
///   処理: [
///     1: project newを実行して成功を確認する
///   ]
///   引数: [
///     path: 作成先のパス
///   ]
///   戻り値: [なし]
/// }
fn new_project(path: &Path) {
    let (code, _) = cli(&[
        "--json",
        "-p",
        &path.to_string_lossy(),
        "project",
        "new",
        "--size",
        "8",
    ]);
    assert_eq!(code, 0);
}

/// {
///   責務: [make_symlink: ファイルへのシンボリックリンクを作る]
///   処理: [
///     1: OSごとのAPIでリンクを作る。権限が無ければ偽を返す
///   ]
///   引数: [
///     target: リンクの指す先
///     link: 作るリンクのパス
///   ]
///   戻り値: [作れたら真]
/// }
fn make_symlink(target: &Path, link: &Path) -> bool {
    #[cfg(unix)]
    {
        std::os::unix::fs::symlink(target, link).is_ok()
    }
    #[cfg(windows)]
    {
        std::os::windows::fs::symlink_file(target, link).is_ok()
    }
}

/// {
///   責務: [symlinked_project_is_never_replaced: シンボリックリンク経由の編集・新規作成・書き出しが拒否されることを検証する]
///   処理: [
///     1: 本物のプロジェクトへのリンクを作る（権限が無い環境では、確認を省略して成功とする）
///     2: リンク経由の編集と--force作成とPNG書き出しがunsafe_pathになることを確認する
///     3: 本物のファイルが変わらず、リンクがリンクのままであることを確認する
///   ]
///   引数: []
///   戻り値: [なし、不一致ならテストを失敗させる]
/// }
#[test]
fn symlinked_project_is_never_replaced() {
    let folder = workspace("symlink");
    let real = folder.join("real.json");
    new_project(&real);
    let link = folder.join("link.json");
    if !make_symlink(&real, &link) {
        eprintln!("symbolic links are not available here; skipping");
        return;
    }
    let before = fs::read(&real).unwrap();
    let link_text = link.to_string_lossy().into_owned();
    for arguments in [
        vec![
            "--json", "-p", &link_text, "pixel", "paint", "0", "0", "#FF0000",
        ],
        vec![
            "--json", "-p", &link_text, "project", "new", "--size", "4", "--force",
        ],
    ] {
        let (code, json) = cli(&arguments);
        assert_eq!(
            (code, json["error"].as_str()),
            (1, Some("unsafe_path")),
            "{arguments:?}"
        );
    }
    let png_link = folder.join("out.png");
    let png_real = folder.join("real.png");
    fs::write(&png_real, b"keep").unwrap();
    assert!(make_symlink(&png_real, &png_link));
    let (code, json) = cli(&[
        "--json",
        "-p",
        &real.to_string_lossy(),
        "export",
        "render",
        "-o",
        &png_link.to_string_lossy(),
    ]);
    assert_eq!((code, json["error"].as_str()), (1, Some("unsafe_path")));
    assert_eq!(fs::read(&real).unwrap(), before);
    assert_eq!(fs::read(&png_real).unwrap(), b"keep");
    assert!(
        fs::symlink_metadata(&link)
            .unwrap()
            .file_type()
            .is_symlink()
    );
    // 読み取りはリンクを通っても安全なので許可される。
    let (code, _) = cli(&["--json", "-p", &link_text, "status"]);
    assert_eq!(code, 0);
}

/// {
///   責務: [shared_hard_link_is_refused: ハードリンクが複数ある作品への書き込みが拒否されることを検証する]
///   処理: [
///     1: 作品のハードリンクを作り、編集がunsafe_pathになることを確認する
///     2: 両方のファイルが変わらないことを確認する
///   ]
///   引数: []
///   戻り値: [なし、不一致ならテストを失敗させる]
/// }
#[cfg(unix)]
#[test]
fn shared_hard_link_is_refused() {
    let folder = workspace("hardlink");
    let real = folder.join("real.json");
    new_project(&real);
    let other = folder.join("other.json");
    fs::hard_link(&real, &other).unwrap();
    let before = fs::read(&real).unwrap();
    let (code, json) = cli(&[
        "--json",
        "-p",
        &real.to_string_lossy(),
        "pixel",
        "paint",
        "0",
        "0",
        "#FF0000",
    ]);
    assert_eq!((code, json["error"].as_str()), (1, Some("unsafe_path")));
    assert_eq!(fs::read(&real).unwrap(), before);
    assert_eq!(fs::read(&other).unwrap(), before);
}
