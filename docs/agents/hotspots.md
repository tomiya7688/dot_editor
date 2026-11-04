# よく触る場所の案内

行番号は古くなるので書きません。場所は `python scripts/hotspots.py <ファイル> [--grep 語]` で出します（全文を読まない）。1つの作業を始める前に `python scripts/task_brief.py <Issue番号>` で設計書と必読ルールを出します。

## GUI（`src/dot_editor.py`）

| 触りたいこと | 探す名前 |
| --- | --- |
| 起動時の部品・入力の登録 | `__init__`、`bind_global_shortcuts`、`bind_focus_region_navigation` |
| メニュー | `build_menu_bar`、`populate_*_menu`、`update_menu_state`、`menu_spec` |
| 左のツール列・フォーカス | `build_sidebar`、`focus_*`、`register_sidebar_focus_target` |
| 描画・塗り・消し・スポイト | `paint_pixel`、`activate_*`、`_child_coordinate` |
| 元に戻す・やり直し | `push_history`、`undo`、`redo`、`make_snapshot`、`restore_snapshot` |
| レイヤー | `add_layer`、`remove_layer`、`move_layer`、`select_layer`、`refresh_layer_list` |
| 拡大・表示・解像度 | `set_zoom`、`update_canvas_size`、`resize_logical_canvas`、`change_canvas_size` |
| 保存・読み込み・書き出し | `save_project`、`load_project`、`save_image` |

GUIの部品はテストで偽物に置き換えているため、起動しなくても確認できます（GUIは勝手に起動しません）。

## Rust

| 触りたいこと | 場所 |
| --- | --- |
| 解像度・保持細部・分割 | `hyper-dot-core/src/canvas.rs`、`split_cell.rs`、`resolution*.rs` |
| レイヤー・合成 | `layered_canvas*.rs`、`alpha_composite.rs` |
| 保存形式 | `project_json*.rs`、`layered_project_json.rs`、`strict_json.rs` |
| PNG書き出し | `png_export.rs` |
| コマンドの追加 | `hyper-dot-cli/src/command_table.rs`、`command_spec.rs`、`*_commands.rs`、`help_text.rs` |
| 出力・エラー | `report.rs`、`cli_error.rs`、`runner.rs` |
| 保存の安全性 | `project_file.rs` |

テストは `hyper-dot-core/tests/`（機能ごとに1ファイル）と `hyper-dot-cli/tests/cli_contract.rs`。Python互換は `scripts/test_rust_*_compat.py`、実行ファイル全体は `scripts/e2e_rust_cli.py`。

## 繰り返す作業は道具を使う

| 作業 | 道具 |
| --- | --- |
| Issueの設計書と必読ルールを知る | `python scripts/task_brief.py N` |
| ファイル内の場所を知る | `python scripts/hotspots.py FILE` |
| PR本文を作る | `python scripts/pr_body.py --issue ... --out FILE` |
| 規則の検査 | `python scripts/check_agent_policy.py` |

同じ手作業を3回行ったら、道具かテンプレートにして、この表に足します。
