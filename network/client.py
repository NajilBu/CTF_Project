import socket
import json
import threading

class GridClient:
    def __init__(self, host_ip, port=5555,
                 on_init=None, on_state_update=None,
                 on_disconnect=None, on_lobby_full=None,
                 on_unlock_result=None, on_profile_result=None):
        self.host_ip = host_ip
        self.port = port
        self.on_init = on_init
        self.on_state_update = on_state_update
        self.on_disconnect = on_disconnect
        self.on_lobby_full = on_lobby_full
        self.on_unlock_result = on_unlock_result
        self.on_profile_result = on_profile_result

        self.client_socket = None
        self.client_running = False
        self.my_player_id = None
        self.game_started = False
        self.countdown = 0

        self.players = {}        # p_id -> {"r", "c", "color", "ip"}
        self.per_player_data = {}  # p_id -> {"visited": set, "items": set, "collected": dict}
        self.map_powerups = {}   # (r, c) -> powerup_id
        self.move_item_targets = set()
        self.chat_history = []
        self.finished_players = []  # p_ids in the order they finished (earliest first)
        self.finish_times = {}      # p_id -> elapsed seconds from round start
        self.finish_target = 1
        self.match_finished = False
        self.difficulty       = "easy"
        self.items_per_player = 3
        self.game_mode        = "solo"

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
                        self.countdown = msg.get("countdown", 0)

                        # Parse map-level powerup positions (hidden pickups remaining on map)
                        self.map_powerups = {
                            (entry["r"], entry["c"]): entry["id"]
                            for entry in msg.get("map_powerups", [])
                        }
                        self.move_item_targets = {
                            int(player_id) for player_id in msg.get("move_item_targets", [])
                        }
                        self.chat_history = list(msg.get("chat_history", []))

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

                        self.finished_players = msg.get("finished_players", [])
                        self.finish_times = {
                            int(k): v for k, v in msg.get("finish_times", {}).items()
                        }
                        self.finish_target     = msg.get("finish_target", 1)
                        self.match_finished    = msg.get("match_finished", False)
                        self.difficulty        = msg.get("difficulty", "easy")
                        self.items_per_player  = msg.get("items_per_player", 3)
                        self.game_mode         = msg.get("game_mode", "solo")

                        if self.on_state_update:
                            self.on_state_update()

                    elif msg.get("type") == "unlock_result":
                        success = msg.get("success", False)
                        if self.on_unlock_result:
                            self.on_unlock_result(success)
                    elif msg.get("type") == "profile_result":
                        if self.on_profile_result:
                            self.on_profile_result(
                                msg.get("success", False), msg.get("reason", "")
                            )
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

    def send_team(self, team_id):
        if not self.client_running:
            return
        team_msg = {"action": "team", "team": team_id}
        try:
            self.client_socket.sendall((json.dumps(team_msg) + "\n").encode())
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

    def send_profile(self, name, color):
        if not self.client_running:
            return
        msg = {"action": "profile", "name": str(name), "color": str(color)}
        try:
            self.client_socket.sendall((json.dumps(msg) + "\n").encode())
        except Exception:
            pass

    def send_chat(self, message):
        if not self.client_running:
            return
        try:
            payload = {"action": "chat", "text": str(message)}
            self.client_socket.sendall((json.dumps(payload) + "\n").encode())
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
        self.finish_times.clear()
        self.move_item_targets.clear()
        self.chat_history.clear()
