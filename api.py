from fastapi import FastAPI, Query
from game import ModeratorAgent
import asyncio
import json
import io
import sys

# 1. 初始化FastAPI服务（对接扣子智能体的接口配置）
app = FastAPI(
    title="狼人杀智能体API",
    description="基于AgentScope的狼人杀多智能体接口，支持游戏启动与胜率查询",
    version="1.0.0"
)

# 2. 初始化游戏主持人（全局单例，确保跨接口状态一致）
moderator = ModeratorAgent()


# 3. 核心接口1：启动狼人杀游戏（支持自定义局数）
@app.get("/start_werewolf", summary="开始1-N局狼人杀游戏", tags=["游戏控制"])
async def start_werewolf(
    game_rounds: int = Query(
        default=1,
        ge=1,
        le=5,
        description="游戏局数，1-5局（Vercel单次请求超时限制内推荐≤3局）"
    )
):
    """
    调用后自动运行指定局数的狼人杀游戏，返回完整游戏日志：
    - 包含每局角色分配、狼人讨论、昼夜行动、投票结果
    - 智能体自学习策略优化记录
    - 全局胜率统计
    """
    # 重置游戏状态（避免多轮调用数据污染）
    moderator.game_count = 0
    moderator.final_stats = {
        name: {"total": 0, "wins": 0, "win_rate": 0.0} 
        for name in moderator.player_agents.keys()
    }
    for agent in moderator.player_agents.values():
        agent.reset_game_state()

    # 捕获游戏终端输出（转为JSON返回）
    old_stdout = sys.stdout
    captured_output = io.StringIO()
    sys.stdout = captured_output

    try:
        # 纯异步调用游戏逻辑（适配FastAPI异步环境，无循环冲突）
        for _ in range(game_rounds):
            await moderator.run_game()
        await moderator.show_final_ranking()

        # 整理返回结果
        game_log = captured_output.getvalue()
        return {
            "status": "success",
            "code": 200,
            "message": f"成功完成{game_rounds}局狼人杀游戏",
            "data": {
                "game_log": game_log,
                "total_rounds": game_rounds,
                "total_players": len(moderator.player_agents)
            }
        }
    except Exception as e:
        # 异常捕获（返回具体错误信息便于调试）
        return {
            "status": "error",
            "code": 500,
            "message": f"游戏运行失败：{str(e)}",
            "data": None
        }
    finally:
        # 恢复标准输出（避免资源泄漏）
        sys.stdout = old_stdout


# 4. 核心接口2：查询最新胜率排名（支持跨游戏局累计统计）
@app.get("/get_ranking", summary="获取所有玩家胜率排名", tags=["数据查询"])
async def get_ranking():
    """
    返回当前所有玩家的胜率排名（按胜率降序→胜场数降序排序）：
    - 包含玩家名、总局数、胜场数、胜率
    - 支持游戏运行中实时查询
    """
    # 整理排名数据（结构化输出，便于扣子智能体解析）
    ranking_list = []
    for player_name, stats in moderator.final_stats.items():
        ranking_list.append({
            "player_name": player_name,
            "total_games": stats["total"],
            "win_count": stats["wins"],
            "win_rate": round(stats["win_rate"] * 100, 1),  # 转为百分比（保留1位小数）
            "win_rate_raw": stats["win_rate"]  # 原始小数（备用）
        })

    # 排序（优先级：胜率降序 > 胜场数降序 > 玩家名升序）
    ranking_list.sort(
        key=lambda x: (-x["win_rate"], -x["win_count"], x["player_name"])
    )

    return {
        "status": "success",
        "code": 200,
        "message": f"共{len(ranking_list)}名玩家，累计运行{moderator.game_count}局",
        "data": {
            "ranking": ranking_list,
            "update_time": asyncio.get_event_loop().time()  # 时间戳（便于缓存判断）
        }
    }


# 5. 健康检查接口（Vercel部署后验证服务可用性）
@app.get("/health", summary="服务健康检查", tags=["系统"])
async def health_check():
    return {
        "status": "success",
        "code": 200,
        "message": "狼人杀API服务正常运行",
        "data": {
            "dependencies": {
                "fastapi": "available",
                "agentscope": "available",
                "uvicorn": "available"
            },
            "agent_count": len(moderator.player_agents)
        }
    }


# 6. 本地运行入口（开发调试用，Vercel部署时自动忽略）
if __name__ == "__main__":
    import uvicorn
    # 本地运行配置（支持热重载）
    uvicorn.run(
        app="api:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        reload_dirs=["."],  # 监听当前目录文件变化
        workers=1  # 单进程（确保游戏状态一致性）
    )