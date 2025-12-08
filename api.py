from fastapi import FastAPI, Query
from game import ModeratorAgent
import asyncio
import json

# 初始化FastAPI服务
app = FastAPI(title="狼人杀智能体API", description="对接扣子智能体的狼人杀游戏接口")
moderator = ModeratorAgent()  # 初始化游戏主持人

# 解决异步兼容问题
try:
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
except:
    pass

# 接口1：开始狼人杀游戏
@app.get("/start_werewolf", summary="开始一局狼人杀游戏")
async def start_werewolf(
    game_rounds: int = Query(default=1, description="游戏局数，默认1局")
):
    """调用后运行狼人杀游戏，返回完整游戏日志"""
    # 重置游戏状态
    moderator.game_count = 0
    moderator.final_stats = {name: {"total": 0, "wins": 0, "win_rate": 0.0} for name in moderator.player_agents.keys()}
    for agent in moderator.player_agents.values():
        agent.reset_game_state()
    
    # 捕获游戏输出
    import io
    import sys
    old_stdout = sys.stdout
    sys.stdout = captured_output = io.StringIO()
    
    try:
        # 运行指定局数
        for _ in range(game_rounds):
            await moderator.run_game()
        await moderator.show_final_ranking()
        game_log = captured_output.getvalue()
        return {
            "status": "success",
            "game_log": game_log,
            "message": f"已完成{game_rounds}局狼人杀游戏"
        }
    finally:
        sys.stdout = old_stdout

# 接口2：查询胜率排名
@app.get("/get_ranking", summary="获取最新胜率排名")
async def get_ranking():
    """返回所有玩家的胜率排名"""
    ranking = []
    for name, stats in moderator.final_stats.items():
        ranking.append({
            "player_name": name,
            "total_games": stats["total"],
            "wins": stats["wins"],
            "win_rate": stats["win_rate"]
        })
    ranking.sort(key=lambda x: (-x["win_rate"], -x["wins"]))
    return {
        "status": "success",
        "ranking": ranking,
        "total_games_played": moderator.game_count
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)