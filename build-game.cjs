/* 构建脚本：把 src/game-core.js 注入到 src/index.template.html 的占位符里，
 * 产出 projects/2048/2048.html —— 一个“双击就能玩”的纯前端单文件。
 * 之所以保留构建步骤，是为了让核心逻辑能同时被浏览器和 Node 测试脚本复用。
 *
 * 运行： node build-game.cjs
 */
const fs = require('fs');
const path = require('path');

const root = __dirname;
const corePath = path.join(root, 'projects', '2048', 'src', 'game-core.js');
const tplPath = path.join(root, 'projects', '2048', 'src', 'index.template.html');
const outPath = path.join(root, 'projects', '2048', '2048.html');

const core = fs.readFileSync(corePath, 'utf8').trim();
const tpl = fs.readFileSync(tplPath, 'utf8');

if (!tpl.includes('/*__GAME_CORE__*/')) {
  console.error('模板里找不到 /*__GAME_CORE__*/ 占位符');
  process.exit(1);
}

const out = tpl.replace('/*__GAME_CORE__*/', core);
fs.writeFileSync(outPath, out, 'utf8');

const kb = (Buffer.byteLength(out, 'utf8') / 1024).toFixed(1);
console.log(`已生成 ${path.relative(root, outPath)}  (${kb} KB, 单文件可直接双击打开)`);
