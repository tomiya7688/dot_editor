use hyper_dot_core::raster::{Color, Raster};
use hyper_dot_core::resolution::Resolution;
use hyper_dot_core::resolution_field::{DetailPolicy, ResolutionField};

fn grid(width: u32, height: u32) -> Resolution {
    Resolution::new(width, height).unwrap()
}

fn patterned() -> Raster {
    let mut raster = Raster::new(grid(16, 16)).unwrap();
    for y in 0..16 {
        for x in 0..16 {
            raster.paint(
                x,
                y,
                [
                    70 + x as u8,
                    90 + y as u8,
                    110 + (x + y) as u8,
                    150 + ((x * y) % 70) as u8,
                ],
            );
        }
    }
    raster
}

fn in_cell(view: Resolution, x: u32, y: u32, edit: Resolution, ex: u32, ey: u32) -> bool {
    let cx = (2 * u64::from(x) + 1) * u64::from(edit.width()) / (2 * u64::from(view.width()));
    let cy = (2 * u64::from(y) + 1) * u64::from(edit.height()) / (2 * u64::from(view.height()));
    cx == u64::from(ex) && cy == u64::from(ey)
}

fn shifted(color: Color, delta: [i64; 4]) -> Color {
    std::array::from_fn(|i| (i64::from(color[i]) + delta[i]).clamp(0, 255) as u8)
}

#[test]
fn preserve_detail_roundtrip() {
    let original = patterned();
    let mut field = ResolutionField::from_raster(original.clone());
    let coarse = grid(7, 7);
    let anchor = field.sample(coarse, 2, 3).unwrap();
    let color = [120, 130, 140, 200];
    let delta = std::array::from_fn(|i| i64::from(color[i]) - i64::from(anchor[i]));

    assert!(
        field
            .paint(coarse, 2, 3, color, DetailPolicy::Preserve)
            .unwrap()
    );
    assert_eq!(field.sample(coarse, 2, 3), Ok(color));
    assert_eq!(field.has_detail_at(coarse, 2, 3), Ok(true));
    field.render(grid(23, 17)).unwrap();
    field.render(grid(1, 1)).unwrap();
    let restored = field.render(grid(16, 16)).unwrap();
    for y in 0..16 {
        for x in 0..16 {
            let old = original.sample(x, y).unwrap();
            let expected = if in_cell(grid(16, 16), x, y, coarse, 2, 3) {
                shifted(old, delta)
            } else {
                old
            };
            assert_eq!(restored.sample(x, y), Ok(expected), "pixel ({x}, {y})");
        }
    }
}

#[test]
fn discard_detail_is_local() {
    let before = ResolutionField::from_raster(patterned());
    let mut field = before.clone();
    let coarse = grid(7, 7);
    let color = [23, 45, 67, 255];
    assert!(
        field
            .paint(coarse, 1, 1, color, DetailPolicy::Discard)
            .unwrap()
    );
    assert_eq!(field.has_detail_at(coarse, 1, 1), Ok(false));
    assert_eq!(field.has_detail_at(coarse, 2, 1), Ok(true));

    for view in [grid(16, 16), grid(79, 53), grid(23, 17)] {
        let output = field.render(view).unwrap();
        for y in 0..view.height() {
            for x in 0..view.width() {
                let expected = if in_cell(view, x, y, coarse, 1, 1) {
                    color
                } else {
                    before.sample(view, x, y).unwrap()
                };
                assert_eq!(
                    output.sample(x, y),
                    Ok(expected),
                    "pixel ({x}, {y}) at {view:?}"
                );
            }
        }
    }
}

#[test]
fn preserve_recovers_raw_samples_after_color_clipping() {
    let mut source = Raster::new(grid(16, 16)).unwrap();
    for y in 0..16 {
        for x in 0..16 {
            source.paint(x, y, [240 + x as u8, 80 + y as u8, 100, 255]);
        }
    }
    let mut field = ResolutionField::from_raster(source.clone());
    let coarse = grid(7, 7);
    let anchor = field.sample(coarse, 1, 1).unwrap();
    field
        .paint(coarse, 1, 1, [255, 100, 120, 255], DetailPolicy::Preserve)
        .unwrap();
    let clipped = field.render(grid(16, 16)).unwrap();
    assert_eq!(clipped.sample(4, 3).unwrap()[0], 255);
    field
        .paint(coarse, 1, 1, [200, 100, 120, 255], DetailPolicy::Preserve)
        .unwrap();
    let delta = std::array::from_fn(|i| i64::from([200, 100, 120, 255][i]) - i64::from(anchor[i]));
    for y in 0..16 {
        for x in 0..16 {
            let old = source.sample(x, y).unwrap();
            let expected = if in_cell(grid(16, 16), x, y, coarse, 1, 1) {
                shifted(old, delta)
            } else {
                old
            };
            assert_eq!(field.sample(grid(16, 16), x, y), Ok(expected));
        }
    }
}

#[test]
fn unchanged_preserve_and_discard_have_different_detail_behavior() {
    let mut field = ResolutionField::from_raster(patterned());
    let before = field.clone();
    let coarse = grid(7, 7);
    let color = field.sample(coarse, 2, 3).unwrap();
    assert!(
        !field
            .paint(coarse, 2, 3, color, DetailPolicy::Preserve)
            .unwrap()
    );
    assert_eq!(field, before);
    assert!(
        field
            .paint(coarse, 2, 3, color, DetailPolicy::Discard)
            .unwrap()
    );
    assert_eq!(field.has_detail_at(coarse, 2, 3), Ok(false));
    assert!(!field.discard_detail(coarse, 2, 3).unwrap());
    assert!(
        !field
            .paint(coarse, 7, 0, [0; 4], DetailPolicy::Discard)
            .unwrap()
    );
}

#[test]
fn undo_snapshot_restores_discarded_detail() {
    let original = patterned();
    let mut field = ResolutionField::from_raster(original.clone());
    let history = field.clone();
    assert!(field.discard_detail(grid(7, 7), 1, 1).unwrap());
    assert_eq!(field.has_detail_at(grid(7, 7), 1, 1), Ok(false));
    assert_eq!(history.render(grid(16, 16)), Ok(original.clone()));
    field = history;
    assert_eq!(field.has_detail_at(grid(7, 7), 1, 1), Ok(true));
    assert_eq!(field.render(grid(16, 16)), Ok(original));
}

#[test]
fn fine_edits_on_unaligned_grids_survive_display_changes() {
    let source = Raster::new(grid(1, 1)).unwrap();
    let mut field = ResolutionField::from_raster(source);
    let fine = grid(23, 17);
    let color = [10, 20, 30, 40];
    field
        .paint(fine, 22, 16, color, DetailPolicy::Preserve)
        .unwrap();
    field.render(grid(7, 7)).unwrap();
    assert_eq!(field.sample(fine, 22, 16), Ok(color));
    assert_eq!(field.sample(fine, 21, 16), Ok([0; 4]));
    assert_eq!(field.retained_resolution(), fine);
    assert!(field.erase(fine, 22, 16, DetailPolicy::Discard).unwrap());
    assert_eq!(field.sample(fine, 22, 16), Ok([0; 4]));
}

#[test]
fn editing_largest_logical_grid_does_not_overflow_or_change_neighboring_samples() {
    let original = patterned();
    let mut field = ResolutionField::from_raster(original.clone());
    let huge = grid(u32::MAX, u32::MAX);
    let color = [5, 6, 7, 8];
    field
        .paint(
            huge,
            u32::MAX - 1,
            u32::MAX - 1,
            color,
            DetailPolicy::Discard,
        )
        .unwrap();
    assert_eq!(field.sample(huge, u32::MAX - 1, u32::MAX - 1), Ok(color));
    assert_eq!(
        field.sample(huge, u32::MAX - 2, u32::MAX - 1),
        original.sample(15, 15)
    );
    assert_eq!(field.render(grid(16, 16)), Ok(original));
}

#[test]
fn preserve_tints_mixed_raster_and_solid_patches_only_inside_the_edit() {
    let mut field = ResolutionField::from_raster(patterned());
    field
        .paint(grid(7, 7), 1, 1, [23, 45, 67, 255], DetailPolicy::Discard)
        .unwrap();
    let before = field.clone();
    let coarse = grid(5, 3);
    let anchor = field.sample(coarse, 0, 0).unwrap();
    let color = [200, 10, 20, 50];
    let delta = std::array::from_fn(|i| i64::from(color[i]) - i64::from(anchor[i]));
    field
        .paint(coarse, 0, 0, color, DetailPolicy::Preserve)
        .unwrap();
    let view = grid(79, 53);
    for y in 0..view.height() {
        for x in 0..view.width() {
            let old = before.sample(view, x, y).unwrap();
            let expected = if in_cell(view, x, y, coarse, 0, 0) {
                shifted(old, delta)
            } else {
                old
            };
            assert_eq!(field.sample(view, x, y), Ok(expected));
        }
    }
}
