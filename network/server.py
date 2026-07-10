import socket
import json
import random
import threading
import time
from config import GRID_ROWS, GRID_COLS, COLORS, play_sound

# Powerup definitions (placeholder — no active function yet)
POWERUPS = [
    {"id": "speed",  "label": "Speed Boost", "icon": "⚡"},
    {"id": "shield", "label": "Shield",      "icon": "🛡"},
    {"id": "reveal", "label": "Reveal",      "icon": "🔍"},
]

# Word pools for Caesar cipher clues
_WORDS_EASY   = ["SECRET", "VAULT", "CIPHER", "MATRIX", "HACKER", "SHIELD", "SYSTEM", "KERNEL", "BINARY", "ROUTER", "CODING", "DECODE"]
_WORDS_HARD   = ["CRYPTOGRAPHY", "INFILTRATE", "DECRYPTION", "ALGORITHM", "CLASSIFIED", "ENCRYPTION", "OBFUSCATE", "INTERCEPT", "VULNERABLE", "PENETRATE", "FRAMEWORK", "CYBERCRIME"]

def make_caesar_clue(difficulty="easy"):
    if difficulty in ("medium", "hard"):
        word  = random.choice(_WORDS_HARD)
        shift = random.choice(list(range(-13, 0)) + list(range(1, 14)))
    else:
        word  = random.choice(_WORDS_EASY)
        shift = random.choice([-5, -4, -3, -2, -1, 1, 2, 3, 4, 5])
    cipher = []
    for char in word:
        shifted = (ord(char) - ord('A') + shift) % 26
        cipher.append(chr(ord('A') + shifted))
    return f"{word}|{''.join(cipher)}|{shift}"

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

        # Global powerup state
        self.powerups         = {}  # (r, c) -> powerup_id str  (remaining on map)
        self.player_powerups  = {}  # p_id -> [slot0, slot1, slot2]  (None or powerup_id)

        # Finish order — p_ids appended in the order they collect all items
        self.finished_players = []  # [p_id, ...]  (ordered by completion time)

        # Difficulty state
        self.difficulty            = "easy"
        self.items_per_player      = 3
        self.cell_close_timer_active = False

    # ------------------------------------------------------------------
    def _all_other_visited(self, p_id):
        """Return the union of all other players' visited cells."""
        result = set()
        for pid, v in self.player_visited.items():
            if pid != p_id:
                result |= v
        return result

    def spawn_player_items(self):
        """Spawn items_per_player unique items for every player, each with a Caesar cipher clue."""
        all_visited = set()
        for v in self.player_visited.values():
            all_visited |= v

        global_items = set()
        for p_id in self.players:
            self.player_items[p_id] = set()
            self.player_item_keys[p_id] = {}
            attempts = 0
            while len(self.player_items[p_id]) < self.items_per_player and attempts < 10000:
                attempts += 1
                r = random.randint(0, GRID_ROWS - 1)
                c = random.randint(0, GRID_COLS - 1)
                if (r, c) not in all_visited and (r, c) not in global_items:
                    self.player_items[p_id].add((r, c))
                    global_items.add((r, c))
                    key = make_caesar_clue(self.difficulty)
                    self.player_item_keys[p_id][(r, c)] = key

    def spawn_powerups(self):
        """Place 2 of each hidden powerup at random global positions (6 total)."""
        all_occupied = set()
        for v in self.player_visited.values():
            all_occupied |= v
        for items in self.player_items.values():
            all_occupied |= items

        self.powerups = {}
        for pu in POWERUPS:
            for _ in range(2):
                attempts = 0
                while attempts < 10000:
                    attempts += 1
                    r = random.randint(0, GRID_ROWS - 1)
                    c = random.randint(0, GRID_COLS - 1)
                    if (r, c) not in all_occupied and (r, c) not in self.powerups:
                        self.powerups[(r, c)] = pu["id"]
                        all_occupied.add((r, c))
                        break

    def start_periodic_spawner(self):
        self.spawner_active = True
        def spawner_loop():
            while self.server_running and self.game_started and getattr(self, "spawner_active", False):
                time.sleep(60)
                if not (self.server_running and self.game_started and getattr(self, "spawner_active", False)):
                    break
                
                # Spawn 1 of each powerup type anywhere on the grid
                for pu in POWERUPS:
                    attempts = 0
                    while attempts < 1000:
                        attempts += 1
                        r = random.randint(0, GRID_ROWS - 1)
                        c = random.randint(0, GRID_COLS - 1)
                        if (r, c) not in self.powerups:
                            self.powerups[(r, c)] = pu["id"]
                            break
                
                if self.on_game_update:
                    self.on_game_update()
                self.broadcast_state()
                
        threading.Thread(target=spawner_loop, daemon=True).start()

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
            self.player_powerups[p_id]  = [None, None, None]

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
                    elif msg.get("action") == "use_powerup":
                        self.process_client_powerup(p_id, msg.get("slot", 0), msg.get("target_id"))
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
        # Finished players are locked in place — they cannot move
        if p_id in self.finished_players:
            return
        p = self.players[p_id]
        new_r = p["r"] + dr
        new_c = p["c"] + dc

        if not (0 <= new_r < GRID_ROWS and 0 <= new_c < GRID_COLS):
            return

        # Block moves onto another player's current position (body collision)
        other_positions = {(p["r"], p["c"]) for pid, p in self.players.items() if pid != p_id}
        if (new_r, new_c) in other_positions:
            return

        # Block moves into another player's visited trail territory
        if (new_r, new_c) in self._all_other_visited(p_id):
            return

        # Detect if player finds their hidden item for the first time
        item_found = False
        if (new_r, new_c) in self.player_items.get(p_id, set()) and (new_r, new_c) not in self.player_visited[p_id]:
            item_found = True

        self.players[p_id]["r"] = new_r
        self.players[p_id]["c"] = new_c
        self.players[p_id]["moves"] = self.players[p_id].get("moves", 0) + 1
        self.player_visited[p_id].add((new_r, new_c))

        # Auto-collect powerup if player steps on one
        if (new_r, new_c) in self.powerups:
            pu_id = self.powerups.pop((new_r, new_c))
            slots = self.player_powerups.setdefault(p_id, [None, None, None])
            for i in range(3):
                if slots[i] is None:
                    slots[i] = pu_id
                    break
            play_sound("collect")
        elif item_found:
            play_sound("item_found")
        else:
            play_sound("move")

        if self.on_game_update:
            self.on_game_update()
        self.broadcast_state()

    # ------------------------------------------------------------------
    def process_client_unlock(self, p_id, r, c, entered_key):
        """Check if the entered key matches the specified item cell. Player must be standing on it."""
        if p_id not in self.players or not self.game_started:
            return
        if r is None or c is None:
            return
        pos = (int(r), int(c))

        # Player must be standing on the item to unlock it
        player_pos = (self.players[p_id]["r"], self.players[p_id]["c"])
        if player_pos != pos:
            play_sound("qte_wrong")
            self._send_to(p_id, {"type": "unlock_result", "success": False})
            return

        item_keys = self.player_item_keys.get(p_id, {})
        items = self.player_items.get(p_id, set())

        if pos in items:
            stored_key = item_keys.get(pos)
            correct_word = ""
            if stored_key and "|" in stored_key:
                correct_word = stored_key.split("|")[0]
            else:
                correct_word = str(stored_key)

            if correct_word and str(entered_key).strip().upper() == correct_word.upper():
                # Correct — collect the item
                self.player_items[p_id].discard(pos)
                del self.player_item_keys[p_id][pos]
                self.player_collected[p_id][pos] = self.players[p_id]["color"]
                play_sound("collect")
                # Record finish order when all 3 items collected
                if len(self.player_collected[p_id]) >= self.items_per_player and p_id not in self.finished_players:
                    self.finished_players.append(p_id)
                self._send_to(p_id, {"type": "unlock_result", "success": True})
                if self.on_game_update:
                    self.on_game_update()
                self.broadcast_state()
            else:
                play_sound("qte_wrong")
                self._send_to(p_id, {"type": "unlock_result", "success": False})
        else:
            play_sound("qte_wrong")
            self._send_to(p_id, {"type": "unlock_result", "success": False})

    def process_client_powerup(self, p_id, slot, target_id=None):
        if p_id not in self.players or not self.game_started:
            return
        slots = self.player_powerups.get(p_id, [None, None, None])
        if slot < 0 or slot >= 3 or slots[slot] is None:
            return

        pu_type = slots[slot]

        if pu_type == "reveal":
            # Mark the player's nearest undiscovered item as visited (revealed)
            my_items   = self.player_items.get(p_id, set())
            my_visited = self.player_visited.get(p_id, set())
            undiscovered = [item for item in my_items if item not in my_visited]
            if undiscovered:
                # Pick the first undiscovered item
                next_item = undiscovered[0]
                self.player_visited[p_id].add(next_item)
                slots[slot] = None
                play_sound("qte_success")
                self.broadcast_state()
            else:
                play_sound("qte_wrong")

        elif pu_type == "shield":
            # Move every other player's item to an undiscovered cell if they're standing on it
            affected = False
            for other_id, other_p in list(self.players.items()):
                if other_id == p_id:
                    continue
                other_pos = (other_p["r"], other_p["c"])
                if other_pos in self.player_items.get(other_id, set()):
                    # Relocate this item to a random cell not visited by other_id
                    other_visited = self.player_visited.get(other_id, set())
                    new_pos = None
                    for _ in range(10000):
                        r = random.randint(0, GRID_ROWS - 1)
                        c = random.randint(0, GRID_COLS - 1)
                        if (r, c) not in other_visited and (r, c) not in self.player_items.get(other_id, set()):
                            new_pos = (r, c)
                            break
                    if new_pos:
                        self.player_items[other_id].discard(other_pos)
                        self.player_items[other_id].add(new_pos)
                        # Reassign key to new position
                        old_key = self.player_item_keys.get(other_id, {}).pop(other_pos, None)
                        if old_key is None:
                            old_key = make_caesar_clue()
                        self.player_item_keys.setdefault(other_id, {})[new_pos] = old_key
                        affected = True

            if affected:
                slots[slot] = None
                play_sound("reset")
                self.broadcast_state()
            else:
                play_sound("qte_wrong")

        elif pu_type == "speed":
            # Teleport target player to a random undiscovered cell
            if target_id is None:
                play_sound("qte_wrong")
                return
            try:
                target_id = int(target_id)
            except (ValueError, TypeError):
                play_sound("qte_wrong")
                return
            if target_id not in self.players:
                play_sound("qte_wrong")
                return

            target_visited = self.player_visited.get(target_id, set())
            new_pos = None
            for _ in range(10000):
                r = random.randint(0, GRID_ROWS - 1)
                c = random.randint(0, GRID_COLS - 1)
                if (r, c) not in target_visited:
                    new_pos = (r, c)
                    break
            if new_pos:
                self.players[target_id]["r"] = new_pos[0]
                self.players[target_id]["c"] = new_pos[1]
                self.player_visited[target_id].add(new_pos)
                slots[slot] = None
                play_sound("reset")
                if self.on_game_update:
                    self.on_game_update()
                self.broadcast_state()
            else:
                play_sound("qte_wrong")

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
                },
                "powerups": self.player_powerups.get(p_id, [None, None, None])
            }
        state_msg = {
            "type": "state",
            "players": {str(k): v for k, v in self.players.items()},
            "game_started": self.game_started,
            "per_player": per_player,
            "map_powerups": [
                {"r": r, "c": c, "id": pu_id}
                for (r, c), pu_id in self.powerups.items()
            ],
            "finished_players": list(self.finished_players),
            "difficulty": self.difficulty,
            "items_per_player": self.items_per_player
        }
        data_str = json.dumps(state_msg) + "\n"
        for conn in list(self.clients.values()):
            try:
                conn.sendall(data_str.encode())
            except Exception:
                pass

    # ------------------------------------------------------------------
    def start_game(self, difficulty="easy"):
        self.difficulty        = difficulty
        self.items_per_player  = 4 if difficulty == "hard" else 3
        self.game_started      = True
        self.finished_players  = []
        self.cell_close_timer_active = False
        self.spawn_player_items()
        self.spawn_powerups()
        self.broadcast_state()
        if not getattr(self, "spawner_active", False):
            self.start_periodic_spawner()
        if difficulty == "hard":
            self.start_cell_close_timer()

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
            self.player_powerups[p_id]  = [None, None, None]
        self.finished_players = []
        self.cell_close_timer_active = False
        self.spawn_player_items()
        self.spawn_powerups()
        play_sound("reset")
        if self.on_game_update:
            self.on_game_update()
        self.broadcast_state()
        if not getattr(self, "spawner_active", False):
            self.start_periodic_spawner()
        if self.difficulty == "hard":
            self.start_cell_close_timer()

    def start_cell_close_timer(self):
        """Hard mode: every 30 s re-close 2-5 visited cells per player."""
        self.cell_close_timer_active = True
        def _tick():
            if not self.game_started or not self.server_running or not self.cell_close_timer_active:
                return
            self._close_random_cells()
            threading.Timer(30.0, _tick).start()
        threading.Timer(30.0, _tick).start()

    def _close_random_cells(self):
        changed = False
        for p_id, visited in list(self.player_visited.items()):
            if p_id not in self.players:
                continue
            player_pos    = (self.players[p_id]["r"], self.players[p_id]["c"])
            items_pos     = self.player_items.get(p_id, set())
            collected_pos = set(self.player_collected.get(p_id, {}).keys())
            # Eligible: visited, but not current position, not an item cell, not already collected
            eligible = list(visited - {player_pos} - items_pos - collected_pos)
            if len(eligible) < 2:
                continue
            count = random.randint(2, min(5, len(eligible)))
            for cell in random.sample(eligible, count):
                self.player_visited[p_id].discard(cell)
            changed = True
        if changed:
            play_sound("reset")
            self.broadcast_state()

    def stop(self):
        self.server_running = False
        self.spawner_active = False
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
