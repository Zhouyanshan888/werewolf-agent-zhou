import asyncio
from agentscope.message import Msg
from agent import PlayerAgent
import random

# 全局配置（九人制狼人杀标准规则）
TOTAL_PLAYERS = 9
TOTAL_GAMES = 3  # 本地运行默认局数，API调用时可自定义
ROLE_CONFIG = {
    "werewolf": 3,    # 3狼人
    "seer": 1,        # 1预言家
    "witch": 1,       # 1女巫
    "hunter": 1,      # 1猎人
    "villager": 3     # 3平民
}
ALL_PLAYERS = [f"Player{i}" for i in range(1, TOTAL_PLAYERS + 1)]  # Player1-Player9


class ModeratorAgent:
    def __init__(self):
        """初始化游戏主持人：创建所有玩家智能体、初始化统计数据"""
        self.game_count = 0  # 已进行游戏局数
        # 为每个玩家创建PlayerAgent实例
        self.player_agents = {name: PlayerAgent(name) for name in ALL_PLAYERS}
        # 玩家胜率统计（总局数、胜场数、胜率）
        self.final_stats = {
            name: {"total": 0, "wins": 0, "win_rate": 0.0} 
            for name in ALL_PLAYERS
        }

    def assign_roles(self) -> dict:
        """随机分配角色：按ROLE_CONFIG比例打乱，返回{玩家名: 角色}字典"""
        roles = []
        # 按配置生成角色列表
        for role, count in ROLE_CONFIG.items():
            roles.extend([role] * count)
        # 随机打乱角色顺序
        random.shuffle(roles)
        # 绑定玩家与角色
        return dict(zip(ALL_PLAYERS, roles))

    async def send_private_role(self, player_agent: PlayerAgent, role: str) -> None:
        """向玩家发送私有角色信息（符合AgentScope框架消息格式）"""
        private_msg = Msg(
            name="Moderator",  # 消息发送者（主持人）
            content=[{"type": "text", "text": f"[{player_agent.name} ONLY] Your role: {role.upper()}"}],
            role="system"  # 消息角色（系统通知）
        )
        # 调用PlayerAgent的observe方法接收角色信息
        await player_agent.observe(private_msg)

    def get_alive_players(self, role_map: dict, eliminated: list) -> list:
        """获取当前存活玩家列表：排除已淘汰玩家"""
        return [
            p for p in ALL_PLAYERS 
            if p not in eliminated  # 未被淘汰
            and role_map.get(p) is not None  # 角色分配有效
        ]

    async def wolf_discussion(self, wolf_agents: list, role_map: dict, alive_players: list) -> list:
        """狼人讨论阶段：3轮讨论，批量异步获取狼人建议（适配Vercel无阻塞运行）"""
        discussion_records = []
        for round_num in range(1, 4):  # 共3轮讨论
            discussion_records.append(f"\n--- 狼人讨论第{round_num}轮 ---")
            # 批量创建异步任务（减少Vercel环境下的阻塞时间）
            tasks = [
                agent(
                    role_map=role_map, 
                    alive_players=alive_players, 
                    action_type="discussion"  # 标记为“讨论”动作
                ) 
                for agent in wolf_agents
            ]
            # 批量执行任务并获取结果
            proposal_msgs = await asyncio.gather(*tasks)
            # 整理讨论记录（玩家名+建议内容）
            for agent, msg in zip(wolf_agents, proposal_msgs):
                proposal = msg.content[0]["text"]
                discussion_records.append(f"🐺 {agent.name}: {proposal}")
        return discussion_records

    async def get_wolf_target(self, wolf_agents: list, role_map: dict, alive_players: list) -> str:
        """获取狼人统一刀人目标：统计狼人投票最高票，无票时随机兜底"""
        targets = []
        # 收集每个狼人的目标选择
        for agent in wolf_agents:
            # 调用PlayerAgent获取目标（action_type默认"vote"）
            target_msg = await agent(role_map=role_map, alive_players=alive_players)
            # 解析消息内容（转为字典），无vote字段时随机选存活玩家（兜底）
            target_data = eval(target_msg.content[0]["text"])
            target = target_data.get(
                "vote", 
                random.choice([p for p in alive_players if p != agent.name])
            )
            targets.append(target)
        
        # 统计最高票目标
        target_counts = {t: targets.count(t) for t in targets}
        max_count = max(target_counts.values())
        candidate_targets = [t for t, c in target_counts.items() if c == max_count]
        # 票数相同时随机选择
        return random.choice(candidate_targets)

    async def daytime_voting(self, alive_agents: list, role_map: dict, alive_players: list) -> tuple:
        """白天投票阶段：收集所有存活玩家投票，返回淘汰者、投票详情、投票记录"""
        votes = {}  # {投票者: 被投票者}
        vote_details = []  # 投票详情（用于日志输出）
        
        # 收集每个存活玩家的投票
        for agent in alive_agents:
            # 调用PlayerAgent获取投票目标
            vote_msg = await agent(role_map=role_map, alive_players=alive_players)
            vote_text = vote_msg.content[0]["text"]
            vote_data = eval(vote_text)
            
            # 兜底逻辑：无vote字段时随机投其他存活玩家
            target = vote_data.get(
                "vote", 
                random.choice([p for p in alive_players if p != agent.name])
            )
            votes[agent.name] = target
            # 记录投票详情（含玩家完整发言）
            vote_details.append(f"🗳️ {agent.name}: {vote_text}")
        
        # 统计投票结果，确定淘汰者
        target_counts = {t: list(votes.values()).count(t) for t in votes.values()}
        max_count = max(target_counts.values())
        candidate_targets = [t for t, c in target_counts.items() if c == max_count]
        eliminated = random.choice(candidate_targets)
        
        return eliminated, vote_details, votes

    async def run_game(self) -> None:
        """运行单局游戏：完整流程（角色分配→昼夜交替→胜负判定→统计更新）"""
        self.game_count += 1
        print(f"\n==================== 第{self.game_count}局游戏 ====================")
        
        # 初始化本局变量
        role_map = self.assign_roles()  # 随机分配角色
        eliminated = []  # 已淘汰玩家列表
        game_over = False  # 游戏是否结束
        round_num = 1  # 当前轮次（昼夜为一轮）
        
        # 1. 向所有玩家发送私有角色信息
        for name, role in role_map.items():
            await self.send_private_role(self.player_agents[name], role)
        
        # 2. 开局提示（日志输出）
        print(f"\n📢 Moderator: A new game is starting! Players: {', '.join(ALL_PLAYERS)}.")
        print("Assigning roles privately...")
        print(f"\n🎭 All Roles (for demo):")
        for name, role in role_map.items():
            print(f" - {name}: {role.upper()}")
        
        # 3. 游戏主循环（昼夜交替，直到分出胜负）
        while not game_over:
            print(f"\n--- 第{round_num}轮（夜晚+白天）---")
            alive_players = self.get_alive_players(role_map, eliminated)
            # 获取当前存活的狼人及对应智能体
            wolf_players = [p for p in alive_players if role_map[p] == "werewolf"]
            wolf_agents = [self.player_agents[p] for p in wolf_players]

            # ------------------- 夜晚阶段 -------------------
            print(f"\n📢 Moderator:")
            print("🌙 Night falls! Everyone close eyes. Werewolves open eyes!")
            print(f"🗣️ Werewolves (alive): {', '.join(wolf_players) if wolf_players else 'None'}")
            
            # 狼人刀人（至少1只狼存活才进行）
            wolf_target = None
            if len(wolf_agents) >= 1:
                # 狼人讨论（3轮）
                discussion_records = await self.wolf_discussion(wolf_agents, role_map, alive_players)
                print("\n🗣️ Werewolf Discussion (3 rounds):")
                print('\n'.join(discussion_records))
                
                # 狼人统一刀人目标
                wolf_target = await self.get_wolf_target(wolf_agents, role_map, alive_players)
                print(f"\n🐺 Werewolves reach agreement: Eliminate {wolf_target}!")
                
                # 狼人确认目标（输出确认信息）
                print(f"\n📢 Moderator (to werewolves): Confirm eliminate {wolf_target}!")
                for agent in wolf_agents:
                    confirm_msg = await agent(role_map=role_map, alive_players=alive_players)
                    print(f"🐺 {agent.name}: {confirm_msg.content[0]['text']}")
                
                # 标记被刀玩家为淘汰
                if wolf_target not in eliminated:
                    eliminated.append(wolf_target)
                    self.player_agents[wolf_target].mark_dead()  # 更新玩家存活状态
            
            # 女巫用药（仅当前存活女巫可操作）
            witch_players = [p for p in alive_players if role_map[p] == "witch"]
            if witch_players:
                witch_agent = self.player_agents[witch_players[0]]
                print(f"\n📢 Moderator:")
                print("🧙 Witch's turn: Open eyes! You have poison/resurrect potion (one-time use).")
                
                # 获取女巫操作（复活/毒人）
                witch_action = await witch_agent(role_map=role_map, alive_players=alive_players)
                witch_text = witch_action.content[0]["text"]
                witch_data = eval(witch_text)
                print(f"🧙 {witch_agent.name}: {witch_text}")
                
                # 女巫复活（仅被刀玩家可复活，且复活药未使用）
                if witch_data.get("resurrect") and not witch_agent.witch_used["resurrect"]:
                    if wolf_target and wolf_target in eliminated:
                        eliminated.remove(wolf_target)
                        self.player_agents[wolf_target].alive = True  # 恢复存活状态
                        print(f"🧙 Witch resurrects {wolf_target}!")
                    witch_agent.witch_used["resurrect"] = True  # 标记复活药已使用
                
                # 女巫毒人（仅存活玩家可毒，且毒药未使用）
                if witch_data.get("poison") and not witch_agent.witch_used["poison"]:
                    # 优先毒存活狼人，无狼人时随机毒存活玩家（兜底）
                    poison_candidates = [p for p in alive_players if role_map[p] == "werewolf"] or alive_players
                    poison_target = random.choice(poison_candidates)
                    if poison_target not in eliminated and poison_target != witch_agent.name:
                        eliminated.append(poison_target)
                        self.player_agents[poison_target].mark_dead()  # 标记死亡
                        print(f"🧙 Witch poisons {poison_target}!")
                    witch_agent.witch_used["poison"] = True  # 标记毒药已使用

            # ------------------- 白天阶段 -------------------
            print(f"\n📢 Moderator:")
            print("☀️ Day breaks! Everyone open eyes!")
            # 公布夜间淘汰玩家
            current_eliminated = [p for p in eliminated if p in alive_players]
            if current_eliminated:
                print(f"📢 Moderator: Eliminated player(s) last night: {', '.join(current_eliminated)}!")
                # 输出被淘汰玩家的“遗言”
                for p in current_eliminated:
                    dead_agent = self.player_agents[p]
                    last_word_msg = await dead_agent(role_map=role_map, alive_players=alive_players)
                    print(f"💀 {p} (last word): {last_word_msg.content[0]['text']}")
            else:
                print(f"📢 Moderator: No one was eliminated last night!")
            
            # 预言家验人（仅当前存活预言家可操作）
            seer_players = [p for p in alive_players if role_map[p] == "seer"]
            if seer_players:
                seer_agent = self.player_agents[seer_players[0]]
                print(f"\n📢 Moderator:")
                print("🔮 Seer's turn: Open eyes! Check one player's identity.")
                # 获取预言家验人结果
                seer_action = await seer_agent(role_map=role_map, alive_players=alive_players)
                print(f"🔮 {seer_agent.name}: {seer_action.content[0]['text']}")
            
            # 全体投票淘汰（存活玩家参与）
            alive_agents = [self.player_agents[p] for p in alive_players]
            print(f"\n📢 Moderator:")
            print(f"🗣️ Alive players: {', '.join(alive_players)}")
            print("🗳️ Daytime voting: All alive players vote to eliminate one player!")
            # 执行投票
            vote_eliminated, vote_details, votes = await self.daytime_voting(alive_agents, role_map, alive_players)
            # 输出投票详情
            print('\n'.join(vote_details))
            print(f"\n📢 Moderator: Public voting result: {vote_eliminated} (votes: {list(votes.values()).count(vote_eliminated)}) is eliminated!")
            
            # 标记投票淘汰玩家
            if vote_eliminated not in eliminated:
                eliminated.append(vote_eliminated)
                self.player_agents[vote_eliminated].mark_dead()  # 更新存活状态
            
            # 猎人开枪（被投票淘汰且猎人存活时触发）
            if role_map.get(vote_eliminated) == "hunter" and vote_eliminated in alive_players:
                hunter_agent = self.player_agents[vote_eliminated]
                hunter_action = await hunter_agent(role_map=role_map, alive_players=alive_players)
                hunter_data = eval(hunter_action.content[0]["text"])
                # 猎人选择是否开枪
                if hunter_data.get("shoot"):
                    # 优先射存活狼人，无狼人时随机射存活玩家（兜底）
                    shoot_candidates = [p for p in alive_players if role_map[p] == "werewolf"] or [p for p in alive_players if p != vote_eliminated]
                    shoot_target = hunter_data.get("vote", random.choice(shoot_candidates))
                    if shoot_target in alive_players and shoot_target != vote_eliminated:
                        eliminated.append(shoot_target)
                        self.player_agents[shoot_target].mark_dead()
                        print(f"\n🔫 Hunter {vote_eliminated} shoots {shoot_target}! {shoot_target} is eliminated!")

            # ------------------- 胜负判定 -------------------
            # 统计当前存活狼人和平民阵营人数
            final_alive_players = self.get_alive_players(role_map, eliminated)
            final_alive_wolves = [p for p in final_alive_players if role_map[p] == "werewolf"]
            final_alive_good = [p for p in final_alive_players if role_map[p] != "werewolf"]
            
            print(f"\n📊 Current status: Alive wolves: {len(final_alive_wolves)} | Alive good players: {len(final_alive_good)}")
            
            # 判定条件1：狼人全部淘汰 → 好人阵营胜利
            if len(final_alive_wolves) == 0:
                print(f"\n📢 Moderator:")
                print("🎉 ===== GAME OVER =====\n🏆 Good players win!")
                # 更新玩家胜率统计
                for name, agent in self.player_agents.items():
                    if role_map[name] != "werewolf":  # 好人阵营
                        agent.mark_win()
                        self.final_stats[name]["wins"] += 1
                    else:  # 狼人阵营
                        agent.mark_lose()
                    # 更新总局数和胜率
                    self.final_stats[name]["total"] += 1
                    self.final_stats[name]["win_rate"] = round(
                        self.final_stats[name]["wins"] / self.final_stats[name]["total"], 
                        2
                    )
                game_over = True
            
            # 判定条件2：狼人数 ≥ 好人人数 → 狼人阵营胜利
            elif len(final_alive_wolves) >= len(final_alive_good):
                print(f"\n📢 Moderator:")
                print("🎉 ===== GAME OVER =====\n🏆 Werewolves win!")
                # 更新玩家胜率统计
                for name, agent in self.player_agents.items():
                    if role_map[name] == "werewolf":  # 狼人阵营
                        agent.mark_win()
                        self.final_stats[name]["wins"] += 1
                    else:  # 好人阵营
                        agent.mark_lose()
                    # 更新总局数和胜率
                    self.final_stats[name]["total"] += 1
                    self.final_stats[name]["win_rate"] = round(
                        self.final_stats[name]["wins"] / self.final_stats[name]["total"], 
                        2
                    )
                game_over = True
            
            # ------------------- 智能体策略优化 -------------------
            # 所有玩家更新历史记录（用于下局自学习）
            for name, agent in self.player_agents.items():
                if name in votes:  # 该玩家参与了本轮投票
                    vote_target = votes[name]
                    # 判断该玩家是否胜利（用于统计目标胜率）
                    is_win = (role_map[name] != "werewolf" and len(final_alive_wolves) == 0) or \
                             (role_map[name] == "werewolf" and len(final_alive_wolves) >= len(final_alive_good))
                    # 更新玩家历史记录（自学习核心）
                    agent.update_history(vote_target, is_win, role_map)
            
            # 进入下一轮
            round_num += 1

        # ------------------- 本局总结 -------------------
        print(f"\n📈 Agent Strategy Optimization Result (Game {self.game_count}):")
        for name, agent in self.player_agents.items():
            print(f" - {name}: High-win targets={agent.effective_targets}, Win rate={agent.win_rate}")
        
        print(f"\n📢 Moderator:")
        print("💭 Reflection time: Each player reviews their performance!")
        # 输出每个玩家的本局表现
        for name, agent in self.player_agents.items():
            role = role_map[name].upper()
            win_flag = "Won" if (role != "WEREWOLF" and len(final_alive_wolves) == 0) or \
                               (role == "WEREWOLF" and len(final_alive_wolves) >= len(final_alive_good)) else "Lost"
            print(f"🤔 {name}: Role={role}, Win rate={agent.win_rate}, High-win targets={agent.effective_targets}! Result: {win_flag}")
        
        # 重置所有玩家的本局状态（为下局准备）
        for agent in self.player_agents.values():
            agent.reset_game_state()

    async def show_final_ranking(self):
        """展示全局胜率排名：按胜率→胜场数→玩家名排序，带颜色标记（终端可见）"""
        print(f"\n📊 Final Win Rate Ranking (Total Games: {self.game_count})")
        print("-" * 60)
        # 排序：胜率降序 → 胜场数降序 → 玩家名升序
        sorted_players = sorted(
            self.final_stats.items(),
            key=lambda x: (-x[1]["win_rate"], -x[1]["wins"], x[0])
        )
        # 输出排名
        for i, (name, stats) in enumerate(sorted_players, 1):
            win_rate = stats["win_rate"]
            wins = stats["wins"]
            total = stats["total"]
            
            # 胜率颜色标记（终端ANSI代码）：高胜率绿色、中等黄色、低胜率红色
            if win_rate >= 0.8:
                rate_str = f"\033[92m{win_rate:.2f}\033[0m"  # 绿色
            elif win_rate >= 0.5:
                rate_str = f"\033[93m{win_rate:.2f}\033[0m"  # 黄色
            else:
                rate_str = f"\033[91m{win_rate:.2f}\033[0m"  # 红色
            
            print(f" {i:2d}. {name:8s} | Total Games: {total:2d} | Wins: {wins:2d} | Win Rate: {rate_str}")
        print("-" * 60)
        
        # 输出详细统计
        print(f"\n🏆 Final Win Rate Statistics:")
        for name, stats in self.final_stats.items():
            print(f" - {name}: Total Games={stats['total']}, Wins={stats['wins']}, Win Rate={stats['win_rate']}")
        print("\n🎮 Game finished! Thanks for playing!")

    async def run(self):
        """运行多局游戏：默认运行TOTAL_GAMES局，结束后展示全局排名"""
        for _ in range(TOTAL_GAMES):
            await self.run_game()
        await self.show_final_ranking()


# 本地运行入口（直接执行game.py时触发，Vercel部署时不执行）
if __name__ == "__main__":
    # Windows系统异步事件循环兼容（解决本地运行报错）
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except:
        pass
    # 初始化主持人并启动游戏
    moderator = ModeratorAgent()
    asyncio.run(moderator.run())