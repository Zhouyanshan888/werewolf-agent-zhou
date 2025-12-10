from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import asyncio
import json

# 初始化FastAPI应用（Coze要求必须有可访问的app实例）
app = FastAPI()

# 模拟狼人杀游戏逻辑（替换成你原有game.py/agent.py的调用逻辑）
async def run_werewolf_game(game_rounds: int = 1):
    """狼人杀游戏核心逻辑，返回标准结果"""
    # 这里替换成你原有game.py里的游戏运行代码
    result = {
        "game_rounds": game_rounds,
        "winner": "狼人阵营",
        "player_ranking": [{"name": "狼人1", "win_rate": 1.0}, {"name": "村民1", "win_rate": 0.0}],
        "log": "游戏运行完成：狼人阵营获胜"
    }
    await asyncio.sleep(2)  # 模拟游戏运行耗时
    return result

# 健康检查接口（用于验证服务是否正常）
@app.get("/health")
@app.post("/health")
async def health_check():
    return JSONResponse({
        "status": "success",
        "code": 200,
        "message": "狼人杀API服务正常运行",
        "data": {}
    })

# 狼人杀启动接口（适配Coze调用：支持POST/GET，接收参数，返回标准JSON）
@app.api_route("/start_werewolf", methods=["GET", "POST"])
async def start_werewolf(request: Request):
    try:
        # 兼容Coze的GET/POST参数传递
        if request.method == "GET":
            params = request.query_params
        else:
            params = await request.json()
        
        # 获取游戏局数（默认1局）
        game_rounds = int(params.get("game_rounds", 1))
        
        # 运行游戏逻辑
        game_result = await run_werewolf_game(game_rounds)
        
        # 返回Coze要求的标准JSON格式
        return JSONResponse({
            "status": "success",
            "code": 200,
            "message": "游戏运行成功",
            "data": game_result
        })
    except Exception as e:
        # 异常捕获，返回Coze可识别的错误格式
        return JSONResponse({
            "status": "failed",
            "code": 500,
            "message": f"游戏运行失败：{str(e)}",
            "data": {}
        }, status_code=200)  # 注意：Coze不接收500状态码，统一返回200

# 胜率查询接口（适配Coze调用）
@app.api_route("/get_ranking", methods=["GET", "POST"])
async def get_ranking():
    try:
        # 这里替换成你原有胜率统计逻辑
        ranking = [
            {"player": "狼人1", "win_times": 3, "total_times": 5, "win_rate": 0.6},
            {"player": "预言家1", "win_times": 2, "total_times": 5, "win_rate": 0.4},
            {"player": "村民1", "win_times": 1, "total_times": 5, "win_rate": 0.2}
        ]
        return JSONResponse({
            "status": "success",
            "code": 200,
            "message": "胜率排名查询成功",
            "data": ranking
        })
    except Exception as e:
        return JSONResponse({
            "status": "failed",
            "code": 500,
            "message": f"查询失败：{str(e)}",
            "data": {}
        }, status_code=200)

# Vercel Python运行时需要的入口（固定写法）
def handler(event, context):
    import mangum
    return mangum.Mangum(app)(event, context)
