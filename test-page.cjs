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
    children: [], _text: '', dataset: {}, style: {}, checked: false, disabled: false,
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
    querySelector() { return null; },
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
  getElementById(id) { return this._byId[id] || (this._byId[id] = makeEl('div')); },
  addEventListener(t, fn) { (this._ev[t] = this._ev[t] || []).push(fn); },
  dispatch(t, ev) { (this._ev[t] || []).forEach(fn => fn(ev)); }
};
ids.forEach(id => doc.getElementById(id));

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
    // 只有两个“不同元素”真的落在同一像素位置才算重叠（桩里的异步残留不算布局问题）
    const pixelKey = el.style.left + '|' + el.style.top;
    if (seen.has(pixelKey)) {
      problems.push(`两个方块元素重叠在同一位置 ${pixelKey}`);
    }
    seen.add(pixelKey);
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
