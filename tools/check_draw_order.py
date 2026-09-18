"""检查 PDF 内容流里的绘制顺序：所有色块/线条必须早于文字出现。

为什么需要这个检查：PDF 的绘制顺序就是指令顺序，后画的会盖住先画的。
曾经因为“先画引用文字、后画浅蓝底框”，整段引用文字被色块盖没了。
运行： py -3 tools/check_draw_order.py
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

    ok = True
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

        last_shape = -1      # 最后一个色块/线条的指令序号
        first_text = None    # 第一个文字的指令序号
        late_shapes = []     # 出现在文字之后的色块
        for i, ln in enumerate(content.split('\n')):
            is_text = ' Tm ' in ln and ' Tj ' in ln
            is_shape = (' re f ' in ln) or (' l S ' in ln)
            if is_shape:
                last_shape = i
                if first_text is not None:
                    late_shapes.append((i, ln[:70]))
            elif is_text and first_text is None:
                first_text = i

        print('页面 %d：%d 条指令；最后一个图形在第 %d 条，第一个文字在第 %s 条'
              % (num, len(content.split('\n')), last_shape, first_text))
        if late_shapes:
            ok = False
            print('  [FAIL] 有 %d 个色块/线条画在文字之后（会盖住文字）：' % len(late_shapes))
            for i, ln in late_shapes[:5]:
                print('     第 %d 条：%s' % (i, ln))
        else:
            print('  [OK] 所有色块与线条都在文字之前绘制，不会遮挡文字')

    print('')
    print('绘制顺序检查：%s' % ('PASS 通过' if ok else 'FAIL 有问题'))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
