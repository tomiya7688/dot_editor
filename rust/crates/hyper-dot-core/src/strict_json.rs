//! JSON value visitor rejecting duplicate keys, including in unknown fields.
use serde::de::{self, Deserialize, DeserializeSeed, Deserializer, MapAccess, SeqAccess, Visitor};
use serde_json::{Map, Value};
use std::fmt;

/// {
///   責務: [StrictJson: 重複キー・過剰な深さを拒否してJSON値を組み立てる]
///   フィールド: [
///     0: 組み立てたJSON値
///     1: 現在のコンテナ深さ、ルートは1
///   ]
/// }
pub(crate) struct StrictJson(pub(crate) Value, pub(crate) usize);

impl<'de> Deserialize<'de> for StrictJson {
    /// {
    ///   責務: [deserialize: 深さと重複検査を伴うJSON値の読み込みを開始する]
    ///   処理: [
    ///     1: 深さを準備してJSON型に応じた訪問処理へ委譲する
    ///   ]
    ///   引数: [
    ///     deserializer: JSON値を読み出すデシリアライザ
    ///   ]
    ///   戻り値: [厳密に検証したJSON値または構文・深さエラー]
    /// }
    fn deserialize<D: Deserializer<'de>>(deserializer: D) -> Result<Self, D::Error> {
        deserializer.deserialize_any(StrictJson(Value::Null, 1))
    }
}

impl<'de> DeserializeSeed<'de> for StrictJson {
    type Value = Self;
    /// {
    ///   責務: [deserialize: 深さと重複検査を伴うJSON値の読み込みを開始する]
    ///   処理: [
    ///     1: 深さを準備してJSON型に応じた訪問処理へ委譲する
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///     deserializer: JSON値を読み出すデシリアライザ
    ///   ]
    ///   戻り値: [厳密に検証したJSON値または構文・深さエラー]
    /// }
    fn deserialize<D: Deserializer<'de>>(self, deserializer: D) -> Result<Self, D::Error> {
        deserializer.deserialize_any(self)
    }
}

impl<'de> Visitor<'de> for StrictJson {
    type Value = Self;
    /// {
    ///   責務: [expecting: JSON訪問処理が受け付ける入力を説明する]
    ///   処理: [
    ///     1: 重複のないJSON値であることを整形先へ書く
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///     formatter: 診断文の出力先
    ///   ]
    ///   戻り値: [整形結果]
    /// }
    fn expecting(&self, formatter: &mut fmt::Formatter) -> fmt::Result {
        formatter.write_str("a JSON value with unique object keys")
    }
    /// {
    ///   責務: [visit_bool: 真偽値をJSON値として受け取る]
    ///   処理: [
    ///     1: 真偽値と現在の深さを格納する
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///     value: 変換・検査するJSON値
    ///   ]
    ///   戻り値: [JSON真偽値]
    /// }
    fn visit_bool<E: de::Error>(self, value: bool) -> Result<Self, E> {
        Ok(Self(Value::Bool(value), self.1))
    }
    /// {
    ///   責務: [visit_i64: 符号付き整数をJSON値として受け取る]
    ///   処理: [
    ///     1: 整数と現在の深さを格納する
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///     value: 変換・検査するJSON値
    ///   ]
    ///   戻り値: [JSON数値]
    /// }
    fn visit_i64<E: de::Error>(self, value: i64) -> Result<Self, E> {
        Ok(Self(value.into(), self.1))
    }
    /// {
    ///   責務: [visit_u64: 符号なし整数をJSON値として受け取る]
    ///   処理: [
    ///     1: 整数と現在の深さを格納する
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///     value: 変換・検査するJSON値
    ///   ]
    ///   戻り値: [JSON数値]
    /// }
    fn visit_u64<E: de::Error>(self, value: u64) -> Result<Self, E> {
        Ok(Self(value.into(), self.1))
    }
    /// {
    ///   責務: [visit_f64: 有限の小数をJSON値として受け取る]
    ///   処理: [
    ///     1: 有限のJSON数値へ変換する
    ///     2: 現在の深さとともに格納する
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///     value: 変換・検査するJSON値
    ///   ]
    ///   戻り値: [JSON数値または非有限数値エラー]
    /// }
    fn visit_f64<E: de::Error>(self, value: f64) -> Result<Self, E> {
        serde_json::Number::from_f64(value)
            .map(|value| Self(Value::Number(value), self.1))
            .ok_or_else(|| E::custom("invalid JSON number"))
    }
    /// {
    ///   責務: [visit_str: 借用文字列をJSON文字列として受け取る]
    ///   処理: [
    ///     1: 文字列を所有値へ複製する
    ///     2: 現在の深さを格納する
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///     value: 変換・検査するJSON値
    ///   ]
    ///   戻り値: [JSON文字列]
    /// }
    fn visit_str<E: de::Error>(self, value: &str) -> Result<Self, E> {
        Ok(Self(Value::String(value.into()), self.1))
    }
    /// {
    ///   責務: [visit_string: 所有文字列をJSON文字列として受け取る]
    ///   処理: [
    ///     1: 文字列と現在の深さを格納する
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///     value: 変換・検査するJSON値
    ///   ]
    ///   戻り値: [JSON文字列]
    /// }
    fn visit_string<E: de::Error>(self, value: String) -> Result<Self, E> {
        Ok(Self(Value::String(value), self.1))
    }
    /// {
    ///   責務: [visit_unit: nullをJSON値として受け取る]
    ///   処理: [
    ///     1: nullと現在の深さを格納する
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///   ]
    ///   戻り値: [JSON null]
    /// }
    fn visit_unit<E: de::Error>(self) -> Result<Self, E> {
        Ok(Self(Value::Null, self.1))
    }
    /// {
    ///   責務: [visit_seq: 深さ制限内のJSON配列を読み込む]
    ///   処理: [
    ///     1: 128コンテナ上限を検査する
    ///     2: 子の深さを増やして要素を読み込む
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///     sequence: 配列要素の入力
    ///   ]
    ///   戻り値: [JSON配列または構文・深さエラー]
    /// }
    fn visit_seq<A: SeqAccess<'de>>(self, mut sequence: A) -> Result<Self, A::Error> {
        if self.1 > 128 {
            return Err(de::Error::custom("JSON nesting exceeds 128 containers"));
        }
        let mut values = Vec::new();
        while let Some(StrictJson(value, _)) =
            sequence.next_element_seed(StrictJson(Value::Null, self.1 + 1))?
        {
            values.push(value);
        }
        Ok(Self(Value::Array(values), self.1))
    }
    /// {
    ///   責務: [visit_map: 重複キーのないJSONオブジェクトを読み込む]
    ///   処理: [
    ///     1: 128コンテナ上限を検査する
    ///     2: キーの重複と子値を順に検査する
    ///     3: 一意なキーと値を格納する
    ///   ]
    ///   引数: [
    ///     self: 現在の値・状態
    ///     map: オブジェクト項目の入力
    ///   ]
    ///   戻り値: [JSONオブジェクトまたは重複・深さエラー]
    /// }
    fn visit_map<A: MapAccess<'de>>(self, mut map: A) -> Result<Self, A::Error> {
        if self.1 > 128 {
            return Err(de::Error::custom("JSON nesting exceeds 128 containers"));
        }
        let mut values = Map::new();
        while let Some(key) = map.next_key::<String>()? {
            if values.contains_key(&key) {
                return Err(de::Error::custom(format!("duplicate JSON key: {key}")));
            }
            let StrictJson(value, _) = map.next_value_seed(StrictJson(Value::Null, self.1 + 1))?;
            values.insert(key, value);
        }
        Ok(Self(Value::Object(values), self.1))
    }
}
