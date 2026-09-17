"""极简 PDF 生成器 + TrueType 子集内嵌（只用标准库）。
之所以自己写：本机没有 reportlab / fpdf，Edge 无头在沙箱里跑不起来（命名管道被限制），
所以直接按 PDF 规范手工拼对象，并把中文字体做成真子集嵌进去，保证任何阅读器都能正常显示。
"""
import struct
import zlib
from fontkit import TrueTypeFont, build_subset


class PdfBuilder:
    def __init__(self, width=595.28, height=841.89):
        self.width = width
        self.height = height
        self.objects = {}      # obj num -> bytes 内容
        self.next_num = 1
        self.pages = []

    # ------------------------------ 底层 ------------------------------
    def _alloc(self):
        n = self.next_num
        self.next_num += 1
        return n

    def add_obj(self, payload):
        n = self._alloc()
        self.objects[n] = payload
        return n

    def add_stream(self, data, extra=''):
        if isinstance(data, str):
            data = data.encode('latin-1')
        comp = zlib.compress(data)
        head = ('<< /Length %d /Filter /FlateDecode %s>>\n' % (len(comp), extra)).encode('ascii')
        return self.add_obj(head + b'stream\n' + comp + b'\nendstream')

    # --------------------------- 字体（子集） ---------------------------
    def add_font(self, ttf_path, font_index, chars, ps_name='SubFont', bold=False):
        font = TrueTypeFont(ttf_path, font_index)
        unicodes = set(ord(c) for c in chars if ord(c) > 31)
        unicodes.add(32)
        fontfile, cp2gid, num_glyphs = build_subset(font, unicodes, name=ps_name)

        flags = 4 | 32 | (1 << 18) if bold else 4 | 32
        bbox = [0, -200, 1000, 900]
        scale = 1000.0 / font.units_per_em
        ascent = int(font.ascent * scale)
        descent = int(font.descent * scale)
        cap = int(ascent * 0.7)

        cid2gid = bytes(bytearray().join(struct.pack('>H', g) for g in ([0] + sorted(cp2gid.values()))))
        # 注意：CID = 子集 gid，因此 CIDToGIDMap 可以是恒等映射 -> 用 /Identity
        fontfile_num = self.add_stream(fontfile, '/Length1 %d' % len(fontfile))
        # CIDSet：声明子集里实际用到哪些 CID（PDF/A 与部分严格阅读器要求）
        n_bytes = (num_glyphs + 7) // 8
        bits = bytearray(n_bytes)
        for g in cp2gid.values():
            bits[g >> 3] |= (0x80 >> (g & 7))
        bits[0] |= 0x80   # .notdef 也算
        cidset_num = self.add_stream(bytes(bits))
        descriptor = (
            '<< /Type /FontDescriptor /FontName /%s /Flags %d '
            '/FontBBox [%d %d %d %d] /ItalicAngle 0 /Ascent %d /Descent %d /CapHeight %d '
            '/StemV %d /FontFile2 %d 0 R /CIDSet %d 0 R >>'
            % (ps_name, flags, bbox[0], bbox[1], bbox[2], bbox[3], ascent, descent, cap,
               120 if bold else 80, fontfile_num, cidset_num)
        )
        desc_num = self.add_obj(descriptor.encode('ascii'))
        cidfont = (
            '<< /Type /Font /Subtype /CIDFontType2 /BaseFont /%s '
            '/CIDSystemInfo << /Registry (Adobe) /Ordering (Identity) /Supplement 0 >> '
            '/FontDescriptor %d 0 R /DW 1000 /W [0 [%s]] /CIDToGIDMap /Identity >>'
            % (ps_name, desc_num, ' '.join(str(int(font.advance(g))) for g in range(num_glyphs)))
        )
        cid_num = self.add_obj(cidfont.encode('ascii'))
        tounicode = self._tounicode_cmap(cp2gid)
        tu_num = self.add_stream(tounicode)
        font_num = self.add_obj(
            ('<< /Type /Font /Subtype /Type0 /BaseFont /%s /Encoding /Identity-H '
             '/DescendantFonts [%d 0 R] /ToUnicode %d 0 R >>' % (ps_name, cid_num, tu_num)).encode('ascii')
        )
        return {
            'obj': font_num,
            'cp2gid': cp2gid,
            'gid2adv': {g: font.advance(g) for g in range(num_glyphs)},
            'units': font.units_per_em,
        }

    def _tounicode_cmap(self, cp2gid):
        pairs = sorted((gid, cp) for cp, gid in cp2gid.items())
        lines = ['/CIDInit /ProcSet findresource begin', '12 dict begin', 'begincmap',
                 '/CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def',
                 '/CMapName /Adobe-Identity-UCS def', '/CMapType 2 def',
                 '1 begincodespacerange', '<0000> <FFFF>', 'endcodespacerange']
        chunk = 100
        for i in range(0, len(pairs), chunk):
            part = pairs[i:i + chunk]
            lines.append('%d beginbfchar' % len(part))
            for gid, cp in part:
                dst = cp if cp <= 0xFFFF else 0xFFFD
                lines.append('<%04X> <%04X>' % (gid, dst))
            lines.append('endbfchar')
        lines += ['endcmap', 'CMapName currentdict /CMap defineresource pop', 'end', 'end']
        return '\n'.join(lines)

    # ---------------------------- 页面内容 ----------------------------
    def text_width(self, font, s, size):
        w = 0.0
        for ch in s:
            gid = font['cp2gid'].get(ord(ch), 0)
            w += font['gid2adv'].get(gid, 1000)
        return w * size / 1000.0

    def _encode(self, font, s):
        out = bytearray()
        for ch in s:
            gid = font['cp2gid'].get(ord(ch), 0)
            out += struct.pack('>H', gid)
        return bytes(out)

    def add_page(self, ops):
        """ops 是内容流字符串列表（已含坐标）。"""
        content = '\n'.join(ops)
        c_num = self.add_stream(content.encode('latin-1'))
        font_res = self._font_resources()
        page = ('<< /Type /Page /Parent %d 0 R /MediaBox [0 0 %.2f %.2f] '
                '/Resources << /Font << %s >> >> /Contents %d 0 R >>'
                % (self._pages_num(), self.width, self.height, font_res, c_num))
        p = self.add_obj(page.encode('ascii'))
        self.pages.append(p)
        return p

    def _font_resources(self):
        return ' '.join('/%s %d 0 R' % (name, f['obj']) for name, f in self.fonts.items())

    def _pages_num(self):
        if not hasattr(self, '_pages_obj'):
            self._pages_obj = self._alloc()
        return self._pages_obj

    def use_fonts(self, fonts):
        self.fonts = fonts

    def save(self, path):
        pages_obj = self._pages_num()
        kids = ' '.join('%d 0 R' % p for p in self.pages)
        self.objects[pages_obj] = ('<< /Type /Pages /Count %d /Kids [%s] >>'
                                   % (len(self.pages), kids)).encode('ascii')
        catalog = self.add_obj(('<< /Type /Catalog /Pages %d 0 R >>' % pages_obj).encode('ascii'))
        max_num = max(self.objects)
        buf = bytearray(b'%PDF-1.7\n%\xe2\xe3\xcf\xd3\n')
        offsets = {}
        for n in sorted(self.objects):
            offsets[n] = len(buf)
            buf += ('%d 0 obj\n' % n).encode('ascii') + self.objects[n] + b'\nendobj\n'
        xref_pos = len(buf)
        buf += ('xref\n0 %d\n' % (max_num + 1)).encode('ascii')
        buf += b'0000000000 65535 f \n'
        for n in range(1, max_num + 1):
            if n in offsets:
                buf += ('%010d 00000 n \n' % offsets[n]).encode('ascii')
            else:
                buf += b'0000000000 65535 f \n'
        buf += ('trailer\n<< /Size %d /Root %d 0 R >>\nstartxref\n%d\n%%%%EOF\n'
                % (max_num + 1, catalog, xref_pos)).encode('ascii')
        open(path, 'wb').write(bytes(buf))
        return path


# ============================ 文本布局助手 ============================
class Doc:
    def __init__(self, builder, fonts, margin=48):
        self.b = builder
        self.fonts = fonts
        self.margin = margin
        self.ops = []
        self.y = builder.height - margin
        self.width = builder.width - 2 * margin

    def set_y(self, y):
        self.y = y

    def line(self, x1, y1, x2, y2, color=(0.85, 0.88, 0.92), w=0.7):
        self.ops.append('q %.3f %.3f %.3f RG %.2f w %.2f %.2f m %.2f %.2f l S Q'
                        % (color[0], color[1], color[2], w, x1, y1, x2, y2))

    def rect(self, x, y, w, h, color=(0.93, 0.95, 0.99), radius=0):
        self.ops.append('q %.3f %.3f %.3f rg %.2f %.2f %.2f %.2f re f Q'
                        % (color[0], color[1], color[2], x, y, w, h))

    def text(self, s, size=10.5, font='R', color=(0.12, 0.16, 0.22), x=None, align='left',
             max_width=None, force_width=None, line_gap=1.42, indent=0):
        """写一段文字；可自动换行（CJK 逐字断行，ASCII 尽量整词）。"""
        f = self.fonts[font]
        if x is None:
            x = self.margin
        avail = max_width if max_width else (self.width - (x - self.margin))
        lines = self._wrap(s, f, size, avail)
        for ln in lines:
            w = self.text_w(ln, f, size)
            if force_width:
                scale = 100.0 * force_width / w if w > 0 else 100.0
                tx = x
            else:
                scale = 100.0
                if align == 'center':
                    tx = x + (avail - w) / 2.0
                elif align == 'right':
                    tx = x + avail - w
                else:
                    tx = x + indent
            enc = self.b._encode(f, ln)
            self.ops.append(
                'BT /%s %.2f Tf %.2f Tz %.3f %.3f %.3f rg 1 0 0 1 %.2f %.2f Tm <%s> Tj ET'
                % (font, size, scale, color[0], color[1], color[2], tx, self.y, enc.hex().upper())
            )
            self.y -= size * line_gap
        return self.y

    def text_w(self, s, f, size):
        return self.b.text_width(f, s, size)

    def _wrap(self, s, f, size, avail):
        out = []
        for para in s.split('\n'):
            if not para:
                out.append('')
                continue
            cur = ''
            i = 0
            while i < len(para):
                ch = para[i]
                # ASCII 单词尽量不拆开
                token = ch
                if ord(ch) < 128 and (ch.isalnum() or ch in '-_./@:'):
                    j = i
                    while j < len(para) and ord(para[j]) < 128 and (para[j].isalnum() or para[j] in '-_./@:'):
                        j += 1
                    token = para[i:j]
                    i = j
                else:
                    i += 1
                if self.text_w(cur + token, f, size) <= avail:
                    cur += token
                else:
                    if cur:
                        out.append(cur)
                    cur = token
            if cur:
                out.append(cur)
        return out or ['']
