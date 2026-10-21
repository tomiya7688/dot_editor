use hyper_dot_core::layer_error::LayerError;
use hyper_dot_core::layered_canvas::LayeredCanvas;
use hyper_dot_core::raster::{Color, Raster};
use hyper_dot_core::resolution::Resolution;
use hyper_dot_core::resolution_field::DetailPolicy;

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
///   責務: [crc32: 検査用にCRC32を独立した実装で求める]
///   処理: [
///     1: ビット単位で多項式を畳み込む
///   ]
///   引数: [
///     bytes: CRCの対象
///   ]
///   戻り値: [CRC32値]
/// }
fn crc32(bytes: &[u8]) -> u32 {
    let mut value = 0xFFFF_FFFFu32;
    for byte in bytes {
        value ^= u32::from(*byte);
        for _ in 0..8 {
            value = if value & 1 == 1 {
                0xEDB8_8320 ^ (value >> 1)
            } else {
                value >> 1
            };
        }
    }
    !value
}

/// {
///   責務: [decode: 書き出したPNGを検査しながら画素の行列へ戻す]
///   処理: [
///     1: 署名と各チャンクの長さ・CRCを確認する
///     2: IHDRが8bit RGBAであることを確認する
///     3: 圧縮なしのdeflateブロックとAdler-32を確認して走査線を復元する
///   ]
///   引数: [
///     png: 検査するPNGのバイト列
///   ]
///   戻り値: [幅・高さと、行ごとのRGBA色]
/// }
fn decode(png: &[u8]) -> (u32, u32, Vec<Vec<Color>>) {
    assert_eq!(&png[..8], &[0x89, b'P', b'N', b'G', 0x0D, 0x0A, 0x1A, 0x0A]);
    let mut position = 8;
    let (mut width, mut height) = (0, 0);
    let mut idat = Vec::new();
    let mut kinds = Vec::new();
    while position < png.len() {
        let length = u32::from_be_bytes(png[position..position + 4].try_into().unwrap()) as usize;
        let kind = &png[position + 4..position + 8];
        let data = &png[position + 8..position + 8 + length];
        let stored = u32::from_be_bytes(
            png[position + 8 + length..position + 12 + length]
                .try_into()
                .unwrap(),
        );
        assert_eq!(stored, crc32(&png[position + 4..position + 8 + length]));
        kinds.push(kind.to_vec());
        match kind {
            b"IHDR" => {
                width = u32::from_be_bytes(data[0..4].try_into().unwrap());
                height = u32::from_be_bytes(data[4..8].try_into().unwrap());
                assert_eq!(&data[8..], &[8, 6, 0, 0, 0]);
            }
            b"IDAT" => idat.extend_from_slice(data),
            _ => {}
        }
        position += 12 + length;
    }
    assert_eq!(kinds.first().unwrap().as_slice(), b"IHDR");
    assert_eq!(kinds.last().unwrap().as_slice(), b"IEND");
    assert_eq!(&idat[..2], &[0x78, 0x01]);
    let mut raw = Vec::new();
    let mut at = 2;
    loop {
        let is_last = idat[at] == 1;
        let length = u16::from_le_bytes([idat[at + 1], idat[at + 2]]);
        assert_eq!(!length, u16::from_le_bytes([idat[at + 3], idat[at + 4]]));
        raw.extend_from_slice(&idat[at + 5..at + 5 + length as usize]);
        at += 5 + length as usize;
        if is_last {
            break;
        }
    }
    let (mut low, mut high) = (1u32, 0u32);
    for byte in &raw {
        low = (low + u32::from(*byte)) % 65_521;
        high = (high + low) % 65_521;
    }
    assert_eq!(idat[at..], ((high << 16) | low).to_be_bytes());
    let row_bytes = width as usize * 4 + 1;
    assert_eq!(raw.len(), row_bytes * height as usize);
    let rows = raw
        .chunks(row_bytes)
        .map(|row| {
            assert_eq!(row[0], 0, "filter type");
            row[1..]
                .chunks(4)
                .map(|pixel| pixel.try_into().unwrap())
                .collect()
        })
        .collect();
    (width, height, rows)
}

/// {
///   責務: [png_round_trips_size_alpha_and_hidden_color: PNGの寸法・透明度・透明画素のRGBが書き出しで保たれることを回帰検証する]
///   処理: [
///     1: 不透明・半透明・透明（RGB付き）の画素を持つラスタを書き出す
///     2: 検査用の復号結果と元のラスタを比較する
///   ]
///   引数: []
///   戻り値: [なし、不一致ならテストを失敗させる]
/// }
#[test]
fn png_round_trips_size_alpha_and_hidden_color() {
    let mut raster = Raster::new(grid(3, 2)).unwrap();
    raster.paint(0, 0, [255, 0, 0, 255]);
    raster.paint(1, 0, [10, 20, 30, 128]);
    raster.paint(2, 1, [7, 8, 9, 0]);
    let (width, height, rows) = decode(&raster.to_png().unwrap());
    assert_eq!((width, height), (3, 2));
    assert_eq!(rows[0][0], [255, 0, 0, 255]);
    assert_eq!(rows[0][1], [10, 20, 30, 128]);
    assert_eq!(rows[1][2], [7, 8, 9, 0]);
    assert_eq!(rows[1][0], [0, 0, 0, 0]);
}

/// {
///   責務: [large_png_spans_several_stored_blocks: 65535バイトを超える画像が複数ブロックでも正しく復号できることを回帰検証する]
///   処理: [
///     1: 1ブロックに収まらない大きさのラスタを書き出す
///     2: ブロック分割後も全画素が一致することを比較する
///   ]
///   引数: []
///   戻り値: [なし、不一致ならテストを失敗させる]
/// }
#[test]
fn large_png_spans_several_stored_blocks() {
    let mut raster = Raster::new(grid(200, 100)).unwrap();
    for y in 0..100 {
        for x in 0..200 {
            raster.paint(x, y, [x as u8, y as u8, (x ^ y) as u8, 200]);
        }
    }
    let (width, height, rows) = decode(&raster.to_png().unwrap());
    assert_eq!((width, height), (200, 100));
    for y in 0..100 {
        for x in 0..200 {
            assert_eq!(rows[y as usize][x as usize], raster.sample(x, y).unwrap());
        }
    }
}

/// {
///   責務: [export_size_scales_nearest_and_rejects_smaller_sizes: 書き出しサイズ指定が最近傍拡大になり小さい指定を拒否することを回帰検証する]
///   処理: [
///     1: 2層の作品を整数倍・非整数倍へ拡大した画素を、画素の中心の位置計算で比較する
///     2: 自然な解像度より小さい指定がエラーになることを確認する
///   ]
///   引数: []
///   戻り値: [なし、不一致ならテストを失敗させる]
/// }
#[test]
fn export_size_scales_nearest_and_rejects_smaller_sizes() {
    let mut document = LayeredCanvas::new(grid(2, 2)).unwrap();
    document
        .paint(1, 0, [255, 0, 0, 255], DetailPolicy::Preserve)
        .unwrap();
    document
        .paint(0, 1, [0, 255, 0, 255], DetailPolicy::Preserve)
        .unwrap();
    let native = document.composite().unwrap();
    for size in [2, 3, 5, 8] {
        let scaled = document.composite_scaled(grid(size, size)).unwrap();
        assert_eq!(scaled.resolution(), grid(size, size));
        for y in 0..size {
            for x in 0..size {
                let source_x = (2 * x + 1) * 2 / (2 * size);
                let source_y = (2 * y + 1) * 2 / (2 * size);
                assert_eq!(
                    scaled.sample(x, y),
                    native.sample(source_x, source_y),
                    "{size}: ({x}, {y})"
                );
            }
        }
    }
    assert_eq!(
        document.composite_scaled(grid(1, 2)),
        Err(LayerError::ExportSmallerThanNative)
    );
}
