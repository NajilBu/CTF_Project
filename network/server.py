import socket
import json
import random
import threading
import time
import re
from config import GRID_ROWS, GRID_COLS, COLORS, play_sound
from network.discovery import LobbyDiscoveryResponder

# Powerup definitions (placeholder — no active function yet)
POWERUPS = [
    {"id": "speed",  "label": "Speed Boost", "icon": "⚡"},
    {"id": "shield", "label": "Shield",      "icon": "🛡"},
    {"id": "reveal", "label": "Reveal",      "icon": "🔍"},
]
POWERUP_SLOTS = {"reveal": 0, "shield": 1, "speed": 2}
MAX_MAP_POWERUPS_PER_TYPE = 3
POWERUP_SPAWN_INTERVAL_SECONDS = 30
HARD_POWERUP_SPAWN_INTERVAL_SECONDS = 15
MAX_CHAT_MESSAGES = 100
MAX_CHAT_LENGTH = 240

# Word pools for Caesar cipher clues
_WORDS_EASY   = ["SECRET", "VAULT", "CIPHER", "MATRIX", "HACKER", "SHIELD", "SYSTEM", "KERNEL", "BINARY", "ROUTER", "CODING", "DECODE"]
_WORDS_HARD   = ["CRYPTOGRAPHY", "INFILTRATE", "DECRYPTION", "ALGORITHM", "CLASSIFIED", "ENCRYPTION", "OBFUSCATE", "INTERCEPT", "VULNERABLE", "PENETRATE", "FRAMEWORK", "CYBERCRIME"]

def make_caesar_clue(difficulty="easy"):
    if difficulty == "hard":
        # Random letters remove dictionary-word recognition from hard mode.
        word = "".join(random.choices(
            "ABCDEFGHIJKLMNOPQRSTUVWXYZ", k=random.randint(9, 13)
        ))
        shift = random.choice(list(range(-13, 0)) + list(range(1, 14)))
    elif difficulty == "medium":
        word  = random.choice(_WORDS_HARD)
        shift = random.choice(list(range(-13, 0)) + list(range(1, 14)))
    else:
        word  = random.choice(_WORDS_EASY)
        shift = random.choice([-5, -4, -3, -2, -1, 1, 2, 3, 4, 5])
    cipher = []
    for char in word:
        shifted = (ord(char) - ord('A') + shift) % 26
        cipher.append(chr(ord('A') + shifted))
    mode = "encrypt" if difficulty == "hard" else "decrypt"
    return f"{word}|{''.join(cipher)}|{shift}|{mode}"

def expected_caesar_answer(clue):
    parts = str(clue or "").split("|")
    if len(parts) < 3:
        return str(clue or "")
    word, cipher = parts[0], parts[1]
    mode = parts[3] if len(parts) >= 4 else "decrypt"
    return cipher if mode == "encrypt" else word

class GridServer:
    def __init__(self, port=5555, max_players=4, on_lobby_update=None, on_game_update=None):
        self.port = port
        self.max_players = max_players
        self.on_lobby_update = on_lobby_update
        self.on_game_update = on_game_update

        self.server_socket = None
        self.server_running = False
        self.game_started = False
        self.chat_history = []
        self.countdown = 0
        self.countdown_active = False

        self.clients = {}    # p_id -> socket
        self.players = {}    # p_id -> {"r", "c", "color", "ip"}
        self._color_lock = threading.Lock()

        # Per-player state
        self.player_visited   = {}  # p_id -> set of (r, c)
        self.player_items     = {}  # p_id -> set of (r, c)  (remaining items)
        self.player_collected = {}  # p_id -> {(r, c): color}
        self.player_item_keys = {}  # p_id -> {(r, c): str numeric key}
        self.host_discovered_items = set()  # host-only visibility; never sent to clients

        # Global powerup state
        self.powerups         = {}  # (r, c) -> powerup_id str  (remaining on map)
        self.player_powerups  = {}  # p_id -> [slot0, slot1, slot2]  (None or powerup_id)

        # Finish order — p_ids appended in the order they collect all items
        self.finished_players = []  # [p_id, ...]  (ordered by completion time)
        self.finish_times = {}      # p_id -> elapsed seconds from round start
        self.round_start_time = None
        self.finish_target = 1
        self.match_finished = False

        # Difficulty state
        self.difficulty            = "easy"
        self.items_per_player      = 3
        self.cell_close_timer_active = False
        self.discovery = LobbyDiscoveryResponder(self._discovery_state)

    def _discovery_state(self):
        return {
            "port": self.port,
            "players": len(self.players),
            "max_players": self.max_players,
            "game_started": self.game_started,
            "countdown": self.countdown,
        }

    # ------------------------------------------------------------------
    def _all_other_visited(self, p_id):
        """Return the union of all other players' visited cells."""
        result = set()
        for pid, v in self.player_visited.items():
            if pid != p_id:
                result |= v
        return result

    @staticmethod
    def finish_target_for(player_count):
        if player_count >= 4:
            return 3
        if player_count == 3:
            return 2
        return 1

    def spawn_player_items(self):
        """Spawn items_per_player unique items for every player, each with a Caesar cipher clue."""
        self.host_discovered_items.clear()
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
            while (self.server_running and self.game_started and not self.match_finished
                   and getattr(self, "spawner_active", False)):
                time.sleep(self.powerup_spawn_interval())
                if not (self.server_running and self.game_started and not self.match_finished
                        and getattr(self, "spawner_active", False)):
                    break
                
                self.spawn_periodic_powerups_once()
                
                if self.on_game_update:
                    self.on_game_update()
                self.broadcast_state()
                
        threading.Thread(target=spawner_loop, daemon=True).start()

    def powerup_spawn_interval(self):
        return (HARD_POWERUP_SPAWN_INTERVAL_SECONDS
                if self.difficulty == "hard"
                else POWERUP_SPAWN_INTERVAL_SECONDS)

    def spawn_periodic_powerups_once(self):
        """Spawn at most one of each type without exceeding the per-type map cap."""
        for pu in POWERUPS:
            pu_id = pu["id"]
            current_count = sum(1 for value in self.powerups.values() if value == pu_id)
            if current_count >= MAX_MAP_POWERUPS_PER_TYPE:
                continue
            for _ in range(1000):
                position = (
                    random.randint(0, GRID_ROWS - 1),
                    random.randint(0, GRID_COLS - 1),
                )
                if position not in self.powerups:
                    self.powerups[position] = pu_id
                    break

    # ------------------------------------------------------------------
    def start(self):
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self.server_socket.bind(("0.0.0.0", self.port))
            self.server_socket.listen(6)
            self.server_running = True
            threading.Thread(target=self._accept_connections, daemon=True).start()
            self.discovery.start()
            return True
        except Exception as e:
            print(f"Server bind failed: {e}")
            return False

    def _accept_connections(self):
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

            # Reuse the lowest available lobby slot after a player disconnects.
            p_id = next(
                slot for slot in range(1, self.max_players + 1)
                if slot not in self.clients
            )
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
            with self._color_lock:
                color = self.available_player_color(p_id)
                self.players[p_id] = {
                    "r": r, "c": c, "color": color, "ip": addr[0],
                    "moves": 0, "ready": False, "name": f"Player {p_id}",
                }
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

            self._append_chat(
                "system", "SYSTEM", "#8c8c9a",
                f"{self.players[p_id]['name']} joined the lobby.",
                broadcast=False,
            )

            if self.on_lobby_update:
                self.on_lobby_update()
            self.broadcast_state()

            threading.Thread(target=self._handle_client,
                             args=(p_id, conn), daemon=True).start()

    def available_player_color(self, p_id):
        """Choose a unique preset color, preferring the lobby slot's normal color."""
        used_colors = {
            str(player.get("color", "")).lower()
            for player in self.players.values()
        }
        preferred_index = (p_id - 1) % len(COLORS)
        ordered_colors = COLORS[preferred_index:] + COLORS[:preferred_index]
        return next(
            (color for color in ordered_colors if color.lower() not in used_colors),
            COLORS[preferred_index],
        )

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
                    elif msg.get("action") == "profile":
                        self.process_client_profile(p_id, msg.get("name", ""), msg.get("color", ""))
                    elif msg.get("action") == "chat":
                        self.process_client_chat(p_id, msg.get("text", ""))
            except Exception:
                break

        try:
            conn.close()
        except Exception:
            pass
        leaving_name = self.players.get(p_id, {}).get("name", f"Player {p_id}")
        self.host_discovered_items.difference_update(self.player_items.get(p_id, set()))
        for d in (self.clients, self.players,
                  self.player_visited, self.player_items, self.player_collected,
                  self.player_item_keys, self.player_powerups):
            if p_id in d:
                del d[p_id]

        self._append_chat(
            "system", "SYSTEM", "#8c8c9a",
            f"{leaving_name} left the lobby.", broadcast=False,
        )

        if self.on_lobby_update:
            self.on_lobby_update()
        if self.on_game_update and self.game_started:
            self.on_game_update()
        self.broadcast_state()

    def process_client_profile(self, p_id, name, color):
        if (p_id not in self.players
                or (self.game_started and not self.match_finished
                    and p_id not in self.finished_players)):
            self._send_to(p_id, {
                "type": "profile_result", "success": False,
                "reason": "Profiles can only be changed in the lobby.",
            })
            return

        clean_name = " ".join(str(name).split())[:16]
        clean_color = str(color).strip().lower()
        if not clean_name:
            self._send_to(p_id, {
                "type": "profile_result", "success": False,
                "reason": "Player name cannot be blank.",
            })
            return
        if not re.fullmatch(r"#[0-9a-f]{6}", clean_color):
            self._send_to(p_id, {
                "type": "profile_result", "success": False,
                "reason": "Choose a valid player color.",
            })
            return
        with self._color_lock:
            if any(
                other_id != p_id and player.get("color", "").lower() == clean_color
                for other_id, player in self.players.items()
            ):
                self._send_to(p_id, {
                    "type": "profile_result", "success": False,
                    "reason": "That color is already used by another player.",
                })
                return

            old_name = self.players[p_id].get("name", f"Player {p_id}")
            self.players[p_id]["name"] = clean_name
            self.players[p_id]["color"] = clean_color
        self._send_to(p_id, {"type": "profile_result", "success": True})
        if self.game_started:
            if self.on_game_update:
                self.on_game_update()
        elif self.on_lobby_update:
            self.on_lobby_update()
        if old_name != clean_name:
            self._append_chat(
                "system", "SYSTEM", "#8c8c9a",
                f"{old_name} is now known as {clean_name}.", broadcast=False,
            )
        self.broadcast_state()

    @staticmethod
    def clean_chat_text(text):
        clean = " ".join(str(text).split())
        return clean[:MAX_CHAT_LENGTH]

    def _append_chat(self, kind, name, color, text, broadcast=True):
        clean_text = self.clean_chat_text(text)
        if not clean_text:
            return False
        self.chat_history.append({
            "kind": kind, "name": name, "color": color, "text": clean_text,
        })
        self.chat_history = self.chat_history[-MAX_CHAT_MESSAGES:]
        if self.game_started:
            if self.on_game_update:
                self.on_game_update()
        elif self.on_lobby_update:
            self.on_lobby_update()
        if broadcast:
            self.broadcast_state()
        return True

    def process_client_chat(self, p_id, text):
        if p_id not in self.players:
            return False
        player = self.players[p_id]
        return self._append_chat(
            "player", player.get("name", f"Player {p_id}"),
            player.get("color", "#ffffff"), text,
        )

    def send_host_chat(self, text):
        return self._append_chat("host", "HOST", "#ffd24d", text)

    # ------------------------------------------------------------------
    def process_client_move(self, p_id, dr, dc):
        if p_id not in self.players or not self.game_started or self.match_finished:
            return
        # Finished players are locked in place — they cannot move
        if p_id in self.finished_players:
            return
        p = self.players[p_id]
        new_r = p["r"] + dr
        new_c = p["c"] + dc

        if not (0 <= new_r < GRID_ROWS and 0 <= new_c < GRID_COLS):
            return

        item_found = (
            (new_r, new_c) in self.player_items.get(p_id, set())
            and (new_r, new_c) not in self.player_visited[p_id]
        )
        if any((new_r, new_c) in items for items in self.player_items.values()):
            self.host_discovered_items.add((new_r, new_c))

        self.players[p_id]["r"] = new_r
        self.players[p_id]["c"] = new_c
        self.players[p_id]["moves"] = self.players[p_id].get("moves", 0) + 1
        self.player_visited[p_id].add((new_r, new_c))

        # Auto-collect powerup if player steps on one
        if (new_r, new_c) in self.powerups:
            pu_id = self.powerups[(new_r, new_c)]
            slots = self.player_powerups.setdefault(p_id, [None, None, None])
            slot_index = POWERUP_SLOTS[pu_id]
            if slots[slot_index] is None:
                self.powerups.pop((new_r, new_c))
                slots[slot_index] = pu_id
                play_sound("collect")
            else:
                play_sound("move")
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
        if p_id not in self.players or not self.game_started or self.match_finished:
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
            correct_word = expected_caesar_answer(stored_key)

            if correct_word and str(entered_key).strip().upper() == correct_word.upper():
                # Correct — collect the item
                self.player_items[p_id].discard(pos)
                self.host_discovered_items.discard(pos)
                del self.player_item_keys[p_id][pos]
                self.player_collected[p_id][pos] = self.players[p_id]["color"]
                play_sound("collect")
                # Record finish order when all required items are collected.
                if len(self.player_collected[p_id]) >= self.items_per_player and p_id not in self.finished_players:
                    self.finished_players.append(p_id)
                    if self.round_start_time:
                        self.finish_times[p_id] = time.time() - self.round_start_time
                    if len(self.finished_players) >= self.finish_target:
                        self.match_finished = True
                        self.cell_close_timer_active = False
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
        if p_id not in self.players or not self.game_started or self.match_finished:
            return
        slots = self.player_powerups.get(p_id, [None, None, None])
        if slot < 0 or slot >= 3 or slots[slot] is None:
            return

        pu_type = slots[slot]
        if POWERUP_SLOTS.get(pu_type) != slot:
            return

        if pu_type == "reveal":
            # Mark the player's nearest undiscovered item as visited (revealed)
            my_items   = self.player_items.get(p_id, set())
            my_visited = self.player_visited.get(p_id, set())
            undiscovered = [item for item in my_items if item not in my_visited]
            if undiscovered:
                # Pick the first undiscovered item
                next_item = undiscovered[0]
                self.player_visited[p_id].add(next_item)
                self.host_discovered_items.add(next_item)
                slots[slot] = None
                play_sound("qte_success")
                self.broadcast_state()
            else:
                play_sound("qte_wrong")

        elif pu_type == "shield":
            try:
                owner_id = int(target_id)
            except (ValueError, TypeError):
                owner_id = None

            affected = False
            if owner_id in self.players and owner_id != p_id:
                eligible_items = list(
                    self.player_items.get(owner_id, set())
                    & self.host_discovered_items
                )
                source_pos = random.choice(eligible_items) if eligible_items else None
                owner_visited = self.player_visited.get(owner_id, set())
                owner_pos = (self.players[owner_id]["r"], self.players[owner_id]["c"])
                occupied_items = set().union(*self.player_items.values()) if self.player_items else set()
                new_pos = None
                if source_pos is not None:
                    for _ in range(10000):
                        candidate = (
                            random.randint(0, GRID_ROWS - 1),
                            random.randint(0, GRID_COLS - 1),
                        )
                        if (candidate not in owner_visited and candidate not in occupied_items
                                and candidate != owner_pos):
                            new_pos = candidate
                            break
                if source_pos is not None and new_pos:
                    self.player_items[owner_id].discard(source_pos)
                    self.player_items[owner_id].add(new_pos)
                    self.host_discovered_items.discard(source_pos)
                    old_key = self.player_item_keys.get(owner_id, {}).pop(source_pos, None)
                    self.player_item_keys.setdefault(owner_id, {})[new_pos] = old_key
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
    def _build_state(self, recipient_id):
        per_player = {}
        for p_id in self.players:
            is_owner = p_id == recipient_id
            player_state = {
                "visited": list(self.player_visited.get(p_id, set())) if is_owner else [],
                "items":   list(self.player_items.get(p_id, set())),
                "collected": {
                    f"{r},{c}": color
                    for (r, c), color in self.player_collected.get(p_id, {}).items()
                } if is_owner else {},
                "powerups": self.player_powerups.get(p_id, [None, None, None])
            }
            player_state["item_keys"] = {
                f"{r},{c}": key
                for (r, c), key in self.player_item_keys.get(p_id, {}).items()
            } if is_owner else {}
            per_player[str(p_id)] = player_state
        return {
            "type": "state",
            "players": {str(k): v for k, v in self.players.items()},
            "game_started": self.game_started,
            "per_player": per_player,
            "map_powerups": [
                {"r": r, "c": c, "id": pu_id}
                for (r, c), pu_id in self.powerups.items()
            ],
            "move_item_targets": self.move_item_targets_for(recipient_id),
            "finished_players": list(self.finished_players),
            "finish_times": {str(k): v for k, v in self.finish_times.items()},
            "finish_target": self.finish_target,
            "match_finished": self.match_finished,
            "difficulty": self.difficulty,
            "items_per_player": self.items_per_player,
            "countdown": self.countdown,
            "chat_history": list(self.chat_history),
        }

    def move_item_targets_for(self, p_id):
        return [
            owner_id for owner_id, items in self.player_items.items()
            if owner_id != p_id and bool(items & self.host_discovered_items)
        ]

    def broadcast_state(self):
        for p_id, conn in list(self.clients.items()):
            try:
                data_str = json.dumps(self._build_state(p_id)) + "\n"
                conn.sendall(data_str.encode())
            except Exception:
                pass

    # ------------------------------------------------------------------
    def start_game(self, difficulty="easy"):
        self.countdown         = 0
        self.countdown_active  = False
        self.difficulty        = difficulty
        self.items_per_player  = 4 if difficulty == "hard" else 3
        self.game_started      = True
        self.finished_players  = []
        self.finish_times      = {}
        self.round_start_time  = time.time()
        self.finish_target     = self.finish_target_for(len(self.players))
        self.match_finished    = False
        self.cell_close_timer_active = False
        self.spawn_player_items()
        self.spawn_powerups()
        self.broadcast_state()
        if not getattr(self, "spawner_active", False):
            self.start_periodic_spawner()
        if difficulty == "hard":
            self.start_cell_close_timer()

    def begin_countdown(self, difficulty="easy", seconds=3):
        """Broadcast a synchronized lobby countdown, then start the match."""
        if self.game_started or self.countdown_active:
            return
        self.difficulty = difficulty
        self.items_per_player = 4 if difficulty == "hard" else 3
        self.countdown_active = True
        self.countdown = max(1, int(seconds))
        self.broadcast_state()

        def tick():
            while self.server_running and self.countdown_active and self.countdown > 0:
                time.sleep(1)
                self.countdown -= 1
                if self.countdown > 0:
                    self.broadcast_state()
            if self.server_running and self.countdown_active:
                self.start_game(self.difficulty)
                if self.on_game_update:
                    self.on_game_update()

        threading.Thread(target=tick, daemon=True).start()

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
        self.finish_times = {}
        self.round_start_time = time.time()
        self.finish_target = self.finish_target_for(len(self.players))
        self.match_finished = False
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
            if (not self.game_started or self.match_finished or not self.server_running
                    or not self.cell_close_timer_active):
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
        self.countdown_active = False
        self.countdown = 0
        self.spawner_active = False
        self.discovery.stop()
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
        self.host_discovered_items.clear()
        self.chat_history.clear()
