"""Tick-recorder reader for SN289-SN300 (research only). The packet decoder is python-engine/tick_recorder.py's
decode_packet / read_chunk, copied verbatim (that module imports the engine's settings, which the research venv does not
load). A day folder is a local, read-only copy of /data/research/ticks/<day> from the Production engine container."""
from __future__ import annotations

import json
import lzma
import struct
from pathlib import Path

import numpy as np

REC = struct.Struct(">qH")
LOCAL = Path(__file__).resolve().parent / "_local"
DAY0_NS = None


def packet_token(packet):
    return int.from_bytes(packet[0:4], "big")


def _divisor(token):
    segment = token & 0xFF
    return 1e7 if segment == 3 else 1e4 if segment == 6 else 100.0


def _u32(packet, at):
    return struct.unpack_from(">I", packet, at)[0]


def decode_packet(packet):
    token = packet_token(packet)
    div = _divisor(token)
    row = {"token": token, "length": len(packet), "ltp": _u32(packet, 4) / div}
    if token & 0xFF == 9:
        if len(packet) >= 28:
            row.update(high=_u32(packet, 8) / div, low=_u32(packet, 12) / div, open=_u32(packet, 16) / div,
                       close=_u32(packet, 20) / div)
        if len(packet) >= 32:
            row["exchange_ts"] = _u32(packet, 28)
        return row
    if len(packet) >= 44:
        row.update(last_qty=_u32(packet, 8), avg_price=_u32(packet, 12) / div, volume=_u32(packet, 16),
                   buy_qty=_u32(packet, 20), sell_qty=_u32(packet, 24), open=_u32(packet, 28) / div,
                   high=_u32(packet, 32) / div, low=_u32(packet, 36) / div, close=_u32(packet, 40) / div)
    if len(packet) >= 184:
        row.update(last_trade_ts=_u32(packet, 44), oi=_u32(packet, 48), oi_high=_u32(packet, 52),
                   oi_low=_u32(packet, 56), exchange_ts=_u32(packet, 60))
        levels = [(_u32(packet, at), _u32(packet, at + 4) / div, struct.unpack_from(">H", packet, at + 8)[0])
                  for at in range(64, 184, 12)]
        row["bids"] = [{"qty": q, "price": p, "orders": o} for q, p, o in levels[:5]]
        row["asks"] = [{"qty": q, "price": p, "orders": o} for q, p, o in levels[5:]]
    return row


def read_chunk(path):
    raw = lzma.decompress(Path(path).read_bytes())
    rows, pos = [], 0
    while pos < len(raw):
        recv_ns, length = REC.unpack_from(raw, pos)
        pos += REC.size
        row = decode_packet(raw[pos:pos + length])
        row["recv_ns"] = recv_ns
        rows.append(row)
        pos += length
    return rows


def instruments(folder):
    out = {}
    for line in (Path(folder) / "instruments.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            out[r["token"]] = r
    return out


def load_day(folder, keep=None):
    """{token: dict of numpy arrays sorted by receipt: t (s since 09:15 IST), ltp, bid, ask, bq, aq, b5, a5 (5-level qty
    sums), bids (5,n), asks (5,n), bidq (5,n), askq (5,n)}; keep(token) filters instruments."""
    folder = Path(folder)
    meta = instruments(folder)
    acc = {}
    for ch in sorted(folder.glob("chunk-*.bin.xz")):
        for r in read_chunk(ch):
            tok = r["token"]
            if keep is not None and not keep(tok, meta.get(tok)):
                continue
            acc.setdefault(tok, []).append(r)
    day = folder.name[-10:]
    import datetime as dt
    import pytz
    t0 = pytz.timezone("Asia/Kolkata").localize(dt.datetime.fromisoformat(day + "T09:15:00")).timestamp()
    out = {}
    for tok, rows in acc.items():
        rows.sort(key=lambda r: r["recv_ns"])
        n = len(rows)
        d = {"t": np.array([r["recv_ns"] / 1e9 - t0 for r in rows]), "ltp": np.array([r["ltp"] for r in rows])}
        if "bids" in rows[0]:
            bp = np.array([[lv["price"] for lv in r.get("bids", [{"price": 0}] * 5)] for r in rows]).T
            ap = np.array([[lv["price"] for lv in r.get("asks", [{"price": 0}] * 5)] for r in rows]).T
            bq = np.array([[lv["qty"] for lv in r.get("bids", [{"qty": 0}] * 5)] for r in rows], dtype=float).T
            aq = np.array([[lv["qty"] for lv in r.get("asks", [{"qty": 0}] * 5)] for r in rows], dtype=float).T
            d.update(bids=bp, asks=ap, bidq=bq, askq=aq, bid=bp[0], ask=ap[0], bq=bq[0], aq=aq[0], b5=bq.sum(0), a5=aq.sum(0))
        out[tok] = d
    return meta, out


def asof(d, t, field):
    """The value of `field` at the last packet with receipt <= t, and that packet's age (s)."""
    k = np.searchsorted(d["t"], t, side="right") - 1
    if k < 0:
        return None, None
    return d[field][k], t - d["t"][k]


def first_after(d, t):
    k = np.searchsorted(d["t"], t, side="left")
    return None if k >= len(d["t"]) else k
