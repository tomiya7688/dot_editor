use hyper_dot_core::canvas::Canvas;
use hyper_dot_core::project_json::ProjectJsonError;
use hyper_dot_core::raster::Raster;
use hyper_dot_core::resolution::Resolution;
use hyper_dot_core::resolution_field::DetailPolicy;
use serde_json::{Value, json};

/// {
///   責務: [grid: テスト用の正の解像度を作る]
///   処理: [
///     1: 幅と高さを検証してResolutionを生成する
///   ]
///   引数: [
///     width: 対象領域の幅
///     height: 対象領域の高さ
///   ]
///   戻り値: [解像度、不正な寸法ならテストを失敗させる]
/// }
fn grid(width: u32, height: u32) -> Resolution {
    Resolution::new(width, height).unwrap()
}

/// {
///   責務: [export_matches_shared_transparent_non_square_fixture: 透明・非正方形の共有fixtureと出力を一致させることを回帰検証する]
///   処理: [
///     1: 対象の画像・状態を用意する
///     2: 透明・非正方形の共有fixtureと出力を一致させる操作を実行し期待結果をassertで比較する
///   ]
///   引数: []
///   戻り値: [なし、不一致ならテストを失敗させる]
/// }
#[test]
fn export_matches_shared_transparent_non_square_fixture() {
    let mut raster = Raster::new(grid(2, 1)).unwrap();
    raster.paint(1, 0, [17, 34, 51, 0]);
    let canvas = Canvas::from_raster(raster);
    let actual: Value = serde_json::from_str(&canvas.to_json().unwrap()).unwrap();
    let expected: Value = serde_json::from_str(include_str!(
        "../../../../tests/fixtures/project_json/transparent_rectangular_v2.json"
    ))
    .unwrap();
    assert_eq!(actual, expected);
}

/// {
///   責務: [cropped_sources_keep_original_pixel_boundaries_and_unclamped_offsets: 切り出し元の画素境界と未飽和の色差分を保持することを回帰検証する]
///   処理: [
///     1: 対象の画像・状態を用意する
///     2: 切り出し元の画素境界と未飽和の色差分を保持する操作を実行し期待結果をassertで比較する
///   ]
///   引数: []
///   戻り値: [なし、不一致ならテストを失敗させる]
/// }
#[test]
fn cropped_sources_keep_original_pixel_boundaries_and_unclamped_offsets() {
    let mut raster = Raster::new(grid(4, 1)).unwrap();
    for x in 0..4 {
        raster.paint(x, 0, [10 + x as u8 * 50, 20, 30, 255]);
    }
    let mut canvas = Canvas::from_raster(raster);
    canvas
        .set_resolution(grid(2, 1), DetailPolicy::Preserve)
        .unwrap();
    canvas
        .paint(0, 0, [0, 20, 30, 255], DetailPolicy::Preserve)
        .unwrap();
    let source: Value = serde_json::from_str(&canvas.to_json().unwrap()).unwrap();
    assert_eq!(source["pixels"][0][0], "#00141E");
    let patches = source["retained_field"].as_array().unwrap();
    let shifted = patches
        .iter()
        .find(|patch| patch["offset"][0] == -60)
        .unwrap();
    assert_eq!(shifted["clip"], json!([[0, 1], [0, 1], [1, 2], [1, 1]]));
    assert_eq!(shifted["extent"], shifted["clip"]);
    assert_eq!(shifted["resolution"], json!([2, 1]));
    assert_eq!(shifted["pixels"], json!([["#0A141E", "#3C141E"]]));
    assert_eq!(shifted["offset"], json!([-60, 0, 0, 0]));
}

/// {
///   責務: [export_sorts_split_records_and_includes_collapsed_child_samples: 分割記録を整列し折りたたみ子標本も出力することを回帰検証する]
///   処理: [
///     1: 対象の画像・状態を用意する
///     2: 分割記録を整列し折りたたみ子標本も出力する操作を実行し期待結果をassertで比較する
///   ]
///   引数: []
///   戻り値: [なし、不一致ならテストを失敗させる]
/// }
#[test]
fn export_sorts_split_records_and_includes_collapsed_child_samples() {
    let mut canvas = Canvas::new(grid(3, 2)).unwrap();
    canvas.split_cell(2, 1).unwrap();
    canvas.split_cell(0, 0).unwrap();
    canvas
        .paint_child(2, 1, (0, 1), [1, 2, 3, 128], DetailPolicy::Discard)
        .unwrap();
    canvas.paint(2, 1, [40; 4], DetailPolicy::Preserve).unwrap();
    canvas.collapse_cell(2, 1).unwrap();
    let source: Value = serde_json::from_str(&canvas.to_json().unwrap()).unwrap();
    assert_eq!(source["retained_splits"][0]["x"], 0);
    assert_eq!(source["retained_splits"][1]["base"], "#28282828");
    assert_eq!(source["refined_cells"][1]["expanded"], false);
    assert_eq!(source["refined_cells"][1]["children"][1][0], "#01020380");
    canvas
        .set_resolution(grid(7, 5), DetailPolicy::Preserve)
        .unwrap();
    let source: Value = serde_json::from_str(&canvas.to_json().unwrap()).unwrap();
    assert!(source.get("refined_cells").is_none());
    assert_eq!(source["retained_splits"].as_array().unwrap().len(), 2);
}

/// {
///   責務: [repeated_export_preserves_undo_redo_and_is_deterministic: 書き出しの決定性とUndo/Redoの非変更ことを回帰検証する]
///   処理: [
///     1: 対象の画像・状態を用意する
///     2: 書き出しの決定性とUndo/Redoの非変更操作を実行し期待結果をassertで比較する
///   ]
///   引数: []
///   戻り値: [なし、不一致ならテストを失敗させる]
/// }
#[test]
fn repeated_export_preserves_undo_redo_and_is_deterministic() {
    let mut canvas = Canvas::new(grid(4, 3)).unwrap();
    canvas.split_region(1, 1, 2, 2).unwrap();
    canvas.paint(0, 0, [100; 4], DetailPolicy::Discard).unwrap();
    canvas.undo().unwrap();
    let before = canvas.clone();
    assert_eq!(canvas.to_json().unwrap(), canvas.to_json().unwrap());
    assert_eq!(canvas, before);
    assert!(canvas.can_redo());
}

/// {
///   責務: [unsupported_coordinates_and_output_sizes_fail_without_mutation: 非対応座標と出力サイズで状態を変更しないことを回帰検証する]
///   処理: [
///     1: 対象の画像・状態を用意する
///     2: 非対応座標と出力サイズで状態を変更しない操作を実行し期待結果をassertで比較する
///   ]
///   引数: []
///   戻り値: [なし、不一致ならテストを失敗させる]
/// }
#[test]
fn unsupported_coordinates_and_output_sizes_fail_without_mutation() {
    let mut canvas = Canvas::new(grid(1, 1)).unwrap();
    canvas
        .set_resolution(grid(16_777_217, 1), DetailPolicy::Preserve)
        .unwrap();
    canvas.paint(0, 0, [1; 4], DetailPolicy::Discard).unwrap();
    canvas
        .set_resolution(grid(1, 1), DetailPolicy::Preserve)
        .unwrap();
    let before = canvas.clone();
    assert!(matches!(
        canvas.to_json(),
        Err(ProjectJsonError::CoordinateLimitExceeded)
    ));
    assert_eq!(canvas, before);
    canvas
        .set_resolution(grid(u32::MAX, 1), DetailPolicy::Preserve)
        .unwrap();
    let before = canvas.clone();
    assert!(matches!(canvas.to_json(), Err(ProjectJsonError::Raster(_))));
    assert_eq!(canvas, before);
}
