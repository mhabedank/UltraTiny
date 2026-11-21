# Contract: Model File Format "UTNY" v1

Little-endian. All offsets relative to file start. Every tensor starts 4-byte aligned.

## Header (64 bytes)

| Offset | Type | Field | Notes |
|--------|------|-------|-------|
| 0 | char[4] | `magic` | `"UTNY"` |
| 4 | u16 | `format_version` | `1`; any layout change bumps it (Constitution IV) |
| 6 | u16 | `header_size` | `64` |
| 8 | u16 | `vocab_size` | ≤ 96 |
| 10 | u16 | `d_model` | |
| 12 | u16 | `n_layers` | |
| 14 | u16 | `n_heads` | |
| 16 | u16 | `n_kv_heads` | |
| 18 | u16 | `d_ff` | |
| 20 | u16 | `ctx_len` | |
| 22 | u16 | `flags` | bit 0: tied embeddings (must be 1 in v1) |
| 24 | f32 | `norm_eps` | |
| 28 | u32 | `alphabet_offset` | |
| 32 | u32 | `meta_offset` | UTF-8 JSON string (RunMetadata summary), NUL-terminated |
| 36 | u32 | `tensors_offset` | |
| 40 | u32 | `payload_size` | bytes from `alphabet_offset` to end of file |
| 44 | u32 | `payload_crc32` | CRC-32 (IEEE) over the payload |
| 48 | u32 | `n_params` | for the banner |
| 52 | u8[8] | `reserved` | zero |
| 60 | u32 | `header_crc32` | CRC-32 over bytes 0–59 |

## Alphabet block

`u32 count`, then `count` × `u32` Unicode code points, index = token ID. Entries 0–4 are
`0xFFFF0000 + k` for the specials `<pad>, <bos>, <sep>, <eos>, <unk>`.

## Tensor block (fixed order, no names)

Quantized matrix `Q[rows × cols]`: `f32 scale[rows]` followed by `i8 w[rows × cols]` (row-major),
padded to 4 bytes. Real value = `w[r][c] * scale[r]`. Vector `F[n]`: `f32[n]`.

1. `tok_emb` Q[vocab × d_model] (also the output head, tied)
2. `pos_emb` Q[ctx_len × d_model]
3. For each layer `l` in 0 … n_layers−1:
   1. `attn_norm` F[d_model]
   2. `wq` Q[d_model × d_model] (rows = outputs)
   3. `wk` Q[(n_kv_heads·head_dim) × d_model]
   4. `wv` Q[(n_kv_heads·head_dim) × d_model]
   5. `wo` Q[d_model × d_model]
   6. `ffn_norm` F[d_model]
   7. `w1` Q[d_ff × d_model]
   8. `w2` Q[d_model × d_ff]
4. `final_norm` F[d_model]

## Validation rules (runtime loader)

- Reject on wrong magic, `format_version ≠ 1`, header CRC mismatch, payload CRC mismatch,
  `payload_size + header_size > partition size`, `vocab_size > 96`,
  `d_model % n_heads ≠ 0`, `flags` bit 0 not set, or computed arena size > arena capacity.
- Each rejection maps to a distinct error code (see runtime API) and console message.

## Quantization rules (exporter and reference)

- `scale[r] = max(|row|) / 127` (if 0 → 1.0); `w = clamp(round_half_away(x / scale), −127, 127)`.
