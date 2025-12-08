import asyncio
from agentscope.message import Msg
from agent import PlayerAgent
import random

# 全局配置
TOTAL_PLAYERS = 9
TOTAL_GAMES = 3
ROLE_CONFIG = {
    "werewolf": 3,
    "seer": 1,
    "witch": 1,
    "hunter": 1,
    "villager": 3
}
ALL_PLAYERS = [f"Player{i}" for i in range(1, TOTAL_PLAYERS + 1)]

class ModeratorAgent:
    def __init__(self):
        self.game_count = 0
        self.player_agents = {name: PlayerAgent(name) for name in ALL_PLAYERS}
        self.final_stats = {name: {"total": 0, "wins": 0, "win_rate": 0.0} for name in ALL_PLAYERS}

    def assign_roles(self) -> dict:
        """随机分配角色（符合九人制规则）"""
        roles = []
        for role, count in ROLE_CONFIG.items():
            roles.extend([role] * count)
        random.shuffle(roles)
        return dict(zip(ALL_PLAYERS, roles))

    async def send_private_role(self, player_agent: PlayerAgent, role: str) -> None:
        """发送私有角色信息（AgentScope方式）"""
        private_msg = Msg(
            name="Moderator",
            content=[{"type": "text", "text": f"[{player_agent.name} ONLY] Your role: {role.upper()}"}],
            role="system"
        )
        await player_agent.observe(private_msg)

    def get_alive_players(self, role_map: dict, eliminated: list) -> list:
        """获取存活玩家列表"""
        return [p for p in ALL_PLAYERS if p not in eliminated and role_map.get(p) is not None]

    async def wolf_discussion(self, wolf_agents: list, role_map: dict, alive_players: list) -> list:
        """狼人3轮讨论"""
        discussion_records = []
        for round_num in range(1, 4):
            discussion_records.append(f"\n--- 狼人讨论第{round_num}轮 ---")
            for agent in wolf_agents:
                proposal_msg = await agent(role_map=role_map, alive_players=alive_players, action_type="discussion")
                proposal = proposal_msg.content[0]["text"]
                discussion_records.append(f"🐺 {agent.name}: {proposal}")
        return discussion_records

    async def get_wolf_target(self, wolf_agents: list, role_map: dict, alive_players: list) -> str:
        """获取狼人统一刀人目标"""
        targets = []
        for agent in wolf_agents:
            target_msg = await agent(role_map=role_map, alive_players=alive_players)
            target_data = eval(target_msg.content[0]["text"])
            target = target_data.get("vote", random.choice(alive_players))  # 兜底
            targets.append(target)
        
        # 统计最高票目标
        target_counts = {t: targets.count(t) for t in targets}
        max_count = max(target_counts.values())
        candidate_targets = [t for t, c in target_counts.items() if c == max_count]
        return random.choice(candidate_targets)

    async def daytime_voting(self, alive_agents: list, role_map: dict, alive_players: list) -> tuple:
        """白天投票（加兜底，解决KeyError）"""
        votes = {}
        vote_details = []
        for agent in alive_agents:
            vote_msg = await agent(role_map=role_map, alive_players=alive_players)
            vote_data = eval(vote_msg.content[0]["text"])
            # 兜底：取不到vote就随机选（排除自己）
            target = vote_data.get("vote", random.choice([p for p in alive_players if p != agent.name]))
            votes[agent.name] = target
            vote_details.append(f"🗳️ {agent.name}: {vote_msg.content[0]['text']}")
        
        # 统计投票结果
        target_counts = {t: list(votes.values()).count(t) for t in votes.values()}
        max_count = max(target_counts.values())
        candidate_targets = [t for t, c in target_counts.items() if c == max_count]
        eliminated = random.choice(candidate_targets)
        return eliminated, vote_details, votes

    async def run_game(self) -> None:
        """运行单局游戏"""
        self.game_count += 1
        print(f"\n==================== 第{self.game_count}局游戏 ====================")
        
        # 初始化本局变量
        role_map = self.assign_roles()
        eliminated = []
        game_over = False
        
        # 发送角色信息
        for name, role in role_map.items():
            await self.send_private_role(self.player_agents[name], role)
        
        # 开局提示
        print(f"\n📢 Moderator: A new game is starting! Players: {', '.join(ALL_PLAYERS)}.")
        print("Assigning roles privately...")
        print(f"\n🎭 All Roles (for demo):")
        for name, role in role_map.items():
            print(f" - {name}: {role.upper()}")
        
        round_num = 1
        while not game_over:
            print(f"\n--- 第{round_num}轮（夜晚+白天）---")
            alive_players = self.get_alive_players(role_map, eliminated)
            wolf_players = [p for p in alive_players if role_map[p] == "werewolf"]
            wolf_agents = [self.player_agents[p] for p in wolf_players]
            
            # 夜晚阶段：狼人刀人
            print(f"\n📢 Moderator:")
            print("🌙 Night falls! Everyone close eyes. Werewolves open eyes!")
            print(f"🗣️ Werewolves (alive): {', '.join(wolf_players)}")
            
            if len(wolf_agents) >= 1:
                # 狼人讨论
                discussion_records = await self.wolf_discussion(wolf_agents, role_map, alive_players)
                print("\n🗣️ Werewolf Discussion (3 rounds):")
                print(''.join(discussion_records))
                
                # 狼人统一目标
                wolf_target = await self.get_wolf_target(wolf_agents, role_map, alive_players)
                print(f"\n🐺 Werewolves reach agreement: Eliminate {wolf_target}!")
                
                # 狼人确认目标
                print(f"\n📢 Moderator (to werewolves): Confirm eliminate {wolf_target}!")
                for agent in wolf_agents:
                    confirm_msg = await agent(role_map=role_map, alive_players=alive_players)
                    print(f"🐺 {agent.name}: {confirm_msg.content[0]['text']}")
                
                # 标记被刀玩家
                eliminated.append(wolf_target)
                self.player_agents[wolf_target].mark_dead()
            
            # 夜晚阶段：女巫用药
            witch_player = [p for p in alive_players if role_map[p] == "witch"]
            if witch_player:
                witch_agent = self.player_agents[witch_player[0]]
                print(f"\n📢 Moderator:")
                print("🧙 Witch's turn: Open eyes! You have poison/resurrect potion (one-time use).")
                witch_action = await witch_agent(role_map=role_map, alive_players=alive_players)
                witch_data = eval(witch_action.content[0]["text"])
                print(f"🧙 {witch_agent.name}: {witch_action.content[0]['text']}")
                
                # 女巫救人
                if witch_data.get("resurrect") and wolf_target in eliminated:
                    eliminated.remove(wolf_target)
                    self.player_agents[wolf_target].alive = True
                    print(f"🧙 Witch resurrects {wolf_target}!")
                
                # 女巫毒人
                if witch_data.get("poison"):
                    # 随机选一个狼人毒（兜底）
                    poison_target = random.choice([p for p in alive_players if role_map[p] == "werewolf"]) if wolf_players else random.choice(alive_players)
                    if poison_target not in eliminated:
                        eliminated.append(poison_target)
                        self.player_agents[poison_target].mark_dead()
                        print(f"🧙 Witch poisons {poison_target}!")
                
                # 标记女巫用药
                witch_agent.witch_used["resurrect"] = witch_data.get("resurrect", False)
                witch_agent.witch_used["poison"] = witch_data.get("poison", False)
            
            # 白天阶段：公布死亡
            print(f"\n📢 Moderator:")
            print("☀️ Day breaks! Everyone open eyes!")
            current_eliminated = [p for p in eliminated if p in alive_players]
            if current_eliminated:
                print(f"📢 Moderator: Eliminated player: {', '.join(current_eliminated)}!")
                for p in current_eliminated:
                    dead_agent = self.player_agents[p]
                    last_word_msg = await dead_agent(role_map=role_map, alive_players=alive_players)
                    print(f"💀 {p} (last word): {last_word_msg.content[0]['text']}")
            
            # 白天阶段：预言家验人
            seer_player = [p for p in alive_players if role_map[p] == "seer"]
            if seer_player:
                seer_agent = self.player_agents[seer_player[0]]
                print(f"\n📢 Moderator:")
                print("🔮 Seer's turn: Open eyes! Check one player's identity.")
                seer_action = await seer_agent(role_map=role_map, alive_players=alive_players)
                print(f"🔮 {seer_agent.name}: {seer_action.content[0]['text']}")
            
            # 白天阶段：全体投票
            alive_agents = [self.player_agents[p] for p in alive_players]
            print(f"\n📢 Moderator:")
            print(f"🗣️ Alive players: {', '.join(alive_players)}")
            print("🗳️ Daytime voting: All alive players vote to eliminate one狼人!")
            vote_eliminated, vote_details, votes = await self.daytime_voting(alive_agents, role_map, alive_players)
            print('\n'.join(vote_details))
            print(f"\n📢 Moderator: Public voting result: {vote_eliminated} (votes: {list(votes.values()).count(vote_eliminated)}) is eliminated!")
            
            # 标记投票淘汰玩家
            eliminated.append(vote_eliminated)
            self.player_agents[vote_eliminated].mark_dead()
            
            # 猎人开枪
            if role_map.get(vote_eliminated) == "hunter" and vote_eliminated not in [p for p in eliminated if p != vote_eliminated]:
                hunter_agent = self.player_agents[vote_eliminated]
                hunter_action = await hunter_agent(role_map=role_map, alive_players=alive_players)
                hunter_data = eval(hunter_action.content[0]["text"])
                if hunter_data.get("shoot"):
                    shoot_target = hunter_data.get("vote", random.choice(alive_players))
                    if shoot_target in alive_players and shoot_target != vote_eliminated:
                        eliminated.append(shoot_target)
                        self.player_agents[shoot_target].mark_dead()
                        print(f"\nHunter {vote_eliminated} shoots {shoot_target}! {shoot_target} is eliminated!")
            
            # 判断游戏结束
            final_alive_wolves = [p for p in self.get_alive_players(role_map, eliminated) if role_map[p] == "werewolf"]
            final_alive_good = [p for p in self.get_alive_players(role_map, eliminated) if role_map[p] != "werewolf"]
            print(f"\n📊 Current status: Alive wolves: {len(final_alive_wolves)} | Alive good: {len(final_alive_good)}")
            
            if len(final_alive_wolves) == 0:
                print(f"\n📢 Moderator:")
                print("🎉 ===== GAME OVER =====\n🏆 Good players win!")
                # 更新胜率
                for name, agent in self.player_agents.items():
                    if role_map[name] != "werewolf":
                        agent.mark_win()
                        self.final_stats[name]["wins"] += 1
                    else:
                        agent.mark_lose()
                    self.final_stats[name]["total"] += 1
                    self.final_stats[name]["win_rate"] = round(self.final_stats[name]["wins"] / self.final_stats[name]["total"], 2)
                game_over = True
            elif len(final_alive_wolves) >= len(final_alive_good):
                print(f"\n📢 Moderator:")
                print("🎉 ===== GAME OVER =====\n🏆 Werewolves win!")
                # 更新胜率
                for name, agent in self.player_agents.items():
                    if role_map[name] == "werewolf":
                        agent.mark_win()
                        self.final_stats[name]["wins"] += 1
                    else:
                        agent.mark_lose()
                    self.final_stats[name]["total"] += 1
                    self.final_stats[name]["win_rate"] = round(self.final_stats[name]["wins"] / self.final_stats[name]["total"], 2)
                game_over = True
            
            # 更新智能体策略
            for name, agent in self.player_agents.items():
                if name in votes:
                    vote_target = votes[name]
                    is_win = (role_map[name] != "werewolf" and len(final_alive_wolves) == 0) or (role_map[name] == "werewolf" and len(final_alive_wolves) >= len(final_alive_good))
                    agent.update_history(vote_target, is_win, role_map)
            
            round_num += 1

        # 本局总结
        print(f"\n📈 Agent Strategy Optimization Result (Game {self.game_count}):")
        for name, agent in self.player_agents.items():
            print(f" - {name}: 高胜率目标={agent.effective_targets}, 胜率={agent.win_rate}")
        
        print(f"\n📢 Moderator:")
        print("💭 Reflection time: Each player reviews their performance!")
        final_alive_wolves = [p for p in self.get_alive_players(role_map, eliminated) if role_map[p] == "werewolf"]
        for name, agent in self.player_agents.items():
            role = role_map[name].upper()
            win_flag = '赢了' if (role != 'WEREWOLF' and len(final_alive_wolves) == 0) or (role == 'WEREWOLF' and len(final_alive_wolves) >= len(final_alive_good)) else '输了'
            print(f"🤔 {name}: 我是{role}，胜率：{agent.win_rate}，高胜率目标={agent.effective_targets}！{win_flag}")

        # 重置本局状态
        for agent in self.player_agents.values():
            agent.reset_game_state()

    async def show_final_ranking(self):
        """展示最终胜率排名"""
        print(f"\n📊 Final Win Rate Ranking (Total Games: {TOTAL_GAMES})")
        print("-" * 60)
        sorted_players = sorted(
            self.final_stats.items(),
            key=lambda x: (-x[1]["win_rate"], -x[1]["wins"], x[0])
        )
        for i, (name, stats) in enumerate(sorted_players, 1):
            win_rate = stats["win_rate"]
            wins = stats["wins"]
            total = stats["total"]
            
            # 胜率颜色标记（仅终端可见）
            if win_rate >= 0.8:
                rate_str = f"\033[92m{win_rate:.2f}\033[0m"
            elif win_rate >= 0.5:
                rate_str = f"\033[93m{win_rate:.2f}\033[0m"
            else:
                rate_str = f"\033[91m{win_rate:.2f}\033[0m"
            
            print(f" {i:2d}. {name:8s} | 总局数: {total:2d} | 胜场: {wins:2d} | 胜率: {rate_str}")
        print("-" * 60)
        
        print(f"\n🏆 Final Win Rate Statistics:")
        for name, stats in self.final_stats.items():
            print(f" - {name}: Total games={stats['total']}, Wins={stats['wins']}, Win rate={stats['win_rate']}")
        print("\n🎮 Game finished! Thanks for playing!")

    async def run(self):
        """运行多局游戏"""
        for _ in range(TOTAL_GAMES):
            await self.run_game()
        await self.show_final_ranking()

if __name__ == "__main__":
    # Windows异步事件循环兼容（解决运行报错）
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except:
        pass
    # 启动游戏
    moderator = ModeratorAgent()
    asyncio.run(moderator.run())