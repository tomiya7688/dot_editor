use hyper_dot_core::canvas::{Canvas, CanvasError};
use hyper_dot_core::raster::{Raster, RasterError};
use hyper_dot_core::resolution::Resolution;
use hyper_dot_core::resolution_field::DetailPolicy;

fn grid(width: u32, height: u32) -> Resolution {
    Resolution::new(width, height).unwrap()
}

#[test]
fn rectangular_region_is_local_and_one_undo_restores_all_cells() {
    let mut source = Raster::new(grid(7, 5)).unwrap();
    for y in 0..5 {
        for x in 0..7 {
            source.paint(x, y, [x as u8, y as u8, 40, 255]);
        }
    }
    let mut canvas = Canvas::from_raster(source.clone());
    let before = canvas.render_at(grid(23, 17)).unwrap();
    assert_eq!(canvas.split_region(2, 1, 3, 2), Ok(6));
    assert_eq!(canvas.render(), Ok(source.clone()));
    assert_eq!(canvas.render_at(grid(23, 17)), Ok(before));
    assert_eq!(canvas.native_resolution(), Ok(grid(14, 10)));
    for y in 0..5 {
        for x in 0..7 {
            let inside = (2..5).contains(&x) && (1..3).contains(&y);
            assert_eq!(canvas.is_split(x, y), inside);
            if inside {
                for child in [(0, 0), (1, 0), (0, 1), (1, 1)] {
                    assert_eq!(
                        canvas.sample_child(x, y, child),
                        Ok(source.sample(x, y).unwrap())
                    );
                }
            }
        }
    }
    canvas.undo().unwrap();
    assert!(!canvas.can_undo());
    assert_eq!(canvas.native_resolution(), Ok(grid(7, 5)));
    for y in 0..5 {
        for x in 0..7 {
            assert!(!canvas.is_split(x, y));
        }
    }
    canvas.redo().unwrap();
    assert!(canvas.is_split(4, 2));
    assert_eq!(canvas.render(), Ok(source));
}

#[test]
fn region_expansion_survives_unaligned_grid_changes_with_retained_samples() {
    let mut source = Raster::new(grid(16, 12)).unwrap();
    for y in 0..12 {
        for x in 0..16 {
            source.paint(x, y, [40 + x as u8, 60 + y as u8, 80, 255]);
        }
    }
    let mut canvas = Canvas::from_raster(source.clone());
    canvas
        .set_resolution(grid(4, 3), DetailPolicy::Preserve)
        .unwrap();
    assert_eq!(canvas.split_region(1, 1, 2, 2), Ok(4));
    let parent = canvas.sample(2, 2).unwrap();
    let child = canvas.sample_child(2, 2, (1, 0)).unwrap();
    let native = canvas.render_native().unwrap();
    canvas
        .set_resolution(grid(7, 5), DetailPolicy::Preserve)
        .unwrap();
    canvas
        .set_resolution(grid(4, 3), DetailPolicy::Preserve)
        .unwrap();
    assert_eq!(canvas.render_at(grid(16, 12)), Ok(source));
    assert_eq!(canvas.render_native(), Ok(native));
    assert_eq!(canvas.sample(2, 2), Ok(parent));
    assert_eq!(canvas.sample_child(2, 2, (1, 0)), Ok(child));
    assert!(canvas.is_split(1, 1));
    assert!(canvas.is_split(2, 2));
}

#[test]
fn mixed_expanded_collapsed_and_new_cells_keep_parent_overrides_and_children() {
    let mut canvas = Canvas::new(grid(4, 3)).unwrap();
    canvas.split_cell(0, 1).unwrap();
    canvas.split_cell(1, 1).unwrap();
    canvas.paint(1, 1, [40; 4], DetailPolicy::Preserve).unwrap();
    canvas
        .paint_child(1, 1, (1, 0), [90; 4], DetailPolicy::Discard)
        .unwrap();
    canvas.collapse_cell(1, 1).unwrap();
    let before = canvas.render_at(grid(8, 6)).unwrap();
    assert_eq!(canvas.split_region(0, 1, 3, 1), Ok(2));
    assert_eq!(canvas.sample(1, 1), Ok([40; 4]));
    assert_eq!(canvas.sample_child(1, 1, (1, 0)), Ok([90; 4]));
    assert_eq!(canvas.render_at(grid(8, 6)), Ok(before.clone()));
    canvas.undo().unwrap();
    assert!(canvas.is_split(0, 1));
    assert!(!canvas.is_split(1, 1));
    assert!(!canvas.is_split(2, 1));
    assert_eq!(canvas.render_at(grid(8, 6)), Ok(before));
    canvas.redo().unwrap();
    assert!(canvas.is_split(1, 1));
    assert!(canvas.is_split(2, 1));
}

#[test]
fn noop_region_keeps_redo_but_a_new_split_invalidates_it() {
    let mut canvas = Canvas::new(grid(3, 2)).unwrap();
    canvas.split_region(0, 0, 2, 2).unwrap();
    canvas.split_cell(2, 0).unwrap();
    canvas.undo().unwrap();
    let before = canvas.clone();
    assert_eq!(canvas.split_region(0, 0, 2, 2), Ok(0));
    assert_eq!(canvas, before);
    assert_eq!(canvas.split_region(1, 0, 2, 2), Ok(2));
    assert!(!canvas.can_redo());
}

#[test]
fn invalid_regions_and_overflow_leave_state_and_history_intact() {
    let mut canvas = Canvas::new(grid(7, 5)).unwrap();
    canvas.split_cell(0, 0).unwrap();
    canvas.undo().unwrap();
    let before = canvas.clone();
    for (x, y, width, height) in [(0, 0, 0, 1), (0, 0, 1, 0)] {
        assert_eq!(
            canvas.split_region(x, y, width, height),
            Err(CanvasError::InvalidRegionSize)
        );
        assert_eq!(canvas, before);
    }
    for (x, y, width, height) in [
        (7, 0, 1, 1),
        (0, 5, 1, 1),
        (6, 4, 2, 1),
        (6, 4, 1, 2),
        (u32::MAX, 0, 1, 1),
        (0, u32::MAX, 1, 1),
        (1, 0, u32::MAX, 1),
        (0, 1, 1, u32::MAX),
    ] {
        assert_eq!(
            canvas.split_region(x, y, width, height),
            Err(CanvasError::RegionOutOfBounds {
                x,
                y,
                width,
                height
            })
        );
        assert_eq!(canvas, before);
    }
    assert_eq!(canvas.split_region(6, 4, 1, 1), Ok(1));
}

#[test]
fn rectangular_child_grid_is_validated_by_both_dimensions_and_pixel_budget() {
    let mut valid = Canvas::new(grid(1800, 500)).unwrap();
    assert_eq!(valid.split_region(1799, 499, 1, 1), Ok(1));
    assert_eq!(valid.native_resolution(), Ok(grid(3600, 1000)));
    for (resolution, expected) in [
        (
            grid(4096, 1),
            CanvasError::Raster(RasterError::DimensionLimitExceeded {
                width: 8192,
                height: 2,
            }),
        ),
        (
            grid(2048, 1025),
            CanvasError::Raster(RasterError::PixelBudgetExceeded),
        ),
    ] {
        let mut canvas = Canvas::new(resolution).unwrap();
        let before = canvas.clone();
        assert_eq!(canvas.split_region(0, 0, 1, 1), Err(expected));
        assert_eq!(canvas, before);
    }
}

#[test]
fn budget_counts_new_records_not_reexpanded_cells_and_rejects_atomically() {
    let mut canvas = Canvas::new(grid(65, 64)).unwrap();
    assert_eq!(canvas.split_region(0, 0, 64, 64), Ok(4096));
    canvas.collapse_cell(63, 63).unwrap();
    assert_eq!(canvas.split_region(0, 0, 64, 64), Ok(1));
    canvas.undo().unwrap();
    let before = canvas.clone();
    // A collapsed record would expand before the new record in row order.
    assert_eq!(
        canvas.split_region(63, 63, 2, 1),
        Err(CanvasError::SplitLimitExceeded)
    );
    assert_eq!(canvas, before);
    assert!(canvas.can_redo());
    assert_eq!(
        canvas.split_region(0, 0, 65, 64),
        Err(CanvasError::SplitLimitExceeded)
    );
    assert_eq!(canvas, before);
}

#[test]
fn splits_from_other_grids_are_preserved_and_count_toward_the_budget() {
    let mut canvas = Canvas::new(grid(64, 64)).unwrap();
    canvas.split_region(0, 0, 64, 64).unwrap();
    canvas.paint(1, 1, [60; 4], DetailPolicy::Preserve).unwrap();
    canvas
        .set_resolution(grid(7, 5), DetailPolicy::Preserve)
        .unwrap();
    let before = canvas.clone();
    assert_eq!(
        canvas.split_region(0, 0, 1, 1),
        Err(CanvasError::SplitLimitExceeded)
    );
    assert_eq!(canvas, before);
    canvas
        .set_resolution(grid(64, 64), DetailPolicy::Preserve)
        .unwrap();
    assert!(canvas.is_split(1, 1));
    assert_eq!(canvas.sample(1, 1), Ok([60; 4]));
}
