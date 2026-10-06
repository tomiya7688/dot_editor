use hyper_dot_core::raster::{Color, Raster};
use hyper_dot_core::resolution::Resolution;

const CLEAR: Color = [0, 0, 0, 0];
const RED: Color = [255, 0, 0, 255];
const BLUE: Color = [0, 0, 255, 128];

/// {
///   責務: [raster: テスト用の透明ラスタを確保する]
///   処理: [
///     1: 正の解像度を作りラスタを確保する
///   ]
///   引数: [
///     width: 対象領域の幅
///     height: 対象領域の高さ
///   ]
///   戻り値: [透明ラスタ、確保失敗ならテストを失敗させる]
/// }
fn raster(width: u32, height: u32) -> Raster {
    Raster::new(Resolution::new(width, height).unwrap()).unwrap()
}

/// {
///   責務: [fills_only_four_connected_region: 4近傍で連結する領域だけを塗ることを回帰検証する]
///   処理: [
///     1: 対象の画像・状態を用意する
///     2: 4近傍で連結する領域だけを塗る操作を実行し期待結果をassertで比較する
///   ]
///   引数: []
///   戻り値: [なし、不一致ならテストを失敗させる]
/// }
#[test]
fn fills_only_four_connected_region() {
    let mut image = raster(4, 3);
    for (x, y) in [(0, 0), (1, 0), (1, 1), (2, 2), (3, 2)] {
        image.paint(x, y, RED);
    }

    assert_eq!(image.fill(0, 0, BLUE), Ok(3));
    let expected = [
        [BLUE, BLUE, CLEAR, CLEAR],
        [CLEAR, BLUE, CLEAR, CLEAR],
        [CLEAR, CLEAR, RED, RED],
    ];
    for (y, row) in expected.iter().enumerate() {
        for (x, color) in row.iter().enumerate() {
            assert_eq!(image.sample(x as u32, y as u32), Ok(*color));
        }
    }
}

/// {
///   責務: [non_square_fill_stays_on_its_side_of_a_wall: 非正方形画像で壁の反対側を塗らないことを回帰検証する]
///   処理: [
///     1: 対象の画像・状態を用意する
///     2: 非正方形画像で壁の反対側を塗らない操作を実行し期待結果をassertで比較する
///   ]
///   引数: []
///   戻り値: [なし、不一致ならテストを失敗させる]
/// }
#[test]
fn non_square_fill_stays_on_its_side_of_a_wall() {
    let mut image = raster(5, 3);
    for y in 0..3 {
        image.paint(2, y, RED);
    }

    assert_eq!(image.fill(0, 1, BLUE), Ok(6));
    for y in 0..3 {
        for x in 0..5 {
            let expected = match x {
                0 | 1 => BLUE,
                2 => RED,
                _ => CLEAR,
            };
            assert_eq!(image.sample(x, y), Ok(expected));
        }
    }
}

/// {
///   責務: [paint_fill_erase: 描画・塗りつぶし・消去の連続操作ことを回帰検証する]
///   処理: [
///     1: 対象の画像・状態を用意する
///     2: 描画・塗りつぶし・消去の連続操作操作を実行し期待結果をassertで比較する
///   ]
///   引数: []
///   戻り値: [なし、不一致ならテストを失敗させる]
/// }
#[test]
fn paint_fill_erase() {
    let mut image = raster(3, 2);
    assert!(image.paint(2, 1, RED));
    assert_eq!(image.fill(0, 0, RED), Ok(5));
    assert!(image.erase(0, 0));
    assert_eq!(image.fill(1, 0, CLEAR), Ok(5));
    assert_eq!(image, raster(3, 2));
}

/// {
///   責務: [rgba_matching_includes_alpha_and_hidden_rgb: RGBA一致に透明度と隠れたRGBを含めることを回帰検証する]
///   処理: [
///     1: 対象の画像・状態を用意する
///     2: RGBA一致に透明度と隠れたRGBを含める操作を実行し期待結果をassertで比較する
///   ]
///   引数: []
///   戻り値: [なし、不一致ならテストを失敗させる]
/// }
#[test]
fn rgba_matching_includes_alpha_and_hidden_rgb() {
    let mut image = raster(3, 1);
    image.paint(0, 0, [10, 20, 30, 128]);
    image.paint(1, 0, [10, 20, 30, 255]);
    image.paint(2, 0, [10, 20, 30, 0]);

    assert_eq!(image.fill(0, 0, BLUE), Ok(1));
    assert_eq!(image.fill(2, 0, CLEAR), Ok(1));
    assert_eq!(image.sample(0, 0), Ok(BLUE));
    assert_eq!(image.sample(1, 0), Ok([10, 20, 30, 255]));
    assert_eq!(image.sample(2, 0), Ok(CLEAR));
}

/// {
///   責務: [unchanged_color_and_out_of_bounds_seed_do_not_mutate: 同色と範囲外始点で変更しないことを回帰検証する]
///   処理: [
///     1: 対象の画像・状態を用意する
///     2: 同色と範囲外始点で変更しない操作を実行し期待結果をassertで比較する
///   ]
///   引数: []
///   戻り値: [なし、不一致ならテストを失敗させる]
/// }
#[test]
fn unchanged_color_and_out_of_bounds_seed_do_not_mutate() {
    let mut image = raster(2, 3);
    image.paint(0, 0, RED);
    let before = image.clone();

    assert_eq!(image.fill(0, 0, RED), Ok(0));
    assert_eq!(image.fill(2, 0, BLUE), Ok(0));
    assert_eq!(image.fill(0, 3, BLUE), Ok(0));
    assert_eq!(image.fill(u32::MAX, u32::MAX, BLUE), Ok(0));
    assert_eq!(image, before);
}

/// {
///   責務: [fills_long_single_row_and_column: 長い1行・1列を塗りつぶすことを回帰検証する]
///   処理: [
///     1: 対象の画像・状態を用意する
///     2: 長い1行・1列を塗りつぶす操作を実行し期待結果をassertで比較する
///   ]
///   引数: []
///   戻り値: [なし、不一致ならテストを失敗させる]
/// }
#[test]
fn fills_long_single_row_and_column() {
    for (width, height) in [(4096, 1), (1, 4096)] {
        let mut image = raster(width, height);
        assert_eq!(image.fill(0, 0, BLUE), Ok(4096));
        assert_eq!(image.sample(width - 1, height - 1), Ok(BLUE));
        assert_eq!(image.fill(width - 1, height - 1, BLUE), Ok(0));
    }
}
