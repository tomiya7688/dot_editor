use hyper_dot_core::raster::{Raster, RasterError};
use hyper_dot_core::resolution::Resolution;
use hyper_dot_core::resolution_field::ResolutionField;

/// {
///   責務: [resolution: テスト用の正の解像度を作る]
///   処理: [
///     1: 幅と高さを検証してResolutionを生成する
///   ]
///   引数: [
///     width: 対象領域の幅
///     height: 対象領域の高さ
///   ]
///   戻り値: [解像度、不正な寸法ならテストを失敗させる]
/// }
fn resolution(width: u32, height: u32) -> Resolution {
    Resolution::new(width, height).unwrap()
}

/// {
///   責務: [patterned: 位置ごとに異なるRGBAのテスト画像を作る]
///   処理: [
///     1: 画像を確保する
///     2: 座標から色を計算して各画素へ描く
///   ]
///   引数: [
///     width: 対象領域の幅
///     height: 対象領域の高さ
///   ]
///   戻り値: [標本位置と細部保持の比較に使うラスタ]
/// }
fn patterned(width: u32, height: u32) -> Raster {
    let mut raster = Raster::new(resolution(width, height)).unwrap();
    for y in 0..height {
        for x in 0..width {
            raster.paint(
                x,
                y,
                [
                    (70 + x % 40) as u8,
                    (90 + y % 40) as u8,
                    (110 + (x + y) % 40) as u8,
                    (150 + (x * y) % 70) as u8,
                ],
            );
        }
    }
    raster
}

/// {
///   責務: [arbitrary_resolution_roundtrip: 任意解像度の往復で元の画像を復元することを回帰検証する]
///   処理: [
///     1: 対象の画像・状態を用意する
///     2: 任意解像度の往復で元の画像を復元する操作を実行し期待結果をassertで比較する
///   ]
///   引数: []
///   戻り値: [なし、不一致ならテストを失敗させる]
/// }
#[test]
fn arbitrary_resolution_roundtrip() {
    let original = patterned(16, 16);
    let field = ResolutionField::from_raster(original.clone());
    let before = field.clone();

    for (width, height) in [(7, 7), (23, 17), (1, 31), (31, 1), (16, 16)] {
        let projected = field.render(resolution(width, height)).unwrap();
        assert_eq!(projected.resolution(), resolution(width, height));
        assert_eq!(field.retained_resolution(), resolution(16, 16));
    }
    assert_eq!(field.render(resolution(16, 16)), Ok(original));
    assert_eq!(field, before);
}

/// {
///   責務: [rectangular_source_roundtrip: 非正方形の元画像を往復することを回帰検証する]
///   処理: [
///     1: 対象の画像・状態を用意する
///     2: 非正方形の元画像を往復する操作を実行し期待結果をassertで比較する
///   ]
///   引数: []
///   戻り値: [なし、不一致ならテストを失敗させる]
/// }
#[test]
fn rectangular_source_roundtrip() {
    let original = patterned(23, 17);
    let field = ResolutionField::from_raster(original.clone());
    field.render(resolution(7, 5)).unwrap();
    field.render(resolution(41, 13)).unwrap();

    assert_eq!(field.render(resolution(23, 17)), Ok(original));
    assert_eq!(field.retained_resolution(), resolution(23, 17));
}

/// {
///   責務: [center_on_source_boundary_selects_right_and_bottom_pixel: 元画像境界の中心位置を右・下の画素へ割り当てることを回帰検証する]
///   処理: [
///     1: 対象の画像・状態を用意する
///     2: 元画像境界の中心位置を右・下の画素へ割り当てる操作を実行し期待結果をassertで比較する
///   ]
///   引数: []
///   戻り値: [なし、不一致ならテストを失敗させる]
/// }
#[test]
fn center_on_source_boundary_selects_right_and_bottom_pixel() {
    let mut source = Raster::new(resolution(2, 2)).unwrap();
    source.paint(0, 0, [255, 0, 0, 255]);
    source.paint(1, 0, [0, 255, 0, 255]);
    source.paint(0, 1, [0, 0, 255, 255]);
    source.paint(1, 1, [10, 20, 30, 40]);
    let field = ResolutionField::from_raster(source);

    assert_eq!(field.sample(resolution(1, 1), 0, 0), Ok([10, 20, 30, 40]));
    assert_eq!(field.sample(resolution(4, 4), 1, 1), Ok([255, 0, 0, 255]));
    assert_eq!(field.sample(resolution(4, 4), 2, 1), Ok([0, 255, 0, 255]));
}

/// {
///   責務: [unaligned_projection_matches_exact_center_fixture: 不整列投影を正確な中心fixtureと一致させることを回帰検証する]
///   処理: [
///     1: 対象の画像・状態を用意する
///     2: 不整列投影を正確な中心fixtureと一致させる操作を実行し期待結果をassertで比較する
///   ]
///   引数: []
///   戻り値: [なし、不一致ならテストを失敗させる]
/// }
#[test]
fn unaligned_projection_matches_exact_center_fixture() {
    let mut source = Raster::new(resolution(3, 2)).unwrap();
    let colors = [
        [[1, 0, 0, 11], [2, 0, 0, 22], [3, 0, 0, 33]],
        [[4, 0, 0, 44], [5, 0, 0, 55], [6, 0, 0, 66]],
    ];
    for (y, row) in colors.iter().enumerate() {
        for (x, color) in row.iter().enumerate() {
            source.paint(x as u32, y as u32, *color);
        }
    }
    let field = ResolutionField::from_raster(source);
    let projected = field.render(resolution(5, 3)).unwrap();
    let expected = [
        [
            colors[0][0],
            colors[0][0],
            colors[0][1],
            colors[0][2],
            colors[0][2],
        ],
        [
            colors[1][0],
            colors[1][0],
            colors[1][1],
            colors[1][2],
            colors[1][2],
        ],
        [
            colors[1][0],
            colors[1][0],
            colors[1][1],
            colors[1][2],
            colors[1][2],
        ],
    ];
    for (y, row) in expected.iter().enumerate() {
        for (x, color) in row.iter().enumerate() {
            assert_eq!(projected.sample(x as u32, y as u32), Ok(*color));
        }
    }
}

/// {
///   責務: [downscale_retains_unsampled_detail_and_views_are_independent: 縮小で未表示細部を保持し各表示を独立させることを回帰検証する]
///   処理: [
///     1: 対象の画像・状態を用意する
///     2: 縮小で未表示細部を保持し各表示を独立させる操作を実行し期待結果をassertで比較する
///   ]
///   引数: []
///   戻り値: [なし、不一致ならテストを失敗させる]
/// }
#[test]
fn downscale_retains_unsampled_detail_and_views_are_independent() {
    let mut source = Raster::new(resolution(16, 16)).unwrap();
    source.paint(0, 0, [255, 0, 0, 255]);
    let field = ResolutionField::from_raster(source.clone());
    let mut view = field.render(resolution(1, 1)).unwrap();
    assert_eq!(view.sample(0, 0), Ok([0, 0, 0, 0]));
    view.paint(0, 0, [0, 255, 0, 255]);

    assert_eq!(field.render(resolution(16, 16)), Ok(source));
    assert_eq!(
        field.clone().sample(resolution(16, 16), 0, 0),
        Ok([255, 0, 0, 255])
    );
}

/// {
///   責務: [sample_handles_largest_logical_grid_and_rejects_outside_coordinates: 最大論理グリッドで標本化し範囲外を拒否することを回帰検証する]
///   処理: [
///     1: 対象の画像・状態を用意する
///     2: 最大論理グリッドで標本化し範囲外を拒否する操作を実行し期待結果をassertで比較する
///   ]
///   引数: []
///   戻り値: [なし、不一致ならテストを失敗させる]
/// }
#[test]
fn sample_handles_largest_logical_grid_and_rejects_outside_coordinates() {
    let source = patterned(23, 17);
    let last = source.sample(22, 16).unwrap();
    let field = ResolutionField::from_raster(source);
    let grid = resolution(u32::MAX, u32::MAX);

    assert_eq!(field.sample(grid, u32::MAX - 1, u32::MAX - 1), Ok(last));
    assert_eq!(
        field.sample(grid, u32::MAX, 0),
        Err(RasterError::CoordinateOutOfBounds { x: u32::MAX, y: 0 })
    );
    assert_eq!(
        field.sample(resolution(2, 3), 0, 3),
        Err(RasterError::CoordinateOutOfBounds { x: 0, y: 3 })
    );
}

/// {
///   責務: [rejected_output_allocation_keeps_retained_source: 出力確保の拒否で元画像を維持することを回帰検証する]
///   処理: [
///     1: 対象の画像・状態を用意する
///     2: 出力確保の拒否で元画像を維持する操作を実行し期待結果をassertで比較する
///   ]
///   引数: []
///   戻り値: [なし、不一致ならテストを失敗させる]
/// }
#[test]
fn rejected_output_allocation_keeps_retained_source() {
    let original = patterned(3, 2);
    let field = ResolutionField::from_raster(original.clone());

    assert_eq!(
        field.render(resolution(4096, 4096)),
        Err(RasterError::PixelBudgetExceeded)
    );
    assert_eq!(field.render(resolution(3, 2)), Ok(original));
}
