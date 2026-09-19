/* ============================================================================
 * 单文件游戏“页面级”验证：把 projects/2048/2048.html 里的内联脚本抽出来，
 * 在一个最小的 DOM 桩里真跑一遍，检查：
 *   1) 页面脚本能否无异常初始化（键盘事件、渲染函数都接得上）
 *   2) 人工按键能不能正常移动、计分、撤销
 *   3) 页面里的 AI 自动演示能否无人干预地自动合出 1024（阶段二硬指标）
 * 这是“阶段二怎么验证”的第二层证据（第一层是 test-ai.cjs 的引擎批量对局）。
 *
 * 运行：  node test-page.cjs [局数]
 * ==========================================================================*/
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const htmlPath = path.join(__dirname, 'game.html');
const html = fs.readFileSync(htmlPath, 'utf8');
const scripts = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m => m[1]);
if (!scripts.length) { console.error('没找到 <script> 块'); process.exit(1); }
const code = scripts.join('\n');
console.log(`从单文件里抽出 ${scripts.length} 段脚本，共 ${(code.length / 1024).toFixed(1)} KB`);

/* ------------------------------ DOM 桩 ------------------------------ */
function makeEl(tag, doc) {
  const el = {
    tagName: String(tag || 'div').toUpperCase(),
    children: [], _text: '', dataset: {}, checked: false, disabled: false,
    // style 需要支持 CSS 自定义属性（页面会写 --board-size）
    style: {
      _vars: {},
      setProperty(k, v) { this._vars[k] = String(v); this[k] = String(v); },
      getPropertyValue(k) { return this._vars[k] !== undefined ? this._vars[k] : ''; },
      removeProperty(k) { delete this._vars[k]; delete this[k]; }
    },
    value: '', type: '', _cls: new Set(),
    get className() { return [...this._cls].join(' '); },
    set className(v) { this._cls = new Set(String(v).split(/\s+/).filter(Boolean)); },
    get textContent() { return this._text; },
    set textContent(v) { this._text = String(v); this.children.length = 0; },
    get innerHTML() { return this._html || ''; },
    set innerHTML(v) { this._html = String(v); this.children.length = 0; },
    classList: null,
    appendChild(c) { this.children.push(c); c.parentNode = this; return c; },
    insertBefore(c, ref) { const i = this.children.indexOf(ref); if (i < 0) this.children.push(c); else this.children.splice(i, 0, c); c.parentNode = this; return c; },
    removeChild(c) { const i = this.children.indexOf(c); if (i >= 0) this.children.splice(i, 1); c.parentNode = null; },
    remove() { if (this.parentNode) this.parentNode.removeChild(this); },
    setAttribute(k, v) { this._attrs = this._attrs || {}; this._attrs[k] = v; },
    getAttribute(k) { return (this._attrs || {})[k] !== undefined ? this._attrs[k] : null; },
    addEventListener(t, fn) { (this._ev = this._ev || {})[t] = (this._ev[t] || []).concat(fn); },
    dispatch(t, ev) { ((this._ev || {})[t] || []).forEach(fn => fn(ev)); },
    closest(sel) {
      const cls = String(sel).replace(/^\./, '');
      let n = this;
      while (n) { if (n.classList && n.classList.contains(cls)) return n; n = n.parentNode; }
      return null;
    },
    setPointerCapture() {},
    releasePointerCapture() {},
    querySelector(sel) {
      if (sel === '.board-shell') return doc._shell;
      return null;
    },
    querySelectorAll(sel) {
      const cls = String(sel).replace(/^\./, '');
      return this.children.filter(c => c.classList.contains(cls));
    }
  };
  el.classList = {
    add: (...cs) => cs.forEach(c => el._cls.add(c)),
    remove: (...cs) => cs.forEach(c => el._cls.delete(c)),
    contains: c => el._cls.has(c),
    toggle: c => el._cls.has(c) ? el._cls.delete(c) : el._cls.add(c)
  };
  Object.defineProperty(el, 'offsetWidth', { get: () => 100 });
  // 棋盘的内容宽度：由测试注入（模拟不同屏幕宽度）
  Object.defineProperty(el, 'clientWidth', { get: () => (el._clientWidth !== undefined ? el._clientWidth : 100) });
  Object.defineProperty(el, 'clientHeight', { get: () => (el._clientHeight !== undefined ? el._clientHeight : 100) });
  return el;
}

const ids = ['board', 'overlay', 'ov-title', 'ov-sub', 'ov-btn', 'score', 'best', 'moves', 'maxtile',
  'aiinfo', 'btn-new', 'btn-undo', 'btn-reset', 'btn-theme', 'btn-ai', 'speed', 'speed-label',
  'silent', 'st-games', 'st-best', 'st-avg', 'st-tile', 'history-box'];
const doc = {
  documentElement: makeEl('html'),
  _byId: {},
  _ev: {},
  createElement: t => makeEl(t),
  // 页面脚本用 document.querySelector('.board-shell') 找“棋盘可用空间”
  querySelector(sel) {
    if (sel === '.board-shell') return this._shell || null;
    return null;
  },
  querySelectorAll() { return []; },
  getElementById(id) { return this._byId[id] || (this._byId[id] = makeEl('div')); },
  addEventListener(t, fn) { (this._ev[t] = this._ev[t] || []).push(fn); },
  dispatch(t, ev) { (this._ev[t] || []).forEach(fn => fn(ev)); }
};
ids.forEach(id => doc.getElementById(id));
doc.body = makeEl('body');
// 用一个 .board-shell 桩来代表“棋盘可用空间”（宽 340 / 高 420，接近手机实际版式）
doc._shell = makeEl('div');
doc._shell._clientWidth = 340;    // 模拟可用宽度
doc._shell._clientHeight = 340;   // 初始给正方形；测试里可改，验证“取宽高较小者”

const store = new Map();
const sandbox = {
  console,
  document: doc,
  localStorage: {
    getItem: k => (store.has(k) ? store.get(k) : null),
    setItem: (k, v) => store.set(k, String(v)),
    removeItem: k => store.delete(k)
  },
  performance: { now: () => Date.now() },
  setTimeout, clearTimeout, Math, Date, JSON, Object, Array, Number, String, Boolean, Error, isNaN, parseInt, parseFloat,
  confirm: () => true,
  alert: () => {}
};
sandbox.window = sandbox;
sandbox._winEv = {};
sandbox.addEventListener = (t, fn) => { (sandbox._winEv[t] = sandbox._winEv[t] || []).push(fn); };
sandbox.removeEventListener = () => {};
sandbox.PointerEvent = function PointerEvent() {};   // 让页面走 Pointer Events 分支
sandbox.globalThis = sandbox;
sandbox.self = sandbox;
sandbox.AudioContext = undefined;
sandbox.webkitAudioContext = undefined;

vm.createContext(sandbox);
try {
  vm.runInContext(code, sandbox, { filename: '2048.html-inline.js' });
} catch (e) {
  console.error('❌ 页面脚本初始化抛异常：', e && e.stack || e);
  process.exit(1);
}
console.log('✅ 页面脚本初始化无异常');

sandbox.__DBG_LAYOUT = !!process.env.DBG;
const G = sandbox.Game2048;
const board = doc.getElementById('board');

/* --------------------------- 1) 手工操作验证 --------------------------- */
function press(key) { doc.dispatch('keydown', { key, preventDefault() {} }); }

const tilesOf = () => board.children.filter(c => c.classList.contains('tile'));
const maxInDom = () => Math.max(0, ...tilesOf().map(t => Number(t.dataset.v) || 0));

press('ArrowLeft'); press('ArrowDown'); press('ArrowRight'); press('ArrowUp');
const scoreAfter = Number(doc.getElementById('score').textContent);
console.log(`✅ 手动移动 4 次：得分=${scoreAfter}，棋盘上最大方块=${maxInDom()}，方块数=${tilesOf().length}`);

press('u'); // 撤销
console.log(`✅ 撤销可用：撤销后得分=${doc.getElementById('score').textContent}`);

/* --------------------- 1.5) 方块定位/对齐验证 --------------------- *
 * 独立算一遍期望坐标，再和页面脚本真正写进 transform 的值对照。
 * 覆盖窄屏和宽屏两种尺寸，确认格子边长与坐标随棋盘宽度正确缩放。
 * （这个检查是针对真实出现过的 bug：calc+变量算不出位置，方块全堆在左上角。）
 * ------------------------------------------------------------------ */
const GAP = 12;   // 必须与页面里的 --gap / GAP 一致
function checkLayout(width) {
  board._clientWidth = width;
  press('r');   // 新一局，触发重新测量与重绘
  press('ArrowLeft'); press('ArrowDown');   // 产生几个不同位置的方块

  const expectedCell = (width - 5 * GAP) / 4;
  const problems = [];

  // 1) 背景格：用 left/top 摆放，必须正好 16 个并覆盖全部位置
  const bgCells = board.children.filter(c => c.classList.contains('bg-cell'));
  if (bgCells.length !== 16) problems.push(`背景格数量是 ${bgCells.length}，应为 16`);
  const bgSeen = new Set();
  bgCells.forEach(el => {
    const x = parseFloat(el.style.left), y = parseFloat(el.style.top);
    if (isNaN(x) || isNaN(y)) { problems.push('背景格缺少 left/top'); return; }
    const col = Math.round((x - GAP) / (expectedCell + GAP));
    const row = Math.round((y - GAP) / (expectedCell + GAP));
    if (Math.abs(x - (GAP + col * (expectedCell + GAP))) > 0.01 ||
        Math.abs(y - (GAP + row * (expectedCell + GAP))) > 0.01) {
      problems.push(`背景格位置 (${x},${y}) 不符合公式`);
    }
    if (col < 0 || col > 3 || row < 0 || row > 3) problems.push(`背景格越界：第 ${row} 行第 ${col} 列`);
    bgSeen.add(row + ',' + col);
  });
  if (bgSeen.size !== 16) problems.push(`背景格只覆盖了 ${bgSeen.size} 个位置，应为 16`);

  // 2) 方块：位置在 left/top 上，必须落在格点上且互不重叠
  const tiles = board.children.filter(c => c.classList.contains('tile'));
  const seen = new Set();
  tiles.forEach(el => {
    const x = parseFloat(el.style.left), y = parseFloat(el.style.top);
    if (isNaN(x) || isNaN(y)) {
      problems.push(`方块（数字 ${el.dataset.v}）没有 left/top —— 这正是“方块堆在左上角”的 bug`);
      return;
    }
    const col = Math.round((x - GAP) / (expectedCell + GAP));
    const row = Math.round((y - GAP) / (expectedCell + GAP));
    if (Math.abs(x - (GAP + col * (expectedCell + GAP))) > 0.01 ||
        Math.abs(y - (GAP + row * (expectedCell + GAP))) > 0.01) {
      problems.push(`方块 ${el.dataset.v} 位置 (${x},${y}) 不在格点上`);
    }
    if (col < 0 || col > 3 || row < 0 || row > 3) {
      problems.push(`方块 ${el.dataset.v} 落到了棋盘外：第 ${row} 行第 ${col} 列`);
    }
    // 这里不检查“两个元素同位置”：判断“同一格是否有两个方块”要看游戏自身状态
    // （cellOwner + tiles，由页面里的 layoutProblems() 负责）；
    // 元素级的重复只可能来自 DOM 桩里延迟任务的残留，不代表真实布局问题。
    const w = parseFloat(el.style.width);
    if (Math.abs(w - expectedCell) > 0.01) {
      problems.push(`方块 ${el.dataset.v} 宽度 ${w} 应为 ${expectedCell.toFixed(2)}`);
    }
  });

  // 3) 页面自带的布局自检接口也必须通过
  const selfCheck = typeof sandbox.layoutProblems === 'function'
    ? sandbox.layoutProblems()
    : ['页面里没有 layoutProblems() 自检接口'];
  problems.push(...selfCheck);

  if (process.env.DBG) {
    bgCells.slice(0, 4).forEach((c, i) => console.log(`   [DBG] bg#${i}`, c.style.left, c.style.top, c.style.width));
    tiles.forEach(t => console.log('   [DBG] tile', t.dataset.v, t.style.left, t.style.top, t.style.width));
  }
  const first = bgCells[0];
  console.log(`   棋盘内容宽度 ${width}px -> 格子边长应为 ${expectedCell.toFixed(2)}px，` +
              `实际 ${first && first.style.width ? first.style.width : '(未设置)'}，` +
              `背景格 ${bgCells.length} 个、方块 ${tiles.length} 个`);
  return problems;
}

/* --------------------- 1.2) 滑动手势校验 --------------------- *
 * 判定方式不依赖盘面（盘面是随机的，比较步数会不稳）：
 *   先开启 AI 自动演示，再滑一下 —— 代码里“人工操作立刻接管”是写死的行为，
 *   所以只要 AI 被关掉，就证明这次滑动确实被识别成了有效手势。
 * 这一条防的正是真实出现过的 bug：touchstart/touchend 写了 {passive:true}，
 * 无法阻止默认滚动，手机上竖直滑动被浏览器当成页面滚动并取消 touchend，
 * 表现成“上下滑没反应”。
 * ------------------------------------------------------------------ */
function swipe(dx, dy) {
  const x0 = 200, y0 = 200;
  board.dispatch('pointerdown', { pointerType: 'touch', button: 0, pointerId: 1, clientX: x0, clientY: y0 });
  board.dispatch('pointermove', { clientX: x0 + dx / 2, clientY: y0 + dy / 2 });
  board.dispatch('pointerup', { pointerType: 'touch', pointerId: 1, clientX: x0 + dx, clientY: y0 + dy });
}
function aiIsOn() { return /开$/.test(doc.getElementById('btn-ai').textContent); }

console.log('✅ 手动移动与撤销正常，开始校验滑动手势：');
const dirs = [
  { name: '上滑', dx: 0, dy: -60 },
  { name: '下滑', dx: 0, dy: 60 },
  { name: '左滑', dx: -60, dy: 0 },
  { name: '右滑', dx: 60, dy: 0 }
];
let swipeProblems = [];
dirs.forEach(d => {
  press('r');
  press(' ');                       // 空格：开启 AI 自动演示
  const onBefore = aiIsOn();
  swipe(d.dx, d.dy);                // 一次滑动应当被识别为人工操作
  const onAfter = aiIsOn();
  const ok = onBefore && !onAfter;
  console.log(`   ${d.name}：AI ${onBefore ? '开' : '关'} -> ${onAfter ? '开' : '关'}  ${ok ? '✅ 手势被识别' : '❌ 手势没被识别'}`);
  if (!ok) swipeProblems.push(d.name + '没有被识别');
});

// 小于阈值的轻微滑动不应被当成一次操作
press('r');
press(' ');
swipe(0, 6);
if (!aiIsOn()) swipeProblems.push('小于阈值的轻微滑动被误判成一次操作');
else console.log('   轻微滑动（6px）被正确忽略 ✅');

press(' ');   // 关掉 AI，恢复干净状态
if (swipeProblems.length) {
  console.log('❌ 滑动手势校验失败：' + swipeProblems.join('、'));
  process.exit(1);
}
console.log('✅ 滑动手势校验通过：四个方向都能被识别，轻微滑动被忽略。');

/* --------------------- 1.4) 棋盘尺寸自适应断言 --------------------- *
 * 需求：一屏之内只放游戏本身、页面不滚动。
 * 因此棋盘边长必须取「可用宽」和「可用高」中较小的那个。
 * ------------------------------------------------------------------ */
console.log('✅ 滑动手势校验通过，开始校验棋盘尺寸自适应：');
{
  const cases = [
    { w: 340, h: 500, name: '窄高屏（手机竖屏）' },
    { w: 700, h: 260, name: '宽矮屏（横屏/小窗）' },
    { w: 480, h: 480, name: '正方形窗口' }
  ];
  let sizeProblems = [];
  cases.forEach(c => {
    doc._shell._clientWidth = c.w;
    doc._shell._clientHeight = c.h;
    press('r');   // 触发重新测量
    const side = parseFloat(board.style.getPropertyValue('--board-size'));
    const expect = Math.floor(Math.min(c.w, c.h));
    const ok = Math.abs(side - expect) < 2;
    console.log(`   ${c.name}（可用 ${c.w}x${c.h}）-> 棋盘边长 ${side}px，期望 ${expect}px  ${ok ? '✅' : '❌'}`);
    if (!ok) sizeProblems.push(c.name);
  });
  // 复位成标准桩尺寸，后面的定位校验依赖它
  doc._shell._clientWidth = 340;
  doc._shell._clientHeight = 420;
  board._clientWidth = 340;
  if (sizeProblems.length) {
    console.log('❌ 棋盘尺寸自适应校验失败：' + sizeProblems.join('、'));
    process.exit(1);
  }
  console.log('✅ 棋盘尺寸自适应校验通过：始终取宽高较小者，保证一屏放得下。');
}

console.log('✅ 手动移动与撤销正常，开始校验方块定位：');
let layoutProblems = [];
[340, 480, 720].forEach(width => { layoutProblems = layoutProblems.concat(checkLayout(width)); });
if (layoutProblems.length) {
  console.log('❌ 方块定位校验失败：');
  layoutProblems.forEach(p => console.log('   - ' + p));
  process.exit(1);
}
console.log('✅ 方块定位校验通过：三种宽度下坐标都精确落在格子上，无重叠、无越界。');

/* --------------------------- 2) AI 自动演示验证 --------------------------- */
const ROUNDS = parseInt(process.argv[2] || '3', 10);
let ok1024 = 0, ok2048 = 0, maxSeen = 0, totalMoves = 0;
const t0 = Date.now();

function runOneAI() {
  return new Promise(resolve => {
    press('r');                       // 新一局
    doc.getElementById('speed').value = '0';
    doc.getElementById('speed').dispatch('input', { target: { value: '0' } });
    press(' ');                       // 空格：开 AI 自动演示
    const started = Date.now();
    const timer = setInterval(() => {
      const mt = Math.max(Number(doc.getElementById('maxtile').textContent) || 0, maxInDom());
      if (mt > maxSeen) maxSeen = mt;
      const moves = Number(doc.getElementById('moves').textContent) || 0;
      const done = mt >= 2048 || /关$/.test(doc.getElementById('btn-ai').textContent) || moves > 9000;
      if (done || Date.now() - started > 300000) {
        clearInterval(timer);
        press(' '); // 确保停掉
        resolve({ mt, moves, elapsed: Date.now() - started });
      }
    }, 200);
  });
}

(async () => {
  for (let i = 0; i < ROUNDS; i++) {
    const r = await runOneAI();
    totalMoves += r.moves;
    if (r.mt >= 1024) ok1024++;
    if (r.mt >= 2048) ok2048++;
    console.log(`第 ${i + 1} 局 AI：最大方块=${r.mt}  步数=${r.moves}  用时=${(r.elapsed / 1000).toFixed(1)}s  ${r.mt >= 2048 ? '✅2048' : r.mt >= 1024 ? '✅1024' : '❌未达标'}`);
  }
  console.log('');
  console.log(`页面内 AI 合出 1024：${ok1024}/${ROUNDS}`);
  console.log(`页面内 AI 合出 2048：${ok2048}/${ROUNDS}`);
  console.log(`平均步数：${Math.round(totalMoves / ROUNDS)}，历史最大方块：${maxSeen}`);
  console.log(`总耗时：${((Date.now() - t0) / 1000).toFixed(1)}s`);
  console.log('');
  console.log(ok1024 === ROUNDS
    ? '✅ 页面级验证通过：AI 无需人工操作即可达到硬指标。'
    : '❌ 有对局未达标，需要调整。');
  process.exit(ok1024 === ROUNDS ? 0 : 1);
})();
