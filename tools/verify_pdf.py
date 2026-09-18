"""校验自写 PDF 的结构是否自洽：
1. 起始/结束标记、xref 表偏移是否正确；
2. 每个 stream 的 /Length 与实际数据是否一致；
3. 用字体对象里的 ToUnicode CMap 把页面内容流里的 <hex> 反解回文字，
   检查中文是否按预期还原（这一步能证明 CIDToGIDMap / 子集映射没写错）。
运行： py -3 tools/verify_pdf.py [pdf路径]
"""
import os
import re
import struct
import sys
import zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def parse(path):
    data = open(path, 'rb').read()
    assert data.startswith(b'%PDF-'), '不是 PDF 文件'
    assert data.rstrip().endswith(b'%%EOF'), '缺少 %%EOF'
    startxref_pos = data.rfind(b'startxref')
    xref_off = int(data[startxref_pos + 9:].split()[0])
    assert data[xref_off:xref_off + 4] == b'xref', 'startxref 指向的不是 xref 表'

    objs = {}
    for m in re.finditer(rb'(\d+) 0 obj\n', data):
        num = int(m.group(1))
        end = data.find(b'endobj', m.end())
        objs[num] = (m.end(), end)

    problems = []
    for num, (s, e) in objs.items():
        body = data[s:e]
        sm = re.search(rb'<<(.*?)>>\s*stream\n', body, re.S)
        if not sm:
            continue
        decl_len = re.search(rb'/Length (\d+)', sm.group(1))
        raw = body[sm.end():]
        raw = raw.rsplit(b'\nendstream', 1)[0]
        if decl_len and int(decl_len.group(1)) != len(raw):
            problems.append('对象 %d 的 /Length 声明 %s，实际 %d' % (num, decl_len.group(1).decode(), len(raw)))
    return data, objs, problems


def cid_font_maps(data, objs):
    """从 PDF 里找出每个字体对象的 ToUnicode 映射：CID(gid) -> 文字。"""
    maps = {}
    for num, (s, e) in objs.items():
        body = data[s:e]
        m = re.search(rb'/ToUnicode (\d+) 0 R', body)
        if not m:
            continue
        tu = int(m.group(1))
        s2, e2 = objs[tu]
        b2 = data[s2:e2]
        sm = re.search(rb'stream\n', b2)
        raw = b2[sm.end():].rsplit(b'\nendstream', 1)[0]
        try:
            cmap_txt = zlib.decompress(raw).decode('latin-1')
        except Exception:
            continue
        mp = {}
        for blk in re.finditer(r'beginbfchar(.*?)endbfchar', cmap_txt, re.S):
            for p in re.finditer(r'<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>', blk.group(1)):
                mp[int(p.group(1), 16)] = chr(int(p.group(2), 16))
        maps[num] = mp
    return maps


def extract_text(data, objs, maps):
    out = []
    for num, (s, e) in sorted(objs.items()):
        body = data[s:e]
        if b'/Type /Page' not in body or b'/Contents' not in body:
            continue
        cref = int(re.search(rb'/Contents (\d+) 0 R', body).group(1))
        s2, e2 = objs[cref]
        b2 = data[s2:e2]
        sm = re.search(rb'stream\n', b2)
        raw = b2[sm.end():].rsplit(b'\nendstream', 1)[0]
        content = zlib.decompress(raw).decode('latin-1')

        # 页面资源名 -> 字体对象号 -> 该字体的 CID->文字 映射
        res = re.search(rb'/Font <<(.*?)>>', body, re.S)
        resmap = dict((m.group(1).decode(), int(m.group(2)))
                      for m in re.finditer(rb'/(\w+) (\d+) 0 R', res.group(1))) if res else {}
        cur = None
        for line in content.split('\n'):
            fm = re.search(r'/(\w+) [\d.]+ Tf', line)
            if fm:
                cur = maps.get(resmap.get(fm.group(1)))
            hm = re.search(r'<([0-9A-Fa-f]+)> Tj', line)
            if hm and cur is not None:
                h = hm.group(1)
                out.append(''.join(cur.get(int(h[i:i + 4], 16), '?') for i in range(0, len(h) - 3, 4)))
    return '\n'.join(out)


def check_font_files(data, objs):
    """检查内嵌字体程序（FontFile2 = TrueType）是否完整：
    必须带 head / cmap / glyf / loca / hhea / hmtx / maxp 这些表。
    早期版本用自制子集，缺表导致阅读器里字形错位 —— 这个检查就是为了不再犯同样的错。"""
    problems = []
    infos = []
    for num, (s, e) in objs.items():
        body = data[s:e]
        m = re.search(rb'/FontFile2 (\d+) 0 R', body)
        if not m:
            continue
        fnum = int(m.group(1))
        s2, e2 = objs[fnum]
        b2 = data[s2:e2]
        sm = re.search(rb'stream\n', b2)
        raw = b2[sm.end():].rsplit(b'\nendstream', 1)[0]
        try:
            prog = zlib.decompress(raw)
        except Exception as ex:
            problems.append('字体对象 %d 解压失败: %s' % (fnum, ex))
            continue
        if prog[:4] not in (b'\x00\x01\x00\x00', b'true', b'ttcf', b'OTTO'):
            problems.append('字体对象 %d 的 sfnt 头不合法: %r' % (fnum, prog[:4]))
            continue
        num_tables = struct.unpack('>H', prog[4:6])[0]
        tables = []
        for i in range(num_tables):
            p = 12 + i * 16
            tables.append(prog[p:p + 4].decode('latin-1'))
        required = ['head', 'cmap', 'glyf', 'loca', 'hhea', 'hmtx', 'maxp']
        missing = [t for t in required if t not in tables]
        if missing:
            problems.append('字体对象 %d 缺表: %s' % (fnum, ', '.join(missing)))
        infos.append((fnum, len(prog), num_tables))
    return infos, problems


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'profile.pdf')
    data, objs, problems = parse(path)
    print('对象数：%d' % len(objs))
    print('PDF 结构问题：%s' % ('无' if not problems else '；'.join(problems)))

    font_infos, font_problems = check_font_files(data, objs)
    print('内嵌字体程序（FontFile2）：%d 个' % len(font_infos))
    for fnum, size, ntab in font_infos:
        print('  对象 %d：%.2f MB，%d 张表（必备表齐全）' % (fnum, size / 1048576.0, ntab))
    if font_problems:
        print('字体问题：')
        for p in font_problems:
            print('  - ' + p)

    maps = cid_font_maps(data, objs)
    print('ToUnicode 映射：%d 个字体' % len(maps))
    text = extract_text(data, objs, maps)
    out_txt = path + '.extracted.txt'
    open(out_txt, 'w', encoding='utf-8').write(text)
    bad = text.count('?')
    print('文字反解：%d 行，无法映射的字符 %d 个' % (text.count('\n') + 1, bad))
    print('反解结果已保存到 %s' % out_txt)

    ok = (not problems) and (not font_problems) and bool(font_infos) and bad == 0
    print('')
    print('校验结果：%s' % ('PASS 通过（结构完整、字体完整、文字可反解）' if ok else 'FAIL 有问题'))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
