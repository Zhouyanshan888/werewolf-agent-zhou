from fastapi import FastAPI
from fastapi.responses import PlainTextResponse
import io
import sys

# 初始化FastAPI应用（适配Vercel Web环境）
app = FastAPI()

# ========== 狼人杀游戏核心逻辑 ==========
class Player:
    def __init__(self, name, role):
        self.name = name
        self.role = role  # "WEREWOLF", "VILLAGER", "SEER", "WITCH", "HUNTER"
        self.alive = True
        self.win_rate = 0.0
        self.high_win_targets = []

    def vote(self, target, say=""):
        if self.role == "WEREWOLF":
            return {"vote": target, "reach_agreement": True, "say": say}
        elif self.role == "SEER":
            return {"vote": target, "check": target, "identity": "狼人" if target in [p.name for p in players if p.role == "WEREWOLF"] else "好人", "say": say}
        elif self.role == "WITCH":
            return {"vote": target, "resurrect": True, "poison": False, "say": say}
        elif self.role == "HUNTER":
            return {"vote": target, "shoot": False, "say": say}
        else:  # VILLAGER
            return {"vote": target, "say": say}

class Game:
    def __init__(self, player_names):
        self.roles = ["WEREWOLF", "WEREWOLF", "WEREWOLF", "VILLAGER", "VILLAGER", "VILLAGER", "SEER", "WITCH", "HUNTER"]
        self.players = [Player(name, role) for name, role in zip(player_names, self.roles)]
        self.alive_wolves = 3
        self.alive_good = 6
        self.game_results = []

    def night_phase(self):
        wolves = [p for p in self.players if p.role == "WEREWOLF" and p.alive]
        target = wolves[0].vote("Player5", "我建议刀Player5！他是seer，刀他胜率50%，稳赢！")["vote"]
        witch = [p for p in self.players if p.role == "WITCH" and p.alive][0]
        if witch.vote(target)["resurrect"]:
            return "No one was eliminated last night!"
        else:
            self.alive_good -= 1
            return f"Eliminated player(s) last night: {target}!"

    def day_phase(self):
        votes = {}
        for p in self.players:
            if p.alive:
                target = p.vote("Player2" if p.role == "WEREWOLF" else "Player7", f"之前投{target}赢过，他肯定是狼人，跟票准没错！")["vote"]
                votes[target] = votes.get(target, 0) + 1
        eliminated = max(votes, key=votes.get)
        if eliminated in [p.name for p in self.players if p.role == "WEREWOLF"]:
            self.alive_wolves -= 1
        else:
            self.alive_good -= 1
        return f"Public voting result: {eliminated} (votes: {votes[eliminated]}) is eliminated!"

    def run_game(self):
        output = []
        output.append("==================== 狼人杀游戏 ====================")
        output.append(f"🎭 All Roles: {[f'{p.name}: {p.role}' for p in self.players]}")
        for round_num in range(3):
            output.append(f"\n--- 第{round_num+1}轮（夜晚+白天）---")
            output.append(f"📢 Moderator: {self.night_phase()}")
            output.append(f"📢 Moderator: {self.day_phase()}")
            output.append(f"📊 Current status: Alive wolves: {self.alive_wolves} | Alive good players: {self.alive_good}")
        if self.alive_wolves == 0:
            output.append("\n🎉 ===== GAME OVER =====\n🏆 Good players win!")
        else:
            output.append("\n🎉 ===== GAME OVER =====\n🏆 Werewolves win!")
        return "\n".join(output)

# ========== Web服务配置（适配Vercel） ==========
class CaptureOutput:
    def __enter__(self):
        self.old_stdout = sys.stdout
        sys.stdout = self.buffer = io.StringIO()
        return self
    def __exit__(self, *args):
        sys.stdout = self.old_stdout

@app.get("/", response_class=PlainTextResponse)
def root():
    player_names = [f"Player{i}" for i in range(1, 10)]
    game = Game(player_names)
    with CaptureOutput() as capture:
        game_result = game.run_game()
    return game_result

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
