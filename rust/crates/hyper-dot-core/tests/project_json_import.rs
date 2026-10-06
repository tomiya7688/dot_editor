use hyper_dot_core::canvas::Canvas;
use hyper_dot_core::resolution::Resolution;
use hyper_dot_core::resolution_field::DetailPolicy;
use serde_json::{Value, json};

fn grid(w: u32, h: u32) -> Resolution {
    Resolution::new(w, h).unwrap()
}
fn fixture() -> Value {
    serde_json::from_str(include_str!(
        "../../../../tests/fixtures/project_json/transparent_rectangular_v2.json"
    ))
    .unwrap()
}
fn load(source: &Value) -> Canvas {
    Canvas::from_json(&source.to_string()).unwrap()
}

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
