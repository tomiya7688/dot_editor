use hyper_dot_core::canvas::{Canvas, CanvasError};
use hyper_dot_core::raster::{Raster, RasterError};
use hyper_dot_core::resolution::Resolution;
use hyper_dot_core::resolution_field::{DetailPolicy, ResolutionFieldError};

fn grid(width: u32, height: u32) -> Resolution {
    Resolution::new(width, height).unwrap()
}

#[test]
fn fill_matches_raster_connectivity_and_rgba_from_every_seed() {
    let mut source = Raster::new(grid(7, 5)).unwrap();
    let colors = [[10, 20, 30, 0], [11, 20, 30, 0], [10, 20, 30, 1]];
    for y in 0..5 {
        for x in 0..7 {
            source.paint(x, y, colors[((x * x + y * 3) % 3) as usize]);
        }
    }
    for policy in [DetailPolicy::Preserve, DetailPolicy::Discard] {
        for y in 0..5 {
            for x in 0..7 {
                let mut expected = source.clone();
                let count = expected.fill(x, y, [0; 4]).unwrap();
                let mut canvas = Canvas::from_raster(source.clone());
                assert_eq!(canvas.fill(x, y, [0; 4], policy), Ok(count));
                assert_eq!(canvas.render(), Ok(expected.clone()));
                assert!(canvas.undo().unwrap());
                assert_eq!(canvas.render(), Ok(source.clone()));
                assert!(!canvas.can_undo());
                assert!(canvas.redo().unwrap());
                assert_eq!(canvas.render(), Ok(expected));
            }
        }
    }
}

#[test]
fn diagonal_cells_are_not_connected_and_replacement_does_not_extend_the_region() {
    let mut source = Raster::new(grid(3, 3)).unwrap();
    for (x, y) in [(1, 0), (0, 1), (2, 1), (1, 2)] {
        source.paint(x, y, [255; 4]);
    }
    let mut canvas = Canvas::from_raster(source);
    assert_eq!(canvas.fill(0, 0, [255; 4], DetailPolicy::Preserve), Ok(1));
    assert_eq!(canvas.sample(1, 1), Ok([0; 4]));
    assert_eq!(canvas.sample(2, 0), Ok([0; 4]));
}

fn detailed_source() -> Raster {
    let mut source = Raster::new(grid(8, 2)).unwrap();
    for y in 0..2 {
        for x in 0..8 {
            let value = if x >= 6 {
                200
            } else if x % 2 == 1 {
                40
            } else {
                10 + x as u8
            };
            source.paint(x, y, [value, 40, 40, 255]);
        }
    }
    source
}

#[test]
fn coarse_fill_preserves_or_discards_only_connected_detail_in_one_history_step() {
    for policy in [DetailPolicy::Preserve, DetailPolicy::Discard] {
        let source = detailed_source();
        let mut canvas = Canvas::from_raster(source.clone());
        canvas
            .set_resolution(grid(4, 1), DetailPolicy::Preserve)
            .unwrap();
        assert_eq!(canvas.fill(1, 0, [60, 40, 40, 255], policy), Ok(3));
        let after = canvas.render_at(grid(8, 2)).unwrap();
        for y in 0..2 {
            for x in 0..8 {
                let mut expected = source.sample(x, y).unwrap();
                if x < 6 {
                    expected[0] = if policy == DetailPolicy::Preserve {
                        expected[0] + 20
                    } else {
                        60
                    };
                }
                assert_eq!(after.sample(x, y), Ok(expected));
            }
        }
        canvas.undo().unwrap();
        assert_eq!(canvas.resolution(), grid(4, 1));
        assert_eq!(canvas.render_at(grid(8, 2)), Ok(source));
        canvas.redo().unwrap();
        assert_eq!(canvas.render_at(grid(8, 2)), Ok(after));
    }
}

#[test]
fn same_color_discard_traverses_plain_cells_to_reach_collapsed_detail() {
    let mut canvas = Canvas::new(grid(4, 1)).unwrap();
    canvas.split_cell(2, 0).unwrap();
    // Metadata alone is detail, even when every retained sample is transparent.
    // A child write also partitions the field outside this parent, so it would
    // not be a fixture with exactly one detailed cell.
    canvas.collapse_cell(2, 0).unwrap();
    let before = canvas.clone();
    assert_eq!(canvas.fill(0, 0, [0; 4], DetailPolicy::Preserve), Ok(0));
    assert_eq!(canvas, before);
    assert_eq!(canvas.fill(0, 0, [0; 4], DetailPolicy::Discard), Ok(1));
    assert!(!canvas.has_detail_at(2, 0).unwrap());
    assert_eq!(
        canvas.sample_child(2, 0, (0, 0)),
        Err(CanvasError::CellNotSplit { x: 2, y: 0 })
    );
    canvas.undo().unwrap();
    assert!(!canvas.is_split(2, 0));
    assert_eq!(canvas.sample_child(2, 0, (0, 0)), Ok([0; 4]));
}

#[test]
fn fill_uses_saved_parent_colors_and_preserve_keeps_children_unchanged() {
    for collapsed in [false, true] {
        for policy in [DetailPolicy::Preserve, DetailPolicy::Discard] {
            let mut canvas = Canvas::new(grid(3, 1)).unwrap();
            canvas.split_cell(1, 0).unwrap();
            canvas
                .paint_child(1, 0, (1, 1), [90; 4], DetailPolicy::Discard)
                .unwrap();
            if collapsed {
                canvas.collapse_cell(1, 0).unwrap();
            }
            let before = canvas.render_at(grid(6, 2)).unwrap();
            assert_eq!(canvas.fill(0, 0, [20; 4], policy), Ok(3));
            assert_eq!(canvas.sample(1, 0), Ok([20; 4]));
            if policy == DetailPolicy::Preserve {
                assert_eq!(canvas.sample_child(1, 0, (1, 1)), Ok([90; 4]));
                assert_eq!(canvas.sample_child(1, 0, (0, 0)), Ok([0; 4]));
                assert_eq!(canvas.is_split(1, 0), !collapsed);
            } else {
                assert!(!canvas.has_detail_at(1, 0).unwrap());
                assert_eq!(
                    canvas.render_at(grid(6, 2)).unwrap().sample(3, 1),
                    Ok([20; 4])
                );
            }
            canvas.undo().unwrap();
            assert_eq!(canvas.render_at(grid(6, 2)), Ok(before));
            assert_eq!(canvas.is_split(1, 0), !collapsed);
        }
    }
}

#[test]
fn split_parent_override_is_a_connectivity_barrier() {
    let mut canvas = Canvas::new(grid(3, 1)).unwrap();
    canvas.split_cell(1, 0).unwrap();
    canvas.paint(1, 0, [90; 4], DetailPolicy::Preserve).unwrap();
    assert_eq!(canvas.fill(0, 0, [20; 4], DetailPolicy::Discard), Ok(1));
    assert_eq!(canvas.sample(2, 0), Ok([0; 4]));
    assert_eq!(canvas.sample(1, 0), Ok([90; 4]));
    assert!(canvas.is_split(1, 0));
}

#[test]
fn coarse_fill_updates_or_removes_saved_cross_grid_splits() {
    for policy in [DetailPolicy::Preserve, DetailPolicy::Discard] {
        let mut canvas = Canvas::new(grid(1, 1)).unwrap();
        canvas
            .set_resolution(grid(16, 12), DetailPolicy::Preserve)
            .unwrap();
        canvas.split_cell(1, 1).unwrap();
        canvas.paint(1, 1, [40; 4], DetailPolicy::Preserve).unwrap();
        canvas.collapse_cell(1, 1).unwrap();
        canvas
            .set_resolution(grid(7, 5), DetailPolicy::Preserve)
            .unwrap();
        assert_eq!(canvas.fill(6, 4, [5; 4], policy), Ok(35));
        canvas
            .set_resolution(grid(16, 12), DetailPolicy::Preserve)
            .unwrap();
        assert_eq!(
            canvas.sample(1, 1),
            Ok(if policy == DetailPolicy::Preserve {
                [45; 4]
            } else {
                [5; 4]
            })
        );
        if policy == DetailPolicy::Preserve {
            assert_eq!(canvas.sample_child(1, 1, (0, 0)), Ok([5; 4]));
        } else {
            assert_eq!(
                canvas.sample_child(1, 1, (0, 0)),
                Err(CanvasError::CellNotSplit { x: 1, y: 1 })
            );
        }
    }
}

#[test]
fn same_color_coarse_discard_counts_detail_cells_and_undo_restores_samples() {
    let source = detailed_source();
    let mut canvas = Canvas::from_raster(source.clone());
    canvas
        .set_resolution(grid(4, 1), DetailPolicy::Preserve)
        .unwrap();
    assert_eq!(
        canvas.fill(0, 0, [40, 40, 40, 255], DetailPolicy::Discard),
        Ok(3)
    );
    for x in 0..3 {
        assert!(!canvas.has_detail_at(x, 0).unwrap());
    }
    assert!(canvas.has_detail_at(3, 0).unwrap());
    canvas.undo().unwrap();
    assert_eq!(canvas.render_at(grid(8, 2)), Ok(source));
}

#[test]
fn noop_and_out_of_bounds_fill_preserve_redo_and_success_invalidates_it() {
    let mut canvas = Canvas::new(grid(3, 2)).unwrap();
    canvas.paint(0, 0, [1; 4], DetailPolicy::Preserve).unwrap();
    canvas.undo().unwrap();
    let before = canvas.clone();
    for policy in [DetailPolicy::Preserve, DetailPolicy::Discard] {
        assert_eq!(canvas.fill(0, 0, [0; 4], policy), Ok(0));
        assert_eq!(canvas.fill(u32::MAX, 0, [1; 4], policy), Ok(0));
        assert_eq!(canvas.fill(0, 2, [1; 4], policy), Ok(0));
        assert_eq!(canvas, before);
    }
    assert_eq!(canvas.fill(0, 0, [2; 4], DetailPolicy::Preserve), Ok(6));
    assert!(!canvas.can_redo());
}

#[test]
fn whole_canvas_fill_exceeds_patch_count_without_losing_preserved_detail() {
    for policy in [DetailPolicy::Preserve, DetailPolicy::Discard] {
        let mut canvas = Canvas::new(grid(128, 96)).unwrap();
        assert_eq!(canvas.fill(127, 95, [8; 4], policy), Ok(128 * 96));
        assert_eq!(canvas.retained_resolution(), grid(1, 1));
        assert_eq!(canvas.sample(0, 0), Ok([8; 4]));
        canvas.undo().unwrap();
        assert_eq!(canvas.retained_resolution(), grid(128, 96));
        assert!(!canvas.can_undo());
    }
    let source = detailed_source();
    let mut canvas = Canvas::from_raster(source.clone());
    canvas
        .set_resolution(grid(1, 1), DetailPolicy::Preserve)
        .unwrap();
    assert_eq!(
        canvas.fill(0, 0, [30, 40, 40, 255], DetailPolicy::Preserve),
        Ok(1)
    );
    assert_eq!(canvas.retained_resolution(), grid(8, 2));
    assert_ne!(
        canvas.render_at(grid(8, 2)).unwrap().sample(0, 0),
        canvas.render_at(grid(8, 2)).unwrap().sample(7, 0)
    );
    canvas.undo().unwrap();
    assert_eq!(canvas.render_at(grid(8, 2)), Ok(source));
}

#[test]
fn partial_fill_budget_failure_rolls_back_all_staged_cells_and_history() {
    let mut source = Raster::new(grid(65, 65)).unwrap();
    for y in 0..65 {
        source.paint(64, y, [255; 4]);
    }
    let mut canvas = Canvas::from_raster(source);
    canvas.split_cell(64, 64).unwrap();
    canvas.undo().unwrap();
    let before = canvas.clone();
    assert_eq!(
        canvas.fill(0, 0, [1; 4], DetailPolicy::Discard),
        Err(CanvasError::Field(
            ResolutionFieldError::PatchBudgetExceeded
        ))
    );
    assert_eq!(canvas, before);
    assert!(canvas.can_redo());
}

#[test]
fn unsafe_projection_fails_without_changing_logical_state() {
    let mut canvas = Canvas::new(grid(1, 1)).unwrap();
    canvas
        .set_resolution(grid(u32::MAX, 1), DetailPolicy::Preserve)
        .unwrap();
    let before = canvas.clone();
    assert_eq!(
        canvas.fill(0, 0, [1; 4], DetailPolicy::Discard),
        Err(CanvasError::Raster(RasterError::DimensionLimitExceeded {
            width: u32::MAX,
            height: 1
        }))
    );
    assert_eq!(canvas, before);
}
