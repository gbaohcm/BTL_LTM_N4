# gui_client_pretty.py — GUI đẹp hơn cho Caro (Tkinter thuần)
# Chạy: python gui_client_pretty.py --name an --host 127.0.0.1 --port 7777
# Đặt file cạnh common.py, server.py. Không cần cài thư viện ngoài.

import argparse
import asyncio
import threading
import time
import queue
from dataclasses import dataclass, field
from typing import List, Optional, Tuple
import tkinter as tk
from tkinter import messagebox, ttk

from common import send_json, recv_json, BOARD_SIZE, COORDS, THINK_TIME_SECONDS

# -------------------- Theme --------------------
BG = "#0f172a"          # slate-900
PANEL = "#111827"       # gray-900
BORDER = "#1f2937"      # gray-800
GRID = "#475569"        # slate-600
ACCENT = "#22d3ee"      # cyan-400
ACCENT2 = "#f472b6"     # pink-400
TEXT = "#e5e7eb"        # gray-200
SUB = "#9ca3af"         # gray-400
X_COLOR = "#60a5fa"     # blue-400
O_COLOR = "#f87171"     # red-400
LAST_MOVE = "#fde68a"   # amber-200
WINLINE = "#22c55e"     # green-500

CELL = 36
PAD = 28
BOARD_PIX = CELL*BOARD_SIZE

@dataclass
class GameState:
    you: Optional[str] = None
    opponent: Optional[str] = None
    board: List[List[str]] = field(default_factory=lambda: [["." for _ in range(BOARD_SIZE)] for _ in range(BOARD_SIZE)])
    your_turn: bool = False
    deadline: Optional[float] = None
    last_move: Optional[Tuple[int,int]] = None
    win_line: Optional[List[Tuple[int,int]]] = None

class PrettyClient:
    def __init__(self, name: str, host: str, port: int):
        self.name, self.host, self.port = name, host, port
        self.reader = None; self.writer = None; self.loop = None
        self.in_q: "queue.Queue[dict]" = queue.Queue()
        self.game = GameState()
        self.users: list[str] = []
        self.hover_xy: Optional[Tuple[int,int]] = None

        # ------------- GUI -------------
        self.root = tk.Tk()
        self.root.title(f"Caro — {self.name}")
        self.root.configure(bg=BG)
        self.root.minsize(980, 640)

        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("TFrame", background=BG)
        style.configure("Card.TFrame", background=PANEL, relief="flat")
        style.configure("TLabel", background=BG, foreground=TEXT)
        style.configure("Sub.TLabel", foreground=SUB)
        style.configure("Accent.TButton", padding=8)

        left = ttk.Frame(self.root)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=14, pady=14)
        right = ttk.Frame(self.root)
        right.pack(side=tk.RIGHT, fill=tk.Y, padx=14, pady=14)

        # Board card
        board_card = ttk.Frame(left, style="Card.TFrame", padding=12)
        board_card.pack(fill=tk.BOTH, expand=True)
        self.canvas = tk.Canvas(board_card, width=BOARD_PIX+2*PAD, height=BOARD_PIX+2*PAD,
                                bg=PANEL, highlightthickness=0)
        self.canvas.pack()
        self.canvas.bind("<Button-1>", self.on_click)
        self.canvas.bind("<Motion>", self.on_hover)
        self.canvas.bind("<Leave>", lambda e: self.clear_hover())

        status_bar = ttk.Frame(left, style="Card.TFrame", padding=10)
        status_bar.pack(fill=tk.X, pady=(10,0))
        self.lbl_status = ttk.Label(status_bar, text="Chưa trong trận")
        self.lbl_status.pack(side=tk.LEFT)
        self.lbl_timer = ttk.Label(status_bar, text="", style="Sub.TLabel")
        self.lbl_timer.pack(side=tk.RIGHT)

        # Right panel
        users_card = ttk.Frame(right, style="Card.TFrame", padding=12)
        users_card.pack(fill=tk.BOTH)
        ttk.Label(users_card, text="Người chơi online", font=("Segoe UI", 11, "bold")).pack(anchor=tk.W)
        self.list_users = tk.Listbox(users_card, height=14, bg=PANEL, fg=TEXT, selectbackground=ACCENT,
                                     highlightthickness=1, highlightbackground=BORDER, relief="flat")
        self.list_users.pack(fill=tk.BOTH, pady=(6,8))
        btnrow = ttk.Frame(users_card, style="Card.TFrame")
        btnrow.pack(fill=tk.X)
        ttk.Button(btnrow, text="Thách đấu", command=self.challenge).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0,6))
        ttk.Button(btnrow, text="Chấp nhận…", command=self.accept_dialog).pack(side=tk.LEFT, expand=True, fill=tk.X)

        chat_card = ttk.Frame(right, style="Card.TFrame", padding=12)
        chat_card.pack(fill=tk.BOTH, expand=True, pady=(12,0))
        ttk.Label(chat_card, text="Chat", font=("Segoe UI", 11, "bold")).pack(anchor=tk.W)
        self.chat_log = tk.Text(chat_card, height=10, bg=PANEL, fg=TEXT, insertbackground=TEXT,
                                highlightthickness=1, highlightbackground=BORDER, relief="flat")
        self.chat_log.pack(fill=tk.BOTH, expand=True, pady=(6,8))
        chat_row = ttk.Frame(chat_card, style="Card.TFrame")
        chat_row.pack(fill=tk.X)
        self.chat_entry = ttk.Entry(chat_row)
        self.chat_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(chat_row, text="Gửi", command=self.send_chat).pack(side=tk.LEFT, padx=(6,0))

        self.draw_board()

        self.root.after(60, self.poll_q)
        self.root.after(200, self.update_timer)

        # mạng chạy ở thread riêng
        self.start_network()

    # -------------------- Network --------------------
    def start_network(self):
        def runner():
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            self.loop.run_until_complete(self.net_main())
        threading.Thread(target=runner, daemon=True).start()

    async def net_main(self):
        self.reader, self.writer = await asyncio.open_connection(self.host, self.port)
        await send_json(self.writer, {"type":"login","name":self.name})
        self.in_q_put(await recv_json(self.reader))
        try:
            while True:
                self.in_q_put(await recv_json(self.reader))
        except Exception as e:
            self.in_q_put({"type":"_error","msg":str(e)})

    def in_q_put(self, msg: dict):
        self.in_q.put(msg)

    async def send(self, obj: dict):
        if self.writer:
            await send_json(self.writer, obj)

    def send_now(self, obj: dict):
        if self.loop:
            asyncio.run_coroutine_threadsafe(self.send(obj), self.loop)

    # -------------------- Board rendering --------------------
    def draw_board(self):
        c = self.canvas
        c.delete("all")
        # khung bo tròn
        c.create_rectangle(PAD-8, PAD-8, PAD+BOARD_PIX+8, PAD+BOARD_PIX+8, outline=ACCENT, width=1)
        # nền
        c.create_rectangle(PAD, PAD, PAD+BOARD_PIX, PAD+BOARD_PIX, fill=BG, outline=BORDER, width=2)
        # lưới
        for i in range(BOARD_SIZE):
            y = PAD + CELL/2 + i*CELL
            c.create_line(PAD+CELL/2, y, PAD+BOARD_PIX-CELL/2, y, fill=GRID)
            x = PAD + CELL/2 + i*CELL
            c.create_line(x, PAD+CELL/2, x, PAD+BOARD_PIX-CELL/2, fill=GRID)
        # đầu mục
        for i, ch in enumerate(COORDS):
            x = PAD + CELL/2 + i*CELL
            c.create_text(x, PAD-10, text=ch, fill=SUB)
            c.create_text(PAD-14, PAD+CELL/2+i*CELL, text=str(i+1), fill=SUB)
        # win line
        if self.game.win_line:
            for (x,y) in self.game.win_line:
                cx = PAD + CELL/2 + x*CELL
                cy = PAD + CELL/2 + y*CELL
                c.create_rectangle(cx-CELL*0.5, cy-CELL*0.5, cx+CELL*0.5, cy+CELL*0.5,
                                   outline=WINLINE, width=2)
        # quân cờ
        for y in range(BOARD_SIZE):
            for x in range(BOARD_SIZE):
                v = self.game.board[y][x]
                if v != ".":
                    self.draw_piece(x, y, v)
        # last move marker
        if self.game.last_move:
            x,y = self.game.last_move
            cx = PAD + CELL/2 + x*CELL
            cy = PAD + CELL/2 + y*CELL
            r = CELL*0.15
            c.create_oval(cx-r, cy-r, cx+r, cy+r, fill=LAST_MOVE, outline="")
        # hover ghost
        if self.hover_xy and self.game.your_turn:
            x,y = self.hover_xy
            if self.game.board[y][x] == ".":
                self.draw_piece(x,y,self.game.you, ghost=True)

    def draw_piece(self, x:int, y:int, symbol:str, ghost=False):
        cx = PAD + CELL/2 + x*CELL
        cy = PAD + CELL/2 + y*CELL
        r = CELL*0.42
        fill = ""; outline = X_COLOR if symbol=="X" else O_COLOR
        width = 3
        if ghost:
            outline = outline + "80"  # alpha mờ trên Tk alpha hex không chuẩn, dùng trick màu nhạt tương đối
        self.canvas.create_oval(cx-r, cy-r, cx+r, cy+r, outline=outline, width=width)
        self.canvas.create_text(cx, cy, text=symbol, fill=outline, font=("Segoe UI", int(CELL*0.55), "bold"))

    def board_xy(self, xpix, ypix):
        x = int((xpix - PAD) // CELL)
        y = int((ypix - PAD) // CELL)
        if 0 <= x < BOARD_SIZE and 0 <= y < BOARD_SIZE:
            return x, y
        return None

    def on_click(self, ev):
        pos = self.board_xy(ev.x, ev.y)
        if not pos or not self.game.your_turn:
            return
        x,y = pos
        if self.game.board[y][x] == ".":
            self.send_now({"type":"move","x":x,"y":y})

    def on_hover(self, ev):
        pos = self.board_xy(ev.x, ev.y)
        if pos != self.hover_xy:
            self.hover_xy = pos
            self.draw_board()

    def clear_hover(self):
        self.hover_xy = None
        self.draw_board()

    # -------------------- UI helpers --------------------
    def append_chat(self, line: str):
        self.chat_log.insert(tk.END, line + "\n")
        self.chat_log.see(tk.END)

    def challenge(self):
        sel = self.list_users.curselection()
        if not sel: return
        opp = self.list_users.get(sel[0])
        if opp == self.name: return
        self.send_now({"type":"challenge","opponent":opp})
        messagebox.showinfo("Đã gửi", f"Đã gửi lời mời tới {opp}")

    def accept_dialog(self):
        w = tk.Toplevel(self.root); w.configure(bg=BG)
        ttk.Label(w, text="Nhập tên người đã mời bạn:").pack(padx=10, pady=(10,6))
        ent = ttk.Entry(w); ent.pack(padx=10, pady=(0,8))
        ttk.Button(w, text="Chấp nhận", command=lambda:(self.send_now({"type":"accept","opponent":ent.get().strip()}), w.destroy())).pack(pady=(0,10))
        ent.focus_set()

    # -------------------- Network message pump --------------------
    def poll_q(self):
        try:
            while True:
                self.handle_msg(self.in_q.get_nowait())
        except queue.Empty:
            pass
        self.root.after(60, self.poll_q)

    def handle_msg(self, msg: dict):
        t = msg.get("type")
        if t == "login_ok":
            self.append_chat("[system] Đăng nhập thành công.")
        elif t == "user_list":
            self.list_users.delete(0, tk.END)
            self.users = list(msg.get("users", []))
            for u in self.users:
                self.list_users.insert(tk.END, u)
        elif t == "invite":
            frm = msg.get("from")
            if messagebox.askyesno("Lời mời", f"{frm} thách đấu. Chấp nhận?"):
                self.send_now({"type":"accept","opponent":frm})
        elif t == "match_start":
            self.game = GameState()
            self.game.you = msg.get("you")
            self.game.opponent = msg.get("opponent")
            self.lbl_status.config(text=f"Trận với {self.game.opponent} | Bạn: {self.game.you}")
            self.draw_board()
        elif t == "your_turn":
            self.game.your_turn = True
            self.game.deadline = msg.get("deadline")
            self.draw_board()
        elif t == "move_ok":
            x,y = msg["x"], msg["y"]
            self.game.board[y][x] = msg.get("symbol","?")
            self.game.last_move = (x,y)
            self.game.your_turn = False
            self.draw_board()
        elif t == "opponent_move":
            x,y = msg["x"], msg["y"]
            self.game.board[y][x] = msg.get("symbol","?")
            self.game.last_move = (x,y)
            self.draw_board()
        elif t == "match_end":
            self.game.your_turn = False
            self.game.deadline = None
            self.draw_board()
            reason = msg.get("reason"); winner = msg.get("winner")
            messagebox.showinfo("Kết thúc", f"Lý do: {reason}\nKết quả: {winner}")
            self.lbl_status.config(text="Chưa trong trận")
        elif t == "chat":
            self.append_chat(f"[{msg.get('from')}] {msg.get('text')}")
        elif t == "error":
            messagebox.showerror("Lỗi", msg.get("msg"))
        elif t == "_error":
            self.append_chat("[system] Mất kết nối máy chủ.")

    def update_timer(self):
        if self.game.your_turn and self.game.deadline:
            remain = int(self.game.deadline - time.time())
            if remain < 0: remain = 0
            self.lbl_timer.config(text=f"Thời gian: {remain}s")
        else:
            self.lbl_timer.config(text="")
        self.root.after(200, self.update_timer)

    def run(self):
        self.root.mainloop()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7777)
    args = parser.parse_args()
    PrettyClient(args.name, args.host, args.port).run()
