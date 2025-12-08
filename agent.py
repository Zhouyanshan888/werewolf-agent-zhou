from agentscope.agent import AgentBase
from agentscope.message import Msg
from typing import Dict, Any, List
import random

ALL_PLAYERS = [f"Player{i}" for i in range(1, 10)]

class PlayerAgent(AgentBase):
    def __init__(self, name: str):
        # 适配所有AgentScope 1.0.x版本：无参初始化AgentBase
        super().__init__()
        # 手动绑定name属性
        self.name = name
        self.game_count = 0
        self.win_count = 0
        self.win_rate = 0.0
        self.role = None
        self.alive = True
        
        # 跨局记忆
        self.history = {
            "wolf_targets": [],
            "vote_records": [],
            "suspicious_players": set()
        }
        self.witch_used = {"resurrect": False, "poison": False}
        self.effective_targets = []
        self.target_history = {}

    def filter_self(self, target_list: List[str]) -> List[str]:
        return [t for t in target_list if t != self.name and t in ALL_PLAYERS]

    def get_opponent_camp(self, role_map: Dict[str, str]) -> List[str]:
        if self.role == "werewolf":
            return [p for p in ALL_PLAYERS if role_map.get(p, "") != "werewolf" and p != self.name]
        else:
            return [p for p in ALL_PLAYERS if role_map.get(p, "") == "werewolf"]

    def get_key_players(self, role_map: Dict[str, str], alive_players: List[str], camp: str = "good") -> List[str]:
        key_roles = ["seer", "hunter", "witch"]
        if camp == "good":
            return [p for p in alive_players if role_map.get(p, "") in key_roles and role_map.get(p, "") != "werewolf"]
        else:
            return [p for p in alive_players if role_map.get(p, "") == "werewolf"]

    async def observe(self, msg: Msg) -> None:
        """接收角色信息（赛事强制要求）"""
        msg_text = msg.content[0]["text"] if msg.content else ""
        if f"[{self.name} ONLY] Your role:" in msg_text:
            self.role = msg_text.split("Your role: ")[1].strip().lower()

    def _smart_target(self, role_map: Dict[str, str], alive_players: List[str]) -> str:
        """智能选目标（对立阵营+存活）"""
        opponent_camp_alive = [p for p in self.get_opponent_camp(role_map) if p in alive_players]
        
        # 优先选高胜率目标
        effective_opponent_targets = [t for t in self.effective_targets if t in opponent_camp_alive]
        if effective_opponent_targets:
            return random.choice(effective_opponent_targets)
        
        # 次选可疑玩家
        suspicious_opponents = [t for t in self.history["suspicious_players"] if t in opponent_camp_alive]
        if suspicious_opponents:
            return random.choice(suspicious_opponents)
        
        # 随机选对立阵营
        if opponent_camp_alive:
            return random.choice(opponent_camp_alive)
        
        # 兜底
        non_self_alive = [p for p in alive_players if p != self.name]
        return non_self_alive[0] if non_self_alive else "Player1"

    def _get_target_win_rate(self, target: str) -> int:
        """目标胜率（百分比）"""
        stats = self.target_history.get(target, {"win": 0, "total": 0})
        return round(stats["win"] / stats["total"] * 100) if stats["total"] > 0 else 50

    def optimize_strategy(self) -> None:
        """自学习策略优化"""
        if not self.history["vote_records"]:
            return
        
        # 统计目标胜率
        for record in self.history["vote_records"]:
            target = record["target"]
            is_win = record["win"]
            if target not in self.target_history:
                self.target_history[target] = {"win": 0, "total": 0}
            self.target_history[target]["total"] += 1
            if is_win:
                self.target_history[target]["win"] += 1
        
        # 筛选高胜率目标
        self.effective_targets = [
            t for t, stats in self.target_history.items()
            if stats["total"] > 0 and stats["win"] / stats["total"] > 0.5
        ]

    def update_history(self, vote_target: str, is_win: bool, role_map: Dict[str, str]) -> None:
        """更新跨局记忆"""
        opponent_camp = self.get_opponent_camp(role_map)
        if vote_target in opponent_camp and vote_target != self.name:
            self.history["vote_records"].append({"target": vote_target, "win": is_win})
            if self.role == "werewolf":
                self.history["wolf_targets"].append(vote_target)
            if not is_win:
                self.history["suspicious_players"].add(vote_target)
            # 更新目标胜率
            if vote_target not in self.target_history:
                self.target_history[vote_target] = {"win": 0, "total": 0}
            self.target_history[vote_target]["total"] += 1
            if is_win:
                self.target_history[vote_target]["win"] += 1
        self.optimize_strategy()

    def state_dict(self) -> Dict[str, Any]:
        """赛事强制要求：状态保存"""
        return {
            "name": self.name,
            "game_count": self.game_count,
            "win_count": self.win_count,
            "win_rate": self.win_rate,
            "role": self.role,
            "alive": self.alive,
            "history": {
                "wolf_targets": self.history["wolf_targets"],
                "vote_records": self.history["vote_records"],
                "suspicious_players": list(self.history["suspicious_players"])
            },
            "witch_used": self.witch_used,
            "effective_targets": self.effective_targets,
            "target_history": self.target_history
        }

    def load_state_dict(self, state_dict: Dict[str, Any]) -> None:
        """赛事强制要求：状态加载"""
        self.name = state_dict.get("name", self.name)
        self.game_count = state_dict.get("game_count", 0)
        self.win_count = state_dict.get("win_count", 0)
        self.win_rate = state_dict.get("win_rate", 0.0)
        self.role = state_dict.get("role", None)
        self.alive = state_dict.get("alive", True)
        history = state_dict.get("history", {})
        self.history = {
            "wolf_targets": history.get("wolf_targets", []),
            "vote_records": history.get("vote_records", []),
            "suspicious_players": set(history.get("suspicious_players", []))
        }
        self.witch_used = state_dict.get("witch_used", {"resurrect": False, "poison": False})
        self.effective_targets = state_dict.get("effective_targets", [])
        self.target_history = state_dict.get("target_history", {})
        self._update_win_rate()

    def _update_win_rate(self) -> None:
        """更新胜率"""
        self.win_rate = round(self.win_count / max(self.game_count, 1), 2) if self.game_count > 0 else 0.0

    def mark_win(self) -> None:
        """标记胜利"""
        self.win_count += 1
        self.game_count += 1
        self._update_win_rate()

    def mark_lose(self) -> None:
        """标记失败"""
        self.game_count += 1
        self._update_win_rate()

    def mark_dead(self) -> None:
        """标记死亡"""
        self.alive = False

    def reset_game_state(self) -> None:
        """重置本局状态"""
        self.role = None
        self.alive = True
        self.witch_used = {"resurrect": False, "poison": False}

    async def __call__(self, role_map: Dict[str, str] = None, alive_players: List[str] = None, action_type: str = "vote", *args, **kwargs) -> Msg:
        """赛事强制要求：核心交互函数"""
        if role_map is None:
            role_map = {}
        if alive_players is None:
            alive_players = ALL_PLAYERS
        if self.role is None:
            self.role = "villager"
        
        opponent_camp_alive = [p for p in self.get_opponent_camp(role_map) if p in alive_players]
        non_opponent_camp_alive = [p for p in alive_players if p not in opponent_camp_alive and p != self.name]
        
        # 狼人讨论阶段
        if action_type == "discussion" and self.role == "werewolf":
            key_good_players = self.get_key_players(role_map, alive_players, camp="good")
            if key_good_players:
                target = random.choice(key_good_players)
                role_name = role_map.get(target, "villager")
                win_rate = self._get_target_win_rate(target)
                proposal = f"我建议刀{target}！他是{role_name}，刀他胜率{win_rate}%，稳赢！"
            else:
                target = self._smart_target(role_map, alive_players)
                win_rate = self._get_target_win_rate(target)
                proposal = f"我建议刀{target}！之前投他胜率{win_rate}%，他是好人，刀他稳赢！"
            return Msg(
                name=self.name,
                content=[{"type": "text", "text": proposal}],
                role="assistant"
            )
        
        # 核心目标选择
        target = None
        if self.role == "werewolf":
            if random.random() < 0.7 or len(non_opponent_camp_alive) < 1:
                key_good_players = self.get_key_players(role_map, alive_players, camp="good")
                target = random.choice(key_good_players) if key_good_players else self._smart_target(role_map, alive_players)
            else:
                target = random.choice(non_opponent_camp_alive) if non_opponent_camp_alive else self._smart_target(role_map, alive_players)
        else:
            key_wolf_players = self.get_key_players(role_map, alive_players, camp="wolf")
            target = random.choice(key_wolf_players) if key_wolf_players else self._smart_target(role_map, alive_players)
        
        # 统一所有角色输出：必含vote字段（解决KeyError）
        win_rate = self._get_target_win_rate(target)
        if self.role == "werewolf":
            content = {
                "vote": target,
                "reach_agreement": True,
                "say": f"之前投{target}胜率{win_rate}%，他是{'好人' if target in opponent_camp_alive else '狼人'}，刀他稳赢！"
            }
        elif self.role == "witch":
            witch_resurrect = random.choices([True, False], weights=[0.7, 0.3])[0] if (not self.witch_used["resurrect"] and self.get_key_players(role_map, alive_players, camp="good")) else random.choice([True, False])
            witch_poison = random.choices([True, False], weights=[0.8, 0.2])[0] if (not self.witch_used["poison"] and self.get_key_players(role_map, alive_players, camp="wolf")) else random.choice([True, False])
            say = f"我记得{target}是{'狼人' if target in opponent_camp_alive else '好人'}，解药/毒药留着关键时候用！"
            content = {
                "vote": target,
                "resurrect": witch_resurrect,
                "poison": witch_poison,
                "say": say
            }
        elif self.role == "seer":
            identity = "狼人" if target in opponent_camp_alive else "好人"
            content = {
                "vote": target,
                "check": target,
                "identity": identity,
                "say": f"查过{target}胜率{win_rate}%，他大概率是{identity}，验他准赢！"
            }
        elif self.role == "hunter":
            content = {
                "vote": target,
                "shoot": random.choice([True, False]),
                "say": f"{target}是狼人，投他胜率高，敢投我就带走他！"
            }
        else:  # 平民
            content = {
                "vote": target,
                "say": f"之前投{target}赢过，他肯定是狼人，跟票准没错！"
            }
        
        # 返回标准Msg对象（赛事要求）
        return Msg(
            name=self.name,
            content=[{"type": "text", "text": str(content).replace("'", '"')}],
            role="assistant"
        )