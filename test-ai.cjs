/* ============================================================================
 * 阶段二验证脚本：用 Node 无头（不开浏览器、不画界面）批量跑 AI 对局，
 * 统计「合出 1024 的成功率」「合出 2048 的成功率」「平均步数」，用于证明
 * AI 不是“碰巧赢一把”，而是稳定达标。
 *
 * 运行：  node test-ai.cjs [局数] [每步思考毫秒]
 * ==========================================================================*/
const G = require('./projects/2048/src/game-core.js');

// 可复现的伪随机数（mulberry32），保证同一 seed 结果一致
function makeRng(seed) {
  let a = seed >>> 0;
  return function () {
    a |= 0; a = (a + 0x6D2B79F5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function playOne(seed, opts) {
  const rnd = makeRng(seed);
  let board = G.newGame(rnd);
  let score = 0, moves = 0;
  let got1024 = false, got2048 = false;
  const MAX_TURNS = 6000; // 防止极端情况下死循环

  while (moves < MAX_TURNS) {
    const best = G.aiBestMove(board, opts);
    if (!best) break; // 无路可走 = 游戏结束
    const res = G.move(board, best.dir);
    if (!res.moved) break;
    board = res.board;
    score += res.gained;
    moves++;
    G.spawn(board, rnd);
    const m = G.maxTile(board);
    if (m >= 1024) got1024 = true;
    if (m >= 2048) got2048 = true;
    if (!G.canMove(board)) break;
  }
  return { score, moves, maxTile: G.maxTile(board), got1024, got2048 };
}

const games = parseInt(process.argv[2] || '30', 10);
const thinkMs = parseInt(process.argv[3] || '40', 10);
const opts = { timeLimit: thinkMs, maxDepth: 8 };

console.log(`== 2048 阶段二 AI 无头验证 ==`);
console.log(`局数=${games}  每步思考上限=${thinkMs}ms  搜索深度上限=${opts.maxDepth}`);
console.log('');

let ok1024 = 0, ok2048 = 0, sumScore = 0, sumMoves = 0, maxTile = 0;
const t0 = Date.now();
const perGame = [];

for (let i = 0; i < games; i++) {
  const r = playOne(1000 + i, opts);
  if (r.got1024) ok1024++;
  if (r.got2048) ok2048++;
  sumScore += r.score;
  sumMoves += r.moves;
  if (r.maxTile > maxTile) maxTile = r.maxTile;
  perGame.push(r);
  process.stdout.write(
    `第 ${String(i + 1).padStart(3)} 局  seed=${1000 + i}  得分=${String(r.score).padStart(7)}  ` +
    `步数=${String(r.moves).padStart(4)}  最大方块=${String(r.maxTile).padStart(5)}  ` +
    `${r.got2048 ? '✅2048' : r.got1024 ? '✅1024' : '❌未达标'}\n`
  );
}

const sec = ((Date.now() - t0) / 1000).toFixed(1);
console.log('');
console.log(`合出 1024 成功率：${ok1024}/${games} = ${(ok1024 / games * 100).toFixed(1)}%`);
console.log(`合出 2048 成功率：${ok2048}/${games} = ${(ok2048 / games * 100).toFixed(1)}%`);
console.log(`平均得分：${Math.round(sumScore / games)}   平均步数：${Math.round(sumMoves / games)}   历史最大方块：${maxTile}`);
console.log(`总耗时：${sec}s（平均每局 ${(sec / games).toFixed(1)}s）`);
console.log('');
console.log(ok1024 === games
  ? '结论：全部对局均达成硬指标（AI 自动合出 1024）。'
  : `结论：有 ${games - ok1024} 局未达标，需要调整启发式权重或加深搜索。`);
