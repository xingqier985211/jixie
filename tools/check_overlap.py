"""把 PDF 里所有文字基线、矩形、线段的坐标抽出来，检查有没有互相压住。
比肉眼更可靠：直接算几何关系。
运行： py -3 tools/check_overlap.py
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

        texts = []   # (基线 y, x, 字号)
        rects = []   # (x, y, w, h)
        lines = []
        for line in content.split('\n'):
            tm = re.search(r'/R ([\d.]+) Tf .*?1 0 0 1 ([\d.]+) ([\d.]+) Tm', line)
            if tm:
                texts.append((float(tm.group(3)), float(tm.group(2)), float(tm.group(1))))
            tm2 = re.search(r'/(\w+) ([\d.]+) Tf .*?1 0 0 1 ([\d.]+) ([\d.]+) Tm', line)
            if tm2 and not tm:
                texts.append((float(tm2.group(4)), float(tm2.group(3)), float(tm2.group(2))))
            r = re.search(r'rg ([\d.-]+) ([\d.-]+) ([\d.-]+) ([\d.-]+) re f', line)
            if r:
                rects.append(tuple(float(r.group(i)) for i in range(1, 5)))
            l = re.search(r'([\d.-]+) ([\d.-]+) m ([\d.-]+) ([\d.-]+) l S', line)
            if l:
                lines.append(tuple(float(l.group(i)) for i in range(1, 5)))

        texts.sort(reverse=True)   # 从上到下
        print('页面 %d：文字 %d 行，矩形 %d 个，线段 %d 条' % (num, len(texts), len(rects), len(lines)))
        print('')
        print('  ---- 上半页与文字块的关系（从上到下）----')
        # 找出所有"比较高"的填充矩形（排除细线、色块小条）
        big = [r for r in rects if r[3] > 2]
        for (base, x, size) in texts:
            mark = ''
            for (rx, ry, rw, rh) in big:
                # 基线落在矩形内、且矩形不是那条 3pt 宽的左侧装饰条
                if rx <= x <= rx + rw and ry <= base <= ry + rh and rw > 50:
                    mark = '   ← 落在填充块 y=[%.1f, %.1f] 内' % (ry, ry + rh)
            print('  y=%7.2f x=%6.2f size=%4.1f%s' % (base, x, size, mark))
        print('')
        print('  ---- 大块填充矩形 ----')
        for (rx, ry, rw, rh) in sorted(big, key=lambda r: -r[1]):
            print('  x=%6.2f y=%7.2f w=%6.1f h=%5.1f  (y 范围 %.1f ~ %.1f)'
                  % (rx, ry, rw, rh, ry, ry + rh))
    return 0


if __name__ == '__main__':
    sys.exit(main())
