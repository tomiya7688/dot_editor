use hyper_dot_core::canvas::Canvas;
use hyper_dot_core::layered_canvas::LayeredCanvas;
use hyper_dot_core::resolution::Resolution;
use hyper_dot_core::resolution_field::DetailPolicy;
use serde_json::{Value, json};

/// 文書の一部を壊すための変更処理。
type Change = Box<dyn Fn(&mut Value)>;

/// {
///   責務: [fixture: Python参照版で保存したレイヤー付き見本文書を読む]
///   処理: [
///     1: 共有フィクスチャのJSON文字列を返す
///   ]
///   引数: []
///   戻り値: [見本文書のJSON文字列]
/// }
fn fixture() -> &'static str {
    include_str!("../../../../tests/fixtures/project_json/layered_v2.json")
}

/// {
///   責務: [fixture_value: 見本文書をJSON値として読み、テストで一部を壊せるようにする]
///   処理: [
///     1: 見本文書を解析する
///   ]
///   引数: []
///   戻り値: [JSON値]
/// }
fn fixture_value() -> Value {
    serde_json::from_str(fixture()).unwrap()
}

/// {
///   責務: [python_document_loads_with_structure_and_composite: Python版の文書の構成と合成結果がRustで再現されることを回帰検証する]
///   処理: [
///     1: 見本文書を読み込み、名前・表示・選択・履歴を比較する
///     2: 展開セルを含む合成の代表画素をPython版の値と比較する
///   ]
///   引数: []
///   戻り値: [なし、不一致ならテストを失敗させる]
/// }
#[test]
fn python_document_loads_with_structure_and_composite() {
    let document = LayeredCanvas::from_json(fixture()).unwrap();
    assert_eq!(document.layer_names(), vec!["背景", "半透明", "隠し"]);
    assert_eq!(document.active_layer(), "半透明");
    assert_eq!(document.is_layer_visible(Some("隠し")), Ok(false));
    assert_eq!(document.is_layer_visible(Some("半透明")), Ok(true));
    assert!(!document.can_undo() && !document.can_redo());
    let flattened = document.composite().unwrap();
    assert_eq!(flattened.resolution(), Resolution::new(6, 4).unwrap());
    // 値はPython版 LayeredPixelCanvas.composite() の出力。
    assert_eq!(flattened.sample(0, 0), Ok([10, 120, 200, 255]));
    assert_eq!(flattened.sample(2, 1), Ok([133, 60, 100, 255]));
    assert_eq!(flattened.sample(5, 2), Ok([6, 31, 49, 255]));
}

/// {
///   責務: [save_and_load_keeps_every_layer_detail: 保存と再読込で全層の細部と構成が変わらないことを回帰検証する]
///   処理: [
///     1: 見本文書を編集して保持細部を作り、JSONへ保存して読み戻す
///     2: 構成・各層の単独JSON・合成を元の作品と比較する
///   ]
///   引数: []
///   戻り値: [なし、不一致ならテストを失敗させる]
/// }
#[test]
fn save_and_load_keeps_every_layer_detail() {
    let mut document = LayeredCanvas::from_json(fixture()).unwrap();
    document
        .set_resolution(Resolution::new(2, 2).unwrap(), DetailPolicy::Preserve)
        .unwrap();
    document.select_layer("背景").unwrap();
    let restored = LayeredCanvas::from_json(&document.to_json().unwrap()).unwrap();
    assert_eq!(restored.layer_names(), document.layer_names());
    assert_eq!(restored.active_layer(), "背景");
    assert_eq!(restored.is_layer_visible(Some("隠し")), Ok(false));
    for name in document.layer_names() {
        assert_eq!(
            restored.layer(name).unwrap().to_json().unwrap(),
            document.layer(name).unwrap().to_json().unwrap(),
            "{name}"
        );
    }
    assert_eq!(restored.composite().unwrap(), document.composite().unwrap());
    let detail = Resolution::new(6, 4).unwrap();
    assert_eq!(
        restored.render_at(detail).unwrap(),
        document.render_at(detail).unwrap()
    );
    assert!(!restored.can_undo());
}

/// {
///   責務: [malformed_layered_documents_are_rejected: 構成が不正なレイヤー付き文書が全て拒否されることを回帰検証する]
///   処理: [
///     1: 見本文書を一つずつ壊した文書を用意する
///     2: すべて読み込みに失敗することを確認する
///   ]
///   引数: []
///   戻り値: [なし、受理した文書があればテストを失敗させる]
/// }
#[test]
fn malformed_layered_documents_are_rejected() {
    let broken: Vec<(&str, Change)> = vec![
        ("version", Box::new(|s| s["version"] = json!(3))),
        ("no layers", Box::new(|s| s["layers"] = json!([]))),
        (
            "duplicate",
            Box::new(|s| s["layers"][1]["name"] = json!("背景")),
        ),
        ("blank", Box::new(|s| s["layers"][1]["name"] = json!("  "))),
        (
            "visible",
            Box::new(|s| s["layers"][1]["visible"] = json!("yes")),
        ),
        ("active", Box::new(|s| s["active_layer"] = json!("無い"))),
        ("resolution", Box::new(|s| s["resolution"] = json!([5, 2]))),
        ("canvas size", Box::new(|s| s["canvas_size"] = json!(9))),
        (
            "no source",
            Box::new(|s| {
                s["layers"][1].as_object_mut().unwrap().remove("source");
            }),
        ),
        (
            "layer pixels",
            Box::new(|s| s["layers"][0]["source"]["pixels"] = json!([])),
        ),
    ];
    for (name, change) in broken {
        let mut source = fixture_value();
        change(&mut source);
        assert!(
            LayeredCanvas::from_json(&source.to_string()).is_err(),
            "{name}"
        );
    }
    let mut mismatched = fixture_value();
    mismatched["layers"][1]["source"] =
        json!({"version": 1, "canvas_size": 2, "pixels": [[null, null], [null, null]]});
    assert!(LayeredCanvas::from_json(&mismatched.to_string()).is_err());
    assert!(LayeredCanvas::from_json("[]").is_err());
}

/// {
///   責務: [legacy_layered_version_one_is_migrated_on_load: 旧形式のレイヤー付き文書が読み込めversion 2で保存されることを回帰検証する]
///   処理: [
///     1: versionを持たない文書を読み込み、既定値を比較する
///     2: 保存した文書がversion 2になることを確認する
///   ]
///   引数: []
///   戻り値: [なし、不一致ならテストを失敗させる]
/// }
#[test]
fn legacy_layered_version_one_is_migrated_on_load() {
    let legacy = json!({"layers": [
        {"name": "下", "source": {"canvas_size": 2, "pixels": [["#102030", null], [null, "#FF000080"]]}},
        {"name": "上", "visible": false, "source": {"canvas_size": 2, "pixels": [[null, null], ["#00FF00", null]]}},
    ]});
    let document = LayeredCanvas::from_json(&legacy.to_string()).unwrap();
    assert_eq!(document.layer_names(), vec!["下", "上"]);
    assert_eq!(document.active_layer(), "下");
    assert_eq!(document.is_layer_visible(Some("上")), Ok(false));
    assert_eq!(document.sample(1, 1), Ok([255, 0, 0, 128]));
    let saved: Value = serde_json::from_str(&document.to_json().unwrap()).unwrap();
    assert_eq!(saved["version"], 2);
    assert_eq!(saved["resolution"], json!([2, 2]));
}

/// {
///   責務: [flat_and_layered_loaders_do_not_accept_each_others_documents: 単一Canvas用と層付き用の読み込み口が互いの文書を受理しないことを回帰検証する]
///   処理: [
///     1: 層付き文書を単一Canvasの読み込みへ渡す
///     2: 単一Canvasの文書を層付きの読み込みへ渡す
///   ]
///   引数: []
///   戻り値: [なし、受理した場合はテストを失敗させる]
/// }
#[test]
fn flat_and_layered_loaders_do_not_accept_each_others_documents() {
    assert!(Canvas::from_json(fixture()).is_err());
    let flat = Canvas::new(Resolution::new(2, 2).unwrap())
        .unwrap()
        .to_json()
        .unwrap();
    assert!(LayeredCanvas::from_json(&flat).is_err());
}
