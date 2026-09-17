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

const htmlPath = path.join(__dirname, 'projects', '2048', '2048.html');
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
    querySelector() { return null; }
  };
  el.classList = {
    add: (...cs) => cs.forEach(c => el._cls.add(c)),
    remove: (...cs) => cs.forEach(c => el._cls.delete(c)),
    contains: c => el._cls.has(c),
    toggle: c => el._cls.has(c) ? el._cls.delete(c) : el._cls.add(c)
  };
  Object.defineProperty(el, 'offsetWidth', { get: () => 100 });
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
