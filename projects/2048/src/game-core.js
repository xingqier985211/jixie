/* ============================================================================
 * 2048 游戏核心逻辑（纯函数，无 DOM 依赖）
 * 说明：本文件既是浏览器端游戏引擎，也是 Node 端 AI 验证脚本的引擎。
 * 之所以把核心逻辑和界面分开，是为了能用 Node 无头批量跑 AI 对局，
 * 用数据证明“阶段二：AI 自动合出 1024”这个硬指标不是靠运气。
 * ==========================================================================*/
(function (root, factory) {
  var api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api; // Node
  root.Game2048 = api;                                                    // 浏览器
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  var SIZE = 4;
  var CELLS = SIZE * SIZE;
  var WIN_TILE = 1024;   // 任务书硬指标：AI 自动合出 1024
  var BONUS_TILE = 2048; // 加分项
  var SPAWN_P2 = 0.9;    // 新方块 90% 出 2
  var SPAWN_P4 = 0.1;    // 10% 出 4

  /* ---------------------------- 基础棋盘操作 ---------------------------- */

  function emptyBoard() {
    return new Array(CELLS).fill(0);
  }

  function cloneBoard(b) {
    return b.slice();
  }

  function emptyCells(b) {
    var out = [];
    for (var i = 0; i < CELLS; i++) if (b[i] === 0) out.push(i);
    return out;
  }

  function maxTile(b) {
    var m = 0;
    for (var i = 0; i < CELLS; i++) if (b[i] > m) m = b[i];
    return m;
  }

  // 用可注入的随机源，方便测试时复现某一局
  function spawn(b, rnd) {
    rnd = rnd || Math.random;
    var cells = emptyCells(b);
    if (!cells.length) return -1;
    var idx = cells[Math.floor(rnd() * cells.length)];
    b[idx] = rnd() < SPAWN_P2 ? 2 : 4;
    return idx;
  }

  function newGame(rnd) {
    var b = emptyBoard();
    spawn(b, rnd);
    spawn(b, rnd);
    return b;
  }

  /* --------------------------- 单行向左合并 ---------------------------- *
   * 2048 的移动本质：把每一行（或每一列）都当成“向左合并”来处理。
   * 左移 -> 直接合并每行；右移 -> 每行倒序后合并再倒回来；
   * 上移 -> 把列取出来当行；下移 -> 列倒序。
   * 合并规则：从滑动的方向开始，每个方块只参与一次合并（2 2 2 2 -> 4 4）。
   * -------------------------------------------------------------------- */
  function slideLine(line) {
    var vals = [];
    var i;
    for (i = 0; i < SIZE; i++) if (line[i] !== 0) vals.push(line[i]);

    var merged = [];
    var gained = 0;
    for (i = 0; i < vals.length; i++) {
      if (i + 1 < vals.length && vals[i] === vals[i + 1]) {
        var v = vals[i] * 2;
        merged.push(v);
        gained += v;
        i++; // 跳过被吃掉的那个，保证“一格只合并一次”
      } else {
        merged.push(vals[i]);
      }
    }
    while (merged.length < SIZE) merged.push(0);

    var changed = false;
    for (i = 0; i < SIZE; i++) if (merged[i] !== line[i]) { changed = true; break; }
    return { line: merged, gained: gained, changed: changed };
  }

  var DIRS = {
    left:  { r: 0,  c: -1 },
    right: { r: 0,  c: 1 },
    up:    { r: -1, c: 0 },
    down:  { r: 1,  c: 0 }
  };

  // 取第 i 条“线”：左右移动取行，上下移动取列；reverse 表示从滑动方向那一端起算
  function readLine(b, dir, i, reverse) {
    var line = new Array(SIZE);
    for (var j = 0; j < SIZE; j++) {
      var k = reverse ? SIZE - 1 - j : j;
      var r, c;
      if (dir === 'left' || dir === 'right') { r = i; c = k; }   // 行
      else { r = k; c = i; }                                     // 列
      line[j] = b[r * SIZE + c];
    }
    return line;
  }

  function writeLine(b, dir, i, reverse, line) {
    for (var j = 0; j < SIZE; j++) {
      var k = reverse ? SIZE - 1 - j : j;
      var r, c;
      if (dir === 'left' || dir === 'right') { r = i; c = k; }
      else { r = k; c = i; }
      b[r * SIZE + c] = line[j];
    }
  }

  /* ------------------------------- 移动 -------------------------------- */

  // 返回 { board, gained, moved }，不修改原棋盘
  function move(b, dir) {
    if (!DIRS[dir]) return { board: cloneBoard(b), gained: 0, moved: false };
    var nb = cloneBoard(b);
    var reverse = (dir === 'right' || dir === 'down');
    var gained = 0;
    var moved = false;
    for (var i = 0; i < SIZE; i++) {
      var line = readLine(nb, dir, i, reverse);
      var res = slideLine(line);
      if (res.changed) moved = true;
      gained += res.gained;
      writeLine(nb, dir, i, reverse, res.line);
    }
    return { board: nb, gained: gained, moved: moved };
  }

  /* 给界面用的“轨迹”：返回 目标格 -> [来源格, ...]
   * 界面靠它知道哪几张牌滑到哪、哪两张牌叠在一起，从而播滑动/合并动画。
   * 数据结果本身由 move() 决定，这里只是把过程复现一遍，供动画使用。 */
  function traceMove(b, dir) {
    var mapping = {};
    if (!DIRS[dir]) return mapping;
    var reverse = (dir === 'right' || dir === 'down');
    for (var i = 0; i < SIZE; i++) {
      var indices = [];
      for (var j = 0; j < SIZE; j++) {
        var k = reverse ? SIZE - 1 - j : j;
        indices.push((dir === 'left' || dir === 'right') ? (i * SIZE + k) : (k * SIZE + i));
      }
      var vals = [], src = [];
      for (var t = 0; t < SIZE; t++) {
        if (b[indices[t]]) { vals.push(b[indices[t]]); src.push(indices[t]); }
      }
      var froms = [];
      for (var q = 0; q < vals.length; q++) {
        if (q + 1 < vals.length && vals[q] === vals[q + 1]) {
          froms.push([src[q], src[q + 1]]);
          q++;
        } else {
          froms.push([src[q]]);
        }
      }
      while (froms.length < SIZE) froms.push([]);
      for (var p = 0; p < SIZE; p++) mapping[indices[p]] = froms[p];
    }
    return mapping;
  }

  function canMove(b) {
    if (emptyCells(b).length) return true;
    for (var r = 0; r < SIZE; r++) {
      for (var c = 0; c < SIZE; c++) {
        var v = b[r * SIZE + c];
        if (c + 1 < SIZE && v === b[r * SIZE + c + 1]) return true;
        if (r + 1 < SIZE && v === b[(r + 1) * SIZE + c]) return true;
      }
    }
    return false;
  }

  function isWin(b, tile) {
    return maxTile(b) >= (tile || WIN_TILE);
  }

  /* ------------------------------ 启发式 ------------------------------- *
   * 四个指标（都在“越大越好”的方向上加权）：
   * 1. 空格数    —— 空格是活下去的本钱，没有空格任何一步都可能致死；
   * 2. 单调性    —— 每行每列都尽量单向递增/递减，方块才会顺着一个方向排队合并；
   * 3. 平滑度    —— 相邻格子数值差距越小越好，差距大说明以后想合并要绕很远；
   * 4. 最大方块  —— 轻微加分，鼓励早点把大块做出来。
   * 权重是靠 Node 批量对局调出来的（见 test-ai.cjs 的验证数据）。
   * -------------------------------------------------------------------- */
  var W = { empty: 270, mono: 47, smooth: 18, max: 1.0 };

  function countEmpty(b) {
    var n = 0;
    for (var i = 0; i < CELLS; i++) if (b[i] === 0) n++;
    return n;
  }

  function monotonicity(b) {
    var totals = [0, 0, 0, 0]; // 上、下、左、右四个方向的单调性
    for (var r = 0; r < SIZE; r++) {
      for (var c = 0; c < SIZE - 1; c++) {
        var a = b[r * SIZE + c], d = b[r * SIZE + c + 1];
        if (a > d) totals[2] += d - a; else totals[3] += a - d;
      }
    }
    for (var c2 = 0; c2 < SIZE; c2++) {
      for (var r2 = 0; r2 < SIZE - 1; r2++) {
        var u = b[r2 * SIZE + c2], v = b[(r2 + 1) * SIZE + c2];
        if (u > v) totals[0] += v - u; else totals[1] += u - v;
      }
    }
    return Math.max(totals[0], totals[1]) + Math.max(totals[2], totals[3]);
  }

  function smoothness(b) {
    var s = 0;
    for (var r = 0; r < SIZE; r++) {
      for (var c = 0; c < SIZE; c++) {
        var v = b[r * SIZE + c];
        if (!v) continue;
        if (c + 1 < SIZE && b[r * SIZE + c + 1]) s -= Math.abs(v - b[r * SIZE + c + 1]);
        if (r + 1 < SIZE && b[(r + 1) * SIZE + c]) s -= Math.abs(v - b[(r + 1) * SIZE + c]);
      }
    }
    return s;
  }

  function evaluate(b) {
    if (!canMove(b)) return -1e9; // 死局直接判负
    return W.empty * countEmpty(b) + W.mono * monotonicity(b) +
           W.smooth * smoothness(b) + W.max * maxTile(b);
  }

  /* --------------------------- Expectimax AI --------------------------- *
   * 玩家节点：枚举 4 个方向，取最大值（对手是"随机"，所以不是纯 minimax）；
   * 随机节点：枚举所有空格，按 90%/10% 的概率分别放 2 和 4，取加权平均；
   * 用 alpha-beta 在玩家节点剪枝，缓存局面避免重复搜索。
   * -------------------------------------------------------------------- */
  var aiStats = { nodes: 0 };
  var TT = new Map();

  function boardKey(b) {
    return b.join(',');
  }

  function aiBestMove(board, opts) {
    opts = opts || {};
    var timeLimit = opts.timeLimit || 45;        // 单步思考上限(ms)
    var maxDepth = opts.maxDepth || 6;           // 搜索深度(层)
    var deadline = Date.now() + timeLimit;
    TT.clear();
    aiStats.nodes = 0;

    var dirs = ['up', 'left', 'down', 'right']; // 顺序影响剪枝效率
    var best = null;
    var bestScore = -Infinity;

    for (var i = 0; i < dirs.length; i++) {
      var res = move(board, dirs[i]);
      if (!res.moved) continue;
      var s = expectChance(res.board, maxDepth - 1, -Infinity, Infinity, deadline);
      if (s > bestScore) { bestScore = s; best = dirs[i]; }
    }
    if (best === null) return null; // 没有合法走法
    return { dir: best, score: bestScore, nodes: aiStats.nodes };
  }

  // 随机节点：加权平均
  function expectChance(b, depth, alpha, beta, deadline) {
    aiStats.nodes++;
    var cells = emptyCells(b);
    if (!cells.length) return evaluate(b);
    if (depth <= 0 || Date.now() > deadline) return evaluate(b);

    var key = boardKey(b);
    var hit = TT.get(key);
    if (hit !== undefined) return hit;

    var total = 0;
    // 只统计“价值最高”的剪枝条件对随机节点不适用，这里做完整平均保证评估准确
    for (var i = 0; i < cells.length; i++) {
      var idx = cells[i];
      b[idx] = 2;
      total += SPAWN_P2 * expectPlayer(b, depth - 1, alpha, beta, deadline);
      b[idx] = 4;
      total += SPAWN_P4 * expectPlayer(b, depth - 1, alpha, beta, deadline);
      b[idx] = 0;
    }
    var val = total / cells.length;
    if (TT.size < 60000) TT.set(key, val);
    return val;
  }

  // 玩家节点：取最大
  function expectPlayer(b, depth, alpha, beta, deadline) {
    aiStats.nodes++;
    if (depth <= 0 || Date.now() > deadline) return evaluate(b);

    var dirs = ['up', 'left', 'down', 'right'];
    var best = -Infinity;
    var any = false;
    for (var i = 0; i < dirs.length; i++) {
      var res = move(b, dirs[i]);
      if (!res.moved) continue;
      any = true;
      var s = expectChance(res.board, depth - 1, alpha, beta, deadline);
      if (s > best) best = s;
      if (best > alpha) alpha = best;
      if (alpha >= beta) break; // 剪枝
    }
    return any ? best : evaluate(b);
  }

  return {
    SIZE: SIZE,
    CELLS: CELLS,
    WIN_TILE: WIN_TILE,
    BONUS_TILE: BONUS_TILE,
    emptyBoard: emptyBoard,
    cloneBoard: cloneBoard,
    newGame: newGame,
    spawn: spawn,
    move: move,
    traceMove: traceMove,
    canMove: canMove,
    isWin: isWin,
    maxTile: maxTile,
    emptyCells: emptyCells,
    slideLine: slideLine,
    evaluate: evaluate,
    aiBestMove: aiBestMove,
    aiStats: aiStats
  };
});
