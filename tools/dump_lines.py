"""打印 PDF 里每一行文字的 y 坐标与内容（用 ToUnicode 反解），用于精确排查版面。
运行： py -3 tools/dump_lines.py
"""
import os
import re
import sys
import zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, 'profile.pdf')
    data = open(path, 'rb').read()
    objs = {}
    for m in re.finditer(rb'(\d+) 0 obj\n', data):
        objs[int(m.group(1))] = (m.end(), data.find(b'endobj', m.end()))

    # 字体对象 -> ToUnicode 映射
    maps = {}
    for num, (s, e) in objs.items():
        body = data[s:e]
        m = re.search(rb'/ToUnicode (\d+) 0 R', body)
        if not m:
            continue
        s2, e2 = objs[int(m.group(1))]
        b2 = data[s2:e2]
        sm = re.search(rb'stream\n', b2)
        raw = b2[sm.end():].rsplit(b'\nendstream', 1)[0]
        txt = zlib.decompress(raw).decode('latin-1')
        mp = {}
        for blk in re.finditer(r'beginbfchar(.*?)endbfchar', txt, re.S):
            for p in re.finditer(r'<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>', blk.group(1)):
                mp[int(p.group(1), 16)] = chr(int(p.group(2), 16))
        maps[num] = mp

    rows = []
    for num, (s, e) in sorted(objs.items()):
        body = data[s:e]
        if b'/Type /Page' not in body or b'/Contents' not in body:
            continue
        res = re.search(rb'/Font <<(.*?)>>', body, re.S)
        resmap = dict((m.group(1).decode(), int(m.group(2)))
                      for m in re.finditer(rb'/(\w+) (\d+) 0 R', res.group(1)))
        cref = int(re.search(rb'/Contents (\d+) 0 R', body).group(1))
        s2, e2 = objs[cref]
        b2 = data[s2:e2]
        sm = re.search(rb'stream\n', b2)
        raw = b2[sm.end():].rsplit(b'\nendstream', 1)[0]
        content = zlib.decompress(raw).decode('latin-1')
        cur = None
        for line in content.split('\n'):
            fm = re.search(r'/(\w+) ([\d.]+) Tf', line)
            if fm:
                cur = maps.get(resmap.get(fm.group(1)))
                fname = fm.group(1)
            tm = re.search(r'1 0 0 1 ([\d.]+) ([\d.]+) Tm <([0-9A-Fa-f]+)> Tj', line)
            if tm and cur:
                h = tm.group(3)
                text = ''.join(cur.get(int(h[i:i + 4], 16), '?') for i in range(0, len(h) - 3, 4))
                rows.append((float(tm.group(2)), float(tm.group(1)), fname, text))

    rows.sort()
    for y, x, fname, text in rows:
        print('y=%7.2f x=%6.2f [%s] %s' % (y, x, fname, text[:64]))


if __name__ == '__main__':
    main()
