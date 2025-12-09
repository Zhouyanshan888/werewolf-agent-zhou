# main.py（赛事启动文件）
import asyncio
from game import ModeratorAgent

if __name__ == "__main__":
    asyncio.run(ModeratorAgent().run())