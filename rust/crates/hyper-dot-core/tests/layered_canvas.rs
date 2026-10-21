use hyper_dot_core::canvas::CanvasError;
use hyper_dot_core::layer_error::LayerError;
use hyper_dot_core::layered_canvas::{LayeredCanvas, MAX_LAYERS, MoveDirection};
use hyper_dot_core::raster::{Color, RasterError};
use hyper_dot_core::resolution::Resolution;
use hyper_dot_core::resolution_field::DetailPolicy;

const RED: Color = [255, 0, 0, 255];
const BLUE: Color = [0, 0, 255, 255];

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
///   責務: [three_layers: 背景・A・Bの3層を持つ作品を作る]
///   処理: [
///     1: 背景だけの作品へ2層を追加し、最上層を選択状態にする
///   ]
///   引数: []
///   戻り値: [3層の作品]
/// }
fn three_layers() -> LayeredCanvas {
    let mut document = LayeredCanvas::new(grid(2, 2)).unwrap();
    document.add_layer("A").unwrap();
    document.add_layer("B").unwrap();
    document
}

/// {
///   責務: [new_document_has_a_selected_visible_background: 新しい作品が背景だけを選択して持つことを回帰検証する]
///   処理: [
///     1: 作品を作り、層の一覧・選択・表示・履歴を比較する
///   ]
///   引数: []
///   戻り値: [なし、不一致ならテストを失敗させる]
/// }
#[test]
fn new_document_has_a_selected_visible_background() {
    let document = LayeredCanvas::new(grid(3, 2)).unwrap();
    assert_eq!(document.layer_names(), vec!["背景"]);
    assert_eq!(document.active_layer(), "背景");
    assert_eq!(document.is_layer_visible(None), Ok(true));
    assert_eq!(document.resolution(), grid(3, 2));
    assert!(!document.can_undo() && !document.can_redo());
}

/// {
///   責務: [layer_names_are_trimmed_and_validated: レイヤー名の整形と拒否条件を回帰検証する]
///   処理: [
///     1: 空名・重複・上限超過・存在しない名前の操作を実行する
///     2: エラー種別と、失敗後に作品が変わらないことを比較する
///   ]
///   引数: []
///   戻り値: [なし、不一致ならテストを失敗させる]
/// }
#[test]
fn layer_names_are_trimmed_and_validated() {
    let mut document = LayeredCanvas::new(grid(1, 1)).unwrap();
    assert_eq!(document.add_layer("  線画  "), Ok(()));
    assert_eq!(document.layer_names(), vec!["背景", "線画"]);
    let before = document.clone();
    assert_eq!(document.add_layer("   "), Err(LayerError::EmptyName));
    assert_eq!(
        document.add_layer("線画"),
        Err(LayerError::DuplicateName("線画".to_owned()))
    );
    assert_eq!(
        document.select_layer("無い"),
        Err(LayerError::NoSuchLayer("無い".to_owned()))
    );
    assert_eq!(
        document.rename_layer("背景", Some("線画")),
        Err(LayerError::DuplicateName("背景".to_owned()))
    );
    assert_eq!(document, before);
    for index in 0..MAX_LAYERS - 2 {
        document.add_layer(&format!("層{index}")).unwrap();
    }
    assert_eq!(document.layer_names().len(), MAX_LAYERS);
    assert_eq!(document.add_layer("あふれ"), Err(LayerError::TooManyLayers));
}

/// {
///   責務: [removing_layers_keeps_the_selection_valid: 削除後も選択が有効な層を指すことと最後の1層を削除できないことを回帰検証する]
///   処理: [
///     1: 選択中・下位・上位の層を削除して選択名を比較する
///     2: 1層になった作品の削除を拒否する
///   ]
///   引数: []
///   戻り値: [なし、不一致ならテストを失敗させる]
/// }
#[test]
fn removing_layers_keeps_the_selection_valid() {
    let mut document = three_layers();
    assert_eq!(document.active_layer(), "B");
    assert_eq!(document.remove_layer(Some("背景")), Ok(()));
    assert_eq!(document.active_layer(), "B");
    assert_eq!(document.layer_names(), vec!["A", "B"]);
    assert_eq!(document.remove_layer(None), Ok(()));
    assert_eq!(document.active_layer(), "A");
    assert_eq!(document.remove_layer(None), Err(LayerError::LastLayer));
    assert_eq!(document.layer_names(), vec!["A"]);
    assert_eq!(document.undo(), Ok(true));
    assert_eq!(document.layer_names(), vec!["A", "B"]);
    assert_eq!(document.active_layer(), "B");
}

/// {
///   責務: [rename_and_move_keep_the_selected_layer: 名前変更と移動の後も選択が同じ層を指すことを回帰検証する]
///   処理: [
///     1: 選択層を移動・改名し、選択名と合成順を比較する
///     2: 端での移動と同名への改名が履歴を作らないことを確認する
///   ]
///   引数: []
///   戻り値: [なし、不一致ならテストを失敗させる]
/// }
#[test]
fn rename_and_move_keep_the_selected_layer() {
    let mut document = three_layers();
    document.select_layer("A").unwrap();
    assert_eq!(document.move_layer(MoveDirection::Up, None), Ok(true));
    assert_eq!(document.layer_names(), vec!["背景", "B", "A"]);
    assert_eq!(document.active_layer(), "A");
    assert_eq!(document.move_layer(MoveDirection::Up, None), Ok(false));
    assert_eq!(
        document.move_layer(MoveDirection::Down, Some("B")),
        Ok(true)
    );
    assert_eq!(document.layer_names(), vec!["B", "背景", "A"]);
    assert_eq!(document.active_layer(), "A");
    assert_eq!(document.rename_layer("線画", None), Ok(true));
    assert_eq!(document.rename_layer("線画", None), Ok(false));
    assert_eq!(document.layer_names(), vec!["B", "背景", "線画"]);
    assert_eq!(document.active_layer(), "線画");
    // 追加2回に加え、移動・移動・改名の3回だけが履歴に残る。
    for _ in 0..5 {
        assert_eq!(document.undo(), Ok(true));
    }
    assert_eq!(document.undo(), Ok(false));
    assert_eq!(document.layer_names(), vec!["背景"]);
}

/// {
///   責務: [edits_affect_only_the_selected_layer: 描画が選択中の層だけを変更することを回帰検証する]
///   処理: [
///     1: 2層のうち上層を選択して描画し、各層の画素を比較する
///   ]
///   引数: []
///   戻り値: [なし、不一致ならテストを失敗させる]
/// }
#[test]
fn edits_affect_only_the_selected_layer() {
    let mut document = LayeredCanvas::new(grid(2, 2)).unwrap();
    document.add_layer("上").unwrap();
    assert_eq!(document.paint(1, 0, RED, DetailPolicy::Preserve), Ok(true));
    assert_eq!(document.paint(1, 0, RED, DetailPolicy::Preserve), Ok(false));
    assert_eq!(document.sample(1, 0), Ok(RED));
    assert_eq!(document.layer("背景").unwrap().sample(1, 0), Ok([0; 4]));
    document.select_layer("背景").unwrap();
    assert_eq!(document.sample(1, 0), Ok([0; 4]));
}

/// {
///   責務: [unchanged_operations_keep_the_redo_history: 変更のない操作がRedoを消さないことを回帰検証する]
///   処理: [
///     1: 描画をUndoした後に、変更なしの描画・選択・表示設定を実行する
///     2: Redoが残ることと、実際の編集でRedoが消えることを比較する
///   ]
///   引数: []
///   戻り値: [なし、不一致ならテストを失敗させる]
/// }
#[test]
fn unchanged_operations_keep_the_redo_history() {
    let mut document = LayeredCanvas::new(grid(2, 2)).unwrap();
    document.paint(0, 0, RED, DetailPolicy::Preserve).unwrap();
    document.undo().unwrap();
    assert_eq!(
        document.paint(0, 0, [0; 4], DetailPolicy::Preserve),
        Ok(false)
    );
    assert_eq!(document.set_layer_visibility(true, None), Ok(false));
    document.select_layer("背景").unwrap();
    assert!(document.can_redo());
    document.paint(1, 1, BLUE, DetailPolicy::Preserve).unwrap();
    assert!(!document.can_redo());
}

/// {
///   責務: [region_split_and_fill_are_single_document_undo_steps: 領域分割と塗りつぶしがそれぞれ作品の1回のUndoになることを回帰検証する]
///   処理: [
///     1: 上層で領域分割と塗りつぶしを実行する
///     2: Undoを1回ずつ行い、各層の状態を比較する
///   ]
///   引数: []
///   戻り値: [なし、不一致ならテストを失敗させる]
/// }
#[test]
fn region_split_and_fill_are_single_document_undo_steps() {
    let mut document = LayeredCanvas::new(grid(4, 4)).unwrap();
    document.add_layer("上").unwrap();
    assert_eq!(document.split_region(0, 0, 2, 2), Ok(4));
    assert_eq!(document.fill(0, 0, RED, DetailPolicy::Preserve), Ok(16));
    assert_eq!(document.native_resolution(), Ok(grid(8, 8)));
    assert_eq!(document.undo(), Ok(true));
    assert_eq!(document.sample(3, 3), Ok([0; 4]));
    assert_eq!(document.native_resolution(), Ok(grid(8, 8)));
    assert_eq!(document.undo(), Ok(true));
    assert_eq!(document.native_resolution(), Ok(grid(4, 4)));
    assert_eq!(document.active_layer(), "上");
    // 残る履歴は層の追加だけで、分割と塗りつぶしは別の2段階だった。
    assert_eq!(document.undo(), Ok(true));
    assert_eq!(document.layer_names(), vec!["背景"]);
    assert!(!document.can_undo());
    for _ in 0..3 {
        assert_eq!(document.redo(), Ok(true));
    }
    assert_eq!(document.native_resolution(), Ok(grid(8, 8)));
    assert_eq!(document.sample(3, 3), Ok(RED));
    assert_eq!(document.redo(), Ok(false));
}

/// {
///   責務: [resolution_change_applies_to_all_layers_in_one_step: 解像度変更が全層に1回の履歴として適用されることを回帰検証する]
///   処理: [
///     1: 2層へ描画して解像度を変更し、全層の解像度を比較する
///     2: Undo/Redoで全層が一緒に戻ることを比較する
///   ]
///   引数: []
///   戻り値: [なし、不一致ならテストを失敗させる]
/// }
#[test]
fn resolution_change_applies_to_all_layers_in_one_step() {
    let mut document = LayeredCanvas::new(grid(2, 2)).unwrap();
    document.paint(0, 0, RED, DetailPolicy::Preserve).unwrap();
    document.add_layer("上").unwrap();
    document.paint(1, 1, BLUE, DetailPolicy::Preserve).unwrap();
    assert_eq!(
        document.set_resolution(grid(2, 2), DetailPolicy::Preserve),
        Ok(false)
    );
    assert_eq!(
        document.set_resolution(grid(4, 4), DetailPolicy::Preserve),
        Ok(true)
    );
    assert_eq!(document.layer("背景").unwrap().resolution(), grid(4, 4));
    assert_eq!(document.layer("上").unwrap().resolution(), grid(4, 4));
    assert_eq!(document.undo(), Ok(true));
    assert_eq!(document.layer("背景").unwrap().resolution(), grid(2, 2));
    assert_eq!(document.layer("上").unwrap().resolution(), grid(2, 2));
    assert_eq!(document.redo(), Ok(true));
    assert_eq!(document.resolution(), grid(4, 4));
}

/// {
///   責務: [failed_resolution_change_leaves_every_layer_and_history_intact: 描画予算を超える解像度変更が全層と履歴を変えないことを回帰検証する]
///   処理: [
///     1: 2層の作品で、画素数上限を超える解像度への破棄変更を試みる
///     2: エラー種別と、作品全体が変更前と等しいことを比較する
///   ]
///   引数: []
///   戻り値: [なし、不一致ならテストを失敗させる]
/// }
#[test]
fn failed_resolution_change_leaves_every_layer_and_history_intact() {
    let mut document = LayeredCanvas::new(grid(2, 2)).unwrap();
    document.paint(0, 0, RED, DetailPolicy::Preserve).unwrap();
    document.add_layer("上").unwrap();
    let before = document.clone();
    let result = document.set_resolution(grid(4096, 4096), DetailPolicy::Discard);
    assert_eq!(
        result,
        Err(LayerError::Canvas(CanvasError::Raster(
            RasterError::PixelBudgetExceeded
        )))
    );
    assert_eq!(document, before);
}

/// {
///   責務: [document_history_keeps_only_the_latest_fifty_steps: 作品履歴が最新50件に制限されることを回帰検証する]
///   処理: [
///     1: 52回の可視状態切り替えを行い、Undoできる回数を数える
///   ]
///   引数: []
///   戻り値: [なし、不一致ならテストを失敗させる]
/// }
#[test]
fn document_history_keeps_only_the_latest_fifty_steps() {
    let mut document = LayeredCanvas::new(grid(1, 1)).unwrap();
    for step in 0..52 {
        assert_eq!(document.set_layer_visibility(step % 2 == 1, None), Ok(true));
    }
    let mut undone = 0;
    while document.undo().unwrap() {
        undone += 1;
    }
    assert_eq!(undone, 50);
}
