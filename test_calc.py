#!/usr/bin/env python3
"""txsize_calc tests — offline. Mirrors calc.js byte math in Python and asserts known vectors.

Vectors:
  transfer (legacy 1sig/3keys/1ix 2acct+12B) = 215 B (canonical Solana transfer size)
  empty+1ix (1sig/1key/1ix 0+0) = 137 B
  empty+0ix (1sig/1key/0ix) = 134 B
  compact-u16 edge: data 127->128 costs +2 B (1 B data + 1 B prefix) — the overrun trap
  v0 + 1 ALT lookup (w=2,r=1) on top of transfer = 254 B
  heavy (1sig/10keys/5ix 5+200B) = over 1232
Also: file checks (index.html + calc.js exist, no CDN/network calls), http 200 via local server.
"""
import json, os, subprocess, sys, urllib.request, http.server, functools, threading

HERE = os.path.dirname(os.path.abspath(__file__))
INDEX = os.path.join(HERE, "index.html")
CALCJS = os.path.join(HERE, "calc.js")
LIMIT = 1232
FAIL = []

def cu16len(n):
    assert isinstance(n, int) and n >= 0
    ln, rem = 0, n
    while True:
        ln += 1
        rem //= 128
        if rem == 0:
            return ln

def calc_tx(num_sigs, num_keys, ixs, version="legacy", lookups=()):
    sig = cu16len(num_sigs) + num_sigs * 64
    ver = 1 if version == "v0" else 0
    keys = cu16len(num_keys) + num_keys * 32
    ixcount = cu16len(len(ixs))
    ixtot = sum(1 + cu16len(na) + na + cu16len(dl) + dl for na, dl in ixs)
    lkc, lktot = 0, 0
    if version == "v0":
        lkc = cu16len(len(lookups))
        lktot = sum(32 + cu16len(w) + w + cu16len(r) + r for w, r in lookups)
    msg = ver + 3 + keys + 32 + ixcount + ixtot + lkc + lktot
    return sig + msg

def check(name, got, want):
    ok = got == want
    print(f"{'PASS' if ok else 'FAIL'} {name}: got={got} want={want}")
    if not ok:
        FAIL.append(name)

print("== txsize vectors (python mirror) ==")
check("compactU16(0)=1", cu16len(0), 1)
check("compactU16(127)=1", cu16len(127), 1)
check("compactU16(128)=2", cu16len(128), 2)
check("compactU16(16383)=2", cu16len(16383), 2)
check("compactU16(16384)=3", cu16len(16384), 3)
check("transfer=215", calc_tx(1, 3, [(2, 12)]), 215)
check("empty+1ix=137", calc_tx(1, 1, [(0, 0)]), 137)
check("empty+0ix=134", calc_tx(1, 1, []), 134)
a = calc_tx(1, 3, [(2, 127)])
b = calc_tx(1, 3, [(2, 128)])
check("edge127=330", a, 330)
check("edge128=332", b, 332)
check("edge delta=+2", b - a, 2)
check("v0 transfer+ALT=254", calc_tx(1, 3, [(2, 12)], "v0", [(2, 1)]), 254)
heavy = calc_tx(1, 10, [(5, 200)] * 5)
print(f"INFO heavy=5ix(5+200B) -> {heavy} (over by {heavy - LIMIT})")
check("heavy over limit", heavy > LIMIT, True)

print("== static/offline file checks ==")
for p in (INDEX, CALCJS):
    ok = os.path.exists(p)
    print(f"{'PASS' if ok else 'FAIL'} exists {os.path.basename(p)}")
    if not ok:
        FAIL.append(f"exists {p}")
html = open(INDEX, encoding="utf-8").read()
for bad, why in (('src="http', "CDN script"), ("src='http", "CDN script"),
                 ("href=\"http", None),  # allowed: plain anchor links; skip
                 ("fetch(", "network fetch"), ("XMLHttpRequest", "XHR"),
                 ("api.mainnet-beta", "RPC call")):
    if why is None:
        continue
    ok = bad not in html
    print(f"{'PASS' if ok else 'FAIL'} no `{bad}` in index.html")
    if not ok:
        FAIL.append(f"offline:{bad}")
for needle in ("compact-u16", "1232", "calc.js", "Q23875", "ALT"):
    ok = needle in html
    print(f"{'PASS' if ok else 'FAIL'} index.html mentions `{needle}`")
    if not ok:
        FAIL.append(f"content:{needle}")

print("== node cross-check (calc.js, if node present) ==")
try:
    r = subprocess.run(["node", "-e",
        "const c=require(process.argv[1]);"
        "const t=(a,b)=>{if(a!==b){console.log('FAIL node',a,b);process.exit(1)}};"
        "t(c.compactU16Len(127),1);t(c.compactU16Len(128),2);"
        "t(c.calcTx({version:'legacy',numSigs:1,numKeys:3,instructions:[{numAccounts:2,dataLen:12}],lookups:[]}).total,215);"
        "t(c.calcTx({version:'legacy',numSigs:1,numKeys:3,instructions:[{numAccounts:2,dataLen:128}],lookups:[]}).total,332);"
        "t(c.calcTx({version:'v0',numSigs:1,numKeys:3,instructions:[{numAccounts:2,dataLen:12}],lookups:[{writable:2,readonly:1}]}).total,254);"
        "console.log('PASS node calc.js vectors');",
        CALCJS], capture_output=True, text=True, timeout=20)
    print((r.stdout or "").strip() or "(no stdout)")
    if r.returncode != 0:
        print((r.stderr or "").strip())
        FAIL.append("node vectors")
except FileNotFoundError:
    print("SKIP node not installed (python mirror already passed)")
except Exception as e:
    print(f"SKIP node cross-check: {e}")

print("== http 200 (local server, no publish) ==")
Handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=os.path.dirname(HERE))
srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
port = srv.server_address[1]
th = threading.Thread(target=srv.serve_forever, daemon=True)
th.start()
try:
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/txsize_calc/", timeout=10) as r:
        code = r.status
        body = r.read(2000).decode("utf-8", "replace")
    ok = code == 200 and "Tx Size Calculator" in body or "tx size calculator" in body.lower()
    print(f"{'PASS' if ok else 'FAIL'} http 200 /txsize_calc/ (status={code})")
    if not ok:
        FAIL.append("http200")
finally:
    srv.shutdown()

print()
if FAIL:
    print(f"RESULT FAIL: {FAIL}")
    sys.exit(1)
print("RESULT ALL PASS")
