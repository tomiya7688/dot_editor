//! JSON value visitor rejecting duplicate keys, including in unknown fields.
use serde::de::{self, Deserialize, DeserializeSeed, Deserializer, MapAccess, SeqAccess, Visitor};
use serde_json::{Map, Value};
use std::fmt;

pub(crate) struct StrictJson(pub(crate) Value, pub(crate) usize);

impl<'de> Deserialize<'de> for StrictJson {
    fn deserialize<D: Deserializer<'de>>(deserializer: D) -> Result<Self, D::Error> {
        deserializer.deserialize_any(StrictJson(Value::Null, 1))
    }
}

impl<'de> DeserializeSeed<'de> for StrictJson {
    type Value = Self;
    fn deserialize<D: Deserializer<'de>>(self, deserializer: D) -> Result<Self, D::Error> {
        deserializer.deserialize_any(self)
    }
}

impl<'de> Visitor<'de> for StrictJson {
    type Value = Self;
    fn expecting(&self, formatter: &mut fmt::Formatter) -> fmt::Result {
        formatter.write_str("a JSON value with unique object keys")
    }
    fn visit_bool<E: de::Error>(self, value: bool) -> Result<Self, E> {
        Ok(Self(Value::Bool(value), self.1))
    }
    fn visit_i64<E: de::Error>(self, value: i64) -> Result<Self, E> {
        Ok(Self(value.into(), self.1))
    }
    fn visit_u64<E: de::Error>(self, value: u64) -> Result<Self, E> {
        Ok(Self(value.into(), self.1))
    }
    fn visit_f64<E: de::Error>(self, value: f64) -> Result<Self, E> {
        serde_json::Number::from_f64(value)
            .map(|value| Self(Value::Number(value), self.1))
            .ok_or_else(|| E::custom("invalid JSON number"))
    }
    fn visit_str<E: de::Error>(self, value: &str) -> Result<Self, E> {
        Ok(Self(Value::String(value.into()), self.1))
    }
    fn visit_string<E: de::Error>(self, value: String) -> Result<Self, E> {
        Ok(Self(Value::String(value), self.1))
    }
    fn visit_unit<E: de::Error>(self) -> Result<Self, E> {
        Ok(Self(Value::Null, self.1))
    }
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
