/* txsize_calc/calc.js — offline Solana transaction size calculator core.
 * No network, no deps. Shared by index.html (browser) and tests (node).
 * Wire format reference: Solana PACKET_DATA_SIZE = 1232 bytes.
 *  legacy: sigs + [header(3) + keys(vec) + blockhash(32) + ixs(vec) ]
 *  v0:     sigs + [version(1) + header(3) + keys(vec) + blockhash(32) + ixs(vec) + lookups(vec)]
 *  compact-u16 (short-vec): 7 bits/byte, MSB=continuation. 0..127 -> 1B, 128..16383 -> 2B, else 3B.
 */
'use strict';

var PACKET_LIMIT = 1232;

function compactU16Len(n) {
  if (!Number.isInteger(n) || n < 0) throw new Error('compactU16: expected non-negative int, got ' + n);
  if (n > 0x1fffff) throw new Error('compactU16: value too large: ' + n);
  var len = 0, rem = n;
  do { len++; rem = Math.floor(rem / 128); } while (rem > 0);
  return len;
}

// Encode a value as compact-u16 bytes (for self-test / demo).
function compactU16Encode(n) {
  if (!Number.isInteger(n) || n < 0) throw new Error('compactU16: expected non-negative int');
  var out = [], rem = n;
  while (true) {
    var b = rem & 0x7f;
    rem = Math.floor(rem / 128);
    if (rem === 0) { out.push(b); break; }
    out.push(b | 0x80);
  }
  return out;
}

function calcTx(p) {
  var numSigs = p.numSigs, numKeys = p.numKeys;
  var ixs = p.instructions || [];
  var lookups = p.lookups || [];
  var version = p.version === 'v0' ? 'v0' : 'legacy';
  if (!Number.isInteger(numSigs) || numSigs < 0 || numSigs > 64) throw new Error('numSigs 0..64');
  if (!Number.isInteger(numKeys) || numKeys < 0 || numKeys > 256) throw new Error('numKeys 0..256');

  var sigPrefix = compactU16Len(numSigs);
  var sigBytes = sigPrefix + numSigs * 64;

  var versionBytes = version === 'v0' ? 1 : 0;
  var headerBytes = 3;
  var keysPrefix = compactU16Len(numKeys);
  var keysBytes = keysPrefix + numKeys * 32;
  var blockhashBytes = 32;

  var ixCountPrefix = compactU16Len(ixs.length);
  var ixTotal = 0, ixRows = [];
  for (var i = 0; i < ixs.length; i++) {
    var na = ixs[i].numAccounts, dl = ixs[i].dataLen;
    if (!Number.isInteger(na) || na < 0 || na > 256) throw new Error('ix[' + i + '].numAccounts 0..256');
    if (!Number.isInteger(dl) || dl < 0 || dl > 1232) throw new Error('ix[' + i + '].dataLen 0..1232');
    var aPrefix = compactU16Len(na), dPrefix = compactU16Len(dl);
    var ixBytes = 1 + aPrefix + na + dPrefix + dl; // programIdIndex + accounts vec + data vec
    ixRows.push({ numAccounts: na, dataLen: dl, acctPrefix: aPrefix, dataPrefix: dPrefix, bytes: ixBytes });
    ixTotal += ixBytes;
  }

  var lookupCountPrefix = 0, lookupTotal = 0, lookupRows = [];
  if (version === 'v0') {
    lookupCountPrefix = compactU16Len(lookups.length);
    for (var j = 0; j < lookups.length; j++) {
      var w = lookups[j].writable, r = lookups[j].readonly;
      if (!Number.isInteger(w) || w < 0 || w > 256) throw new Error('lookup[' + j + '].writable 0..256');
      if (!Number.isInteger(r) || r < 0 || r > 256) throw new Error('lookup[' + j + '].readonly 0..256');
      var wPrefix = compactU16Len(w), rPrefix = compactU16Len(r);
      var lb = 32 + wPrefix + w + rPrefix + r;
      lookupRows.push({ writable: w, readonly: r, wPrefix: wPrefix, rPrefix: rPrefix, bytes: lb });
      lookupTotal += lb;
    }
  } else if (lookups.length > 0) {
    throw new Error('legacy transactions cannot carry address table lookups (use v0)');
  }

  var messageBytes = versionBytes + headerBytes + keysBytes + blockhashBytes + ixCountPrefix + ixTotal + lookupCountPrefix + lookupTotal;
  var total = sigBytes + messageBytes;

  return {
    version: version,
    sigPrefix: sigPrefix, sigBytes: sigBytes,
    versionBytes: versionBytes, headerBytes: headerBytes,
    keysPrefix: keysPrefix, keysBytes: keysBytes,
    blockhashBytes: blockhashBytes,
    ixCountPrefix: ixCountPrefix, ixRows: ixRows, ixTotal: ixTotal,
    lookupCountPrefix: lookupCountPrefix, lookupRows: lookupRows, lookupTotal: lookupTotal,
    messageBytes: messageBytes, total: total,
    limit: PACKET_LIMIT, overBy: total - PACKET_LIMIT,
    fits: total <= PACKET_LIMIT
  };
}

// Base64 -> decoded byte length without allocating the full buffer twice.
function base64DecodedLen(s) {
  s = String(s).replace(/\s+/g, '');
  if (s.length === 0) return 0;
  if (!/^[A-Za-z0-9+/]*={0,2}$/.test(s) || (s.length % 4) !== 0) throw new Error('not valid base64 (length must be multiple of 4)');
  var pad = 0;
  if (s.charAt(s.length - 1) === '=') pad++;
  if (s.charAt(s.length - 2) === '=') pad++;
  return Math.floor(s.length * 3 / 4) - pad;
}

// Export for node tests; browser gets globals.
if (typeof module !== 'undefined' && module.exports) {
  module.exports = { PACKET_LIMIT: PACKET_LIMIT, compactU16Len: compactU16Len, compactU16Encode: compactU16Encode, calcTx: calcTx, base64DecodedLen: base64DecodedLen };
}
