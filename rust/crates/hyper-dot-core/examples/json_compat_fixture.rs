//! Emits in-memory projects and expected observations for the cross-language gate.
use hyper_dot_core::canvas::Canvas;
use hyper_dot_core::raster::Raster;
use hyper_dot_core::resolution::Resolution;
use hyper_dot_core::resolution_field::DetailPolicy;
use serde_json::{Value, json};

fn grid(width: u32, height: u32) -> Resolution {
    Resolution::new(width, height).unwrap()
}

fn pixels(raster: Raster) -> Vec<Vec<[u8; 4]>> {
    let size = raster.resolution();
    (0..size.height())
        .map(|y| {
            (0..size.width())
                .map(|x| raster.sample(x, y).unwrap())
                .collect()
        })
        .collect()
}

fn case(name: &str, canvas: Canvas) -> Value {
    let mut observations = Vec::new();
    for resolution in [
        canvas.resolution(),
        grid(16, 12),
        grid(7, 5),
        grid(23, 17),
        grid(4, 3),
    ] {
        let mut view = canvas.clone();
        view.set_resolution(resolution, DetailPolicy::Preserve)
            .unwrap();
        let native = view.render_native().unwrap();
        observations.push(json!({
            "resolution": [resolution.width(), resolution.height()],
            "logical": pixels(view.render().unwrap()),
            "detail": pixels(view.render_at(resolution).unwrap()),
            "native_resolution": [native.resolution().width(), native.resolution().height()],
            "native": pixels(native),
        }));
    }
    let mut result = json!({"name": name, "source": serde_json::from_str::<Value>(&canvas.to_json().unwrap()).unwrap(), "observations": observations});
    if name == "clipped_offsets" {
        let mut edited = canvas.clone();
        edited
            .set_resolution(grid(7, 5), DetailPolicy::Preserve)
            .unwrap();
        edited
            .paint(1, 1, [50, 60, 70, 128], DetailPolicy::Preserve)
            .unwrap();
        result["edited_detail"] = json!(pixels(edited.render_at(grid(16, 12)).unwrap()));
    }
    result
}

fn main() {
    let mut cases = Vec::new();
    let mut raster = Raster::new(grid(2, 1)).unwrap();
    raster.paint(1, 0, [17, 34, 51, 0]);
    cases.push(case("transparent_rectangular", Canvas::from_raster(raster)));
    let mut source = Raster::new(grid(16, 12)).unwrap();
    for y in 0..12 {
        for x in 0..16 {
            source.paint(
                x,
                y,
                [40 + 3 * x as u8, 60 + 3 * y as u8, 80 + x as u8, 128],
            );
        }
    }
    let mut canvas = Canvas::from_raster(source);
    canvas
        .set_resolution(grid(7, 5), DetailPolicy::Preserve)
        .unwrap();
    cases.push(case("retained_detail", canvas.clone()));
    canvas
        .paint(1, 1, [0, 255, 10, 0], DetailPolicy::Preserve)
        .unwrap();
    cases.push(case("clipped_offsets", canvas.clone()));
    canvas
        .paint(3, 2, [10, 20, 30, 40], DetailPolicy::Discard)
        .unwrap();
    cases.push(case("discarded_detail", canvas.clone()));
    canvas
        .set_resolution(grid(4, 3), DetailPolicy::Preserve)
        .unwrap();
    canvas.split_region(1, 1, 2, 2).unwrap();
    canvas
        .paint_child(1, 1, (1, 0), [5, 6, 7, 8], DetailPolicy::Preserve)
        .unwrap();
    canvas
        .paint_child(2, 2, (0, 1), [90; 4], DetailPolicy::Discard)
        .unwrap();
    canvas.paint(2, 2, [70; 4], DetailPolicy::Preserve).unwrap();
    canvas.collapse_cell(2, 2).unwrap();
    cases.push(case("expanded_and_collapsed", canvas.clone()));
    canvas
        .set_resolution(grid(23, 17), DetailPolicy::Preserve)
        .unwrap();
    cases.push(case("cross_grid_splits", canvas));
    let mut solid = Canvas::new(grid(3, 2)).unwrap();
    solid
        .fill(0, 0, [255, 0, 0, 255], DetailPolicy::Discard)
        .unwrap();
    cases.push(case("solid_fill", solid));
    println!("{}", Value::Array(cases));
}
