//! Human-facing (Japanese) documentation attached to each command id, kept next to the command table.

/// {
///   責務: [CommandDoc: 1つのコマンドに付ける日本語の説明と使用例を保持する]
///   フィールド: [
///     id: コマンドの正規ID（語をピリオドで連結したもの）
///     summary_ja: 利用者向けの短い説明
///     example: 使用例の引数（プログラム名と--json -p art.jsonを除いた語）
///     example_ja: 使用例の説明
///   ]
/// }
pub struct CommandDoc {
    pub id: &'static str,
    pub summary_ja: &'static str,
    pub example: &'static [&'static str],
    pub example_ja: &'static str,
}

/// すべてのコマンドの日本語説明。コマンドとの過不足はテストで検査する。
pub static DOCS: [CommandDoc; 22] = [
    CommandDoc {
        id: "project.new",
        summary_ja: "新しい空のプロジェクトを作る。既存のファイルは--forceなしでは置き換えない",
        example: &["project", "new", "--size", "16"],
        example_ja: "16x16の新しいプロジェクトを作る",
    },
    CommandDoc {
        id: "project.info",
        summary_ja: "プロジェクトの概要と現在のrevisionを見る",
        example: &["project", "info"],
        example_ja: "プロジェクトの概要を見る",
    },
    CommandDoc {
        id: "project.validate",
        summary_ja: "プロジェクトが正しく読めて矛盾がないか確かめる",
        example: &["project", "validate"],
        example_ja: "ファイルが壊れていないか確かめる",
    },
    CommandDoc {
        id: "canvas.info",
        summary_ja: "解像度とレイヤーの数を見る",
        example: &["canvas", "info"],
        example_ja: "解像度を確かめる",
    },
    CommandDoc {
        id: "canvas.resolution.set",
        summary_ja: "すべてのレイヤーの論理解像度を変える。細部は既定で保持される",
        example: &["canvas", "resolution", "set", "32", "32"],
        example_ja: "解像度を32x32に変える",
    },
    CommandDoc {
        id: "pixel.paint",
        summary_ja: "選択中のレイヤーのセルを塗る",
        example: &["pixel", "paint", "3", "4", "#FF8800"],
        example_ja: "セルを橙色に塗る",
    },
    CommandDoc {
        id: "pixel.erase",
        summary_ja: "選択中のレイヤーのセルを透明にする",
        example: &["pixel", "erase", "3", "4"],
        example_ja: "セルを透明にする",
    },
    CommandDoc {
        id: "pixel.fill",
        summary_ja: "同じ色でつながった範囲を塗りつぶす",
        example: &["pixel", "fill", "0", "0", "#00AAFF"],
        example_ja: "つながった範囲を水色で塗りつぶす",
    },
    CommandDoc {
        id: "pixel.sample",
        summary_ja: "選択中のレイヤーのセルの色を読む",
        example: &["pixel", "sample", "3", "4"],
        example_ja: "セルの色を読む",
    },
    CommandDoc {
        id: "detail.split",
        summary_ja: "セルを4つの子セルに分割する",
        example: &["detail", "split", "3", "4"],
        example_ja: "セルを4分割する",
    },
    CommandDoc {
        id: "detail.split-region",
        summary_ja: "長方形の範囲のセルを1回の操作でまとめて分割する",
        example: &["detail", "split-region", "0", "0", "4", "4"],
        example_ja: "左上4x4のセルをまとめて分割する",
    },
    CommandDoc {
        id: "detail.discard",
        summary_ja: "見た目の色を保ったまま、保持している細部を捨てる",
        example: &["detail", "discard", "3", "4"],
        example_ja: "セルの細部を捨てる",
    },
    CommandDoc {
        id: "detail.info",
        summary_ja: "セルが分割済みか、細部を持つかを調べる",
        example: &["detail", "info", "3", "4"],
        example_ja: "セルの分割状態を調べる",
    },
    CommandDoc {
        id: "layer.add",
        summary_ja: "最上層に空のレイヤーを足して選ぶ",
        example: &["layer", "add", "shadow"],
        example_ja: "shadowという名前の層を足す",
    },
    CommandDoc {
        id: "layer.remove",
        summary_ja: "レイヤーを消す。最後の1枚は消せない",
        example: &["layer", "remove", "--layer", "shadow"],
        example_ja: "shadow層を消す",
    },
    CommandDoc {
        id: "layer.select",
        summary_ja: "編集する対象のレイヤーを選ぶ",
        example: &["layer", "select", "shadow"],
        example_ja: "shadow層を選ぶ",
    },
    CommandDoc {
        id: "layer.rename",
        summary_ja: "レイヤーの名前を変える",
        example: &["layer", "rename", "light", "--layer", "shadow"],
        example_ja: "shadow層をlightに改名する",
    },
    CommandDoc {
        id: "layer.move",
        summary_ja: "レイヤーの重なり順を1つ上か下に動かす",
        example: &["layer", "move", "up"],
        example_ja: "選択中の層を1つ上へ動かす",
    },
    CommandDoc {
        id: "layer.visibility",
        summary_ja: "レイヤーを表示(on)または非表示(off)にする",
        example: &["layer", "visibility", "off"],
        example_ja: "選択中の層を隠す",
    },
    CommandDoc {
        id: "layer.list",
        summary_ja: "レイヤーを下の層から順に一覧する",
        example: &["layer", "list"],
        example_ja: "層の一覧を見る",
    },
    CommandDoc {
        id: "export.render",
        summary_ja: "見えているレイヤーを重ねてPNGに書き出す",
        example: &["export", "render", "-o", "art.png", "--size", "64"],
        example_ja: "64x64のPNGに書き出す",
    },
    CommandDoc {
        id: "status",
        summary_ja: "解像度・選択中の層・層の一覧とrevisionをまとめて見る",
        example: &["status"],
        example_ja: "状態をまとめて見る",
    },
];

/// {
///   責務: [positional_ja: 位置引数の種類と日本語の説明を返す]
///   処理: [
///     1: 引数名ごとに、型の種類と説明を対応づける
///   ]
///   引数: [
///     name: 位置引数の名前
///   ]
///   戻り値: [(種類, 説明)。未登録の名前はNone]
/// }
pub fn positional_ja(name: &str) -> Option<(&'static str, &'static str)> {
    Some(match name {
        "x" => ("integer", "左から数えた列（0始まり）"),
        "y" => ("integer", "上から数えた行（0始まり）"),
        "width" => ("integer", "横のセル数"),
        "height" => ("integer", "縦のセル数"),
        "color" => ("color", "色（#RRGGBB または #RRGGBBAA）"),
        "name" => ("string", "レイヤーの名前"),
        "new_name" => ("string", "新しいレイヤー名"),
        "direction" => ("choice", "動かす向き（up か down）"),
        "state" => ("choice", "表示（on）か非表示（off）"),
        _ => return None,
    })
}

/// {
///   責務: [positional_choices: 選択肢のある位置引数の候補を返す]
///   処理: [
///     1: 引数名ごとに候補を対応づける
///   ]
///   引数: [
///     name: 位置引数の名前
///   ]
///   戻り値: [候補の並び。選択肢のない名前は空]
/// }
pub fn positional_choices(name: &str) -> &'static [&'static str] {
    match name {
        "direction" => &["up", "down"],
        "state" => &["on", "off"],
        _ => &[],
    }
}

/// {
///   責務: [option_ja: コマンド固有オプションの種類と日本語の説明を返す]
///   処理: [
///     1: オプション名ごとに、値の種類と説明を対応づける
///   ]
///   引数: [
///     name: `--`付きのオプション名
///   ]
///   戻り値: [(種類, 説明)。未登録の名前はNone]
/// }
pub fn option_ja(name: &str) -> Option<(&'static str, &'static str)> {
    Some(match name {
        "--discard-detail" => ("boolean", "保持している細部を捨てる（既定は保持）"),
        "--child" => (
            "integer",
            "分割済みセルの子セル（CX CY、各0か1）を対象にする",
        ),
        "--layer" => ("string", "対象のレイヤー名（既定は選択中の層）"),
        "--force" => ("boolean", "既存のプロジェクトファイルを置き換える"),
        "--size" => ("integer", "1辺のセル数（正方形）"),
        "--resolution" => ("integer", "横と縦のセル数（W H）"),
        "--output" => ("path", "書き出すPNGファイル（必須）"),
        _ => return None,
    })
}
