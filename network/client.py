import socket
import json
import threading

class GridClient:
    def __init__(self, host_ip, port=5555,
                 on_init=None, on_state_update=None,
                 on_disconnect=None, on_lobby_full=None,
                 on_unlock_result=None):
        self.host_ip = host_ip
        self.port = port
        self.on_init = on_init
        self.on_state_update = on_state_update
        self.on_disconnect = on_disconnect
        self.on_lobby_full = on_lobby_full
        self.on_unlock_result = on_unlock_result

        self.client_socket = None
        self.client_running = False
        self.my_player_id = None
        self.game_started = False

        self.players = {}        # p_id -> {"r", "c", "color", "ip"}
        self.per_player_data = {}  # p_id -> {"visited": set, "items": set, "collected": dict}
        self.map_powerups = {}   # (r, c) -> powerup_id
        self.finished_players = []  # p_ids in the order they finished (earliest first)
        self.difficulty       = "easy"
        self.items_per_player = 3

    # ------------------------------------------------------------------
    def get_my_visited(self):
        return self.per_player_data.get(self.my_player_id, {}).get("visited", set())

    def get_my_items(self):
        return self.per_player_data.get(self.my_player_id, {}).get("items", set())

    def get_my_collected(self):
        return self.per_player_data.get(self.my_player_id, {}).get("collected", {})

    def get_all_other_visited(self):
        result = set()
        for pid, data in self.per_player_data.items():
            if pid != self.my_player_id:
                result |= data.get("visited", set())
        return result

    # ------------------------------------------------------------------
    def connect(self):
        self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            self.client_socket.connect((self.host_ip, self.port))
            self.client_running = True
            threading.Thread(target=self._receive_messages, daemon=True).start()
            return True
        except Exception as e:
            print(f"Client connection failed: {e}")
            return False

    def _receive_messages(self):
        buffer = ""
        while self.client_running:
            try:
                data = self.client_socket.recv(4096).decode()
                if not data:
                    break
                buffer += data
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    if not line:
                        continue

                    if line == "LOBBY_FULL":
                        if self.on_lobby_full:
                            self.on_lobby_full()
                        self.client_running = False
                        break

                    msg = json.loads(line)
                    if msg.get("type") == "init":
                        self.my_player_id = msg["id"]
                        self.max_players = msg.get("max_players", 6)
                        if self.on_init:
                            self.on_init(self.my_player_id)

                    elif msg.get("type") == "state":
                        players_raw = msg["players"]
                        self.players = {int(k): v for k, v in players_raw.items()}
                        self.game_started = msg.get("game_started", False)

                        # Parse map-level powerup positions (hidden pickups remaining on map)
                        self.map_powerups = {
                            (entry["r"], entry["c"]): entry["id"]
                            for entry in msg.get("map_powerups", [])
                        }

                        # Parse per-player data
                        per_player_raw = msg.get("per_player", {})
                        self.per_player_data = {}
                        for pid_str, data in per_player_raw.items():
                            pid = int(pid_str)
                            self.per_player_data[pid] = {
                                "visited": {
                                    tuple(cell) for cell in data.get("visited", [])
                                },
                                "items": {
                                    tuple(item) for item in data.get("items", [])
                                },
                                "collected": {
                                    tuple(int(x) for x in k.split(",")): v
                                    for k, v in data.get("collected", {}).items()
                                },
                                "item_keys": {
                                    tuple(int(x) for x in k.split(",")): v
                                    for k, v in data.get("item_keys", {}).items()
                                },
                                "powerups": data.get("powerups", [None, None, None])
                            }

                        if self.on_state_update:
                            self.on_state_update()

                        self.finished_players = msg.get("finished_players", [])
                        self.difficulty        = msg.get("difficulty", "easy")
                        self.items_per_player  = msg.get("items_per_player", 3)

                    elif msg.get("type") == "unlock_result":
                        success = msg.get("success", False)
                        if self.on_unlock_result:
                            self.on_unlock_result(success)
            except Exception:
                break

        if self.client_running:
            self.client_running = False
            if self.on_disconnect:
                self.on_disconnect()

    def send_move(self, dr, dc):
        if not self.client_running:
            return
        move_msg = {"action": "move", "dr": dr, "dc": dc}
        try:
            self.client_socket.sendall((json.dumps(move_msg) + "\n").encode())
        except Exception:
            pass

    def send_unlock(self, r, c, key):
        if not self.client_running:
            return
        unlock_msg = {"action": "unlock", "r": r, "c": c, "key": str(key)}
        try:
            self.client_socket.sendall((json.dumps(unlock_msg) + "\n").encode())
        except Exception:
            pass

    def send_ready(self, ready):
        if not self.client_running:
            return
        ready_msg = {"action": "ready", "ready": bool(ready)}
        try:
            self.client_socket.sendall((json.dumps(ready_msg) + "\n").encode())
        except Exception:
            pass

    def send_powerup_use(self, slot, target_player_id=None):
        if not self.client_running:
            return
        msg = {"action": "use_powerup", "slot": slot}
        if target_player_id is not None:
            msg["target_id"] = target_player_id
        try:
            self.client_socket.sendall((json.dumps(msg) + "\n").encode())
        except Exception:
            pass

    def stop(self):
        self.client_running = False
        if self.client_socket:
            try:
                self.client_socket.close()
            except Exception:
                pass
            self.client_socket = None
        self.players.clear()
        self.per_player_data.clear()
