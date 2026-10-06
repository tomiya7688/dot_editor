use hyper_dot_core::raster::{Color, Raster};
use hyper_dot_core::resolution::Resolution;
use hyper_dot_core::resolution_field::{DetailPolicy, ResolutionField};

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
///   責務: [patterned: 位置ごとに異なるRGBAのテスト画像を作る]
///   処理: [
///     1: 画像を確保する
///     2: 座標から色を計算して各画素へ描く
///   ]
///   引数: []
///   戻り値: [標本位置と細部保持の比較に使うラスタ]
/// }
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

/// {
///   責務: [in_cell: 表示画素の中心が対象編集セル内にあるか判定する]
///   処理: [
///     1: 整数の中心座標を編集グリッドへ投影する
///     2: 編集セル座標と比較する
///   ]
///   引数: [
///     view: 判定元の論理表示
///     x: 横座標
///     y: 縦座標
///     edit: 編集セルの解像度
///     ex: 編集対象の横セル座標
///     ey: 編集対象の縦セル座標
///   ]
///   戻り値: [対象編集セルに属す場合true]
/// }
fn in_cell(view: Resolution, x: u32, y: u32, edit: Resolution, ex: u32, ey: u32) -> bool {
    let cx = (2 * u64::from(x) + 1) * u64::from(edit.width()) / (2 * u64::from(view.width()));
    let cy = (2 * u64::from(y) + 1) * u64::from(edit.height()) / (2 * u64::from(view.height()));
    cx == u64::from(ex) && cy == u64::from(ey)
}

/// {
///   責務: [shifted: RGBAへ色差分を加え表示範囲に丸める]
///   処理: [
///     1: 各成分へ差分を加算する
///     2: 0から255へ制限する
///   ]
///   引数: [
///     color: 適用するRGBA色
///     delta: RGBA成分ごとの色差分
///   ]
///   戻り値: [補正後のRGBA]
/// }
fn shifted(color: Color, delta: [i64; 4]) -> Color {
    std::array::from_fn(|i| (i64::from(color[i]) + delta[i]).clamp(0, 255) as u8)
}

/// {
///   責務: [preserve_detail_roundtrip: 細部保持編集の往復で元の標本を復元することを回帰検証する]
///   処理: [
///     1: 対象の画像・状態を用意する
///     2: 細部保持編集の往復で元の標本を復元する操作を実行し期待結果をassertで比較する
///   ]
///   引数: []
///   戻り値: [なし、不一致ならテストを失敗させる]
/// }
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

/// {
///   責務: [discard_detail_is_local: 細部破棄を対象セルへ限定することを回帰検証する]
///   処理: [
///     1: 対象の画像・状態を用意する
///     2: 細部破棄を対象セルへ限定する操作を実行し期待結果をassertで比較する
///   ]
///   引数: []
///   戻り値: [なし、不一致ならテストを失敗させる]
/// }
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

/// {
///   責務: [preserve_recovers_raw_samples_after_color_clipping: 色クリップ後も未飽和の標本を復元することを回帰検証する]
///   処理: [
///     1: 対象の画像・状態を用意する
///     2: 色クリップ後も未飽和の標本を復元する操作を実行し期待結果をassertで比較する
///   ]
///   引数: []
///   戻り値: [なし、不一致ならテストを失敗させる]
/// }
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

/// {
///   責務: [unchanged_preserve_and_discard_have_different_detail_behavior: 同色編集の保持と破棄で細部の扱いを区別することを回帰検証する]
///   処理: [
///     1: 対象の画像・状態を用意する
///     2: 同色編集の保持と破棄で細部の扱いを区別する操作を実行し期待結果をassertで比較する
///   ]
///   引数: []
///   戻り値: [なし、不一致ならテストを失敗させる]
/// }
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

/// {
///   責務: [undo_snapshot_restores_discarded_detail: スナップショットから破棄済み細部を復元することを回帰検証する]
///   処理: [
///     1: 対象の画像・状態を用意する
///     2: スナップショットから破棄済み細部を復元する操作を実行し期待結果をassertで比較する
///   ]
///   引数: []
///   戻り値: [なし、不一致ならテストを失敗させる]
/// }
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

/// {
///   責務: [fine_edits_on_unaligned_grids_survive_display_changes: 不整列グリッドの局所編集を表示変更後も維持することを回帰検証する]
///   処理: [
///     1: 対象の画像・状態を用意する
///     2: 不整列グリッドの局所編集を表示変更後も維持する操作を実行し期待結果をassertで比較する
///   ]
///   引数: []
///   戻り値: [なし、不一致ならテストを失敗させる]
/// }
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

/// {
///   責務: [editing_largest_logical_grid_does_not_overflow_or_change_neighboring_samples: 最大論理グリッドの編集で桁あふれと隣接変更を防ぐことを回帰検証する]
///   処理: [
///     1: 対象の画像・状態を用意する
///     2: 最大論理グリッドの編集で桁あふれと隣接変更を防ぐ操作を実行し期待結果をassertで比較する
///   ]
///   引数: []
///   戻り値: [なし、不一致ならテストを失敗させる]
/// }
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

/// {
///   責務: [preserve_tints_mixed_raster_and_solid_patches_only_inside_the_edit: 混在する画像・単色パッチを編集領域内だけ着色することを回帰検証する]
///   処理: [
///     1: 対象の画像・状態を用意する
///     2: 混在する画像・単色パッチを編集領域内だけ着色する操作を実行し期待結果をassertで比較する
///   ]
///   引数: []
///   戻り値: [なし、不一致ならテストを失敗させる]
/// }
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
