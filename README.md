# jixie
加入广工集协
贪吃蛇代码
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>AI贪吃蛇</title>
    <style>
        *{box-sizing:border-box;font-family:system-ui}
        body{display:flex;flex-direction:column;align-items:center;background:#f0f0f0;margin-top:20px}
        #gameBox{border:2px solid #333;background:#fff}
        .panel{margin-bottom:10px;font-size:18px}
        button{padding:6px 14px;margin:0 4px;font-size:16px;cursor:pointer}
    </style>
</head>
<body>
    <div class="panel">
        得分：<span id="score">0</span>｜最高分：<span id="highScore">0</span>｜已吃食物：<span id="eatCount">0</span>
        <br>
        <button id="resetBtn">重置游戏</button>
        <button id="aiToggle">开启AI自动游玩</button>
    </div>
    <canvas id="gameBox" width="400" height="400"></canvas>
    <script>
        const canvas = document.getElementById('gameBox');
        const ctx = canvas.getContext('2d');
        const grid = 20;
        const count = canvas.width / grid;

        // 游戏数据
        let snake = [{x:10,y:10}];
        let food = {};
        let dir = {x:1,y:0};
        let nextDir = {x:1,y:0};
        let score = 0;
        let eatCount = 0;
        let highScore = localStorage.getItem('snakeHigh')||0;
        let gameOver = false;
        let aiMode = false;
        let timer;

        document.getElementById('highScore').innerText = highScore;

        // 生成食物
        function spawnFood(){
            let f;
            while(f){
                f = {x:Math.floor(Math.random()*count),y:Math.floor(Math.random()*count)};
                if(snake.some(s=>s.x===f.x&&s.y===f.y)) f=null;
            }
            food = f;
        }
        spawnFood();

        // BFS寻路 AI核心
        function bfs(start,end,blockSet){
            const queue = [[start]];
            const visited = new Set();
            visited.add(`${start.x},${start.y}`);
            const dirs = [{x:1,y:0},{x:-1,y:0},{x:0,y:1},{x:0,y:-1}];
            while(queue.length>0){
                const path = queue.shift();
                const cur = path[path.length-1];
                if(cur.x===end.x&&cur.y===end.y) return path;
                for(let d of dirs){
                    const nx = cur.x+d.x;
                    const ny = cur.y+d.y;
                    if(nx>=0&&nx<count&&ny>=0&&ny<count){
                        const key = `${nx},${ny}`;
                        if(!visited.has(key) && !blockSet.has(key)){
                            visited.add(key);
                            queue.push([...path,{x:nx,y:ny}]);
                        }
                    }
                }
            }
            return null;
        }

        // AI获取下一步方向
        function getAIDirection(){
            const head = snake[0];
            const bodySet = new Set(snake.map(s=>`${s.x},${s.y}`));
            const path = bfs(head,food,bodySet);
            if(path){
                const next = path[1];
                return {x:next.x-head.x,y:next.y-head.y};
            }else{
                // 找不到食物，找安全方向，防止死路
                const dirs = [{x:1,y:0},{x:-1,y:0},{x:0,y:1},{x:0,y:-1}];
                for(let d of dirs){
                    const nx = head.x+d.x;
                    const ny = head.y+d.y;
                    if(nx>=0&&nx<count&&ny>=0&&ny<count && !bodySet.has(`${nx},${ny}`)){
                        return d;
                    }
                }
                return dir;
            }
        }

        // 绘制
        function draw(){
            ctx.fillStyle="#fff";
            ctx.fillRect(0,0,canvas.width,canvas.height);
            // 蛇
            ctx.fillStyle="#22aa22";
            snake.forEach(seg=>ctx.fillRect(seg.x*grid,seg.y*grid,grid-1,grid-1));
            //食物
            ctx.fillStyle="#ff3333";
            ctx.fillRect(food.x*grid,food.y*grid,grid-1,grid-1);
        }

        // 更新游戏
        function update(){
            if(gameOver) return;
            if(aiMode){
                nextDir = getAIDirection();
            }
            dir = nextDir;
            const head = {x:snake[0].x+dir.x,y:snake[0].y+dir.y};
            //撞墙判定
            if(head.x<0||head.x>=count||head.y<0||head.y>=count){
                gameOver=true;
                alert("游戏结束！");
                return;
            }
            //撞自己
            if(snake.some(s=>s.x===head.x&&s.y===head.y)){
                gameOver=true;
                alert("游戏结束！");
                return;
            }
            snake.unshift(head);
            //吃到食物
            if(head.x===food.x&&head.y===food.y){
                score+=10;
                eatCount++;
                if(score>highScore){
                    highScore=score;
                    localStorage.setItem('snakeHigh',highScore);
                    document.getElementById('highScore').innerText=highScore;
                }
                document.getElementById('score').innerText=score;
                document.getElementById('eatCount').innerText=eatCount;
                spawnFood();
            }else{
                snake.pop();
            }
            draw();
        }

        // 键盘手动控制
        window.addEventListener('keydown',e=>{
            if(aiMode||gameOver) return;
            switch(e.key){
                case 'ArrowUp': if(dir.y!==1) nextDir={x:0,y:-1};break;
                case 'ArrowDown': if(dir.y!==-1) nextDir={x:0,y:1};break;
                case 'ArrowLeft': if(dir.x!==1) nextDir={x:-1,y:0};break;
                case 'ArrowRight': if(dir.x!==-1) nextDir={x:1,y:0};break;
            }
        })

        // 重置按钮
        document.getElementById('resetBtn').onclick = ()=>{
            clearInterval(timer);
            snake = [{x:10,y:10}];
            dir = {x:1,y:0};
            nextDir = {x:1,y:0};
            score=0;eatCount=0;gameOver=false;
            document.getElementById('score').innerText=0;
            document.getElementById('eatCount').innerText=0;
            spawnFood();
            draw();
            timer = setInterval(update,120);
        }

        // AI开关
        document.getElementById('aiToggle').onclick = function(){
            aiMode = !aiMode;
            this.innerText = aiMode ? "关闭AI自动游玩" : "开启AI自动游玩";
        }

        // 启动
        draw();
        timer = setInterval(update,120);
    </script>
</body>
</html>
