"""从生成的 PDF 里把所有文字/线条的 y 坐标抽出来，检查有没有越界或与页脚重叠。
（自己写的版面调试工具；沙箱里没有 pdftoppm 之类的渲染器，就用几何校验代替肉眼看图。）
运行： py -3 tools/check_layout.py
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
        box = re.search(rb'/MediaBox \[0 0 ([\d.]+) ([\d.]+)\]', body)
        pw, ph = float(box.group(1)), float(box.group(2))
        cref = int(re.search(rb'/Contents (\d+) 0 R', body).group(1))
        s2, e2 = objs[cref]
        b2 = data[s2:e2]
        sm = re.search(rb'stream\n', b2)
        raw = b2[sm.end():].rsplit(b'\nendstream', 1)[0]
        content = zlib.decompress(raw).decode('latin-1')

        ys, lines, rects = [], [], []
        for line in content.split('\n'):
            for m in re.finditer(r'([\d.]+) ([\d.]+) Tm', line):
                ys.append(float(m.group(2)))
            for m in re.finditer(r'([\d.-]+) ([\d.-]+) m ([\d.-]+) ([\d.-]+) l S', line):
                lines.append(tuple(float(m.group(i)) for i in range(1, 5)))
            for m in re.finditer(r'([\d.-]+) ([\d.-]+) ([\d.-]+) ([\d.-]+) re f', line):
                rects.append(tuple(float(m.group(i)) for i in range(1, 5)))

        print('页面 %d：%.1f x %.1f，文字行数 %d，线段 %d，矩形 %d'
              % (num, pw, ph, len(ys), len(lines), len(rects)))
        print('  文字最低基线 y=%.1f（越小越靠下），最高 y=%.1f' % (min(ys), max(ys)))
        print('  矩形最低边 y=%.1f' % min(r[1] for r in rects))
        # 页脚横线：y 相同的水平线
        horiz = [l for l in lines if abs(l[1] - l[3]) < 0.01]
        if horiz:
            foot = min(horiz, key=lambda l: l[1])
            print('  最低水平线 y=%.1f（页脚线）' % foot[1])
        top3 = sorted(ys)[:3]
        print('  最低的 3 个文字基线：%s' % ', '.join('%.1f' % v for v in top3))
    return 0


if __name__ == '__main__':
    sys.exit(main())
