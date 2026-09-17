"""从系统字体里抽取字形数据，构建 TrueType 子集，供自写的 PDF 生成器使用。
只用 Python 标准库，不依赖 reportlab / fpdf 等第三方包（本机也没装）。
"""
import struct


def _read_tables(path, font_index=0):
    data = open(path, 'rb').read()
    if data[:4] == b'ttcf':
        (num_fonts,) = struct.unpack('>I', data[8:12])
        if font_index >= num_fonts:
            raise ValueError('font_index 超出 TTC 范围')
        (offset,) = struct.unpack('>I', data[12 + 4 * font_index:16 + 4 * font_index])
    else:
        offset = 0
    num_tables, = struct.unpack('>H', data[offset + 4:offset + 6])
    tables = {}
    for i in range(num_tables):
        p = offset + 12 + i * 16
        tag = data[p:p + 4].decode('latin-1')
        checksum, toff, length = struct.unpack('>III', data[p + 4:p + 16])
        tables[tag] = (toff, length)
    return data, tables


class TrueTypeFont:
    """读取 TTF/TTC，提供 unicode -> glyph id、字形轮廓、宽度等查询。"""

    def __init__(self, path, font_index=0):
        self.path = path
        self.data, self.tables = _read_tables(path, font_index)
        d, t = self.data, self.tables

        head = t['head'][0]
        self.units_per_em = struct.unpack('>H', d[head + 18:head + 20])[0]
        self.index_to_loc_format = struct.unpack('>h', d[head + 50:head + 52])[0]

        hhea = t['hhea'][0]
        self.ascent = struct.unpack('>h', d[hhea + 4:hhea + 6])[0]
        self.descent = struct.unpack('>h', d[hhea + 6:hhea + 8])[0]
        self.num_hmetrics = struct.unpack('>H', d[hhea + 34:hhea + 36])[0]

        maxp = t['maxp'][0]
        self.num_glyphs = struct.unpack('>H', d[maxp + 4:maxp + 6])[0]

        loca_off = t['loca'][0]
        if self.index_to_loc_format == 0:
            n = self.num_glyphs + 1
            self.loca = list(struct.unpack('>%dH' % n, d[loca_off:loca_off + 2 * n]))
            self.loca = [v * 2 for v in self.loca]
        else:
            n = self.num_glyphs + 1
            self.loca = list(struct.unpack('>%dI' % n, d[loca_off:loca_off + 4 * n]))

        self.glyf_off = t['glyf'][0]
        self.hmtx_off = t['hmtx'][0]

        self.cmap = {}
        self._parse_cmap()

    # ----------------------------- cmap -----------------------------
    def _parse_cmap(self):
        d, t = self.data, self.tables
        cmap_off = t['cmap'][0]
        num_tables, = struct.unpack('>H', d[cmap_off + 2:cmap_off + 4])
        best = None
        for i in range(num_tables):
            p = cmap_off + 4 + i * 8
            plat, enc, sub = struct.unpack('>HHI', d[p:p + 8])
            if plat == 3 and enc == 10:
                best = ('fmt12', cmap_off + sub); break
            if plat == 3 and enc == 1 and best is None:
                best = ('fmt4', cmap_off + sub)
            if plat == 0 and best is None:
                best = ('fmt4', cmap_off + sub)
        if best is None:
            return
        kind, off = best
        fmt, = struct.unpack('>H', d[off:off + 2])
        if fmt == 12:
            ngroups, = struct.unpack('>I', d[off + 12:off + 16])
            for g in range(ngroups):
                p = off + 16 + g * 12
                s, e, gid = struct.unpack('>III', d[p:p + 12])
                if e - s > 0x20000:
                    continue
                for cp in range(s, e + 1):
                    self.cmap[cp] = gid + (cp - s)
        elif fmt == 4:
            seg_x2, = struct.unpack('>H', d[off + 6:off + 8])
            seg = seg_x2 // 2
            ends = struct.unpack('>%dH' % seg, d[off + 14:off + 14 + seg_x2])
            starts_off = off + 16 + seg_x2
            starts = struct.unpack('>%dH' % seg, d[starts_off:starts_off + seg_x2])
            deltas_off = starts_off + seg_x2
            deltas = struct.unpack('>%dh' % seg, d[deltas_off:deltas_off + seg_x2])
            range_off = deltas_off + seg_x2
            ranges = struct.unpack('>%dH' % seg, d[range_off:range_off + seg_x2])
            for i in range(seg):
                for cp in range(starts[i], ends[i] + 1):
                    if cp == 0xFFFF:
                        continue
                    if ranges[i] == 0:
                        gid = (cp + deltas[i]) & 0xFFFF
                    else:
                        gp = range_off + i * 2 + ranges[i] + (cp - starts[i]) * 2
                        if gp + 2 > len(d):
                            continue
                        gid, = struct.unpack('>H', d[gp:gp + 2])
                        if gid:
                            gid = (gid + deltas[i]) & 0xFFFF
                    if gid:
                        self.cmap[cp] = gid

    # --------------------------- 字形数据 ---------------------------
    def glyph_data(self, gid):
        if gid < 0 or gid + 1 >= len(self.loca):
            return b''
        start, end = self.loca[gid], self.loca[gid + 1]
        if end <= start:
            return b''   # 空字形（例如空格）
        return self.data[self.glyf_off + start:self.glyf_off + end]

    def advance(self, gid):
        """返回 1000 单位下的字宽（PDF 用）。"""
        return self.raw_advance(gid) * 1000.0 / self.units_per_em

    def raw_advance(self, gid):
        """返回字体自身 em 单位下的原始字宽（写 hmtx 用）。"""
        num = self.num_hmetrics
        if gid < num:
            p = self.hmtx_off + gid * 4
        else:
            p = self.hmtx_off + (num - 1) * 4
        aw, = struct.unpack('>H', self.data[p:p + 2])
        return aw

    def bbox(self, gid):
        g = self.glyph_data(gid)
        if len(g) < 10:
            return (0, 0, 0, 0)
        return struct.unpack('>hhhh', g[2:10])


def _cmap_format4(pairs):
    """构造 cmap 的 format 4 子表：pairs 是 [(unicode, gid), ...]（已按 unicode 排序）。
    把 codepoint 和 gid 都连续 +1 的项合并成一个 segment，用 idDelta 表达，最省空间。"""
    segs = []
    cur = None
    for cp, gid in pairs:
        if cur and cp == cur[1] + 1 and gid == cur[3] + 1:
            cur = (cur[0], cp, cur[2], gid)
            segs[-1] = cur
        else:
            cur = (cp, cp, gid, gid)
            segs.append(cur)
    segs.append((0xFFFF, 0xFFFF, 0, 0))   # 规范要求的收尾段

    n = len(segs)
    end_codes = b''.join(struct.pack('>H', s[1]) for s in segs)
    start_codes = b''.join(struct.pack('>H', s[0]) for s in segs)
    deltas = b''.join(struct.pack('>h', (s[2] - s[0]) & 0xFFFF if False else
                                  ((s[2] - s[0] + 0x8000) % 0x10000 - 0x8000)) for s in segs)
    range_offsets = b'\x00\x00' * n

    body = (struct.pack('>HHHH', 4, 16 + 8 * n, 0, n * 2) +
            struct.pack('>HHH', n * 2, n * 2, 1) +   # segCountX2, searchRange, entrySelector
            struct.pack('>H', 0) +                    # rangeShift
            end_codes + b'\x00\x00' + start_codes + deltas + range_offsets)
    # 子表长度字段
    body = struct.pack('>HH', 4, len(body)) + body[4:]
    sub_off = 12
    header = struct.pack('>HH', 0, 1) + struct.pack('>HHI', 3, 1, sub_off)
    return header + body


def _cmap_cid(pairs):
    """给 PDF 用的 cmap：把 unicode 映射到“子集里的 CID”，格式 4。"""
    return _cmap_format4(sorted(pairs))


def _hhea(font, num_glyphs):
    b = bytearray(36)
    struct.pack_into('>i', b, 0, 0x00010000)
    struct.pack_into('>h', b, 4, int(font.ascent * 1000 / font.units_per_em))
    struct.pack_into('>h', b, 6, int(font.descent * 1000 / font.units_per_em))
    struct.pack_into('>h', b, 8, 0)
    struct.pack_into('>H', b, 10, int(font.advance(font.cmap.get(0x4E00, 1)) * font.units_per_em / 1000) or 1000)
    struct.pack_into('>h', b, 12, 0)
    struct.pack_into('>h', b, 14, 0)
    struct.pack_into('>h', b, 16, int(font.ascent * 1000 / font.units_per_em))
    struct.pack_into('>h', b, 18, int(font.descent * 1000 / font.units_per_em))
    struct.pack_into('>h', b, 20, 0)
    struct.pack_into('>h', b, 22, 0)
    struct.pack_into('>h', b, 24, 1)
    struct.pack_into('>h', b, 26, 0)
    struct.pack_into('>h', b, 28, 0)
    struct.pack_into('>H', b, 32, 0)
    struct.pack_into('>H', b, 34, num_glyphs)
    return bytes(b)


def _hmtx(font, subset_gids):
    """longHorMetric：advanceWidth + lsb（都取原字体里的值，单位是原始 em）。"""
    out = bytearray()
    for old in subset_gids:
        aw = font.raw_advance(old)
        lsb = font.bbox(old)[0]
        out += struct.pack('>Hh', aw, lsb)
    return bytes(out)


def build_subset(font, unicodes, name='SUBSET'):
    """为给定 unicode 集合构建子集，返回 (fontfile_bytes, {unicode: subset_gid}, n_glyphs)。"""
    desired = {}
    for cp in sorted(unicodes):
        gid = font.cmap.get(cp)
        if gid:
            desired[cp] = gid

    # 复合字形的组件也要一起带进来
    gids = set(desired.values())
    stack = list(gids)
    while stack:
        g = stack.pop()
        data = font.glyph_data(g)
        if len(data) >= 10 and struct.unpack('>h', data[0:2])[0] < 0:
            i = 10
            while i + 4 <= len(data):
                flags, comp_gid = struct.unpack('>HH', data[i:i + 4])
                if comp_gid and comp_gid not in gids:
                    gids.add(comp_gid)
                    stack.append(comp_gid)
                i += 4
                i += 4 if flags & 1 else 2
                if flags & 8: i += 2
                elif flags & 0x40: i += 4
                elif flags & 0x80: i += 8
                if not flags & 0x20:
                    break

    subset_gids = sorted(g for g in gids if g != 0)
    new_gid = {old: i + 1 for i, old in enumerate(subset_gids)}   # 0 留给 .notdef
    glyf = bytearray()
    loca = [0]
    for old in subset_gids:
        glyf += font.glyph_data(old)
        if len(glyf) % 2:
            glyf += b'\x00'
        loca.append(len(glyf))

    loca_bytes = b''.join(struct.pack('>I', v) for v in loca)
    n = len(subset_gids) + 1

    head = bytearray(54)
    struct.pack_into('>i', head, 0, 0x00010000)
    struct.pack_into('>I', head, 12, 0x5F0F3CF5)
    struct.pack_into('>H', head, 18, font.units_per_em)
    struct.pack_into('>h', head, 50, 1)          # indexToLocFormat = long
    maxp = bytearray(32)
    struct.pack_into('>i', maxp, 0, 0x00010000)
    struct.pack_into('>H', maxp, 4, n)

    post = struct.pack('>iihhIIIII', 0x00030000, 0, 0, 0, 0, 0, 0, 0, 0)

    # cmap：unicode -> 子集 CID
    pairs = [(cp, new_gid[g]) for cp, g in desired.items() if g in new_gid]
    cmap = _cmap_cid(pairs)

    tables = {
        b'cmap': cmap,
        b'glyf': bytes(glyf),
        b'head': bytes(head),
        b'hhea': _hhea(font, n),
        b'hmtx': _hmtx(font, [0] + subset_gids),
        b'loca': loca_bytes,
        b'maxp': bytes(maxp),
        b'post': post,
    }

    tags = sorted(tables.keys())
    num_tables = len(tags)
    search_range = 16 * (2 ** ((num_tables.bit_length() - 1)))
    entry_selector = search_range.bit_length() - 5 if search_range else 0
    range_shift = num_tables * 16 - search_range

    header = struct.pack('>IHHHH', 0x00010000, num_tables, search_range, entry_selector, range_shift)
    offset = 12 + num_tables * 16
    directory = bytearray()
    body = bytearray()
    for tag in tags:
        payload = tables[tag]
        padded = payload + (b'\x00' * ((4 - len(payload) % 4) % 4))
        directory += tag + struct.pack('>III', 0, offset + len(body), len(payload))
        body += padded

    fontfile = header + bytes(directory) + bytes(body)

    cp2new = {}
    for cp, old in desired.items():
        if old in new_gid:
            cp2new[cp] = new_gid[old]
    return fontfile, cp2new, n
