"""将 MP4 的 moov 原子移到文件前部，便于浏览器边下边拖进度条。"""
from __future__ import annotations

import shutil
import struct
from pathlib import Path


def _iter_boxes(buf: memoryview | bytes, start: int, end: int):
    i = start
    while i + 8 <= end:
        size = struct.unpack(">I", buf[i : i + 4])[0]
        typ = bytes(buf[i + 4 : i + 8]).decode("latin-1")
        header = 8
        if size == 1:
            if i + 16 > end:
                break
            size = struct.unpack(">Q", buf[i + 8 : i + 16])[0]
            header = 16
        elif size == 0:
            size = end - i
        if size < header or i + size > end:
            break
        yield i, typ, size, header
        i += size


def _patch_chunk_offsets(moov: bytearray, delta: int) -> None:
    """递归修正 moov 内 stco/co64。"""

    def walk(start: int, end: int) -> None:
        for i, typ, size, header in _iter_boxes(moov, start, end):
            if typ in ("stco", "co64"):
                # version(1)+flags(3)+entry_count(4)
                base = i + header
                if base + 8 > i + size:
                    continue
                entries = struct.unpack(">I", moov[base + 4 : base + 8])[0]
                if typ == "stco":
                    for e in range(entries):
                        off = base + 8 + e * 4
                        if off + 4 > i + size:
                            break
                        val = struct.unpack(">I", moov[off : off + 4])[0]
                        moov[off : off + 4] = struct.pack(">I", (val + delta) & 0xFFFFFFFF)
                else:
                    for e in range(entries):
                        off = base + 8 + e * 8
                        if off + 8 > i + size:
                            break
                        val = struct.unpack(">Q", moov[off : off + 8])[0]
                        moov[off : off + 8] = struct.pack(">Q", val + delta)
            elif typ in (
                "trak",
                "mdia",
                "minf",
                "stbl",
                "edts",
                "moov",
                "udta",
                "meta",
            ):
                walk(i + header, i + size)

    walk(0, len(moov))


def ensure_mp4_faststart(path: Path) -> bool:
    """
    若 moov 在 mdat 之后，重写为 faststart。
    成功改写返回 True；已是 faststart / 非 mp4 / 失败返回 False。
    """
    path = Path(path)
    if path.suffix.lower() not in {".mp4", ".m4v", ".mov"}:
        return False
    try:
        data = bytearray(path.read_bytes())
    except OSError:
        return False

    atoms = list(_iter_boxes(data, 0, len(data)))
    if not atoms:
        return False

    types = [a[1] for a in atoms]
    if "moov" not in types or "mdat" not in types:
        return False
    moov_i = types.index("moov")
    mdat_i = types.index("mdat")
    if moov_i < mdat_i:
        return False

    moov_start, _, moov_size, _ = atoms[moov_i]
    moov = bytearray(data[moov_start : moov_start + moov_size])
    _patch_chunk_offsets(moov, moov_size)

    parts: list[bytes] = []
    for start, typ, size, _ in atoms:
        if typ == "moov":
            continue
        if typ == "mdat":
            parts.append(bytes(moov))
        parts.append(bytes(data[start : start + size]))

    out = b"".join(parts)
    tmp = path.with_suffix(path.suffix + ".faststart.tmp")
    try:
        tmp.write_bytes(out)
        shutil.move(str(tmp), str(path))
    except OSError:
        if tmp.exists():
            tmp.unlink(missing_ok=True)
        return False
    return True
