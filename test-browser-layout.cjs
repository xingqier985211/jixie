/* ============================================================================
 * 真浏览器布局验证（用 Edge/Chrome 的 DevTools 协议 + 自带 WebSocket 客户端）
 *
 * 为什么需要它：test-page.cjs 用的是最小 DOM 桩，能验证逻辑但量不到真实布局，
 * 所以"方块全部堆在左上角"这种定位 bug 会漏过去。这个脚本启动无头浏览器、
 * 打开真实的 game.html，然后依次按方向键，量出每个方块的实际屏幕坐标，
 * 检查它们是否和 16 个背景格一一对齐。
 *
 * 运行：  node test-browser-layout.cjs [--port 9333]
 * 依赖：  本机装了 Edge 或 Chrome；不需要任何 npm 包。
 * ==========================================================================*/
const { spawn } = require('child_process');
const http = require('http');
const crypto = require('crypto');
const net = require('net');
const fs = require('fs');
const path = require('path');

const PORT = (() => {
  const i = process.argv.indexOf('--port');
  return i >= 0 ? Number(process.argv[i + 1]) : 9333;
})();

const EDGE_CANDIDATES = [
  'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
  'C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe',
  'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
  'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe'
];
const exe = EDGE_CANDIDATES.find(p => fs.existsSync(p));
if (!exe) {
  console.error('没找到 Edge/Chrome，跳过浏览器验证。');
  process.exit(2);
}

const gameUrl = 'file:///' + path.join(__dirname, 'game.html').replace(/\\/g, '/');
const profileDir = path.join(__dirname, '_tools', 'edge-profile');
fs.mkdirSync(profileDir, { recursive: true });

/* ------------------------- 极简 WebSocket 客户端 ------------------------- */
function wsConnect(wsUrl) {
  return new Promise((resolve, reject) => {
    const m = wsUrl.match(/^ws:\/\/([^:/]+):(\d+)(\/.*)$/);
    if (!m) return reject(new Error('bad ws url: ' + wsUrl));
    const key = crypto.randomBytes(16).toString('base64');
    const sock = net.connect(Number(m[2]), m[1], () => {
      sock.write(
        `GET ${m[3]} HTTP/1.1\r\n` +
        `Host: ${m[1]}:${m[2]}\r\n` +
        'Upgrade: websocket\r\nConnection: Upgrade\r\n' +
        `Sec-WebSocket-Key: ${key}\r\nSec-WebSocket-Version: 13\r\n\r\n`
      );
    });
    let buffer = Buffer.alloc(0);
    let upgraded = false;
    const handlers = [];
    const pending = Buffer.alloc(0);

    sock.on('data', chunk => {
      buffer = Buffer.concat([buffer, chunk]);
      if (!upgraded) {
        const idx = buffer.indexOf('\r\n\r\n');
        if (idx < 0) return;
        buffer = buffer.slice(idx + 4);
        upgraded = true;
        resolve({
          send: txt => {
            const payload = Buffer.from(txt, 'utf8');
            const len = payload.length;
            let header;
            if (len < 126) header = Buffer.from([0x81, 0x80 | len]);
            else if (len < 65536) { header = Buffer.alloc(4); header[0] = 0x81; header[1] = 0xFE; header.writeUInt16BE(len, 2); }
            else { header = Buffer.alloc(10); header[0] = 0x81; header[1] = 0xFF; header.writeBigUInt64BE(BigInt(len), 2); }
            const mask = crypto.randomBytes(4);
            const masked = Buffer.from(payload);
            for (let i = 0; i < masked.length; i++) masked[i] ^= mask[i % 4];
            sock.write(Buffer.concat([header, mask, masked]));
          },
          onMessage: fn => handlers.push(fn),
          close: () => sock.destroy()
        });
      }
      // 解析帧
      while (buffer.length >= 2) {
        const b1 = buffer[1];
        let len = b1 & 0x7F;
        let off = 2;
        if (len === 126) { if (buffer.length < 4) break; len = buffer.readUInt16BE(2); off = 4; }
        else if (len === 127) { if (buffer.length < 10) break; len = Number(buffer.readBigUInt64BE(2)); off = 10; }
        if (buffer.length < off + len) break;
        const payload = buffer.slice(off, off + len);
        buffer = buffer.slice(off + len);
        handlers.forEach(fn => fn(payload.toString('utf8')));
      }
    });
    sock.on('error', reject);
  });
}

function httpJson(url) {
  return new Promise((resolve, reject) => {
    http.get(url, res => {
      let data = '';
      res.on('data', d => (data += d));
      res.on('end', () => { try { resolve(JSON.parse(data)); } catch (e) { reject(e); } });
    }).on('error', reject);
  });
}

const sleep = ms => new Promise(r => setTimeout(r, ms));

(async () => {
  const child = spawn(exe, [
    '--headless=new',
    `--remote-debugging-port=${PORT}`,
    `--user-data-dir=${profileDir}`,
    '--no-first-run', '--no-default-browser-check',
    '--disable-extensions', '--disable-sync',
    '--window-size=900,1000',
    gameUrl
  ], { stdio: 'ignore' });

  let targets = null;
  for (let i = 0; i < 40; i++) {
    await sleep(500);
    try {
      targets = await httpJson(`http://127.0.0.1:${PORT}/json/list`);
      if (targets && targets.some(t => t.type === 'page' && t.webSocketDebuggerUrl)) break;
    } catch (e) { /* 还没起来 */ }
  }
  if (!targets) { child.kill(); throw new Error('无头浏览器没有起来（CDP 无响应）'); }

  const page = targets.find(t => t.type === 'page' && t.webSocketDebuggerUrl);
  const ws = await wsConnect(page.webSocketDebuggerUrl);

  let msgId = 0;
  const waiters = new Map();
  ws.onMessage(txt => {
    let msg;
    try { msg = JSON.parse(txt); } catch (e) { return; }
    if (msg.id && waiters.has(msg.id)) {
      const { resolve, reject } = waiters.get(msg.id);
      waiters.delete(msg.id);
      msg.error ? reject(new Error(JSON.stringify(msg.error))) : resolve(msg.result);
    }
  });
  const send = (method, params = {}) => new Promise((resolve, reject) => {
    const id = ++msgId;
    waiters.set(id, { resolve, reject });
    ws.send(JSON.stringify({ id, method, params }));
  });

  const evaluate = async expr => {
    const r = await send('Runtime.evaluate', { expression: expr, returnByValue: true, awaitPromise: true });
    if (r.exceptionDetails) throw new Error('页面里抛异常: ' + JSON.stringify(r.exceptionDetails.exception));
    return r.result.value;
  };

  await send('Runtime.enable');
  await send('Page.enable');
  await sleep(1200);   // 等页面脚本与布局稳定

  const title = await evaluate('document.title');
  console.log('页面标题:', title);

  // 读一个版本标记，确认浏览器加载的是最新构建
  const scriptLen = await evaluate('document.querySelectorAll("script")[0].textContent.length');
  console.log('内联脚本长度:', scriptLen);

  // 按方向键制造真实对局
  const KEYS = ['ArrowLeft', 'ArrowUp', 'ArrowRight', 'ArrowDown'];
  for (let i = 0; i < 40; i++) {
    const key = KEYS[i % KEYS.length];
    await send('Input.dispatchKeyEvent', {
      type: 'keyDown', key, code: key, windowsVirtualKeyCode: { ArrowLeft: 37, ArrowUp: 38, ArrowRight: 39, ArrowDown: 40 }[key]
    });
    await send('Input.dispatchKeyEvent', { type: 'keyUp', key, code: key });
    await sleep(60);
  }
  await sleep(400);   // 等动画与延迟生成结束

  const report = await evaluate(`(() => {
    const board = document.getElementById('board');
    const br = board.getBoundingClientRect();
    const cells = [...board.querySelectorAll('.bg-cell')].map(c => c.getBoundingClientRect());
    const tiles = [...board.querySelectorAll('.tile')].map(t => {
      const r = t.getBoundingClientRect();
      // 找最近的背景格
      let best = -1, bestD = 1e9;
      cells.forEach((cr, i) => {
        const d = Math.hypot(cr.left - r.left, cr.top - r.top);
        if (d < bestD) { bestD = d; best = i; }
      });
      return { v: t.dataset.v, x: Math.round(r.left - br.left), y: Math.round(r.top - br.top),
               w: Math.round(r.width), h: Math.round(r.height), cell: best, offset: Math.round(bestD) };
    });
    return {
      boardSize: Math.round(br.width),
      cell0: { w: Math.round(cells[0].width), h: Math.round(cells[0].height) },
      cellRects: cells.map(c => ({ x: Math.round(c.left - br.left), y: Math.round(c.top - br.top) })),
      tiles,
      score: document.getElementById('score').textContent,
      moves: document.getElementById('moves').textContent,
      maxTile: document.getElementById('maxtile').textContent
    };
  })()`);

  console.log('');
  console.log(`棋盘边长 ${report.boardSize}px，格子 ${report.cell0.w}x${report.cell0.h}px，` +
              `得分 ${report.score}，步数 ${report.moves}，最大方块 ${report.maxTile}`);
  console.log(`背景格前 4 个坐标: ${JSON.stringify(report.cellRects.slice(0, 4))}`);
  console.log(`方块数: ${report.tiles.length}`);
  report.tiles.forEach(t => {
    console.log(`  数字 ${String(t.v).padStart(4)}  位置 (${String(t.x).padStart(3)},${String(t.y).padStart(3)})  ` +
                `尺寸 ${t.w}x${t.h}  最近格子 #${t.cell}  偏差 ${t.offset}px`);
  });

  // 判定：每个方块都必须精确落在某个背景格上，且没有两个方块占同一格
  const problems = [];
  report.tiles.forEach(t => {
    if (t.offset > 2) problems.push(`数字 ${t.v} 没有对齐格子（偏差 ${t.offset}px）`);
    if (t.w !== report.cell0.w || t.h !== report.cell0.h) {
      problems.push(`数字 ${t.v} 尺寸 ${t.w}x${t.h} 与格子 ${report.cell0.w}x${report.cell0.h} 不一致`);
    }
  });
  const used = report.tiles.map(t => t.cell);
  const dup = used.filter((c, i) => used.indexOf(c) !== i);
  if (dup.length) problems.push(`有方块占用同一个格子: ${[...new Set(dup)].join(',')}`);

  console.log('');
  if (problems.length) {
    console.log('❌ 布局验证失败:');
    problems.forEach(p => console.log('   - ' + p));
  } else {
    console.log('✅ 布局验证通过：所有方块都精确对齐背景格，尺寸一致，无重叠。');
  }

  ws.close();
  child.kill();
  await sleep(300);
  process.exit(problems.length ? 1 : 0);
})().catch(err => {
  console.error('验证脚本出错:', err.message);
  process.exit(3);
});
