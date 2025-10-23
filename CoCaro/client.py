import argparse, asyncio, sys, time
from common import send_json, recv_json, parse_coord, COORDS, THINK_TIME_SECONDS

class CaroClient:
    def __init__(self, name: str, host="127.0.0.1", port=7777):
        self.name = name
        self.host = host
        self.port = port
        self.reader = None
        self.writer = None

    async def start(self):
        self.reader, self.writer = await asyncio.open_connection(self.host, self.port)
        await send_json(self.writer, {"type": "login", "name": self.name})
        hello = await recv_json(self.reader)
        if hello.get("type") != "login_ok":
            print("Login failed:", hello)
            return
        print("Logged in as", self.name, "- users:", ", ".join(hello.get("users", [])))
        asyncio.create_task(self.listen())
        await self.repl()

    async def listen(self):
        try:
            while True:
                msg = await recv_json(self.reader)
                t = msg.get("type")
                if t == "user_list":
                    print("[users]", ", ".join(msg.get("users", [])))
                elif t == "invite":
                    print(f"[invite] từ {msg['from']}. Dùng: accept {msg['from']}")
                elif t == "match_start":
                    print(f"[match] Bắt đầu! Bạn là {msg['you']}, đối thủ: {msg['opponent']}")
                elif t == "your_turn":
                    dl = msg.get("deadline")
                    remain = dl - int(time.time()) if dl else THINK_TIME_SECONDS
                    print(f"[turn] Lượt của bạn. Còn {remain}s. Gõ: move <pos>. VD: move H8")
                elif t == "move_ok":
                    print(f"Bạn đánh {COORDS[msg['x']]}{msg['y']+1}")
                elif t == "opponent_move":
                    print(f"Đối thủ đánh {COORDS[msg['x']]}{msg['y']+1}")
                elif t == "match_end":
                    print(f"[kết thúc] lý do: {msg['reason']} | winner: {msg['winner']}")
                elif t == "chat":
                    print(f"[{msg['from']}] {msg['text']}")
                elif t == "error":
                    print("[error]", msg.get("msg"))
        except Exception:
            print("[disconnected]")
            try:
                self.writer and self.writer.close()
            except:
                pass

    async def repl(self):
        print("Lệnh: users | challenge <name> | accept <name> | move <xy> | say <text> | help | quit")
        loop = asyncio.get_running_loop()
        while True:
            cmd = await loop.run_in_executor(None, sys.stdin.readline)
            if not cmd:
                break
            cmd = cmd.strip()
            if cmd == "quit":
                break
            if cmd == "help":
                print("users | challenge <name> | accept <name> | move <xy> | say <text> | quit")
                continue
            if cmd == "users":
                continue
            if cmd.startswith("challenge "):
                _, opp = cmd.split(maxsplit=1)
                await send_json(self.writer, {"type": "challenge", "opponent": opp})
                continue
            if cmd.startswith("accept "):
                _, opp = cmd.split(maxsplit=1)
                await send_json(self.writer, {"type": "accept", "opponent": opp})
                continue
            if cmd.startswith("move "):
                _, pos = cmd.split(maxsplit=1)
                xy = parse_coord(pos)
                if not xy:
                    print("Sai định dạng. Ví dụ: H8 hoặc 8,7 hoặc a1")
                else:
                    await send_json(self.writer, {"type": "move", "x": xy[0], "y": xy[1]})
                continue
            if cmd.startswith("say "):
                _, text = cmd.split(" ", 1)
                await send_json(self.writer, {"type": "chat", "text": text})
                continue
            print("Không hiểu lệnh. Gõ help.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7777)
    args = parser.parse_args()
    asyncio.run(CaroClient(args.name, args.host, args.port).start())
