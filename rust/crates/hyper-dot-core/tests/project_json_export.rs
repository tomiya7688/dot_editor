use hyper_dot_core::canvas::Canvas;
use hyper_dot_core::project_json::ProjectJsonError;
use hyper_dot_core::raster::Raster;
use hyper_dot_core::resolution::Resolution;
use hyper_dot_core::resolution_field::DetailPolicy;
use serde_json::{Value, json};

fn grid(width: u32, height: u32) -> Resolution {
    Resolution::new(width, height).unwrap()
}

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
