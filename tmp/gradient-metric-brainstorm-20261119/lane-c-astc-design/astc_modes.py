"""Parse ASTC 2D block headers (block mode, partitions, CEM, endpoint range) without decoding texels.

Port of astcenc decode_block_mode_2d (downloads/astcenc_block_sizes.cpp L36-L140) plus the
Khronos Data Format 1.3 rules: Table 144/145 (layout), Table 150-152 (multi-partition CEM),
23.13 endpoint range = largest range whose ISE fits the remaining bits, 23.24 illegal encodings.
"""
from __future__ import annotations

from pathlib import Path

LEVELS = [2, 3, 4, 5, 6, 8, 10, 12, 16, 20, 24, 32, 40, 48, 64, 80, 96, 128, 160, 192, 256]
ISE = {2: (1, 0, 0), 3: (0, 1, 0), 4: (2, 0, 0), 5: (0, 0, 1), 6: (1, 1, 0), 8: (3, 0, 0), 10: (1, 0, 1),
       12: (2, 1, 0), 16: (4, 0, 0), 20: (2, 0, 1), 24: (3, 1, 0), 32: (5, 0, 0), 40: (3, 0, 1), 48: (4, 1, 0),
       64: (6, 0, 0), 80: (4, 0, 1), 96: (5, 1, 0), 128: (7, 0, 0), 160: (5, 0, 1), 192: (6, 1, 0), 256: (8, 0, 0)}


def ise_bits(count: int, levels: int) -> int:
    bits, trits, quints = ISE[levels]
    return bits * count + (8 * count * trits + 4) // 5 + (7 * count * quints + 2) // 3


def block_mode_2d(mode: int) -> tuple[int, int, bool, int, int] | None:
    base = (mode >> 4) & 1
    h = (mode >> 9) & 1
    d = (mode >> 10) & 1
    a = (mode >> 5) & 3
    if mode & 3:
        base |= (mode & 3) << 1
        b = (mode >> 7) & 3
        sel = (mode >> 2) & 3
        if sel == 0:
            wx, wy = b + 4, a + 2
        elif sel == 1:
            wx, wy = b + 8, a + 2
        elif sel == 2:
            wx, wy = a + 2, b + 8
        else:
            b &= 1
            wx, wy = (b + 2, a + 2) if mode & 0x100 else (a + 2, b + 6)
    else:
        base |= ((mode >> 2) & 3) << 1
        if ((mode >> 2) & 3) == 0:
            return None
        b = (mode >> 9) & 3
        sel = (mode >> 7) & 3
        if sel == 0:
            wx, wy = 12, a + 2
        elif sel == 1:
            wx, wy = a + 2, 12
        elif sel == 2:
            wx, wy, d, h = a + 6, b + 6, 0, 0
        else:
            sub = (mode >> 5) & 3
            if sub == 0:
                wx, wy = 6, 10
            elif sub == 1:
                wx, wy = 10, 6
            else:
                return None
    count = wx * wy * (d + 1)
    quant = (base - 2) + 6 * h
    levels = LEVELS[quant]
    bits = ise_bits(count, levels)
    if count > 64 or bits < 24 or bits > 96:
        return None
    return wx, wy, bool(d), levels, bits


def parse_block(value: int, bx: int, by: int) -> dict[str, object]:
    if (value & 0x1FF) == 0x1FC:
        rgba = [((value >> (64 + 16 * c)) & 0xFFFF) >> 8 for c in range(4)]
        return {"kind": "void", "rgba8": rgba}
    mode = block_mode_2d(value & 0x7FF)
    if mode is None:
        return {"kind": "error"}
    wx, wy, dual, wlevels, wbits = mode
    if wx > bx or wy > by:
        return {"kind": "error"}
    parts = ((value >> 11) & 3) + 1
    if dual and parts == 4:
        return {"kind": "error"}
    extra = 0
    if parts == 1:
        cems = [(value >> 13) & 0xF]
        header = 17
    else:
        header = 29
        field = (value >> 23) & 0x3F
        if field & 3 == 0:
            cems = [field >> 2] * parts
        else:
            extra = 3 * parts - 4
            top = 128 - wbits
            field |= ((value >> (top - extra)) & ((1 << extra) - 1)) << 6
            base_class = (field & 3) - 1
            cems = [((base_class + ((field >> (2 + i)) & 1)) << 2) | ((field >> (2 + parts + 2 * i)) & 3)
                    for i in range(parts)]
    ccs = 2 if dual else 0
    remaining = 128 - header - wbits - extra - ccs
    nvalues = sum(2 * ((c >> 2) + 1) for c in cems)
    elevels = None
    if nvalues <= 18:
        for lv in reversed(LEVELS):
            if ise_bits(nvalues, lv) <= remaining:
                elevels = lv
                break
    return {"kind": "normal", "grid": (wx, wy), "dual": dual, "weight_levels": wlevels, "weight_bits": wbits,
            "partitions": parts, "cem": cems, "endpoint_values": nvalues, "endpoint_bits": remaining,
            "endpoint_levels": elevels,
            "ccs": ((value >> (128 - wbits - extra - 2)) & 3) if dual else None}


def read_astc(path: Path) -> tuple[int, int, int, int, list[list[dict[str, object]]]]:
    raw = path.read_bytes()
    assert raw[:4] == bytes([0x13, 0xAB, 0xA1, 0x5C]), path
    bx, by = raw[4], raw[5]
    w = int.from_bytes(raw[7:10], "little")
    h = int.from_bytes(raw[10:13], "little")
    nbx, nby = -(-w // bx), -(-h // by)
    rows = []
    off = 16
    for j in range(nby):
        row = []
        for i in range(nbx):
            row.append(parse_block(int.from_bytes(raw[off:off + 16], "little"), bx, by))
            off += 16
        rows.append(row)
    return bx, by, w, h, rows
