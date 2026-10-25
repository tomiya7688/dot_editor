//! Emits layered projects and expected observations for the cross-language gate.
//!
//! Without arguments the example prints Rust-made cases. With `--import` it
//! reads `[{"name", "source"}]` from stdin and reports what Rust loaded.
use std::io::Read;

use hyper_dot_core::layered_canvas::{LayeredCanvas, MoveDirection};
use hyper_dot_core::raster::Raster;
use hyper_dot_core::resolution::Resolution;
use hyper_dot_core::resolution_field::DetailPolicy;
use serde_json::{Value, json};

/// {
///   責務: [grid: 互換検証用の正の解像度を作る]
///   処理: [
///     1: 入力の縦横から解像度を構成する
///   ]
///   引数: [
///     width: 対象領域の幅
///     height: 対象領域の高さ
///   ]
///   戻り値: [検証用解像度]
/// }
fn grid(width: u32, height: u32) -> Resolution {
    Resolution::new(width, height).unwrap()
}

/// {
///   責務: [pixels: 比較用にラスタのRGBA行列を取り出す]
///   処理: [
///     1: 各行・各列の画素を順に読む
///   ]
///   引数: [
///     raster: 元となるRGBAラスタ
///   ]
///   戻り値: [RGBA行列]
/// }
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

/// {
///   責務: [hex: PNGのバイト列をJSONに載せられる16進文字列にする]
///   処理: [
///     1: 各バイトを2桁の小文字16進にして連結する
///   ]
///   引数: [
///     bytes: 変換するバイト列
///   ]
///   戻り値: [16進文字列]
/// }
fn hex(bytes: &[u8]) -> String {
    bytes.iter().map(|byte| format!("{byte:02x}")).collect()
}

/// {
///   責務: [observe: 作品の構成と合成結果をまとめる]
///   処理: [
///     1: 層の名前・表示状態・選択名を記録する
///     2: 自然な解像度の合成と、固定解像度の保持細部合成を記録する
///     3: 3種類のPNG（自然・保持細部16x12・9x9への拡大）と再保存したJSON値を添える
///   ]
///   引数: [
///     document: 観測するレイヤー付き作品
///   ]
///   戻り値: [観測結果のJSON値]
/// }
fn observe(document: &LayeredCanvas) -> Value {
    let names = document.layer_names();
    let visible: Vec<bool> = names
        .iter()
        .map(|name| document.is_layer_visible(Some(name)).unwrap())
        .collect();
    json!({
        "names": names,
        "visible": visible,
        "active_layer": document.active_layer(),
        "native": pixels(document.composite().unwrap()),
        "detail": pixels(document.render_at(grid(16, 12)).unwrap()),
        "png_native": hex(&document.composite().unwrap().to_png().unwrap()),
        "png_detail": hex(&document.render_at(grid(16, 12)).unwrap().to_png().unwrap()),
        "png_scaled": hex(&document.composite_scaled(grid(9, 9)).unwrap().to_png().unwrap()),
        "source": serde_json::from_str::<Value>(&document.to_json().unwrap()).unwrap(),
    })
}

/// {
///   責務: [stacked_translucent: 半透明の重なりと非表示層を持つ作品を作る]
///   処理: [
///     1: 背景と上層に不透明・半透明の色を塗る
///     2: 最上層を非表示にして背景を選択する
///   ]
///   引数: []
///   戻り値: [検証用作品]
/// }
fn stacked_translucent() -> LayeredCanvas {
    let mut document = LayeredCanvas::new(grid(4, 3)).unwrap();
    document
        .fill(0, 0, [10, 120, 200, 255], DetailPolicy::Preserve)
        .unwrap();
    document.add_layer("半透明").unwrap();
    document
        .paint(1, 1, [255, 0, 0, 128], DetailPolicy::Preserve)
        .unwrap();
    document
        .paint(2, 1, [0, 255, 0, 3], DetailPolicy::Preserve)
        .unwrap();
    document.add_layer("隠し").unwrap();
    document
        .paint(0, 0, [1, 2, 3, 255], DetailPolicy::Preserve)
        .unwrap();
    document.set_layer_visibility(false, None).unwrap();
    document.select_layer("背景").unwrap();
    document
}

/// {
///   責務: [refined_with_detail: 展開セルと保持細部を持つ作品を作る]
///   処理: [
///     1: 上層でセルを分割し子セルを塗る
///     2: 解像度を下げて保持細部を残し、層の順序と名前を変える
///   ]
///   引数: []
///   戻り値: [検証用作品]
/// }
fn refined_with_detail() -> LayeredCanvas {
    let mut document = LayeredCanvas::new(grid(4, 3)).unwrap();
    document
        .paint(2, 2, [40, 50, 60, 255], DetailPolicy::Preserve)
        .unwrap();
    document.add_layer("上").unwrap();
    document.split_cell(1, 1).unwrap();
    document
        .paint_child(1, 1, (1, 0), [5, 6, 7, 200], DetailPolicy::Preserve)
        .unwrap();
    document
        .paint(3, 0, [9, 99, 199, 90], DetailPolicy::Preserve)
        .unwrap();
    document
        .set_resolution(grid(2, 2), DetailPolicy::Preserve)
        .unwrap();
    document.move_layer(MoveDirection::Down, None).unwrap();
    document.rename_layer("手前だった層", None).unwrap();
    document
}

/// {
///   責務: [cases: Rustが作る互換検証ケースを列挙する]
///   処理: [
///     1: 各作品を観測してケース名を付ける
///   ]
///   引数: []
///   戻り値: [ケースのJSON配列]
/// }
fn cases() -> Value {
    let documents = [
        ("stacked_translucent", stacked_translucent()),
        ("refined_with_detail", refined_with_detail()),
    ];
    Value::Array(
        documents
            .iter()
            .map(|(name, document)| {
                let mut case = observe(document);
                case["name"] = json!(name);
                case
            })
            .collect(),
    )
}

/// {
///   責務: [import_cases: 標準入力のJSON文書をRustで読み込み結果を報告する]
///   処理: [
///     1: 各文書をLayeredCanvas::from_jsonで読み込む
///     2: 成功なら観測結果、失敗なら理由を記録する
///   ]
///   引数: [
///     input: ケース名とJSON値の配列
///   ]
///   戻り値: [読み込み結果のJSON配列]
/// }
fn import_cases(input: &Value) -> Value {
    Value::Array(
        input
            .as_array()
            .unwrap()
            .iter()
            .map(|entry| {
                let text = entry["source"].to_string();
                let mut report = match LayeredCanvas::from_json(&text) {
                    Ok(document) => observe(&document),
                    Err(error) => json!({"error": error.to_string()}),
                };
                report["name"] = entry["name"].clone();
                report
            })
            .collect(),
    )
}

/// {
///   責務: [main: 引数に応じてRust作成ケースまたは読み込み結果を標準出力へ書く]
///   処理: [
///     1: --importなら標準入力を読み、読み込み結果を出力する
///     2: それ以外はRustが作成したケースを出力する
///   ]
///   引数: []
///   戻り値: [なし]
/// }
fn main() {
    if std::env::args().any(|argument| argument == "--import") {
        let mut text = String::new();
        std::io::stdin().read_to_string(&mut text).unwrap();
        let input: Value = serde_json::from_str(&text).unwrap();
        println!("{}", import_cases(&input));
    } else {
        println!("{}", cases());
    }
}
