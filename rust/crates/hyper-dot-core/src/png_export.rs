//! Dependency-free PNG writing for RGBA rasters.
//!
//! The encoder stores pixels in uncompressed deflate blocks. Files are larger
//! than compressed PNGs but every decoder can read them and the output is
//! byte-for-byte reproducible.

use crate::raster::{Raster, RasterError};

const SIGNATURE: [u8; 8] = [0x89, b'P', b'N', b'G', 0x0D, 0x0A, 0x1A, 0x0A];
const MAX_STORED_BLOCK: usize = 65_535;
const ADLER_MODULUS: u32 = 65_521;
const COLOR_TYPE_RGBA: u8 = 6;
const CRC_TABLE: [u32; 256] = crc_table();

/// {
///   責務: [crc_table: PNGのCRC32計算に使う256項目の表を作る]
///   処理: [
///     1: 各バイト値に対して、反転多項式で8回シフトした値を求める
///   ]
///   引数: []
///   戻り値: [CRC32の表]
/// }
const fn crc_table() -> [u32; 256] {
    let mut table = [0u32; 256];
    let mut index = 0;
    while index < 256 {
        let mut value = index as u32;
        let mut step = 0;
        while step < 8 {
            value = if value & 1 == 1 {
                0xEDB8_8320 ^ (value >> 1)
            } else {
                value >> 1
            };
            step += 1;
        }
        table[index] = value;
        index += 1;
    }
    table
}

/// {
///   責務: [crc32: チャンク種別とデータのCRC32を求める]
///   処理: [
///     1: 初期値から各バイトを表で畳み込む
///     2: 最後に全ビットを反転する
///   ]
///   引数: [
///     parts: CRCの対象になるバイト列を順に並べたもの
///   ]
///   戻り値: [CRC32値]
/// }
fn crc32(parts: &[&[u8]]) -> u32 {
    let mut value = 0xFFFF_FFFFu32;
    for byte in parts.iter().flat_map(|part| part.iter()) {
        value = CRC_TABLE[((value ^ u32::from(*byte)) & 0xFF) as usize] ^ (value >> 8);
    }
    !value
}

/// {
///   責務: [adler32: zlibストリームの末尾に付けるAdler-32を求める]
///   処理: [
///     1: 二つの和を65521で剰余しながらバイトごとに更新する
///   ]
///   引数: [
///     data: 圧縮前のバイト列
///   ]
///   戻り値: [Adler-32値]
/// }
fn adler32(data: &[u8]) -> u32 {
    let (mut low, mut high) = (1u32, 0u32);
    for byte in data {
        low = (low + u32::from(*byte)) % ADLER_MODULUS;
        high = (high + low) % ADLER_MODULUS;
    }
    (high << 16) | low
}

/// {
///   責務: [push_chunk: 長さ・種別・データ・CRCを持つPNGチャンクを追加する]
///   処理: [
///     1: データ長が31ビットに収まることを確認する
///     2: 長さ、種別、データ、CRCを順に書く
///   ]
///   引数: [
///     output: 追記先のバイト列
///     kind: 4文字のチャンク種別
///     data: チャンクのデータ
///   ]
///   戻り値: [成功時は単位値、長さが上限を超えれば確保エラー]
/// }
fn push_chunk(output: &mut Vec<u8>, kind: &[u8; 4], data: &[u8]) -> Result<(), RasterError> {
    let length = u32::try_from(data.len())
        .ok()
        .filter(|length| *length <= i32::MAX as u32)
        .ok_or(RasterError::AllocationFailed)?;
    output.extend_from_slice(&length.to_be_bytes());
    output.extend_from_slice(kind);
    output.extend_from_slice(data);
    output.extend_from_slice(&crc32(&[kind, data]).to_be_bytes());
    Ok(())
}

/// {
///   責務: [scanlines: ラスタをフィルタなしの走査線バイト列へ並べる]
///   処理: [
///     1: 必要な容量を先に確保する
///     2: 各行の先頭にフィルタ種別0を置き、画素のRGBAを順に並べる
///   ]
///   引数: [
///     raster: 書き出すラスタ
///   ]
///   戻り値: [走査線のバイト列または確保・座標エラー]
/// }
fn scanlines(raster: &Raster) -> Result<Vec<u8>, RasterError> {
    let resolution = raster.resolution();
    let row_bytes = resolution.width() as usize * 4 + 1;
    let mut data = Vec::new();
    data.try_reserve_exact(row_bytes * resolution.height() as usize)
        .map_err(|_| RasterError::AllocationFailed)?;
    for y in 0..resolution.height() {
        data.push(0);
        for x in 0..resolution.width() {
            data.extend_from_slice(&raster.sample(x, y)?);
        }
    }
    Ok(data)
}

/// {
///   責務: [stored_zlib: 圧縮なしのdeflateブロックでzlibストリームを作る]
///   処理: [
///     1: zlibヘッダを書く
///     2: 65535バイト以下のブロックに分け、最後のブロックに終端印を付ける
///     3: 末尾にAdler-32を付ける
///   ]
///   引数: [
///     data: 圧縮前のバイト列。空でないこと
///   ]
///   戻り値: [zlibストリームまたは確保エラー]
/// }
fn stored_zlib(data: &[u8]) -> Result<Vec<u8>, RasterError> {
    let blocks = data.len().div_ceil(MAX_STORED_BLOCK);
    let mut stream = Vec::new();
    stream
        .try_reserve_exact(data.len() + blocks * 5 + 6)
        .map_err(|_| RasterError::AllocationFailed)?;
    stream.extend_from_slice(&[0x78, 0x01]);
    for (index, block) in data.chunks(MAX_STORED_BLOCK).enumerate() {
        let is_last = index + 1 == blocks;
        let length = block.len() as u16;
        stream.push(u8::from(is_last));
        stream.extend_from_slice(&length.to_le_bytes());
        stream.extend_from_slice(&(!length).to_le_bytes());
        stream.extend_from_slice(block);
    }
    stream.extend_from_slice(&adler32(data).to_be_bytes());
    Ok(stream)
}

impl Raster {
    /// {
    ///   責務: [to_png: ラスタを透明度を保つ8bit RGBAのPNGへ書き出す]
    ///   処理: [
    ///     1: 署名とIHDRを書く
    ///     2: 走査線を圧縮なしのzlibにしてIDATへ書く
    ///     3: IENDで終える
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///   ]
    ///   戻り値: [PNGのバイト列、確保できなければエラー]
    /// }
    pub fn to_png(&self) -> Result<Vec<u8>, RasterError> {
        let resolution = self.resolution();
        let mut header = Vec::with_capacity(13);
        header.extend_from_slice(&resolution.width().to_be_bytes());
        header.extend_from_slice(&resolution.height().to_be_bytes());
        // 8bit深度、RGBA、標準の圧縮方式、標準のフィルタ、インターレースなし。
        header.extend_from_slice(&[8, COLOR_TYPE_RGBA, 0, 0, 0]);
        let image = stored_zlib(&scanlines(self)?)?;
        let mut output = Vec::new();
        output
            .try_reserve_exact(image.len() + 64)
            .map_err(|_| RasterError::AllocationFailed)?;
        output.extend_from_slice(&SIGNATURE);
        push_chunk(&mut output, b"IHDR", &header)?;
        push_chunk(&mut output, b"IDAT", &image)?;
        push_chunk(&mut output, b"IEND", &[])?;
        Ok(output)
    }
}
