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

    # ---------------------- 字体（内嵌完整字体） ---------------------- *
    # 说明：早期版本用自制的 TrueType 子集（重排字形编号），在某些阅读器里出现
    # “字形错位”——文字位置和数量都对，但显示成无关的拉丁字母。原因是子集字体的
    # glyf/loca 表与 PDF 声明的 CID 对不上。现在改为内嵌**完整字体文件**：
    # CID 直接等于字体本身的 glyph id，配 /CIDToGIDMap /Identity，
    # 映射关系由字体文件保证，不可能错位。代价是文件变大（约 10MB），但绝对可靠。
    # ------------------------------------------------------------------
    def add_font(self, ttf_path, font_index, chars, ps_name='SubFont', bold=False):
        font = TrueTypeFont(ttf_path, font_index)

        # unicode -> 原字体 glyph id（原样保留，不重排）
        cp2gid = {}
        for ch in set(chars):
            cp = ord(ch)
            if cp <= 31:
                continue
            gid = font.cmap.get(cp)
            if gid:
                cp2gid[cp] = gid
        cp2gid[32] = font.cmap.get(32, 0) or cp2gid.get(32, 0)
        # 记录字体里缺字形的字符：这些字符会渲染成空白/方块，必须显式报出来而不是静默忽略
        missing = [ch for ch in sorted(set(chars)) if ord(ch) > 31 and ord(ch) not in font.cmap]

        fontfile = open(ttf_path, 'rb').read()

        flags = 4 | 32 | (1 << 18) if bold else 4 | 32
        bbox = [0, -200, 1000, 900]
        scale = 1000.0 / font.units_per_em
        ascent = int(font.ascent * scale)
        descent = int(font.descent * scale)
        cap = int(ascent * 0.7)

        fontfile_num = self.add_stream(fontfile, '/Length1 %d' % len(fontfile))

        # /W 只列用到的字形宽度（c 形式：起始 CID + [宽度...]），其余走 /DW
        used = sorted(set(cp2gid.values()) | {0})
        w_parts = []
        for g in used:
            w_parts.append('%d [%d]' % (g, int(font.advance(g))))
        w_array = ' '.join(w_parts)

        descriptor = (
            '<< /Type /FontDescriptor /FontName /%s /Flags %d '
            '/FontBBox [%d %d %d %d] /ItalicAngle 0 /Ascent %d /Descent %d /CapHeight %d '
            '/StemV %d /FontFile2 %d 0 R >>'
            % (ps_name, flags, bbox[0], bbox[1], bbox[2], bbox[3], ascent, descent, cap,
               120 if bold else 80, fontfile_num)
        )
        desc_num = self.add_obj(descriptor.encode('ascii'))
        cidfont = (
            '<< /Type /Font /Subtype /CIDFontType2 /BaseFont /%s '
            '/CIDSystemInfo << /Registry (Adobe) /Ordering (Identity) /Supplement 0 >> '
            '/FontDescriptor %d 0 R /DW 1000 /W [%s] /CIDToGIDMap /Identity >>'
            % (ps_name, desc_num, w_array)
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
            'gid2adv': {g: font.advance(g) for g in used},
            'units': font.units_per_em,
            'missing': missing,
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
        """ops 可以是：
        - 字符串列表：按给定顺序输出；
        - (图层, 指令) 列表：先按图层号排序再输出。

        为什么要分层：PDF 的绘制顺序 = 指令顺序，**后画的会盖住先画的**。
        早期版本没分层，导致“先画文字、后画浅色底框”把引用文字整块盖没了。
        现在背景统一用 LAYER_BG、正文用 LAYER_TEXT，输出时自动保证背景在下。
        """
        if ops and isinstance(ops[0], (tuple, list)):
            ordered = [op for _, op in sorted(ops, key=lambda t: t[0])]
        else:
            ordered = list(ops)
        content = '\n'.join(ordered)
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
# 图层：数字小的先输出（先画的在下面）。背景/色块必须早于文字，
# 否则色块会盖住文字 —— 这个坑真实发生过（引用块把整段引用文字盖没了）。
LAYER_BG = 0      # 背景色块、色条
LAYER_RULE = 1    # 分割线、时间轴
LAYER_TEXT = 2    # 所有文字


class Doc:
    def __init__(self, builder, fonts, margin=48):
        self.b = builder
        self.fonts = fonts
        self.margin = margin
        self.ops = []          # [(layer, op)]
        self.y = builder.height - margin
        self.width = builder.width - 2 * margin

    def set_y(self, y):
        self.y = y

    def _add(self, layer, op):
        self.ops.append((layer, op))

    def line(self, x1, y1, x2, y2, color=(0.85, 0.88, 0.92), w=0.7, layer=LAYER_RULE):
        self._add(layer, 'q %.3f %.3f %.3f RG %.2f w %.2f %.2f m %.2f %.2f l S Q'
                  % (color[0], color[1], color[2], w, x1, y1, x2, y2))

    def rect(self, x, y, w, h, color=(0.93, 0.95, 0.99), radius=0, layer=LAYER_BG):
        self._add(layer, 'q %.3f %.3f %.3f rg %.2f %.2f %.2f %.2f re f Q'
                  % (color[0], color[1], color[2], x, y, w, h))

    def text(self, s, size=10.5, font='R', color=(0.12, 0.16, 0.22), x=None, align='left',
             max_width=None, force_width=None, line_gap=1.42, indent=0):
        """写一段文字；可自动换行（CJK 逐字断行，ASCII 尽量整词）。

        返回 (first_baseline, last_baseline, next_y)：
        调用方可以用 first/last 精确地把背景框套在文字外面，
        不必靠“猜行数 × 行距”来估算（估错就会出现背景压住文字的重叠）。
        """
        f = self.fonts[font]
        if x is None:
            x = self.margin
        avail = max_width if max_width else (self.width - (x - self.margin))
        lines = self._wrap(s, f, size, avail)
        first = None
        last = None
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
            self._add(LAYER_TEXT,
                      'BT /%s %.2f Tf %.2f Tz %.3f %.3f %.3f rg 1 0 0 1 %.2f %.2f Tm <%s> Tj ET'
                      % (font, size, scale, color[0], color[1], color[2], tx, self.y, enc.hex().upper()))
            if first is None:
                first = self.y
            last = self.y
            self.y -= size * line_gap
        return first, last, self.y

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
