//! Dependency-free SHA-256, used for project revisions.

/// 各ラウンドで使う定数（FIPS 180-4）。
const ROUND_CONSTANTS: [u32; 64] = [
    0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
    0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
    0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
    0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
    0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
    0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
    0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
    0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
];

/// 初期のハッシュ値（FIPS 180-4）。
const INITIAL_STATE: [u32; 8] = [
    0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19,
];

/// {
///   責務: [compress: 64バイトの塊1つを使ってハッシュの状態を進める]
///   処理: [
///     1: 塊を16語に読み、64語に拡張する
///     2: 64ラウンドの計算を行い、結果を状態へ加える
///   ]
///   引数: [
///     state: 現在のハッシュの状態
///     block: 64バイトの塊
///   ]
///   戻り値: [なし。状態を更新する]
/// }
fn compress(state: &mut [u32; 8], block: &[u8]) {
    let mut words = [0u32; 64];
    for (word, chunk) in words.iter_mut().zip(block.chunks(4)) {
        *word = u32::from_be_bytes([chunk[0], chunk[1], chunk[2], chunk[3]]);
    }
    for index in 16..64 {
        let low = words[index - 15].rotate_right(7)
            ^ words[index - 15].rotate_right(18)
            ^ (words[index - 15] >> 3);
        let high = words[index - 2].rotate_right(17)
            ^ words[index - 2].rotate_right(19)
            ^ (words[index - 2] >> 10);
        words[index] = words[index - 16]
            .wrapping_add(low)
            .wrapping_add(words[index - 7])
            .wrapping_add(high);
    }
    let [mut a, mut b, mut c, mut d, mut e, mut f, mut g, mut h] = *state;
    for index in 0..64 {
        let sigma_e = e.rotate_right(6) ^ e.rotate_right(11) ^ e.rotate_right(25);
        let choose = (e & f) ^ (!e & g);
        let first = h
            .wrapping_add(sigma_e)
            .wrapping_add(choose)
            .wrapping_add(ROUND_CONSTANTS[index])
            .wrapping_add(words[index]);
        let sigma_a = a.rotate_right(2) ^ a.rotate_right(13) ^ a.rotate_right(22);
        let majority = (a & b) ^ (a & c) ^ (b & c);
        let second = sigma_a.wrapping_add(majority);
        h = g;
        g = f;
        f = e;
        e = d.wrapping_add(first);
        d = c;
        c = b;
        b = a;
        a = first.wrapping_add(second);
    }
    for (slot, value) in state.iter_mut().zip([a, b, c, d, e, f, g, h]) {
        *slot = slot.wrapping_add(value);
    }
}

/// {
///   責務: [revision_of: バイト列のSHA-256を「sha256:」付きの小文字16進で返す]
///   処理: [
///     1: 末尾に0x80、0、ビット長を付けて64バイトの倍数にする
///     2: 塊ごとに状態を進める
///     3: 状態を小文字の16進文字列にする
///   ]
///   引数: [
///     bytes: 対象のバイト列
///   ]
///   戻り値: [「sha256:」と64文字の16進からなる文字列]
/// }
pub fn revision_of(bytes: &[u8]) -> String {
    let mut state = INITIAL_STATE;
    let mut padded = bytes.to_vec();
    padded.push(0x80);
    while padded.len() % 64 != 56 {
        padded.push(0);
    }
    padded.extend_from_slice(&((bytes.len() as u64) * 8).to_be_bytes());
    for block in padded.chunks(64) {
        compress(&mut state, block);
    }
    let digits: String = state.iter().map(|word| format!("{word:08x}")).collect();
    format!("sha256:{digits}")
}

/// {
///   責務: [is_revision: 文字列が正しいrevision表記かを判定する]
///   処理: [
///     1: 「sha256:」で始まり、続く64文字がすべて小文字の16進かを調べる
///   ]
///   引数: [
///     text: 調べる文字列
///   ]
///   戻り値: [正しい表記なら真]
/// }
pub fn is_revision(text: &str) -> bool {
    text.strip_prefix("sha256:").is_some_and(|digits| {
        digits.len() == 64
            && digits
                .bytes()
                .all(|byte| matches!(byte, b'0'..=b'9' | b'a'..=b'f'))
    })
}

#[cfg(test)]
mod tests {
    use super::{is_revision, revision_of};

    /// {
    ///   責務: [known_vectors: 公開されているSHA-256の見本と一致することを確認する]
    ///   処理: [
    ///     1: 空、abc、2塊にまたがる長さ、100万個のaを照合する
    ///   ]
    ///   引数: []
    ///   戻り値: [なし。不一致ならテストが失敗する]
    /// }
    #[test]
    fn known_vectors() {
        assert_eq!(
            revision_of(b""),
            "sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        );
        assert_eq!(
            revision_of(b"abc"),
            "sha256:ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
        );
        assert_eq!(
            revision_of(b"abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq"),
            "sha256:248d6a61d20638b8e5c026930c3e6039a33ce45964ff2167f6ecedd419db06c1"
        );
        assert_eq!(
            revision_of(&vec![b'a'; 1_000_000]),
            "sha256:cdc76e5c9914fb9281a1c7e284d73e67f1809a48a497200e046d39ccc7112cd0"
        );
    }

    /// {
    ///   責務: [revision_format: revision表記の判定が厳密であることを確認する]
    ///   処理: [
    ///     1: 正しい表記を受け入れ、大文字・長さ違い・接頭辞違いを拒否する
    ///   ]
    ///   引数: []
    ///   戻り値: [なし。不一致ならテストが失敗する]
    /// }
    #[test]
    fn revision_format() {
        assert!(is_revision(&revision_of(b"x")));
        assert!(!is_revision("sha256:ABC"));
        assert!(!is_revision(&revision_of(b"x").to_uppercase()));
        assert!(!is_revision(&revision_of(b"x").replace("sha256:", "md5:")));
        assert!(!is_revision(&revision_of(b"x")[..70]));
    }
}
