//! Emits in-memory projects and expected observations for the cross-language gate.
use hyper_dot_core::canvas::Canvas;
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
///   責務: [case: 文書と複数解像度での期待観測値をまとめる]
///   処理: [
///     1: 複製Canvasの論理・保持・展開表示を記録する
///     2: JSON文書と必要な追加編集の期待色を付ける
///   ]
///   引数: [
///     name: 互換性ケースの識別名
///     canvas: 観測・直列化するキャンバス
///   ]
///   戻り値: [互換検証ケースのJSON値]
/// }
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

/// {
///   責務: [main: 書き出し・読み込み互換検証のケースを入出力する]
///   処理: [
///     1: 入力モードなら標準入力の文書を検証する
///     2: 書き出しモードなら代表的な保持状態を構成する
///     3: 観測結果を標準出力へJSONで出す
///   ]
///   引数: []
///   戻り値: [なし]
/// }
fn main() {
    if std::env::args().nth(1).as_deref() == Some("--import") {
        match import_cases() {
            Ok(cases) => println!("{cases}"),
            Err(error) => {
                eprintln!("{error}");
                std::process::exit(2);
            }
        }
        return;
    }
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

/// {
///   責務: [import_cases: 標準入力の文書をRustで復元して観測値を返す]
///   処理: [
///     1: 入力ケースのJSON配列を読む
///     2: 各文書を検証付きで復元する
///     3: 複数解像度の観測値をまとめる
///   ]
///   引数: []
///   戻り値: [観測ケース配列またはJSON・読み込みエラー]
/// }
fn import_cases() -> Result<Value, Box<dyn std::error::Error>> {
    use std::io::Read;
    let mut input = String::new();
    std::io::stdin().read_to_string(&mut input)?;
    let cases: Vec<Value> = serde_json::from_str(&input)?;
    let mut output = Vec::new();
    for entry in cases {
        let name = entry["name"].as_str().ok_or("missing case name")?;
        let canvas = Canvas::from_json(&entry["source"].to_string())?;
        output.push(case(name, canvas));
    }
    Ok(Value::Array(output))
}
