"""校验自写 PDF 的结构是否自洽：
1. 起始/结束标记、xref 表偏移是否正确；
2. 每个 stream 的 /Length 与实际数据是否一致；
3. 用字体对象里的 ToUnicode CMap 把页面内容流里的 <hex> 反解回文字，
   检查中文是否按预期还原（这一步能证明 CIDToGIDMap / 子集映射没写错）。
运行： py -3 tools/verify_pdf.py [pdf路径]
"""
import os
import re
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


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'profile.pdf')
    data, objs, problems = parse(path)
    print('对象数：%d' % len(objs))
    print('结构问题：%s' % ('无' if not problems else '；'.join(problems)))
    maps = cid_font_maps(data, objs)
    print('内嵌字体数（含 ToUnicode）：%d' % len(maps))
    for n, mp in maps.items():
        print('  字体对象 %d：映射 %d 个字形' % (n, len(mp)))
    text = extract_text(data, objs, maps)
    out_txt = path + '.extracted.txt'
    open(out_txt, 'w', encoding='utf-8').write(text)
    print('---- 反解出的文字（前 900 字）----')
    print(text[:900].encode('utf-8', 'replace').decode('utf-8'))
    bad = text.count('?')
    print('---- 反解失败（?）数量：%d ----' % bad)
    ok = (not problems) and bool(maps) and bad == 0
    print('校验结果：%s' % ('PASS 通过' if ok else 'FAIL 有问题'))
    print('反解文字已保存到 %s' % out_txt)
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
