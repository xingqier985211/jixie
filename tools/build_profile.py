"""生成个人简介 PDF（纯 Python 手写 PDF + 内嵌中文字体子集）。
运行： py -3 tools/build_profile.py
输出： profile.pdf

排版要点：
- 页面 A4（595.3 x 841.9），左右页边距 MARGIN，页脚固定在页面底部；
- 所有字号/行距/间距集中在下面的“布局常量”，改松紧只动这几个数字；
- 正文块的实际行数会打印出来（layout report），便于确认有没有溢出。
- 汉字必须全部收集进字体子集，否则会缺字（曾经漏掉粗体标题导致标题空白）。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pdfkit_lite import PdfBuilder, Doc

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
YAHEI = r'C:\Windows\Fonts\msyh.ttc'
ARIAL = r'C:\Windows\Fonts\arial.ttf'
ARIAL_BD = r'C:\Windows\Fonts\arialbd.ttf'
MONO = r'C:\Windows\Fonts\consola.ttf'

# ------------------------------- 内容 ---------------------------------
NAME = '丁其炼'
SUB = '集成电路设计与集成系统  ·  个人简介'

INFO = [
    ('姓　　名', '丁其炼'),
    ('专　　业', '集成电路设计与集成系统'),
    ('联系方式', '18344216623'),
    ('爱　　好', '羽毛球、音乐'),
    ('GitHub', 'github.com/xingqier985211'),
    ('个人主页', 'xingqier985211.github.io/jixie'),
]

INTRO = [
    '我是丁其炼，就读于集成电路设计与集成系统专业。我的专业基础是从零开始的，刚接触这个方向时，很多概念对'
    '我来说都很陌生。但我不打算停在“不会”这一步：我愿意花时间去补，把不懂的问题一个个啃下来，一步一步学习、'
    '一步步成长，把每一次“不会”都变成“会了”。',

    '做法上我习惯从最小的闭环开始：先让东西真正跑起来，再回头补原理、加功能。这次用 AI 工具做 2048，我先做出'
    '能玩的版本，再一行行读懂 AI 生成的关键代码——方块的合并顺序、AI 的评分函数与搜索逻辑；接着补上计分制、'
    '主题切换、多局战绩；最后写脚本让 AI 自己跑上百局，用数据确认它确实能稳定合出 1024。',

    '这个过程让我认识到：用 AI 做出东西很快，但只有自己能讲清楚“为什么这样写”，做出来的东西才真正属于自己。'
    '这也正是我选择把每一步过程都记录下来的原因。',
]

QUOTE = ('我是零基础起步，但我相信成长来自持续的努力：今天比昨天多懂一点，把每一步走扎实，'
         '就一定能走到想去的地方。')

TAGS = ['羽毛球', '音乐', '耐心能坚持', '喜欢把问题弄明白', '愿意动手实践']
TAG_TEXT = ('打羽毛球让我习惯了“反复练习—纠正动作—再练习”的节奏，这和学专业、写代码其实是一件事；'
            '音乐则是我卡住时让自己安静下来的方式。进步不靠一次用力，而靠一直不停。')

JOURNEY = [
    ('环境与工具', '注册并管理 GitHub 仓库，熟悉 Git 的提交、分支、合并，以及 cd / ls / mkdir 等命令行基础操作，'
                   '把仓库、分支、提交这些东西先弄明白。'),
    ('第一个作品', '用纯前端 HTML/CSS/JS 做出可玩的 2048：得分与最高分、胜负判定、撤销、键盘与触屏操作，'
                   '外加计分制、主题切换、多局战绩三个增强功能。'),
    ('让 AI 来玩', '实现 Expectimax + α-β 剪枝的自动对局（随机层按 90%/10% 求期望），'
                   '并用无头脚本批量跑局：10 局里 1024 达成 10/10、2048 达成 7/10。'),
    ('讲清为什么', '在 README 里记录提示词迭代、关键代码逻辑、查证 AI 错误信息的过程与踩坑总结，'
                   '确保每一处代码自己都能说明白。'),
]

END = '希望有机会加入协会，在真实的项目里继续学、继续做，也想和同样喜欢动手的同学一起把东西做出来。'

# 作品小节
WORK_TITLE = '2048 小游戏（纯前端单文件）'
WORK_URL = 'xingqier985211.github.io/jixie/2048/2048.html'
WORK_TEXT = ('阶段一：键盘 / 触屏可玩，含得分与最高分、胜负判定、撤销，并实现了计分制、主题切换、多局战绩三个增强功能。'
             '阶段二：Expectimax + α-β 剪枝的 AI 自动对局，实测 10 局中 1024 达成 10/10、2048 达成 7/10。')

# 布局常量：想调松紧只改这里
S_BODY = 10.5        # 正文字号
S_TITLE = 12.5      # 小节标题
S_NAME = 25.0       # 姓名
S_SUB = 10.4
S_INFO = 9.9
S_FOOT = 8.6
LH_BODY = 1.55      # 正文行距倍数
GAP_SECTION = 14.0  # 小节前留白
GAP_SECTION_AFTER = 4.5
GAP_BLOCK = 4.5     # 段落后留白
INFO_ROW_H = 15.0
MARGIN = 46         # 左右页边距
FOOT_LINE_Y = 72    # 页脚横线
FOOT_TEXT_Y = 60    # 页脚文字基线

# 粗体小节标题也要收进字体子集，否则标题会缺字
TITLES = ['基本信息', '自我介绍', '兴趣与性格', '入门阶段的学习路线', '作品', '结尾的话']


def collect_chars():
    s = NAME + SUB + QUOTE + TAG_TEXT + END + WORK_TITLE + WORK_TEXT + ''.join(TITLES) + '“”　'
    for k, v in INFO:
        s += k + v
    s += ''.join(INTRO)
    s += ''.join(TAGS)
    for a, b in JOURNEY:
        s += a + b
    s += ' ·：—、。，；！？（）《》0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz'
    return s


def main():
    b = PdfBuilder()
    chars = collect_chars()
    fonts = {
        'R': b.add_font(YAHEI, 0, chars, ps_name='DQLYaHei'),
        'B': b.add_font(YAHEI, 1, chars, ps_name='DQLYaHeiBold', bold=True),
        'D': b.add_font(ARIAL, 0, chars + 'DQL', ps_name='DQLArial'),
        'E': b.add_font(ARIAL_BD, 0, chars + 'DQL', ps_name='DQLArialBold', bold=True),
        'M': b.add_font(MONO, 0, chars, ps_name='DQLMono'),
    }
    b.use_fonts(fonts)

    d = Doc(b, fonts, margin=MARGIN)
    left, right, width = d.margin, b.width - d.margin, b.width - 2 * d.margin
    report = []

    def lines_of(text, size=S_BODY, font='R', x=left):
        return len(d._wrap(text, fonts[font], size, width - (x - left)))

    def section(title, gap_before=GAP_SECTION, gap_after=GAP_SECTION_AFTER):
        d.y -= gap_before
        d.rect(left, d.y - 2.4, 3.0, S_TITLE + 1.4, color=(0.145, 0.388, 0.921))
        d.text(title, size=S_TITLE, font='B', color=(0.118, 0.227, 0.541), x=left + 9, line_gap=1.1)
        d.y -= gap_after

    # ---------------------- 页头 ----------------------
    d.y -= 2
    d.text(NAME, size=S_NAME, font='B', color=(0.118, 0.227, 0.541), line_gap=1.15)
    d.text(SUB, size=S_SUB, font='R', color=(0.42, 0.45, 0.50), line_gap=1.2)
    d.y -= 4
    d.line(left, d.y, right, d.y, color=(0.145, 0.388, 0.921), w=2.0)
    d.y -= 2

    # ---------------------- 基本信息（两列三行） ----------------------
    section('基本信息', gap_before=11, gap_after=5)
    col_w = width / 2 - 8
    start_y = d.y
    for i, (k, v) in enumerate(INFO):
        col = i % 2
        if col == 0:
            d.y = start_y - (i // 2) * INFO_ROW_H
        x = left + col * (col_w + 16)
        d.text(k, size=S_INFO, font='R', color=(0.45, 0.48, 0.53), x=x, line_gap=1.0)
        d.text(v, size=S_INFO, font='R', color=(0.10, 0.13, 0.18), x=x + 52, line_gap=1.0)
    d.y = start_y - ((len(INFO) + 1) // 2) * INFO_ROW_H
    report.append(('info rows', (len(INFO) + 1) // 2, round(d.y, 1)))

    # ---------------------- 自我介绍 ----------------------
    section('自我介绍')
    for para in INTRO:
        report.append(('intro', lines_of(para), round(d.y, 1)))
        d.text(para, size=S_BODY, font='R', color=(0.20, 0.24, 0.30), line_gap=LH_BODY)
        d.y -= GAP_BLOCK

    d.y -= 2
    report.append(('quote', lines_of(QUOTE, x=left + 14), round(d.y, 1)))
    box_top = d.y + 10
    d.text(QUOTE, size=S_BODY, font='R', color=(0.118, 0.227, 0.541), line_gap=LH_BODY, x=left + 14)
    box_h = box_top - d.y - 3
    d.rect(left, d.y - 1, width, box_h, color=(0.937, 0.965, 1.0))
    d.rect(left, d.y - 1, 3.0, box_h, color=(0.145, 0.388, 0.921))

    # ---------------------- 兴趣与性格 ----------------------
    section('兴趣与性格')
    txt = '　　'.join(TAGS)
    report.append(('tags', lines_of(txt), round(d.y, 1)))
    d.text(txt, size=S_BODY, font='R', color=(0.216, 0.192, 0.639), line_gap=LH_BODY)
    d.y -= 2
    report.append(('tagtext', lines_of(TAG_TEXT), round(d.y, 1)))
    d.text(TAG_TEXT, size=S_BODY, font='R', color=(0.20, 0.24, 0.30), line_gap=LH_BODY)

    # ---------------------- 学习路线 ----------------------
    section('入门阶段的学习路线')
    for i, (t, body) in enumerate(JOURNEY):
        d.ops.append('q 0.145 0.388 0.921 rg %.2f %.2f 3.6 3.6 re f Q' % (left + 1.6, d.y + 3.4))
        if i < len(JOURNEY) - 1:
            d.line(left + 3.4, d.y + 1.6, left + 3.4, d.y - 13.0, color=(0.80, 0.84, 0.90), w=0.8)
        d.text(t + '：', size=S_BODY, font='B', color=(0.118, 0.227, 0.541), x=left + 14, line_gap=1.1)
        report.append(('journey:' + t, lines_of(body, x=left + 14), round(d.y, 1)))
        d.text(body, size=S_BODY, font='R', color=(0.20, 0.24, 0.30), x=left + 14, line_gap=LH_BODY)
        d.y -= GAP_BLOCK

    # ---------------------- 结尾 ----------------------
    section('作品')
    d.text(WORK_TITLE + '　' + WORK_URL, size=S_BODY, font='B', color=(0.118, 0.227, 0.541), line_gap=1.2)
    report.append(('work', lines_of(WORK_TEXT), round(d.y, 1)))
    d.text(WORK_TEXT, size=S_BODY, font='R', color=(0.20, 0.24, 0.30), line_gap=LH_BODY)

    # ---------------------- 结尾 ----------------------
    section('结尾的话')
    report.append(('end', lines_of(END), round(d.y, 1)))
    d.text(END, size=S_BODY, font='R', color=(0.20, 0.24, 0.30), line_gap=LH_BODY)

    # ---------------------- 页脚（固定在页面底部，不动 d.y） ----------------------
    d.line(left, FOOT_LINE_Y, right, FOOT_LINE_Y, color=(0.87, 0.89, 0.92), w=0.7)
    save_y = d.y
    d.y = FOOT_TEXT_Y
    d.text(NAME + ' · 个人简介', size=S_FOOT, font='R', color=(0.62, 0.65, 0.69), line_gap=1.0)
    d.text('集成电路设计与集成系统', size=S_FOOT, font='R', color=(0.62, 0.65, 0.69),
           x=left, align='right', line_gap=1.0)
    d.y = save_y

    b.add_page(d.ops)
    out = os.path.join(ROOT, 'profile.pdf')
    b.save(out)

    print('--- layout report (block, lines, y_before) ---')
    for r in report:
        print('  %-24s lines=%-2s y=%.1f' % r)
    print('OK wrote %s (%.1f KB)' % (os.path.basename(out), os.path.getsize(out) / 1024.0))
    print('content bottom y=%.1f ; footer line y=%d ; footer text y=%d ; page height %.1f'
          % (d.y, FOOT_LINE_Y, FOOT_TEXT_Y, b.height))
    print('free space below content = %.1f pt' % (d.y - FOOT_LINE_Y))


if __name__ == '__main__':
    main()
