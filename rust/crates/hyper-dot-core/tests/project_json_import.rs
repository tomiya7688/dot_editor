use hyper_dot_core::canvas::Canvas;
use hyper_dot_core::resolution::Resolution;
use hyper_dot_core::resolution_field::DetailPolicy;
use serde_json::{Value, json};

/// {
///   責務: [grid: テスト用の正の解像度を作る]
///   処理: [
///     1: 幅と高さを検証してResolutionを生成する
///   ]
///   引数: [
///     w: 対象画像の幅
///     h: 対象画像の高さ
///   ]
///   戻り値: [解像度、不正な寸法ならテストを失敗させる]
/// }
fn grid(w: u32, h: u32) -> Resolution {
    Resolution::new(w, h).unwrap()
}
/// {
///   責務: [fixture: 共有v2文書のテストfixtureを読み込む]
///   処理: [
///     1: 埋め込んだ透明・非正方形fixtureをJSON値に解析する
///   ]
///   引数: []
///   戻り値: [fixtureのJSON値、構文不正ならテストを失敗させる]
/// }
fn fixture() -> Value {
    serde_json::from_str(include_str!(
        "../../../../tests/fixtures/project_json/transparent_rectangular_v2.json"
    ))
    .unwrap()
}
/// {
///   責務: [load: テストのJSON値からCanvasを復元する]
///   処理: [
///     1: JSON値を文字列化してCanvas::from_jsonへ渡す
///   ]
///   引数: [
///     source: 変換・検査する元データ
///   ]
///   戻り値: [復元Canvas、読込失敗ならテストを失敗させる]
/// }
fn load(source: &Value) -> Canvas {
    Canvas::from_json(&source.to_string()).unwrap()
}

/// {
///   責務: [version_two_roundtrip_retains_hidden_rgb_and_starts_with_empty_history: v2の隠れたRGBを保持し履歴なしで読み込むことを回帰検証する]
///   処理: [
///     1: 対象の画像・状態を用意する
///     2: v2の隠れたRGBを保持し履歴なしで読み込む操作を実行し期待結果をassertで比較する
///   ]
///   引数: []
///   戻り値: [なし、不一致ならテストを失敗させる]
/// }
#[test]
fn version_two_roundtrip_retains_hidden_rgb_and_starts_with_empty_history() {
    let canvas = load(&fixture());
    assert_eq!(canvas.resolution(), grid(2, 1));
    assert_eq!(canvas.sample(1, 0), Ok([17, 34, 51, 0]));
    assert!(!canvas.can_undo());
    assert!(!canvas.can_redo());
    assert_eq!(
        serde_json::from_str::<Value>(&canvas.to_json().unwrap()).unwrap(),
        fixture()
    );
}

/// {
///   責務: [shared_legacy_fixture_is_readable_and_migrates_to_version_two: 共有旧形式を読みv2へ移行することを回帰検証する]
///   処理: [
///     1: 対象の画像・状態を用意する
///     2: 共有旧形式を読みv2へ移行する操作を実行し期待結果をassertで比較する
///   ]
///   引数: []
///   戻り値: [なし、不一致ならテストを失敗させる]
/// }
#[test]
fn shared_legacy_fixture_is_readable_and_migrates_to_version_two() {
    let canvas = Canvas::from_json(include_str!(
        "../../../../tests/fixtures/project_json/legacy_refinement_v1.json"
    ))
    .unwrap();
    assert_eq!(canvas.sample_child(0, 0, (1, 0)), Ok([0, 0, 255, 128]));
    assert_eq!(
        serde_json::from_str::<Value>(&canvas.to_json().unwrap()).unwrap()["version"],
        2
    );
}

/// {
///   責務: [collapsed_children_can_be_sampled_when_the_doubled_display_exceeds_render_limits: 倍サイズ描画不能でも折りたたみ子を読み出すことを回帰検証する]
///   処理: [
///     1: 対象の画像・状態を用意する
///     2: 倍サイズ描画不能でも折りたたみ子を読み出す操作を実行し期待結果をassertで比較する
///   ]
///   引数: []
///   戻り値: [なし、不一致ならテストを失敗させる]
/// }
#[test]
fn collapsed_children_can_be_sampled_when_the_doubled_display_exceeds_render_limits() {
    let canvas = Canvas::new(grid(4096, 1)).unwrap();
    let mut source: Value = serde_json::from_str(&canvas.to_json().unwrap()).unwrap();
    source["retained_splits"] =
        json!([{"resolution": [4096,1], "x": 1, "y": 0, "base": null, "expanded": false}]);
    source["refined_cells"] =
        json!([{"x": 1, "y": 0, "expanded": false, "children": [[null,null],[null,null]]}]);
    let restored = load(&source);
    assert_eq!(restored.sample_child(1, 0, (1, 1)), Ok([0; 4]));
    assert_eq!(restored.native_resolution(), Ok(grid(4096, 1)));
    assert!(restored.to_json().is_ok());
}

/// {
///   責務: [split_child_offsets_survive_load_edit_and_history: 子色差分を読み込み・編集・履歴で維持することを回帰検証する]
///   処理: [
///     1: 対象の画像・状態を用意する
///     2: 子色差分を読み込み・編集・履歴で維持する操作を実行し期待結果をassertで比較する
///   ]
///   引数: []
///   戻り値: [なし、不一致ならテストを失敗させる]
/// }
#[test]
fn split_child_offsets_survive_load_edit_and_history() {
    let mut original = Canvas::new(grid(4, 3)).unwrap();
    original.fill(0, 0, [40; 4], DetailPolicy::Discard).unwrap();
    original.split_region(1, 1, 2, 2).unwrap();
    original
        .paint_child(1, 1, (1, 0), [90; 4], DetailPolicy::Preserve)
        .unwrap();
    original
        .paint(1, 1, [70; 4], DetailPolicy::Preserve)
        .unwrap();
    original.collapse_cell(1, 1).unwrap();
    original
        .set_resolution(grid(7, 5), DetailPolicy::Preserve)
        .unwrap();
    let mut restored = Canvas::from_json(&original.to_json().unwrap()).unwrap();
    for resolution in [grid(23, 17), grid(4, 3), grid(16, 12)] {
        restored
            .set_resolution(resolution, DetailPolicy::Preserve)
            .unwrap();
        original
            .set_resolution(resolution, DetailPolicy::Preserve)
            .unwrap();
        assert_eq!(restored.render(), original.render());
        assert_eq!(restored.render_native(), original.render_native());
        assert_eq!(
            restored.render_at(grid(23, 17)),
            original.render_at(grid(23, 17))
        );
    }
    let before = restored.render_at(grid(23, 17)).unwrap();
    restored.paint(0, 0, [0; 4], DetailPolicy::Discard).unwrap();
    restored.undo().unwrap();
    assert_eq!(restored.render_at(grid(23, 17)), Ok(before));
}

/// {
///   責務: [legacy_refined_cells_migrate_parent_children_and_collapsed_state: 旧形式の親色・子色・折りたたみ状態を移行することを回帰検証する]
///   処理: [
///     1: 対象の画像・状態を用意する
///     2: 旧形式の親色・子色・折りたたみ状態を移行する操作を実行し期待結果をassertで比較する
///   ]
///   引数: []
///   戻り値: [なし、不一致ならテストを失敗させる]
/// }
#[test]
fn legacy_refined_cells_migrate_parent_children_and_collapsed_state() {
    for expanded in [false, true] {
        let source = json!({"canvas_size": 2, "pixels": [["#112233", null], [null, null]],
            "refined_cells": [{"x": 0, "y": 0, "expanded": expanded,
                "children": [["#FF0000", "#0000FF80"], [null, "#00FF00"]]}]});
        let canvas = load(&source);
        assert_eq!(canvas.sample(0, 0), Ok([17, 34, 51, 255]));
        assert_eq!(canvas.sample_child(0, 0, (1, 0)), Ok([0, 0, 255, 128]));
        assert_eq!(canvas.is_split(0, 0), expanded);
        let migrated = Canvas::from_json(&canvas.to_json().unwrap()).unwrap();
        assert_eq!(migrated.render_native(), canvas.render_native());
        assert!(!migrated.can_undo());
    }
}

/// {
///   責務: [non_grid_source_extent_preserves_exact_sampling_and_edit_boundaries: グリッドに整列しない元画像範囲の標本と編集境界ことを回帰検証する]
///   処理: [
///     1: 対象の画像・状態を用意する
///     2: グリッドに整列しない元画像範囲の標本と編集境界操作を実行し期待結果をassertで比較する
///   ]
///   引数: []
///   戻り値: [なし、不一致ならテストを失敗させる]
/// }
#[test]
fn non_grid_source_extent_preserves_exact_sampling_and_edit_boundaries() {
    // First source occupies x=[0,2/3), with its pixel boundary at 1/3.
    let source = json!({"version": 2, "canvas_size": 3, "resolution": [3, 1],
    "pixels": [["#320000", "#960000", "#0000FF"]], "retained_splits": [],
    "retained_field": [
        {"clip": [[0,1],[0,1],[2,3],[1,1]], "extent": [[0,1],[0,1],[2,3],[1,1]],
            "resolution": [2,1], "pixels": [["#320000", "#960000"]], "offset": [0,0,0,0]},
        {"clip": [[2,3],[0,1],[1,1],[1,1]], "extent": [[2,3],[0,1],[1,1],[1,1]],
            "resolution": [1,1], "pixels": [["#0000FF"]], "offset": [0,0,0,0]}
    ]});
    let mut canvas = load(&source);
    assert_eq!(
        canvas.render_at(grid(6, 1)).unwrap().sample(1, 0),
        Ok([50, 0, 0, 255])
    );
    assert_eq!(
        canvas.render_at(grid(6, 1)).unwrap().sample(2, 0),
        Ok([150, 0, 0, 255])
    );
    canvas
        .set_resolution(grid(7, 1), DetailPolicy::Preserve)
        .unwrap();
    let before = canvas.render_at(grid(73, 1)).unwrap();
    canvas
        .paint(1, 0, [9, 8, 7, 6], DetailPolicy::Discard)
        .unwrap();
    let after = canvas.render_at(grid(73, 1)).unwrap();
    for x in 0..73 {
        let cell = (2 * x + 1) * 7 / (2 * 73);
        if cell != 1 {
            assert_eq!(after.sample(x, 0), before.sample(x, 0));
        }
    }
    let restored = Canvas::from_json(&canvas.to_json().unwrap()).unwrap();
    assert_eq!(restored.render_at(grid(73, 1)), Ok(after));
}

/// {
///   責務: [duplicates_nonstandard_numbers_trailing_data_and_deep_unknown_fields_are_rejected: 重複キー・非標準数値・末尾データ・深い未知項目を拒否することを回帰検証する]
///   処理: [
///     1: 対象の画像・状態を用意する
///     2: 重複キー・非標準数値・末尾データ・深い未知項目を拒否する操作を実行し期待結果をassertで比較する
///   ]
///   引数: []
///   戻り値: [なし、不一致ならテストを失敗させる]
/// }
#[test]
fn duplicates_nonstandard_numbers_trailing_data_and_deep_unknown_fields_are_rejected() {
    for text in [
        "{\"version\":1,\"version\":2}",
        "{\"extra\":{\"a\":1,\"a\":2}}",
        "{\"name\":1,\"na\\u006de\":2}",
        "{\"extra\":NaN}",
        "{\"extra\":Infinity}",
        "{} {}",
        "[]",
        "null",
    ] {
        assert!(Canvas::from_json(text).is_err(), "{text}");
    }
    let deep = format!("{{\"extra\":{}0{}}}", "[".repeat(150), "]".repeat(150));
    assert!(Canvas::from_json(&deep).is_err());
}

/// {
///   責務: [malformed_shapes_colors_offsets_and_fractions_are_rejected: 不正な寸法・色・差分・分数を拒否することを回帰検証する]
///   処理: [
///     1: 対象の画像・状態を用意する
///     2: 不正な寸法・色・差分・分数を拒否する操作を実行し期待結果をassertで比較する
///   ]
///   引数: []
///   戻り値: [なし、不一致ならテストを失敗させる]
/// }
#[test]
fn malformed_shapes_colors_offsets_and_fractions_are_rejected() {
    let paths = [
        ("/version", json!(true)),
        ("/version", json!(3)),
        ("/resolution/0", json!(0)),
        ("/resolution/0", json!(2.0)),
        ("/resolution/1", json!(-1)),
        ("/canvas_size", json!(3)),
        ("/pixels", json!([])),
        ("/pixels/0/1", json!("#12345Z")),
        ("/retained_field", json!([])),
        ("/retained_field/0/offset/0", json!(1_000_001)),
        ("/retained_field/0/offset/0", json!(true)),
        ("/retained_field/0/clip/0/1", json!(0)),
        ("/retained_field/0/clip/0/1", json!(16_777_217)),
        ("/retained_field/0/clip/2", json!([0, 1])),
        ("/retained_splits", json!({})),
    ];
    for (path, replacement) in paths {
        let mut source = fixture();
        *source.pointer_mut(path).unwrap() = replacement;
        assert!(Canvas::from_json(&source.to_string()).is_err(), "{path}");
    }
}

/// {
///   責務: [overlap_holes_and_clips_outside_extent_are_rejected_without_sampling_panics: 重複・欠落・元範囲外のパッチを安全に拒否することを回帰検証する]
///   処理: [
///     1: 対象の画像・状態を用意する
///     2: 重複・欠落・元範囲外のパッチを安全に拒否する操作を実行し期待結果をassertで比較する
///   ]
///   引数: []
///   戻り値: [なし、不一致ならテストを失敗させる]
/// }
#[test]
fn overlap_holes_and_clips_outside_extent_are_rejected_without_sampling_panics() {
    let mut source = fixture();
    let patch = source["retained_field"][0].clone();
    source["retained_field"].as_array_mut().unwrap().push(patch);
    assert!(Canvas::from_json(&source.to_string()).is_err());
    let mut source = fixture();
    source["retained_field"][0]["clip"][2] = json!([1, 2]);
    assert!(Canvas::from_json(&source.to_string()).is_err());
    let mut source = fixture();
    source["retained_field"][0]["extent"][2] = json!([1, 2]);
    assert!(Canvas::from_json(&source.to_string()).is_err());
}

/// {
///   責務: [split_duplicates_unsafe_expansion_and_preview_disagreement_are_rejected: 重複分割・描画不能な展開・プレビュー不一致を拒否することを回帰検証する]
///   処理: [
///     1: 対象の画像・状態を用意する
///     2: 重複分割・描画不能な展開・プレビュー不一致を拒否する操作を実行し期待結果をassertで比較する
///   ]
///   引数: []
///   戻り値: [なし、不一致ならテストを失敗させる]
/// }
#[test]
fn split_duplicates_unsafe_expansion_and_preview_disagreement_are_rejected() {
    let mut canvas = Canvas::new(grid(2, 1)).unwrap();
    canvas.split_cell(0, 0).unwrap();
    let source: Value = serde_json::from_str(&canvas.to_json().unwrap()).unwrap();
    for (path, value) in [
        ("/retained_splits/0/x", json!(2)),
        ("/retained_splits/0/expanded", json!(1)),
        ("/retained_splits/0/resolution", json!([4096, 1])),
        ("/refined_cells/0/children/0/0", json!("#FF0000")),
        ("/pixels/0/0", json!("#FF0000")),
    ] {
        let mut bad = source.clone();
        *bad.pointer_mut(path).unwrap() = value;
        assert!(Canvas::from_json(&bad.to_string()).is_err(), "{path}");
    }
    let mut bad = source;
    let split = bad["retained_splits"][0].clone();
    bad["retained_splits"].as_array_mut().unwrap().push(split);
    assert!(Canvas::from_json(&bad.to_string()).is_err());
}

/// {
///   責務: [nesting_boundary_matches_the_reference_and_unknown_fields_are_validated: 深さ境界を参照実装と一致させ未知項目も検査することを回帰検証する]
///   処理: [
///     1: 対象の画像・状態を用意する
///     2: 深さ境界を参照実装と一致させ未知項目も検査する操作を実行し期待結果をassertで比較する
///   ]
///   引数: []
///   戻り値: [なし、不一致ならテストを失敗させる]
/// }
#[test]
fn nesting_boundary_matches_the_reference_and_unknown_fields_are_validated() {
    let text = format!(
        "{{\"canvas_size\":1,\"pixels\":[[null]],\"extra\":{}0{}}}",
        "[".repeat(127),
        "]".repeat(127)
    );
    assert!(Canvas::from_json(&text).is_ok());
    let text = format!(
        "{{\"canvas_size\":1,\"pixels\":[[null]],\"extra\":{}0{}}}",
        "[".repeat(128),
        "]".repeat(128)
    );
    assert!(Canvas::from_json(&text).is_err());
}

/// {
///   責務: [patch_and_split_count_limits_are_rejected_before_rendering: パッチ数・分割数の上限を描画前に拒否することを回帰検証する]
///   処理: [
///     1: 対象の画像・状態を用意する
///     2: パッチ数・分割数の上限を描画前に拒否する操作を実行し期待結果をassertで比較する
///   ]
///   引数: []
///   戻り値: [なし、不一致ならテストを失敗させる]
/// }
#[test]
fn patch_and_split_count_limits_are_rejected_before_rendering() {
    let mut source = fixture();
    source["retained_field"] = json!(vec![source["retained_field"][0].clone(); 4097]);
    assert!(Canvas::from_json(&source.to_string()).is_err());
    let mut source = fixture();
    source["retained_splits"] = json!(vec![json!({}); 4097]);
    assert!(Canvas::from_json(&source.to_string()).is_err());
    let mut source = fixture();
    source["layers"] = json!([]);
    assert!(Canvas::from_json(&source.to_string()).is_err());
}

/// {
///   責務: [failures_leave_an_existing_document_and_redo_available: 読み込み失敗で既存文書とRedoを維持することを回帰検証する]
///   処理: [
///     1: 対象の画像・状態を用意する
///     2: 読み込み失敗で既存文書とRedoを維持する操作を実行し期待結果をassertで比較する
///   ]
///   引数: []
///   戻り値: [なし、不一致ならテストを失敗させる]
/// }
#[test]
fn failures_leave_an_existing_document_and_redo_available() {
    let mut canvas = Canvas::new(grid(2, 1)).unwrap();
    canvas.paint(0, 0, [1; 4], DetailPolicy::Discard).unwrap();
    canvas.undo().unwrap();
    let before = canvas.clone();
    assert!(Canvas::from_json("{\"version\":2}").is_err());
    assert_eq!(canvas, before);
    assert!(canvas.redo().unwrap());
}
