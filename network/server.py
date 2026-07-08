import socket
import json
import random
import threading
from config import GRID_ROWS, GRID_COLS, COLORS, play_sound

class GridServer:
    def __init__(self, port=5555, max_players=4, on_lobby_update=None, on_game_update=None):
        self.port = port
        self.max_players = max_players
        self.on_lobby_update = on_lobby_update
        self.on_game_update = on_game_update

        self.server_socket = None
        self.server_running = False
        self.game_started = False

        self.clients = {}    # p_id -> socket
        self.players = {}    # p_id -> {"r", "c", "color", "ip"}

        # Per-player state
        self.player_visited   = {}  # p_id -> set of (r, c)
        self.player_items     = {}  # p_id -> set of (r, c)  (remaining items)
        self.player_collected = {}  # p_id -> {(r, c): color}
        self.player_item_keys = {}  # p_id -> {(r, c): str numeric key}

    # ------------------------------------------------------------------
    def _all_other_visited(self, p_id):
        """Return the union of all other players' visited cells."""
        result = set()
        for pid, v in self.player_visited.items():
            if pid != p_id:
                result |= v
        return result

    def spawn_player_items(self):
        """Spawn 3 unique, globally-distinct items for every player, each with a random 4-digit key."""
        all_visited = set()
        for v in self.player_visited.values():
            all_visited |= v

        global_items = set()
        for p_id in self.players:
            self.player_items[p_id] = set()
            self.player_item_keys[p_id] = {}
            attempts = 0
            while len(self.player_items[p_id]) < 3 and attempts < 10000:
                attempts += 1
                r = random.randint(0, GRID_ROWS - 1)
                c = random.randint(0, GRID_COLS - 1)
                if (r, c) not in all_visited and (r, c) not in global_items:
                    self.player_items[p_id].add((r, c))
                    global_items.add((r, c))
                    # Assign a unique 4-digit key to this item
                    key = str(random.randint(1000, 9999))
                    self.player_item_keys[p_id][(r, c)] = key

    # ------------------------------------------------------------------
    def start(self):
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self.server_socket.bind(("0.0.0.0", self.port))
            self.server_socket.listen(6)
            self.server_running = True
            threading.Thread(target=self._accept_connections, daemon=True).start()
            return True
        except Exception as e:
            print(f"Server bind failed: {e}")
            return False

    def _accept_connections(self):
        player_counter = 0
        while self.server_running:
            try:
                conn, addr = self.server_socket.accept()
            except Exception:
                break

            if len(self.clients) >= self.max_players:
                try:
                    conn.sendall(b"LOBBY_FULL\n")
                    conn.close()
                except Exception:
                    pass
                continue

            player_counter += 1
            p_id = player_counter
            color = COLORS[(p_id - 1) % len(COLORS)]

            # Ensure unique spawn position for players
            occupied = {(p["r"], p["c"]) for p in self.players.values()}
            r = random.randint(0, GRID_ROWS - 1)
            c = random.randint(0, GRID_COLS - 1)
            attempts = 0
            while (r, c) in occupied and attempts < 1000:
                r = random.randint(0, GRID_ROWS - 1)
                c = random.randint(0, GRID_COLS - 1)
                attempts += 1

            self.clients[p_id] = conn
            self.players[p_id] = {"r": r, "c": c, "color": color, "ip": addr[0], "moves": 0, "ready": False}
            self.player_visited[p_id]   = {(r, c)}
            self.player_items[p_id]     = set()
            self.player_collected[p_id] = {}

            init_msg = {"type": "init", "id": p_id,
                        "grid_rows": GRID_ROWS, "grid_cols": GRID_COLS,
                        "max_players": self.max_players}
            try:
                conn.sendall((json.dumps(init_msg) + "\n").encode())
            except Exception:
                pass

            if self.on_lobby_update:
                self.on_lobby_update()
            self.broadcast_state()

            threading.Thread(target=self._handle_client,
                             args=(p_id, conn), daemon=True).start()

    def _handle_client(self, p_id, conn):
        buffer = ""
        while self.server_running:
            try:
                data = conn.recv(1024).decode()
                if not data:
                    break
                buffer += data
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    if not line:
                        continue
                    msg = json.loads(line)
                    if msg.get("action") == "move":
                        self.process_client_move(p_id, msg.get("dr", 0), msg.get("dc", 0))
                    elif msg.get("action") == "unlock":
                        r = msg.get("r")
                        c = msg.get("c")
                        self.process_client_unlock(p_id, r, c, msg.get("key", ""))
                    elif msg.get("action") == "ready":
                        if p_id in self.players:
                            self.players[p_id]["ready"] = bool(msg.get("ready", False))
                            if self.on_lobby_update:
                                self.on_lobby_update()
                            self.broadcast_state()
            except Exception:
                break

        try:
            conn.close()
        except Exception:
            pass
        for d in (self.clients, self.players,
                  self.player_visited, self.player_items, self.player_collected, self.player_item_keys):
            if p_id in d:
                del d[p_id]

        if self.on_lobby_update:
            self.on_lobby_update()
        if self.on_game_update and self.game_started:
            self.on_game_update()
        self.broadcast_state()

    # ------------------------------------------------------------------
    def process_client_move(self, p_id, dr, dc):
        if p_id not in self.players or not self.game_started:
            return
        p = self.players[p_id]
        new_r = p["r"] + dr
        new_c = p["c"] + dc

        if not (0 <= new_r < GRID_ROWS and 0 <= new_c < GRID_COLS):
            return

        # Block moves into another player's territory
        if (new_r, new_c) in self._all_other_visited(p_id):
            return

        self.players[p_id]["r"] = new_r
        self.players[p_id]["c"] = new_c
        self.players[p_id]["moves"] = self.players[p_id].get("moves", 0) + 1
        self.player_visited[p_id].add((new_r, new_c))

        # Automatic item collection is disabled — player must use the lock/key system
        play_sound("move")

        if self.on_game_update:
            self.on_game_update()
        self.broadcast_state()

    # ------------------------------------------------------------------
    def process_client_unlock(self, p_id, r, c, entered_key):
        """Check if the entered key matches the specified item cell (no position requirement)."""
        if p_id not in self.players or not self.game_started:
            return
        if r is None or c is None:
            return
        pos = (int(r), int(c))
        item_keys = self.player_item_keys.get(p_id, {})
        items = self.player_items.get(p_id, set())

        if pos in items and item_keys.get(pos) == str(entered_key):
            # Correct key — collect the item
            self.player_items[p_id].discard(pos)
            del self.player_item_keys[p_id][pos]
            self.player_collected[p_id][pos] = self.players[p_id]["color"]
            play_sound("collect")
            self._send_to(p_id, {"type": "unlock_result", "success": True})
            if self.on_game_update:
                self.on_game_update()
            self.broadcast_state()
        else:
            play_sound("qte_wrong")
            self._send_to(p_id, {"type": "unlock_result", "success": False})

    def _send_to(self, p_id, msg):
        conn = self.clients.get(p_id)
        if conn:
            try:
                conn.sendall((json.dumps(msg) + "\n").encode())
            except Exception:
                pass

    # ------------------------------------------------------------------
    def broadcast_state(self):
        per_player = {}
        for p_id in self.players:
            per_player[str(p_id)] = {
                "visited": list(self.player_visited.get(p_id, set())),
                "items":   list(self.player_items.get(p_id, set())),
                "collected": {
                    f"{r},{c}": color
                    for (r, c), color in self.player_collected.get(p_id, {}).items()
                },
                "item_keys": {
                    f"{r},{c}": key
                    for (r, c), key in self.player_item_keys.get(p_id, {}).items()
                }
            }
        state_msg = {
            "type": "state",
            "players": {str(k): v for k, v in self.players.items()},
            "game_started": self.game_started,
            "per_player": per_player
        }
        data_str = json.dumps(state_msg) + "\n"
        for conn in list(self.clients.values()):
            try:
                conn.sendall(data_str.encode())
            except Exception:
                pass

    # ------------------------------------------------------------------
    def start_game(self):
        self.game_started = True
        self.spawn_player_items()
        self.broadcast_state()

    def reset_game(self):
        for p_id in list(self.players.keys()):
            r = random.randint(0, GRID_ROWS - 1)
            c = random.randint(0, GRID_COLS - 1)
            self.players[p_id]["r"] = r
            self.players[p_id]["c"] = c
            self.players[p_id]["moves"] = 0
            self.players[p_id]["ready"] = False
            self.player_visited[p_id]   = {(r, c)}
            self.player_collected[p_id] = {}
            self.player_item_keys[p_id] = {}
        self.spawn_player_items()
        play_sound("reset")
        if self.on_game_update:
            self.on_game_update()
        self.broadcast_state()

    def stop(self):
        self.server_running = False
        if self.server_socket:
            try:
                self.server_socket.close()
            except Exception:
                pass
            self.server_socket = None
        for conn in list(self.clients.values()):
            try:
                conn.close()
            except Exception:
                pass
        self.clients.clear()
        self.players.clear()
        self.player_visited.clear()
        self.player_items.clear()
        self.player_collected.clear()
