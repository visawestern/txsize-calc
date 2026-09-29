# txsize_calc — offline Solana transaction size calculator

Answers **SSE Q23875 “Get size of the transaction”** (score 0 / answers 0 / views 55,
checked 2026-09-29): `provider.sendAndConfirm(versionedTx)` fails with
`encoding overruns Uint8Array` past the packet limit, and the usual
`transaction.serialize().length` throws the same error — so the overshoot
can never be measured that way.

This tool **counts serialized bytes arithmetically** — no `serialize()`,
no RPC, no keys, no network — so it works even for transactions that are
already over the limit.

## Files

- `index.html` — static UI (only external ref is `./calc.js`, same folder; no CDN/fetch/XHR)
- `calc.js` — shared byte-math core (browser + node): `compactU16Len`, `calcTx`, `base64DecodedLen`
- `test_calc.py` — offline tests: known vectors + file/offline checks + local http 200
- `README.md` — this file

## Byte math

Limit `PACKET_DATA_SIZE = 1232`.

- signatures: `compactU16(n) + n×64`
- message: `version(0/1) + header(3) + [compactU16(k)+k×32] + blockhash(32) + [compactU16(ix)+Σix] + [lookups]`
- per instruction: `1 + compactU16(accts)+accts + compactU16(dataLen)+dataLen`
- per ALT lookup (v0): `32 + compactU16(w)+w + compactU16(r)+r`
- compact-u16: `0…127→1B, 128…16383→2B, 16384…→3B` — growing data 127→128 costs **+2B** (the overrun trap)

## Known vectors (asserted in tests)

| case | expected |
|---|---|
| legacy transfer (1 sig, 3 keys, 1 ix 2 acct + 12 B data) | **215 B** |
| empty + 1 ix (1 sig, 1 key, 1 ix 0+0) | **137 B** |
| empty + 0 ix | **134 B** |
| data 127 → 128 edge | **330 → 332 (+2)** |
| v0 transfer + 1 ALT lookup (w=2,r=1) | **254 B** |
| heavy (1 sig, 10 keys, 5× ix 5+200 B) | **>1232 (OVER)** |

## Run

```sh
python3 txsize_calc/test_calc.py        # vectors + offline checks + http 200
python3 -m http.server 8080             # then open http://127.0.0.1:8080/txsize_calc/
```

Nothing is published, no issue/PR/comment is created. Fully offline except the two
read-only balance checkers (`check_balances.py`, `check_solana.py`).
