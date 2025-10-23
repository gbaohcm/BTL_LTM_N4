from __future__ import annotations
import asyncio, json
from typing import Any, Dict, Tuple, List

BOARD_SIZE = 15
THINK_TIME_SECONDS = 15
COORDS = "ABCDEFGHIJKLMNO"  # 15 cột
DIRS = [(1, 0), (0, 1), (1, 1), (1, -1)]

async def send_json(writer: asyncio.StreamWriter, obj: Dict[str, Any]):
    data = json.dumps(obj, ensure_ascii=False) + "\n"
    writer.write(data.encode("utf-8"))
    await writer.drain()

async def recv_json(reader: asyncio.StreamReader) -> Dict[str, Any]:
    line = await reader.readline()
    if not line:
        raise ConnectionError("peer closed")
    return json.loads(line.decode("utf-8").strip())

def parse_coord(token: str) -> Tuple[int, int] | None:
    token = token.strip().lower()
    if "," in token:
        try:
            x, y = token.split(",")
            return int(x), int(y)
        except:
            return None
    if " " in token:
        try:
            x, y = token.split()
            return int(x), int(y)
        except:
            return None
    if token and token[0].isalpha():
        col = token[0].upper()
        if col in COORDS:
            try:
                row = int(token[1:])
                return COORDS.index(col), row - 1
            except:
                return None
    return None

def check_win(board: List[List[str]], x: int, y: int, symbol: str) -> bool:
    n = len(board)
    for dx, dy in DIRS:
        cnt = 1
        for s in (1, -1):
            nx, ny = x, y
            while True:
                nx += dx * s
                ny += dy * s
                if 0 <= nx < n and 0 <= ny < n and board[ny][nx] == symbol:
                    cnt += 1
                else:
                    break
        if cnt >= 5:
            return True
    return False
