//! Reading, locking and atomically replacing project and export files.

use std::fs::{self, File, OpenOptions, TryLockError};
use std::io::{ErrorKind, Write};
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};
use std::thread;
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

use hyper_dot_core::canvas::Canvas;
use hyper_dot_core::layered_canvas::LayeredCanvas;
use serde_json::Value;

use crate::cli_error::CliError;
use crate::sha256::revision_of;

/// Largest project file read into memory; the core enforces the same limit.
const MAX_PROJECT_BYTES: u64 = 256 * 1024 * 1024;

/// ロックを待つ間隔。
const LOCK_POLL: Duration = Duration::from_millis(10);

/// 同じプロセス内で一時ファイル名を重ならせないための連番。
static TEMPORARY_COUNTER: AtomicU64 = AtomicU64::new(0);

/// {
///   責務: [Snapshot: 読み込んだ作品と、そのときのファイル内容のrevisionを保持する]
///   フィールド: [
///     canvas: 読み込んだ作品
///     revision: ファイルの生バイト列のSHA-256（sha256:付き）
///   ]
/// }
pub struct Snapshot {
    pub canvas: LayeredCanvas,
    pub revision: String,
}

/// {
///   責務: [io_failure: ファイル操作の失敗をCLIの失敗へ変換する]
///   処理: [
///     1: 存在しないファイルとそれ以外の入出力の失敗を種別名で分ける
///   ]
///   引数: [
///     action: 何をしようとしたかの説明
///     path: 対象のパス
///     error: 標準ライブラリが返した入出力エラー
///   ]
///   戻り値: [CLIの実行失敗]
/// }
fn io_failure(action: &str, path: &Path, error: &std::io::Error) -> CliError {
    let code = if error.kind() == ErrorKind::NotFound {
        "file_not_found"
    } else {
        "io_error"
    };
    CliError::failure(code, format!("cannot {action} {}: {error}", path.display()))
}

/// {
///   責務: [load_snapshot: プロジェクトファイルを1回だけ読み、検証した作品とrevisionを返す]
///   処理: [
///     1: 通常のファイルであることと大きさを確認して生バイト列を読む
///     2: 同じバイト列からrevisionを求める
///     3: レイヤー付きか単一Canvasかを判定し、コアの検証つきで読み込む
///   ]
///   引数: [
///     path: プロジェクトファイルのパス
///   ]
///   戻り値: [作品とrevision、読み込めない・不正な文書は実行失敗]
/// }
pub fn load_snapshot(path: &Path) -> Result<Snapshot, CliError> {
    let metadata = fs::metadata(path).map_err(|error| io_failure("read", path, &error))?;
    if !metadata.is_file() {
        return Err(CliError::failure(
            "unsafe_path",
            format!("{} is not a regular file", path.display()),
        ));
    }
    if metadata.len() > MAX_PROJECT_BYTES {
        return Err(CliError::failure(
            "invalid_project",
            format!("{} exceeds the project size limit", path.display()),
        ));
    }
    let bytes = fs::read(path).map_err(|error| io_failure("read", path, &error))?;
    let revision = revision_of(&bytes);
    let text = String::from_utf8(bytes)
        .map_err(|_| CliError::failure("invalid_project", "not valid UTF-8 JSON"))?;
    let probe: Value = serde_json::from_str(&text).map_err(|error| {
        CliError::failure("invalid_project", format!("not valid JSON: {error}"))
    })?;
    let canvas = if probe.get("layers").is_some() {
        LayeredCanvas::from_json(&text)?
    } else {
        LayeredCanvas::from_canvas(Canvas::from_json(&text)?)
    };
    Ok(Snapshot { canvas, revision })
}

/// {
///   責務: [same_target: 2つのパスが同じファイルを指すかを判定する]
///   処理: [
///     1: 既存ならそのまま、なければ親フォルダを正規化してファイル名を付けて実体のパスにする
///     2: 相対・絶対、.や..、シンボリックリンクを経由した別名を同一と判定する
///   ]
///   引数: [
///     first: 1つ目のパス
///     second: 2つ目のパス
///   ]
///   戻り値: [同じ場所を指せば真。判定できなければ文字列の一致]
/// }
pub fn same_target(first: &Path, second: &Path) -> bool {
    match (resolved(first), resolved(second)) {
        (Some(left), Some(right)) => left == right,
        _ => first == second,
    }
}

/// {
///   責務: [resolved: パスの実体の場所を求める]
///   処理: [
///     1: 存在するパスは正規化する
///     2: 存在しないパスは親フォルダを正規化してファイル名をつなぐ
///   ]
///   引数: [
///     path: 対象のパス
///   ]
///   戻り値: [実体のパス、求められなければNone]
/// }
fn resolved(path: &Path) -> Option<PathBuf> {
    if let Ok(canonical) = fs::canonicalize(path) {
        return Some(canonical);
    }
    let parent = match path.parent() {
        Some(parent) if !parent.as_os_str().is_empty() => parent,
        _ => Path::new("."),
    };
    Some(fs::canonicalize(parent).ok()?.join(path.file_name()?))
}

/// {
///   責務: [ensure_safe_target: 書き込み先が、同一性を安全に判定できる通常のファイルか確かめる]
///   処理: [
///     1: 存在しなければ安全とする
///     2: シンボリックリンクと通常でないもの（フォルダなど）を拒否する
///     3: UnixとWindowsでは、ハードリンクが複数あるファイル（Windowsはリンク数を調べられない場合も）を拒否する
///   ]
///   引数: [
///     path: 書き込み先のパス
///   ]
///   戻り値: [安全なら単位値、危険ならunsafe_path]
/// }
pub fn ensure_safe_target(path: &Path) -> Result<(), CliError> {
    let metadata = match fs::symlink_metadata(path) {
        Ok(metadata) => metadata,
        Err(error) if error.kind() == ErrorKind::NotFound => return Ok(()),
        Err(error) => return Err(io_failure("inspect", path, &error)),
    };
    let reason = if metadata.file_type().is_symlink() {
        Some("is a symbolic link")
    } else if !metadata.is_file() {
        Some("is not a regular file")
    } else if has_other_hard_links(path, &metadata) {
        Some("has more than one hard link")
    } else {
        None
    };
    match reason {
        Some(reason) => Err(CliError::failure(
            "unsafe_path",
            format!("refusing to write {}: it {reason}", path.display()),
        )),
        None => Ok(()),
    }
}

/// {
///   責務: [has_other_hard_links: ファイルに他のハードリンクがあるかを調べる]
///   処理: [
///     1: Unixではリンク数が2以上かを返す
///     2: Windowsではファイルを開き、GetFileInformationByHandleのリンク数が2以上かを返す
///     3: それ以外のOSでは判定できないため偽を返す
///   ]
///   引数: [
///     path: ファイルのパス
///     metadata: ファイルのメタデータ
///   ]
///   戻り値: [他のハードリンクがあれば真。Windowsで開けない場合は偽]
/// }
#[cfg(unix)]
fn has_other_hard_links(_path: &Path, metadata: &fs::Metadata) -> bool {
    use std::os::unix::fs::MetadataExt;
    metadata.nlink() > 1
}

/// {
///   責務: [has_other_hard_links: ファイルに他のハードリンクがあるかを調べる]
///   処理: [
///     1: ファイルを読み取り専用で開く
///     2: winapi_util::file::informationでリンク数を取得し、2以上かを返す
///   ]
///   引数: [
///     path: ファイルのパス
///     metadata: 使わない（Unix版と形をそろえる）
///   ]
///   戻り値: [他のハードリンクがあれば真。開けない・取得失敗でも安全側の真]
/// }
#[cfg(windows)]
fn has_other_hard_links(path: &Path, _metadata: &fs::Metadata) -> bool {
    // 安全なラッパー(winapi-util)を使い、unsafe_codeの禁止を保つ。
    // 判定できない場合は安全側に倒し、書き込みを拒否する（開けないファイルは書けない可能性が高い）。
    let Ok(file) = File::open(path) else {
        return true;
    };
    match winapi_util::file::information(&file) {
        Ok(information) => information.number_of_links() > 1,
        Err(_) => true,
    }
}

/// {
///   責務: [has_other_hard_links: ファイルに他のハードリンクがあるかを調べる]
///   処理: [
///     1: UnixでもWindowsでもないOSでは判定できないため偽を返す
///   ]
///   引数: [
///     path: 使わない
///     metadata: 使わない
///   ]
///   戻り値: [常に偽]
/// }
#[cfg(not(any(unix, windows)))]
fn has_other_hard_links(_path: &Path, _metadata: &fs::Metadata) -> bool {
    false
}

/// {
///   責務: [current_revision: ファイルがあれば、その生バイト列のrevisionを返す]
///   処理: [
///     1: 存在しなければNoneにする
///     2: 存在すれば全バイトを読んでrevisionを求める
///   ]
///   引数: [
///     path: 調べるファイルのパス
///   ]
///   戻り値: [revisionまたはNone、読めない場合は実行失敗]
/// }
pub fn current_revision(path: &Path) -> Result<Option<String>, CliError> {
    match fs::read(path) {
        Ok(bytes) => Ok(Some(revision_of(&bytes))),
        Err(error) if error.kind() == ErrorKind::NotFound => Ok(None),
        Err(error) => Err(io_failure("read", path, &error)),
    }
}

/// {
///   責務: [ProjectLock: 1つの作品に対する協調プロセス間の排他ロックを保持する]
///   フィールド: [
///     _file: ロックを握っているsidecarファイル。閉じるとOSが自動で解放する
///   ]
/// }
pub struct ProjectLock {
    _file: File,
}

/// {
///   責務: [lock_path: 作品に対応するsidecarロックファイルのパスを作る]
///   処理: [
///     1: 親フォルダを正規化し、相対・絶対や別名の指定でも同じ場所に揃える
///     2: 大文字小文字を区別しないOSではファイル名を小文字にして別名を避ける
///   ]
///   引数: [
///     path: 作品ファイルのパス
///   ]
///   戻り値: [ロックファイルのパス、親フォルダが無ければ実行失敗]
/// }
fn lock_path(path: &Path) -> Result<PathBuf, CliError> {
    let parent = match path.parent() {
        Some(parent) if !parent.as_os_str().is_empty() => parent.to_path_buf(),
        _ => PathBuf::from("."),
    };
    let directory =
        fs::canonicalize(&parent).map_err(|error| io_failure("open", &parent, &error))?;
    let name = path
        .file_name()
        .ok_or_else(|| CliError::failure("unsafe_path", "the project path has no file name"))?
        .to_string_lossy()
        .into_owned();
    let name = if cfg!(any(windows, target_os = "macos")) {
        name.to_lowercase()
    } else {
        name
    };
    Ok(directory.join(format!(".{name}.lock")))
}

impl ProjectLock {
    /// {
    ///   責務: [acquire: 作品のロックを、期限まで待って取得する]
    ///   処理: [
    ///     1: sidecarファイルを作成または開く（削除はしない）
    ///     2: 期限まで短い間隔でロックを試みる
    ///     3: 取得できなければproject_busyにする
    ///   ]
    ///   引数: [
    ///     path: 作品ファイルのパス
    ///     timeout: 待つ最長時間
    ///   ]
    ///   戻り値: [ロック、取得できなければ実行失敗]
    /// }
    pub fn acquire(path: &Path, timeout: Duration) -> Result<Self, CliError> {
        let sidecar = lock_path(path)?;
        let file = OpenOptions::new()
            .create(true)
            .truncate(false)
            .write(true)
            .open(&sidecar)
            .map_err(|error| io_failure("open the lock file", &sidecar, &error))?;
        let deadline = Instant::now() + timeout;
        loop {
            match file.try_lock() {
                Ok(()) => return Ok(Self { _file: file }),
                Err(TryLockError::WouldBlock) => {
                    if Instant::now() >= deadline {
                        return Err(CliError::failure(
                            "project_busy",
                            format!(
                                "{} is locked by another pixel-cli process (waited {} ms)",
                                path.display(),
                                timeout.as_millis()
                            ),
                        ));
                    }
                    thread::sleep(LOCK_POLL);
                }
                Err(TryLockError::Error(error)) => {
                    return Err(io_failure("lock", &sidecar, &error));
                }
            }
        }
    }
}

/// {
///   責務: [create_temporary: 衝突しない一時ファイルを排他的に作る]
///   処理: [
///     1: プロセス番号・連番・時刻から名前を作り、既存なら別の名前で数回試す
///     2: 既存のファイルやリンクは開かず、新規作成だけを許す
///   ]
///   引数: [
///     path: 最終的なファイルのパス
///   ]
///   戻り値: [一時ファイルのパスと開いたファイル]
/// }
fn create_temporary(path: &Path) -> Result<(PathBuf, File), CliError> {
    let name = path
        .file_name()
        .map(|name| name.to_string_lossy().into_owned())
        .unwrap_or_default();
    for _ in 0..16 {
        let serial = TEMPORARY_COUNTER.fetch_add(1, Ordering::Relaxed);
        let nanos = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .map_or(0, |elapsed| elapsed.subsec_nanos());
        let candidate = path.with_file_name(format!(
            ".{name}.{}.{serial}.{nanos}.tmp",
            std::process::id()
        ));
        match OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&candidate)
        {
            Ok(file) => return Ok((candidate, file)),
            Err(error) if error.kind() == ErrorKind::AlreadyExists => continue,
            Err(error) => return Err(io_failure("write", path, &error)),
        }
    }
    Err(CliError::failure(
        "io_error",
        format!("cannot choose a free temporary name for {}", path.display()),
    ))
}

/// {
///   責務: [write_temporary: 内容を一時ファイルへ書いてディスクへ同期する]
///   処理: [
///     1: 全バイトを書き、同期する
///     2: 失敗したら一時ファイルを消す
///   ]
///   引数: [
///     path: 最終的なファイルのパス
///     bytes: 書き込む内容
///   ]
///   戻り値: [同期済みの一時ファイルのパス]
/// }
fn write_temporary(path: &Path, bytes: &[u8]) -> Result<PathBuf, CliError> {
    let (temporary, mut file) = create_temporary(path)?;
    let written = file.write_all(bytes).and_then(|()| file.sync_all());
    drop(file);
    if let Err(error) = written {
        // 失敗時に一時ファイルを残さない。消せなくても本来の失敗を優先して返す。
        let _ = fs::remove_file(&temporary);
        return Err(io_failure("write", path, &error));
    }
    Ok(temporary)
}

/// {
///   責務: [sync_parent_directory: 置換した名前を親フォルダに確定させるため、親フォルダを同期する]
///   処理: [
///     1: Unixでは親フォルダを開いてディスクへ同期する
///     2: Windowsではフォルダを開いて同期を試みる。開けない・流せなくても成功として扱う（努力目標）
///     3: それ以外のOSでは何もしない
///   ]
///   引数: [
///     path: 置換したファイルのパス
///   ]
///   戻り値: [同期の結果]
/// }
fn sync_parent_directory(path: &Path) -> std::io::Result<()> {
    #[cfg(unix)]
    {
        let parent = match path.parent() {
            Some(parent) if !parent.as_os_str().is_empty() => parent,
            _ => Path::new("."),
        };
        File::open(parent)?.sync_all()
    }
    #[cfg(windows)]
    {
        use std::os::windows::fs::OpenOptionsExt;
        // フォルダのハンドルを開くにはFILE_FLAG_BACKUP_SEMANTICSが要る。
        const FILE_FLAG_BACKUP_SEMANTICS: u32 = 0x0200_0000;
        let parent = match path.parent() {
            Some(parent) if !parent.as_os_str().is_empty() => parent,
            _ => Path::new("."),
        };
        // 努力目標の同期: フォルダのハンドルを開けない・流せない環境（ネットワークドライブなど）があるため、
        // 失敗してもcommit_uncertainにせず成功として扱う（保証範囲は文書に記載）。
        if let Ok(folder) = OpenOptions::new()
            .write(true)
            .custom_flags(FILE_FLAG_BACKUP_SEMANTICS)
            .open(parent)
        {
            let _ = folder.sync_all();
        }
        Ok(())
    }
    #[cfg(not(any(unix, windows)))]
    {
        let _ = path;
        Ok(())
    }
}

/// {
///   責務: [commit_outcome: 置換の後の同期の結果を、利用者への約束に直す]
///   処理: [
///     1: 同期に成功していれば成功にする
///     2: 失敗していれば、置換は済んでいて旧状態を約束できないcommit_uncertainにする
///   ]
///   引数: [
///     path: 置換したファイルのパス
///     synced: 親フォルダの同期の結果
///   ]
///   戻り値: [成功時は単位値、失敗時は再読込を促すcommit_uncertain]
/// }
fn commit_outcome(path: &Path, synced: std::io::Result<()>) -> Result<(), CliError> {
    synced.map_err(|error| {
        CliError::failure(
            "commit_uncertain",
            format!(
                "{} was replaced but syncing its folder failed ({error}); \
                 the file may have changed, so read it again (status) before retrying",
                path.display()
            ),
        )
    })
}

/// {
///   責務: [write_atomic: 途中で失敗しても元のファイルを壊さずに書き込む]
///   処理: [
///     1: 同じフォルダの一意な一時ファイルへ全内容を書いて同期する
///     2: 一時ファイルを最終ファイルへ置き換える
///     3: 置換の後に親フォルダを同期し、失敗したら置換済みの可能性をcommit_uncertainで知らせる
///     4: 置換の前に失敗したら一時ファイルを消して、元のファイルを変えずに失敗を返す
///   ]
///   引数: [
///     path: 書き込み先のパス
///     bytes: 書き込む内容
///   ]
///   戻り値: [成功時は単位値、失敗時は元のファイルを変えずに実行失敗]
/// }
pub fn write_atomic(path: &Path, bytes: &[u8]) -> Result<(), CliError> {
    let temporary = write_temporary(path, bytes)?;
    if let Err(error) = fs::rename(&temporary, path) {
        let _ = fs::remove_file(&temporary);
        return Err(io_failure("write", path, &error));
    }
    commit_outcome(path, sync_parent_directory(path))
}

/// {
///   責務: [create_new_atomic: 既存のファイルを決して置き換えずに新規作成する]
///   処理: [
///     1: 一時ファイルへ全内容を書いて同期する
///     2: ハードリンクで最終名を作る（既に存在すれば失敗する）
///     3: 一時ファイルを消す
///   ]
///   引数: [
///     path: 作成先のパス
///     bytes: 書き込む内容
///   ]
///   戻り値: [成功時は単位値、既に存在すればfile_exists、その他は実行失敗]
/// }
pub fn create_new_atomic(path: &Path, bytes: &[u8]) -> Result<(), CliError> {
    let temporary = write_temporary(path, bytes)?;
    let linked = fs::hard_link(&temporary, path);
    let _ = fs::remove_file(&temporary);
    match linked {
        Ok(()) => commit_outcome(path, sync_parent_directory(path)),
        Err(error) if error.kind() == ErrorKind::AlreadyExists => Err(CliError::failure(
            "file_exists",
            format!(
                "{} already exists; use --force to replace it",
                path.display()
            ),
        )),
        Err(error) => Err(io_failure("write", path, &error)),
    }
}

/// {
///   責務: [save: 作品をレイヤー付きversion 2のJSONとして保存する]
///   処理: [
///     1: 作品をJSONへ直列化する
///     2: 原子的に置き換えて書き込む
///     3: 書き込んだバイト列のrevisionを返す
///   ]
///   引数: [
///     path: 保存先のパス
///     document: 保存する作品
///   ]
///   戻り値: [保存したバイト列のrevision、失敗時は元のファイルを変えずに実行失敗]
/// }
pub fn save(path: &Path, document: &LayeredCanvas) -> Result<String, CliError> {
    let bytes = document.to_json()?.into_bytes();
    write_atomic(path, &bytes)?;
    Ok(revision_of(&bytes))
}

/// {
///   責務: [save_new: 作品を新規ファイルとして保存し、既存のファイルは置き換えない]
///   処理: [
///     1: 作品をJSONへ直列化する
///     2: 置換禁止の原子的な作成で書き込む
///   ]
///   引数: [
///     path: 保存先のパス
///     document: 保存する作品
///   ]
///   戻り値: [保存したバイト列のrevision、既存ならfile_exists]
/// }
pub fn save_new(path: &Path, document: &LayeredCanvas) -> Result<String, CliError> {
    let bytes = document.to_json()?.into_bytes();
    create_new_atomic(path, &bytes)?;
    Ok(revision_of(&bytes))
}

#[cfg(test)]
mod tests {
    use std::io;
    use std::path::Path;

    use super::{commit_outcome, sync_parent_directory};

    /// {
    ///   責務: [RemoveOnDrop: テストが途中で失敗しても、自分が作った一時フォルダを片付ける]
    ///   フィールド: [0: 削除する一時フォルダ]
    /// }
    #[cfg(any(unix, windows))]
    struct RemoveOnDrop(std::path::PathBuf);

    #[cfg(any(unix, windows))]
    impl Drop for RemoveOnDrop {
        /// {
        ///   責務: [drop: 一時フォルダを消す。失敗しても無視する]
        ///   処理: [1: remove_dir_allを呼ぶ]
        ///   引数: [なし]
        ///   戻り値: [なし]
        /// }
        fn drop(&mut self) {
            let _ = std::fs::remove_dir_all(&self.0);
        }
    }

    /// {
    ///   責務: [failed_sync_after_replace_is_commit_uncertain: 置換後の同期の失敗が、再読込を促すcommit_uncertainになることを検証する]
    ///   処理: [
    ///     1: 同期の成功は成功になることを確認する
    ///     2: 同期の失敗は終了値1・commit_uncertainで、再読込の案内を含むことを確認する
    ///   ]
    ///   引数: []
    ///   戻り値: [なし。不一致ならテストが失敗する]
    /// }
    #[test]
    fn failed_sync_after_replace_is_commit_uncertain() {
        let path = Path::new("art.json");
        assert!(commit_outcome(path, Ok(())).is_ok());
        let error = commit_outcome(path, Err(io::Error::other("disk gone"))).unwrap_err();
        assert_eq!((error.exit_code, error.code), (1, "commit_uncertain"));
        assert!(error.message.contains("read it again"), "{}", error.message);
        assert!(error.message.contains("disk gone"));
    }

    /// {
    ///   責務: [syncing_a_real_folder_succeeds: 実在のフォルダの同期が成功することを検証する]
    ///   処理: [
    ///     1: 一時フォルダ内のパスについて親フォルダの同期を行い、成功を確認する
    ///   ]
    ///   引数: []
    ///   戻り値: [なし。不一致ならテストが失敗する]
    /// }
    #[test]
    fn syncing_a_real_folder_succeeds() {
        let folder = std::env::temp_dir();
        assert!(sync_parent_directory(&folder.join("never-created.json")).is_ok());
    }

    /// {
    ///   責務: [hard_linked_target_is_refused: 他のハードリンクがあるファイルが、UnixでもWindowsでも拒否されることを検証する]
    ///   処理: [
    ///     1: 一時フォルダにファイルとそのハードリンクを作る
    ///     2: 単独のファイルは安全、リンクを張った後は両方がunsafe_pathになることを確認する
    ///   ]
    ///   引数: []
    ///   戻り値: [なし。不一致ならテストが失敗する]
    /// }
    #[cfg(any(unix, windows))]
    #[test]
    fn hard_linked_target_is_refused() {
        // 実行ごとに一意な名前にし、他の実行の残りを再利用も削除もしない。
        let nanos = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let folder =
            std::env::temp_dir().join(format!("hyper-dot-hardlink-{}-{nanos}", std::process::id()));
        std::fs::create_dir_all(&folder).unwrap();
        let _cleanup = RemoveOnDrop(folder.clone());
        let original = folder.join("a.json");
        let linked = folder.join("b.json");
        std::fs::write(&original, b"{}").unwrap();
        assert!(super::ensure_safe_target(&original).is_ok());
        std::fs::hard_link(&original, &linked).unwrap();
        let first = super::ensure_safe_target(&original).unwrap_err();
        let second = super::ensure_safe_target(&linked).unwrap_err();
        assert_eq!(first.code, "unsafe_path");
        assert_eq!(second.code, "unsafe_path");
    }
}
