import tkinter as tk
from tkinter import font, messagebox
import random
import time
from config import (
    WINDOW_WIDTH, WINDOW_HEIGHT, GRID_ROWS, GRID_COLS, CELL_SIZE,
    CANVAS_WIDTH, CANVAS_HEIGHT, COLORS, COLOR_NAMES, play_sound
)
from network import GridServer, GridClient
from gui.dialogs import CustomIPDialog, CustomPlayerCountDialog, CustomLockDialog, LockScreenDialog, TeleportDialog, CustomDifficultyDialog

# Powerup display metadata (mirrors POWERUPS list in server.py)
_WORDS_EASY = ["SECRET", "VAULT", "CIPHER", "MATRIX", "HACKER", "SHIELD", "SYSTEM", "KERNEL", "BINARY", "ROUTER", "CODING", "DECODE"]
_WORDS_HARD = ["CRYPTOGRAPHY", "INFILTRATE", "DECRYPTION", "ALGORITHM", "CLASSIFIED", "ENCRYPTION", "OBFUSCATE", "INTERCEPT", "VULNERABLE", "PENETRATE", "FRAMEWORK", "CYBERCRIME"]

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

POWERUP_META = {
    "speed":  {"label": "Teleport",    "icon": "\u26a1", "color": "#ffd24d"},
    "shield": {"label": "Move Item",   "icon": "\U0001f6e1", "color": "#00d2ff"},
    "reveal": {"label": "Reveal",      "icon": "\U0001f50d", "color": "#ff9f1a"},
}

def blend_color(foreground, background="#121214", amount=0.18):
    """Blend two #RRGGBB colors into a Tk-compatible solid color."""
    fg = tuple(int(foreground[i:i + 2], 16) for i in (1, 3, 5))
    bg = tuple(int(background[i:i + 2], 16) for i in (1, 3, 5))
    mixed = tuple(round(b + (f - b) * amount) for f, b in zip(fg, bg))
    return "#" + "".join(f"{value:02x}" for value in mixed)

class GridGameApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Grid Explorer - Multiplayer")
        self.root.configure(bg="#121214")
        self.root.resizable(True, True)
        self.root.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}+0+0")
        try:
            self.root.state("zoomed")   # Maximized on Windows
        except Exception:
            self.root.attributes("-fullscreen", True)


        # Local Game States
        self.player_r = 0
        self.player_c = 0
        self.moves = 0
        self.in_game = False

        # QTE & Cooldown States
        self.last_move_time = 0.0
        self.last_qte_key_time = 0.0
        self.qte_active = False
        self.qte_sequence = []
        self.qte_progress = 0
        self.qte_target_move = (0, 0)
        self.last_known_server_pos = None
        self.per_player_data = {}  # p_id -> {visited, items, collected}
        self.client_cell_arrows = {}  # frozen directions for client-discovered cells
        self.showing_finish_screen = False
        self.finish_screen_match_complete = False

        # Network Game States
        self.is_host = False
        self.is_client = False
        self.my_player_id = None
        self.game_started = False
        self.in_active_game = False
        
        self.server = None
        self.client = None
        self.players = {}
        self.visited_cells = set()   # solo-only
        self.hidden_items = set()     # solo-only
        self.collected_item_cells = {}  # solo-only

        # Difficulty
        self.difficulty       = "easy"
        self.items_per_player = 3
        self.solo_cell_close_active = False

        # Fonts
        self.title_font = font.Font(family="Segoe UI", size=32, weight="bold")
        self.subtitle_font = font.Font(family="Segoe UI", size=12)
        self.score_font = font.Font(family="Segoe UI", size=12, weight="bold")
        self.button_font = font.Font(family="Segoe UI", size=11, weight="bold")
        self.hint_font = font.Font(family="Segoe UI", size=10)

        # UI view structures
        self.current_frame = None
        self.slot_status_labels = []
        self.show_title_screen()

        # Key Bindings
        self.root.bind("<Up>", lambda e: self.move_player(-1, 0))
        self.root.bind("<Down>", lambda e: self.move_player(1, 0))
        self.root.bind("<Left>", lambda e: self.move_player(0, -1))
        self.root.bind("<Right>", lambda e: self.move_player(0, 1))
        
        self.root.bind("<w>", lambda e: self.move_player(-1, 0))
        self.root.bind("<s>", lambda e: self.move_player(1, 0))
        self.root.bind("<a>", lambda e: self.move_player(0, -1))
        self.root.bind("<d>", lambda e: self.move_player(0, 1))
        self.root.bind("<W>", lambda e: self.move_player(-1, 0))
        self.root.bind("<S>", lambda e: self.move_player(1, 0))
        self.root.bind("<A>", lambda e: self.move_player(0, -1))
        self.root.bind("<D>", lambda e: self.move_player(0, 1))
        self.root.bind("<Return>", lambda e: self.open_vault_at_current_item())
        self.root.bind("<KP_Enter>", lambda e: self.open_vault_at_current_item())
        self.root.bind("<Escape>", lambda e: self.cancel_qte())

    def clear_screen(self):
        if self.current_frame:
            self.current_frame.destroy()

    def cleanup_network(self):
        if self.server:
            self.server.stop()
            self.server = None
        if self.client:
            self.client.stop()
            self.client = None
        self.players.clear()
        self.per_player_data.clear()

    def show_title_screen(self):
        self.in_game = False
        self.is_host = False
        self.is_client = False
        self.game_started = False
        self.in_active_game = False
        self.my_player_id = None
        self.qte_active = False
        self.qte_sequence = []
        self.qte_progress = 0
        self.qte_target_move = (0, 0)
        self.last_known_server_pos = None
        self.per_player_data = {}
        self.showing_finish_screen = False
        self.finish_screen_match_complete = False
        self.cleanup_network()
        self.clear_screen()

        self.countdown_active = False
        self.current_frame = tk.Frame(self.root, bg="#090d14")
        self.current_frame.pack(fill="both", expand=True)

        backdrop = tk.Canvas(self.current_frame, bg="#090d14", highlightthickness=0)
        backdrop.place(relx=0, rely=0, relwidth=1, relheight=1)

        def draw_backdrop(event=None):
            backdrop.delete("menu_art")
            w, h = max(backdrop.winfo_width(), 900), max(backdrop.winfo_height(), 600)
            for x in range(0, w, 54):
                backdrop.create_line(x, 0, x, h, fill="#101c29", tags="menu_art")
            for y in range(0, h, 54):
                backdrop.create_line(0, y, w, y, fill="#101c29", tags="menu_art")
            for x, y in ((90, 110), (w-120, 160), (150, h-120), (w-180, h-110)):
                backdrop.create_oval(x-5, y-5, x+5, y+5, fill="#00d2ff", outline="", tags="menu_art")
                backdrop.create_line(x, y, w//2, h//2, fill="#12354a", dash=(4, 8), tags="menu_art")
            backdrop.create_text(w-80, 45, text="SECURE LINK  //  ONLINE", fill="#55ff55",
                                 anchor="e", font=("Consolas", 10, "bold"), tags="menu_art")
            backdrop.create_text(38, h-35, text="CTF GRID NETWORK  •  PORT 5555  •  ENCRYPTED",
                                 fill="#385064", anchor="w", font=("Consolas", 9), tags="menu_art")
        backdrop.bind("<Configure>", draw_backdrop)

        shell = tk.Frame(self.current_frame, bg="#0d141e", highlightthickness=1,
                         highlightbackground="#1b4055")
        shell.place(relx=.5, rely=.49, anchor="center", width=760, height=650)
        tk.Frame(shell, bg="#00d2ff", height=4).pack(fill="x")
        tk.Label(shell, text="◈  CTF OPERATIONS CONSOLE  /  NODE 01", fg="#5f8197",
                 bg="#0d141e", font=("Consolas", 9, "bold"), anchor="w").pack(
                     fill="x", padx=38, pady=(24, 8))
        tk.Label(shell, text="GRID EXPLORER", fg="#eafaff", bg="#0d141e",
                 font=("Segoe UI", 38, "bold")).pack()
        tk.Label(shell, text="CAPTURE  •  DECRYPT  •  DOMINATE", fg="#ffd24d", bg="#0d141e",
                 font=("Consolas", 12, "bold")).pack(pady=(2, 10))
        tk.Label(shell, text="Navigate the encrypted grid, recover hidden flags,\nand outmaneuver rival operators.",
                 fg="#8fa6b6", bg="#0d141e", justify="center",
                 font=self.subtitle_font).pack(pady=(0, 20))

        status = tk.Frame(shell, bg="#111d29", highlightthickness=1, highlightbackground="#1e3344")
        status.pack(fill="x", padx=38, pady=(0, 18))
        for label, color in (("● NETWORK READY", "#55ff55"), ("⚑ FLAGS ARMED", "#ffd24d"),
                             ("▦ GRID 20 × 10", "#00d2ff")):
            tk.Label(status, text=label, fg=color, bg="#111d29",
                     font=("Consolas", 9, "bold")).pack(side="left", expand=True, pady=10)

        btn_container = tk.Frame(shell, bg="#0d141e")
        btn_container.pack(fill="x", padx=72)

        def add_hover(button, normal, hover):
            button.bind("<Enter>", lambda e: button.config(bg=hover))
            button.bind("<Leave>", lambda e: button.config(bg=normal))

        # Solo
        btn_solo = tk.Button(
            btn_container,
            text="01   SOLO INFILTRATION                                      ›",
            command=self.start_solo_game,
            bg="#00d2ff",
            fg="#121214",
            activebackground="#00a3cc",
            activeforeground="#121214",
            font=self.button_font,
            bd=0,
            anchor="w",
            pady=12,
            cursor="hand2"
        )
        btn_solo.pack(fill="x", pady=6)
        add_hover(btn_solo, "#00d2ff", "#4ee2ff")

        # Host
        btn_host = tk.Button(
            btn_container,
            text="02   HOST OPERATIONS ROOM                            ›",
            command=self.host_game_action,
            bg="#16293d",
            fg="#00d2ff",
            activebackground="#ffd24d",
            activeforeground="#121214",
            font=self.button_font,
            bd=0,
            anchor="w",
            pady=12,
            cursor="hand2"
        )
        btn_host.pack(fill="x", pady=6)
        add_hover(btn_host, "#16293d", "#203e59")

        # Join
        btn_join = tk.Button(
            btn_container,
            text="03   JOIN STRIKE TEAM                                     ›",
            command=self.join_game_action,
            bg="#313143",
            fg="#ffffff",
            activebackground="#ffd24d",
            activeforeground="#121214",
            font=self.button_font,
            bd=0,
            anchor="w",
            pady=12,
            cursor="hand2"
        )
        btn_join.pack(fill="x", pady=6)
        add_hover(btn_join, "#313143", "#42425b")

        # Exit
        btn_exit = tk.Button(
            btn_container,
            text="EXIT",
            command=self.root.quit,
            bg="#212128",
            fg="#8c8c9a",
            activebackground="#ff4d4d",
            activeforeground="#ffffff",
            font=self.button_font,
            bd=0,
            width=16,
            pady=10,
            cursor="hand2"
        )
        btn_exit.pack(pady=18)
        add_hover(btn_exit, "#212128", "#4b252d")

    # ------------------ HOST LOBBY LOGIC ------------------

    def host_game_action(self):
        play_sound("click")
        max_p = CustomPlayerCountDialog(self.root, self.button_font).show()
        if not max_p:
            return
        self.max_players = max_p
        self.is_host = True
        self.in_game = True
        self.game_started = False
        self.in_active_game = False
        self.clear_screen()

        # Build Host Lobby Screen
        self.current_frame = tk.Frame(self.root, bg="#121214")
        self.current_frame.pack(fill="both", expand=True)

        self.header = tk.Frame(self.current_frame, bg="#1a1a24", bd=0, height=75)
        self.header.pack(fill="x", side="top")

        self.lbl_host_status = tk.Label(
            self.header, 
            text="HOST LOBBY ROOM - WAITING FOR PLAYERS", 
            fg="#ffd24d", 
            bg="#1a1a24", 
            font=self.score_font
        )
        self.lbl_host_status.pack(side="left", padx=20, pady=10)

        self.btn_back = tk.Button(
            self.header,
            text="CLOSE SERVER",
            command=self.show_title_screen,
            bg="#ff4d4d",
            fg="#ffffff",
            activebackground="#cc3333",
            activeforeground="#ffffff",
            bd=0,
            padx=15,
            pady=5,
            font=self.score_font,
            cursor="hand2"
        )
        self.btn_back.pack(side="right", padx=20, pady=12)

        self.btn_start = tk.Button(
            self.header,
            text="START GAME",
            command=self.start_host_active_game_screen,
            bg="#313143",
            fg="#5f5f6e",
            activebackground="#00a3cc",
            activeforeground="#121214",
            state="disabled",
            bd=0,
            padx=20,
            pady=5,
            font=self.score_font,
            cursor="hand2"
        )
        self.btn_start.pack(side="right", padx=10, pady=12)

        self.btn_demo_start = tk.Button(
            self.header,
            text="DEMO START",
            command=self.start_host_active_game_screen,
            bg="#ff9f1a",
            fg="#121214",
            activebackground="#e68a00",
            activeforeground="#121214",
            bd=0,
            padx=20,
            pady=5,
            font=self.score_font,
            cursor="hand2"
        )
        self.btn_demo_start.pack(side="right", padx=10, pady=12)

        self.sub_header = tk.Frame(self.current_frame, bg="#15151e", height=30)
        self.sub_header.pack(fill="x")
        
        self.lbl_ips = tk.Label(
            self.sub_header,
            text="Starting TCP socket listener on port 5555...",
            fg="#8c8c9a",
            bg="#15151e",
            font=self.hint_font
        )
        self.lbl_ips.pack(padx=20, pady=3, anchor="w")

        self.build_lobby_slots_ui()

        # Init Server Model
        self.server = GridServer(
            port=5555,
            max_players=self.max_players,
            on_lobby_update=lambda: self.root.after(0, self.update_lobby_ui),
            on_game_update=lambda: self.root.after(0, self.on_server_game_update)
        )
        if not self.server.start():
            self.lbl_ips.config(text="Server Port bind failed! Ensure port 5555 is free.", fg="#ff4d4d")
            return
        
        self.lbl_ips.config(text="Listening on port 5555. Share your Radmin VPN IP address with players!")

    def build_lobby_slots_ui(self):
        if hasattr(self, 'lobby_container') and self.lobby_container:
            try:
                self.lobby_container.destroy()
            except Exception:
                pass
        self.lobby_container = tk.Frame(self.current_frame, bg="#121214")
        self.lobby_container.pack(pady=20)

        self.slot_status_labels = []
        max_p = getattr(self, "max_players", 6)

        for i in range(1, max_p + 1):
            row = (i - 1) // 2
            col = (i - 1) % 2
            
            card = tk.Frame(
                self.lobby_container, 
                bg="#1a1a24", 
                bd=1, 
                relief="solid", 
                highlightbackground="#2d2d37", 
                highlightthickness=1, 
                width=420, 
                height=110
            )
            card.grid(row=row, column=col, padx=20, pady=12)
            card.grid_propagate(False)

            color = COLORS[(i - 1) % len(COLORS)]
            color_name = COLOR_NAMES[(i - 1) % len(COLORS)]

            lbl_title = tk.Label(
                card,
                text=f"PLAYER {i} ({color_name})",
                fg=color,
                bg="#1a1a24",
                font=self.score_font
            )
            lbl_title.pack(anchor="w", padx=20, pady=(15, 5))

            lbl_status = tk.Label(
                card,
                text="Waiting for player...",
                fg="#5f5f6e",
                bg="#1a1a24",
                font=self.hint_font
            )
            lbl_status.pack(anchor="w", padx=20)
            self.slot_status_labels.append(lbl_status)

    def update_lobby_ui(self):
        if not hasattr(self, 'slot_status_labels') or not self.slot_status_labels:
            return
        
        # Pull data from model
        current_players = self.server.players if self.is_host else self.client.players
        
        max_p = getattr(self, "max_players", 6)
        for i in range(1, max_p + 1):
            if i - 1 >= len(self.slot_status_labels):
                break
            lbl_status = self.slot_status_labels[i - 1]
            if i in current_players:
                p_info = current_players[i]
                player_prefix = "YOU - " if self.is_client and i == self.my_player_id else ""
                if p_info.get("ready", False):
                    lbl_status.config(
                        text=f"{player_prefix}READY - Connected from {p_info['ip']}",
                        fg="#55ff55"
                    )
                else:
                    lbl_status.config(
                        text=f"{player_prefix}NOT READY - Connected from {p_info['ip']}",
                        fg="#ff4d4d"
                    )
            else:
                lbl_status.config(
                    text="Waiting for player...",
                    fg="#5f5f6e"
                )

        if self.is_host:
            num_players = len(current_players)
            all_ready = num_players > 0 and all(info.get("ready", False) for info in current_players.values())
            if all_ready:
                self.btn_start.config(state="normal", bg="#55ff55", fg="#121214")
            else:
                self.btn_start.config(state="disabled", bg="#313143", fg="#5f5f6e")

            self.lbl_host_status.config(text=f"HOST LOBBY ROOM - ACTIVE PLAYERS: {num_players}/{max_p}")
            ip_list = [f"P{p_id}: {info['ip']}" for p_id, info in current_players.items()]
            ips_text = " | ".join(ip_list) if ip_list else "Waiting for connections..."
            self.lbl_ips.config(text=f"Connected: {ips_text}")

    def on_server_game_update(self):
        if self.server:
            if self.server.game_started and not self.in_active_game:
                self.launch_host_active_game_screen()
                return
            self.players = self.server.players
            # Build per_player_data from server's per-player dicts
            self.per_player_data = {}
            for p_id in self.server.players:
                self.per_player_data[p_id] = {
                    "visited":   self.server.player_visited.get(p_id, set()),
                    "items":     self.server.player_items.get(p_id, set()),
                    "collected": self.server.player_collected.get(p_id, {})
                }
            self.update_host_ui_stats()
            self.draw_elements()

    def start_host_active_game_screen(self):
        play_sound("click")
        # Ask difficulty before starting
        diff = CustomDifficultyDialog(self.root, self.button_font).show()
        if not diff:
            return
        self.difficulty       = diff
        self.items_per_player = 4 if diff == "hard" else 3

        self.countdown_active = True
        self.btn_start.config(state="disabled")
        if hasattr(self, "btn_demo_start"):
            self.btn_demo_start.config(state="disabled")
        self.server.begin_countdown(diff, 3)
        self.show_lobby_countdown(3, is_host=True)
        self.root.after(1000, lambda: self.countdown_active and self.show_lobby_countdown(2, is_host=True))
        self.root.after(2000, lambda: self.countdown_active and self.show_lobby_countdown(1, is_host=True))

    def show_lobby_countdown(self, count, is_host=False):
        """Display the synchronized deployment countdown over the lobby."""
        if not self.current_frame or not self.current_frame.winfo_exists():
            return
        overlay = getattr(self, "countdown_overlay", None)
        if not overlay or not overlay.winfo_exists():
            self.countdown_overlay = tk.Frame(self.current_frame, bg="#08111a",
                                              highlightthickness=2,
                                              highlightbackground="#00d2ff")
            self.countdown_overlay.place(relx=.5, rely=.52, anchor="center", width=520, height=300)
            tk.Label(self.countdown_overlay, text="⚑  MISSION DEPLOYMENT",
                     fg="#ffd24d", bg="#08111a",
                     font=("Consolas", 13, "bold")).pack(pady=(28, 8))
            tk.Label(self.countdown_overlay,
                     text="All operators ready. Synchronizing grid access...",
                     fg="#8fa6b6", bg="#08111a", font=self.hint_font).pack()
            self.countdown_number = tk.Label(self.countdown_overlay, text="",
                                             fg="#00d2ff", bg="#08111a",
                                             font=("Segoe UI", 82, "bold"))
            self.countdown_number.pack(pady=(2, 0))
            tk.Label(self.countdown_overlay, text="HOLD POSITION",
                     fg="#55ff55", bg="#08111a",
                     font=("Consolas", 11, "bold")).pack()
        self.countdown_number.config(text=str(count) if count > 0 else "GO")
        if is_host and hasattr(self, "lbl_host_status"):
            self.lbl_host_status.config(text=f"DEPLOYING OPERATORS IN {count}...")

    def launch_host_active_game_screen(self):
        self.game_started = True
        self.in_active_game = True
        self.countdown_active = False

        self.players = self.server.players
        self.per_player_data = {}
        for p_id in self.server.players:
            self.per_player_data[p_id] = {
                "visited":   self.server.player_visited.get(p_id, set()),
                "items":     self.server.player_items.get(p_id, set()),
                "collected": self.server.player_collected.get(p_id, {})
            }

        self.clear_screen()

        # Build Host Active Game UI
        self.current_frame = tk.Frame(self.root, bg="#121214")
        self.current_frame.pack(fill="both", expand=True)

        self.header = tk.Frame(self.current_frame, bg="#1a1a24", bd=0, height=75)
        self.header.pack(fill="x", side="top")

        self.lbl_host_status = tk.Label(
            self.header, 
            text=f"HOSTING SPECTATOR MODE | ACTIVE PLAYERS: {len(self.players)}/6", 
            fg="#ffd24d", 
            bg="#1a1a24", 
            font=self.score_font
        )
        self.lbl_host_status.pack(side="left", padx=20, pady=10)

        self.lbl_items = tk.Label(
            self.header,
            text="ITEMS: 0/0",
            fg="#55ff55",
            bg="#1a1a24",
            font=self.score_font
        )
        self.lbl_items.pack(side="left", padx=10, pady=10)

        self.btn_back = tk.Button(
            self.header,
            text="CLOSE SERVER",
            command=self.show_title_screen,
            bg="#ff4d4d",
            fg="#ffffff",
            activebackground="#cc3333",
            activeforeground="#ffffff",
            bd=0,
            padx=15,
            pady=5,
            font=self.score_font,
            cursor="hand2"
        )
        self.btn_back.pack(side="right", padx=20, pady=12)

        self.btn_reset = tk.Button(
            self.header,
            text="FORCE RESET",
            command=self.reset_host_game,
            bg="#313143",
            fg="#ffffff",
            activebackground="#42425b",
            activeforeground="#ffffff",
            bd=0,
            padx=15,
            pady=5,
            font=self.score_font,
            cursor="hand2"
        )
        self.btn_reset.pack(side="right", padx=10, pady=12)

        self.sub_header = tk.Frame(self.current_frame, bg="#15151e", height=30)
        self.sub_header.pack(fill="x")
        
        self.lbl_ips = tk.Label(
            self.sub_header,
            text="",
            fg="#8c8c9a",
            bg="#15151e",
            font=self.hint_font
        )
        self.lbl_ips.pack(padx=20, pady=3, anchor="w")

        # Container frame for spectator cards & leaderboard
        self.game_content_frame = tk.Frame(self.current_frame, bg="#121214")
        self.game_content_frame.pack(padx=20, pady=5, fill="both", expand=True)

        # Left: Grid layout container for split screens
        self.spectator_grid_frame = tk.Frame(self.game_content_frame, bg="#121214")
        self.spectator_grid_frame.pack(side="left", padx=(0, 20), fill="both", expand=True)

        # Right: Leaderboard frame
        self.leaderboard_frame = tk.Frame(self.game_content_frame, bg="#1a1a24", bd=2, relief="groove")
        self.leaderboard_frame.pack(side="right", fill="y", padx=(10, 0), pady=5)
        self.leaderboard_frame.pack_propagate(False)
        self.leaderboard_frame.config(width=340)

        lbl_leaderboard_title = tk.Label(
            self.leaderboard_frame,
            text="👑 LEADERBOARD",
            fg="#ffd24d",
            bg="#1a1a24",
            font=("Segoe UI", 14, "bold")
        )
        lbl_leaderboard_title.pack(pady=15, padx=20, anchor="w")

        self.leaderboard_rows_frame = tk.Frame(self.leaderboard_frame, bg="#1a1a24")
        self.leaderboard_rows_frame.pack(fill="both", expand=True)

        self.focused_slot = None
        self.spectator_cards = {}
        max_p = getattr(self, "max_players", 6)
        default_split_size = 17 if max_p > 5 else 22
        split_size = default_split_size
        split_w = 20 * split_size
        split_h = 10 * split_size
        cols = 3 if max_p > 4 else 2
        for slot_id in range(1, max_p + 1):
            row = (slot_id - 1) // cols
            col = (slot_id - 1) % cols

            card_frame = tk.Frame(self.spectator_grid_frame, bg="#1a1a24", bd=2, relief="groove")
            card_frame.grid(row=row, column=col, padx=10, pady=5)

            header_frame = tk.Frame(card_frame, bg="#15151e")
            header_frame.pack(fill="x", side="top")

            lbl_title = tk.Label(
                header_frame,
                text="SLOT " + str(slot_id) + " - EMPTY",
                fg="#8c8c9a",
                bg="#15151e",
                font=("Segoe UI", 10, "bold")
            )
            lbl_title.pack(side="left", padx=10, pady=3)

            lbl_stats = tk.Label(
                header_frame,
                text="",
                fg="#ffd24d",
                bg="#15151e",
                font=("Segoe UI", 9)
            )
            lbl_stats.pack(side="right", padx=10, pady=3)

            canvas = tk.Canvas(
                card_frame,
                width=split_w,
                height=split_h,
                bg="#121214",
                highlightthickness=0
            )
            canvas.pack(padx=5, pady=5)

            # Bind click events for focus/enlarge
            card_frame.bind("<Button-1>", lambda e, s=slot_id: self.focus_spectator_slot(s))
            header_frame.bind("<Button-1>", lambda e, s=slot_id: self.focus_spectator_slot(s))
            lbl_title.bind("<Button-1>", lambda e, s=slot_id: self.focus_spectator_slot(s))
            lbl_stats.bind("<Button-1>", lambda e, s=slot_id: self.focus_spectator_slot(s))
            canvas.bind("<Button-1>", lambda e, s=slot_id: self.focus_spectator_slot(s))

            self.spectator_cards[slot_id] = {
                "frame": card_frame,
                "title_label": lbl_title,
                "stats_label": lbl_stats,
                "canvas": canvas
            }

        # Bind background clicks to reset focus
        self.current_frame.bind("<Button-1>", lambda e: self.focus_spectator_slot(None))
        self.spectator_grid_frame.bind("<Button-1>", lambda e: self.focus_spectator_slot(None))
        self.header.bind("<Button-1>", lambda e: self.focus_spectator_slot(None))
        self.sub_header.bind("<Button-1>", lambda e: self.focus_spectator_slot(None))
        self.lbl_host_status.bind("<Button-1>", lambda e: self.focus_spectator_slot(None))
        if hasattr(self, 'lbl_ips') and self.lbl_ips:
            self.lbl_ips.bind("<Button-1>", lambda e: self.focus_spectator_slot(None))

        # Bind leaderboard clicks to reset focus
        self.leaderboard_frame.bind("<Button-1>", lambda e: self.focus_spectator_slot(None))
        self.leaderboard_rows_frame.bind("<Button-1>", lambda e: self.focus_spectator_slot(None))
        lbl_leaderboard_title.bind("<Button-1>", lambda e: self.focus_spectator_slot(None))

        self.footer = tk.Label(
            self.current_frame,
            text="Host Spectator Mode - Live Split-Screen Player Monitoring",
            fg="#8c8c9a",
            bg="#121214",
            font=self.hint_font
        )
        self.footer.pack(side="bottom", pady=5)
        self.footer.bind("<Button-1>", lambda e: self.focus_spectator_slot(None))

        self.draw_grid()
        self.update_host_ui_stats()
        self.draw_elements()

    def update_host_ui_stats(self):
        if not hasattr(self, 'lbl_host_status'):
            return
        num_players = len(self.players)
        max_p = getattr(self, "max_players", 6)
        if self.server and self.server.match_finished:
            self.lbl_host_status.config(
                text=f"MATCH COMPLETE | FINISHERS: {len(self.server.finished_players)}/{self.server.finish_target}"
            )
            if hasattr(self, "footer"):
                self.footer.config(text="Match Complete - Final Results")
        else:
            self.lbl_host_status.config(text=f"HOSTING SPECTATOR MODE | ACTIVE PLAYERS: {num_players}/{max_p}")
        if hasattr(self, 'lbl_items'):
            total = self.items_per_player * num_players
            found = sum(len(d.get("collected", {})) for d in self.per_player_data.values())
            self.lbl_items.config(text=f"ITEMS: {found}/{total}")
        ip_list = [f"P{p_id}: {info['ip']} ({COLOR_NAMES[(p_id-1)%len(COLOR_NAMES)]})" 
                   for p_id, info in self.players.items()]
        ips_text = " | ".join(ip_list) if ip_list else "Waiting for connections..."
        self.lbl_ips.config(text=ips_text)
        self.update_leaderboard()

    def reset_host_game(self):
        if self.server:
            self.server.reset_game()

    def focus_spectator_slot(self, slot_id):
        if getattr(self, "focused_slot", None) != slot_id:
            self.focused_slot = slot_id
            self.draw_elements()

    def update_leaderboard(self):
        if not hasattr(self, 'leaderboard_rows_frame'):
            return

        # Clear existing rows
        for widget in self.leaderboard_rows_frame.winfo_children():
            widget.destroy()

        # Gather player data
        scores = []
        for p_id, p_info in self.players.items():
            p_data = self.per_player_data.get(p_id, {})
            collected = p_data.get("collected", {})
            items_count = len(collected)
            moves_count = p_info.get("moves", 0)
            scores.append({
                "id": p_id,
                "color": p_info["color"],
                "moves": moves_count,
                "items": items_count
            })

        # Finished players lock their rank by completion order;
        # unfinished players sort below them by items desc, moves asc.
        finished_list = (
            self.server.finished_players if self.is_host and self.server
            else getattr(self.client, "finished_players", []) if self.client else []
        )

        def sort_key(item):
            p_id = item["id"]
            if p_id in finished_list:
                return (0, finished_list.index(p_id), 0)
            return (1, -item["items"], item["moves"])

        scores.sort(key=sort_key)

        # Draw rows
        for rank, item in enumerate(scores, 1):
            p_id = item["id"]
            p_color = item["color"]
            moves = item["moves"]
            items_found = item["items"]
            is_finished = p_id in finished_list

            row_frame = tk.Frame(self.leaderboard_rows_frame,
                                 bg="#1e1e2e" if is_finished else "#1a1a24", pady=5)
            row_frame.pack(fill="x", padx=15, pady=4)

            rank_suffix = "th"
            if rank == 1: rank_suffix = "st"
            elif rank == 2: rank_suffix = "nd"
            elif rank == 3: rank_suffix = "rd"

            lbl_rank = tk.Label(
                row_frame,
                text=f"{rank}{rank_suffix}",
                fg="#ffd24d" if rank == 1 else "#8c8c9a",
                bg=row_frame["bg"],
                font=("Segoe UI", 11, "bold"),
                width=4,
                anchor="w"
            )
            lbl_rank.pack(side="left")

            lbl_dot = tk.Label(
                row_frame,
                text="⬤",
                fg=p_color,
                bg=row_frame["bg"],
                font=("Segoe UI", 12)
            )
            lbl_dot.pack(side="left", padx=5)

            lbl_player = tk.Label(
                row_frame,
                text=f"PLAYER {p_id}",
                fg="#ffffff",
                bg=row_frame["bg"],
                font=("Segoe UI", 10, "bold")
            )
            lbl_player.pack(side="left", padx=5)

            if is_finished:
                # Locked badge — rank is permanently sealed
                tk.Label(
                    row_frame,
                    text="\U0001f3c6 DONE",
                    fg="#ffd24d",
                    bg=row_frame["bg"],
                    font=("Segoe UI", 9, "bold")
                ).pack(side="right", padx=5)
                tk.Label(
                    row_frame,
                    text="\U0001f512",
                    fg="#ffd24d",
                    bg=row_frame["bg"],
                    font=("Segoe UI", 10)
                ).pack(side="right")
            else:
                if items_found >= self.items_per_player:
                    tk.Label(
                        row_frame,
                        text="\U0001f451",
                        fg="#ffd24d",
                        bg=row_frame["bg"],
                        font=("Segoe UI", 10)
                    ).pack(side="left", padx=2)

                tk.Label(
                    row_frame,
                    text=f"{items_found}/{self.items_per_player} Items ({moves} mv)",
                    fg="#55ff55" if items_found >= self.items_per_player else "#ffd24d" if items_found > 0 else "#8c8c9a",
                    bg=row_frame["bg"],
                    font=("Segoe UI", 10)
                ).pack(side="right", padx=5)

    # ------------------ CLIENT LOBBY LOGIC ------------------

    def join_game_action(self):
        play_sound("click")
        host_ip = CustomIPDialog(self.root, self.button_font).show()
        if not host_ip:
            return

        self.is_client = True
        self.in_game = True
        self.game_started = False
        self.in_active_game = False
        self.clear_screen()

        # Build Client Lobby UI
        self.current_frame = tk.Frame(self.root, bg="#121214")
        self.current_frame.pack(fill="both", expand=True)

        self.header = tk.Frame(self.current_frame, bg="#1a1a24", bd=0, height=75)
        self.header.pack(fill="x", side="top")

        self.lbl_lobby_title = tk.Label(
            self.header, 
            text="MULTIPLAYER LOBBY - CONNECTING...", 
            fg="#ffd24d", 
            bg="#1a1a24", 
            font=self.score_font
        )
        self.lbl_lobby_title.pack(side="left", padx=20, pady=15)

        self.client_is_ready = False
        self.btn_ready = tk.Button(
            self.header,
            text="READY",
            command=self.toggle_ready_action,
            bg="#313143",
            fg="#5f5f6e",
            activebackground="#55ff55",
            activeforeground="#121214",
            state="disabled",
            bd=0,
            padx=20,
            pady=5,
            font=self.score_font,
            cursor="hand2"
        )
        self.btn_ready.pack(side="right", padx=10, pady=12)

        self.btn_back = tk.Button(
            self.header,
            text="LEAVE LOBBY",
            command=self.show_title_screen,
            bg="#ff4d4d",
            fg="#ffffff",
            activebackground="#cc3333",
            activeforeground="#ffffff",
            bd=0,
            padx=15,
            pady=5,
            font=self.score_font,
            cursor="hand2"
        )
        self.btn_back.pack(side="right", padx=20, pady=12)

        self.sub_header = tk.Frame(self.current_frame, bg="#15151e", height=30)
        self.sub_header.pack(fill="x")
        
        self.lbl_status_desc = tk.Label(
            self.sub_header,
            text=f"Connecting to host at {host_ip}...",
            fg="#8c8c9a",
            bg="#15151e",
            font=self.hint_font
        )
        self.lbl_status_desc.pack(padx=20, pady=3, anchor="w")

        # Connect Client Model
        self.client = GridClient(
            host_ip=host_ip,
            port=5555,
            on_init=lambda p_id: self.root.after(0, self.on_client_init, p_id),
            on_state_update=lambda: self.root.after(0, self.on_client_state_update),
            on_disconnect=lambda: self.root.after(0, self.on_client_disconnect),
            on_lobby_full=lambda: self.root.after(0, self.on_client_lobby_full),
            on_unlock_result=lambda success: self.root.after(0, lambda: self.on_unlock_result_received(success))
        )
        
        if not self.client.connect():
            messagebox.showerror("Connection Error", f"Could not connect to host at {host_ip}:5555")
            self.show_title_screen()

    def on_client_init(self, p_id):
        self.my_player_id = p_id
        self.max_players = getattr(self.client, "max_players", 6)
        self.lbl_lobby_title.config(text=f"MULTIPLAYER LOBBY - PLAYER {p_id}")
        self.lbl_status_desc.config(text="Toggle ready status to let the Host start...")
        self.btn_ready.config(state="normal", bg="#55ff55", fg="#121214")
        self.build_lobby_slots_ui()

    def on_client_lobby_full(self):
        messagebox.showerror("Lobby Full", "The server lobby is currently full (max 6 players).")
        self.show_title_screen()

    def on_client_state_update(self):
        if self.client:
            self.players = self.client.players
            self.per_player_data = self.client.per_player_data
            self.game_started = self.client.game_started
            countdown = getattr(self.client, "countdown", 0)
            if countdown > 0 and not self.game_started:
                self.countdown_active = True
                self.show_lobby_countdown(countdown)

            # Detect server reset: my visited shrunk back to 1
            my_visited = self.client.get_my_visited()
            if len(my_visited) <= 1 and self.moves > 0:
                self.moves = 0
                self.client_cell_arrows = {}

            # Detect server-forced position changes to cancel QTE
            my_id = self.my_player_id
            if my_id in self.players:
                server_pos = (self.players[my_id]["r"], self.players[my_id]["c"])
                if self.last_known_server_pos is not None and self.last_known_server_pos != server_pos:
                    self.qte_active = False
                self.last_known_server_pos = server_pos

            # Freeze arrow for each newly discovered cell (only unfound items count)
            if my_id in self.per_player_data:
                my_data = self.per_player_data[my_id]
                remaining = my_data.get("items", set())
                collected = my_data.get("collected", {})
                visited = my_data.get("visited", set())
                undiscovered = {item for item in remaining if item not in visited}
                for cell in visited:
                    if cell not in self.client_cell_arrows and cell not in collected:
                        arrow = self.get_closest_item_arrow(cell[0], cell[1], undiscovered)
                        self.client_cell_arrows[cell] = arrow

            if self.game_started:
                self.countdown_active = False
                local_finished = my_id in self.client.finished_players
                if self.client.match_finished or local_finished:
                    if (not self.showing_finish_screen
                            or self.finish_screen_match_complete != self.client.match_finished):
                        self.show_game_finished_screen(self.client.match_finished)
                elif not self.in_active_game or self.showing_finish_screen:
                    self.start_client_active_game_screen()
                else:
                    self.update_client_ui_stats()
                    self.draw_elements()
            else:
                self.update_lobby_ui()

    def on_client_disconnect(self):
        messagebox.showwarning("Connection Lost", "Disconnected from server host.")
        self.show_title_screen()

    def toggle_ready_action(self):
        play_sound("click")
        self.client_is_ready = not self.client_is_ready
        if self.client_is_ready:
            self.btn_ready.config(text="UNREADY", bg="#ff4d4d", fg="#ffffff")
        else:
            self.btn_ready.config(text="READY", bg="#55ff55", fg="#121214")
        if self.client:
            self.client.send_ready(self.client_is_ready)

    def start_client_active_game_screen(self):
        self.in_active_game = True
        self.showing_finish_screen = False
        if not hasattr(self, "client_cell_arrows"):
            self.client_cell_arrows = {}   # frozen (r,c) -> arrow char
        self.selected_powerup_slot = None
        self.clear_screen()

        # Build Client Game GUI
        self.current_frame = tk.Frame(self.root, bg="#121214")
        self.current_frame.pack(fill="both", expand=True)

        self.header = tk.Frame(self.current_frame, bg="#1a1a24", bd=0, height=60)
        self.header.pack(fill="x", side="top")

        self.lbl_player_id = tk.Label(
            self.header, 
            text="PLAYER --", 
            fg="#ffd24d", 
            bg="#1a1a24", 
            font=self.score_font
        )
        self.lbl_player_id.pack(side="left", padx=20, pady=15)

        self.lbl_pos = tk.Label(
            self.header, 
            text="POSITION: --", 
            fg="#ffffff", 
            bg="#1a1a24", 
            font=self.score_font
        )
        self.lbl_pos.pack(side="left", padx=10, pady=15)

        self.lbl_moves = tk.Label(
            self.header, 
            text="MOVES: 0", 
            fg="#00d2ff", 
            bg="#1a1a24", 
            font=self.score_font
        )
        self.lbl_moves.pack(side="left", padx=10, pady=15)

        self.lbl_items = tk.Label(
            self.header, 
            text=f"ITEMS: 0/{self.items_per_player}",
            fg="#55ff55", 
            bg="#1a1a24", 
            font=self.score_font
        )
        self.lbl_items.pack(side="left", padx=10, pady=15)

        self.btn_back = tk.Button(
            self.header,
            text="LEAVE GAME",
            command=self.show_title_screen,
            bg="#ff4d4d",
            fg="#ffffff",
            activebackground="#cc3333",
            activeforeground="#ffffff",
            bd=0,
            padx=15,
            pady=5,
            font=self.score_font,
            cursor="hand2"
        )
        self.btn_back.pack(side="right", padx=20, pady=12)

        # Lock/Key icon button
        self.btn_lock = tk.Button(
            self.header,
            text="🔒 OPEN LOCK",
            command=self.open_lock_dialog,
            bg="#2d2d37",
            fg="#ffd24d",
            activebackground="#ffd24d",
            activeforeground="#121214",
            bd=0,
            padx=15,
            pady=5,
            font=self.score_font,
            cursor="hand2"
        )
        self.btn_lock.pack(side="right", padx=10, pady=12)

        # --- Powerup Bar (3 slots) ---
        self.powerup_bar = tk.Frame(self.header, bg="#1a1a24")
        self.powerup_bar.pack(side="right", padx=10, pady=5)

        tk.Label(self.powerup_bar, text="POWERUPS:",
                 fg="#5f5f6e", bg="#1a1a24",
                 font=("Segoe UI", 9, "bold")
                 ).pack(side="left", padx=(0, 4), pady=5)

        self.powerup_slot_frames = []
        self.powerup_slot_labels = []
        for slot_i in range(3):
            slot_key = str(slot_i + 1)
            sf = tk.Frame(self.powerup_bar, bg="#1a1a24",
                          bd=0, highlightthickness=2,
                          highlightbackground="#2d2d37",
                          width=115, height=34)
            sf.pack(side="left", padx=4, pady=5)
            sf.pack_propagate(False)
            lbl = tk.Label(sf, text=f"[{slot_key}] EMPTY",
                           fg="#3a3a4a", bg="#1a1a24",
                           font=("Segoe UI", 8))
            lbl.pack(expand=True)
            # Click or key 1/2/3 to select
            sf.bind("<Button-1>", lambda e, i=slot_i: self.select_powerup_slot(i))
            lbl.bind("<Button-1>", lambda e, i=slot_i: self.select_powerup_slot(i))
            self.powerup_slot_frames.append(sf)
            self.powerup_slot_labels.append(lbl)

        self.canvas = tk.Canvas(
            self.current_frame,
            width=CANVAS_WIDTH,
            height=CANVAS_HEIGHT,
            bg="#1e1e24",
            highlightthickness=0
        )
        self.canvas.pack(padx=60, pady=30)

        self.footer = tk.Label(
            self.current_frame,
            text="Arrow keys / WASD to move  •  1 / 2 / 3 to select powerup  •  E to use",
            fg="#8c8c9a",
            bg="#121214",
            font=self.hint_font
        )
        self.footer.pack(side="bottom", pady=10)

        # Key bindings for powerup slot selection
        self.root.bind("<Key-1>", lambda e: self.select_powerup_slot(0))
        self.root.bind("<Key-2>", lambda e: self.select_powerup_slot(1))
        self.root.bind("<Key-3>", lambda e: self.select_powerup_slot(2))
        self.root.bind("<Key-e>", lambda e: self.use_selected_powerup())
        self.root.bind("<Key-E>", lambda e: self.use_selected_powerup())

        self.draw_grid()
        self.update_client_ui_stats()
        self.draw_elements()

    def show_game_finished_screen(self, match_complete):
        self.in_active_game = True
        self.showing_finish_screen = True
        self.finish_screen_match_complete = match_complete
        self.qte_active = False
        self.clear_screen()

        self.current_frame = tk.Frame(self.root, bg="#121214")
        self.current_frame.pack(fill="both", expand=True)
        panel = tk.Frame(self.current_frame, bg="#1a1a24", bd=1, relief="solid")
        panel.place(relx=0.5, rely=0.46, anchor="center", width=560, height=390)

        finished = self.my_player_id in self.client.finished_players
        title = "GAME FINISHED" if finished else "MATCH COMPLETE"
        tk.Label(panel, text=title, fg="#55ff55" if finished else "#ffd24d",
                 bg="#1a1a24", font=("Segoe UI", 26, "bold")).pack(pady=(38, 12))

        if finished:
            rank = self.client.finished_players.index(self.my_player_id) + 1
            detail = f"You finished in position {rank}."
        else:
            detail = "The required number of players completed the task."
        tk.Label(panel, text=detail, fg="#ffffff", bg="#1a1a24",
                 font=("Segoe UI", 14, "bold")).pack(pady=8)

        player = self.players.get(self.my_player_id, {})
        collected = len(self.per_player_data.get(self.my_player_id, {}).get("collected", {}))
        tk.Label(panel, text=f"Items: {collected}/{self.client.items_per_player}   Moves: {player.get('moves', self.moves)}",
                 fg="#00d2ff", bg="#1a1a24", font=("Segoe UI", 12)).pack(pady=8)

        status_text = (
            f"Final finishers: {len(self.client.finished_players)}/{self.client.finish_target}"
            if match_complete else
            f"Waiting for finishers: {len(self.client.finished_players)}/{self.client.finish_target}"
        )
        tk.Label(panel, text=status_text, fg="#8c8c9a", bg="#1a1a24",
                 font=("Segoe UI", 11)).pack(pady=12)

        tk.Button(panel, text="RETURN TO TITLE", command=self.show_title_screen,
                  bg="#00d2ff", fg="#121214", activebackground="#00a3cc",
                  activeforeground="#121214", font=self.button_font, bd=0,
                  padx=24, pady=10, cursor="hand2").pack(pady=22)

    def update_client_ui_stats(self):
        if not self.in_active_game or not self.my_player_id:
            return
        
        my_id = self.my_player_id
        if my_id in self.players:
            info = self.players[my_id]
            self.lbl_pos.config(text=f"POSITION: ({info['c']}, {info['r']})")
            
            color_name = COLOR_NAMES[(my_id - 1) % len(COLORS)]
            color_hex = COLORS[(my_id - 1) % len(COLORS)]
            self.lbl_player_id.config(text=f"PLAYER {my_id} ({color_name})", fg=color_hex)
            
        self.lbl_moves.config(text=f"MOVES: {self.moves}")
        if hasattr(self, 'lbl_items') and self.my_player_id in self.per_player_data:
            my_data = self.per_player_data[self.my_player_id]
            found = len(my_data.get("collected", {}))
            self.lbl_items.config(text=f"ITEMS: {found}/{self.items_per_player}")

        # Lock button always available (gold)
        if hasattr(self, 'btn_lock'):
            self.btn_lock.config(bg="#ffd24d", fg="#121214", text="\U0001f512 VAULT")

        self.update_powerup_bar()

    def select_powerup_slot(self, slot_index):
        """Highlight the selected powerup slot (0-based). No-op if slot is empty."""
        if not hasattr(self, 'powerup_slot_frames'):
            return
        # Get current slots for this player
        slots = [None, None, None]
        if self.my_player_id and self.my_player_id in self.per_player_data:
            slots = self.per_player_data[self.my_player_id].get("powerups", [None, None, None])
        elif self.my_player_id == "solo":
            slots = getattr(self, 'solo_powerups', [None, None, None])

        if slots[slot_index] is None:
            return  # empty slot — nothing to select

        self.selected_powerup_slot = slot_index
        play_sound("click")
        self.update_powerup_bar()

    def update_powerup_bar(self):
        """Refresh the 3 powerup slot boxes to reflect current inventory."""
        if not hasattr(self, 'powerup_slot_frames'):
            return

        slots = [None, None, None]
        if self.my_player_id == "solo":
            slots = getattr(self, 'solo_powerups', [None, None, None])
        elif self.my_player_id and self.my_player_id in self.per_player_data:
            slots = self.per_player_data[self.my_player_id].get("powerups", [None, None, None])

        selected = getattr(self, 'selected_powerup_slot', None)

        for i, (sf, lbl) in enumerate(zip(self.powerup_slot_frames, self.powerup_slot_labels)):
            pu_id = slots[i] if i < len(slots) else None
            is_selected = (selected == i and pu_id is not None)

            if pu_id:
                meta = POWERUP_META.get(pu_id, {"label": pu_id, "icon": "?", "color": "#ffffff"})
                lbl.config(
                    text=f"[{i+1}] {meta['icon']} {meta['label']}",
                    fg=meta["color"]
                )
                border_color = "#ffffff" if is_selected else meta["color"]
                bg = "#2a2a3a" if is_selected else "#1a1a24"
            else:
                empty_labels = ("REVEAL", "MOVE ITEM", "TELEPORT")
                lbl.config(text=f"[{i+1}] {empty_labels[i]} (EMPTY)", fg="#5f5f6e")
                border_color = "#2d2d37"
                bg = "#1a1a24"

            sf.config(highlightbackground=border_color, bg=bg)
            lbl.config(bg=bg)

    def open_lock_dialog(self):
        """Open the 3-keyhole vault screen for multiplayer client."""
        if not self.is_client or not self.my_player_id:
            return
        my_id = self.my_player_id
        my_data = self.per_player_data.get(my_id, {})
        visited   = my_data.get("visited", set())
        items     = my_data.get("items", set())       # remaining
        collected = my_data.get("collected", {})      # (r,c) -> color
        item_keys = my_data.get("item_keys", {})      # (r,c) -> key str

        # Build full list of 3 item positions (remaining + collected)
        player_pos = (self.players[my_id]["r"], self.players[my_id]["c"]) if my_id in self.players else None
        all_positions = sorted(list(items) + list(collected.keys()))
        items_data = []
        for i, pos in enumerate(all_positions[:self.items_per_player]):
            items_data.append({
                "index":      i + 1,
                "pos":        pos,
                "key":        item_keys.get(pos),
                "collected":  pos in collected,
                "discovered": pos in visited,
                "is_at":      pos == player_pos,
            })

        def on_submit(pos, entered_key):
            if self.client:
                self.client.send_unlock(pos[0], pos[1], entered_key)
            return None  # async — dialog closes itself

        LockScreenDialog(self.root, self.button_font, items_data, on_submit).show()

    def open_vault_at_current_item(self):
        """Open the vault only when standing on one of the local player's items."""
        if not self.in_active_game or self.qte_active:
            return
        if self.my_player_id == "solo":
            if (self.player_r, self.player_c) in self.hidden_items:
                self.open_lock_dialog_solo()
            return
        if not self.is_client or self.my_player_id not in self.players:
            return
        position = (
            self.players[self.my_player_id]["r"],
            self.players[self.my_player_id]["c"],
        )
        own_items = self.per_player_data.get(self.my_player_id, {}).get("items", set())
        if position in own_items:
            self.open_lock_dialog()

    def on_unlock_result_received(self, success):
        # Dialog handles its own feedback; just refresh the map
        self.draw_elements()
        if success:
            play_sound("collect")

    # ------------------ POWERUP ACTIVATION ------------------

    def use_selected_powerup(self):
        """Called when player presses E. Activates the selected powerup slot."""
        if self.selected_powerup_slot is None:
            return

        slot = self.selected_powerup_slot

        if self.my_player_id == "solo":
            pu = (getattr(self, 'solo_powerups', [None, None, None]))[slot]
            if not pu:
                return

            if pu == "reveal":
                undiscovered = [item for item in self.hidden_items if item not in self.visited_cells]
                if undiscovered:
                    self.visited_cells.add(undiscovered[0])
                    play_sound("qte_success")
                    self.solo_powerups[slot] = None
                    self.selected_powerup_slot = None
                    self.update_powerup_bar()
                    self.draw_elements()
                else:
                    play_sound("qte_wrong")

            elif pu in ("shield", "speed"):
                # Disabled in solo mode — only Reveal is available
                play_sound("qte_wrong")


        else:
            # Multiplayer — delegate to server
            my_id = self.my_player_id
            if not my_id or my_id not in self.per_player_data:
                return
            slots_list = self.per_player_data[my_id].get("powerups", [None, None, None])
            pu = slots_list[slot] if slot < len(slots_list) else None
            if not pu:
                return

            if pu == "speed":
                self.show_player_teleport_selection_dialog(slot)
            else:
                self.send_powerup_use(slot, None)

    def show_player_teleport_selection_dialog(self, slot):
        TeleportDialog(
            self.root,
            self.button_font,
            self.players,
            self.my_player_id,
            lambda target_id: self.send_powerup_use(slot, target_id),
            COLORS,
            COLOR_NAMES
        )

    def send_powerup_use(self, slot, target_id=None):
        if self.client:
            self.client.send_powerup_use(slot, target_id)



    def start_solo_game(self):
        play_sound("click")
        # Ask difficulty before starting
        diff = CustomDifficultyDialog(self.root, self.button_font).show()
        if not diff:
            return   # player cancelled
        self.difficulty       = diff
        self.items_per_player = 4 if diff == "hard" else 3
        self.solo_cell_close_active = False

        self.in_game = True
        self.my_player_id = "solo"
        self.clear_screen()

        # Random spawn inside boundary
        self.player_r = random.randint(0, GRID_ROWS - 1)
        self.player_c = random.randint(0, GRID_COLS - 1)
        self.moves = 0
        self.solo_item_keys = {}
        self.solo_cell_arrows = {}       # (r,c) -> frozen arrow char
        self.solo_powerups = [None, None, None]   # player's 3 slots
        self.selected_powerup_slot = None
        self.solo_map_powerups = self._spawn_solo_powerups()

        self.players = {"solo": {"r": self.player_r, "c": self.player_c, "color": "#00d2ff"}}
        self.visited_cells = {(self.player_r, self.player_c)}
        self.spawn_solo_hidden_items()
        if self.difficulty == "hard":
            self._start_solo_cell_close_timer()

        # Game Frame
        self.current_frame = tk.Frame(self.root, bg="#121214")
        self.current_frame.pack(fill="both", expand=True)

        self.header = tk.Frame(self.current_frame, bg="#1a1a24", bd=0, height=60)
        self.header.pack(fill="x", side="top")

        lbl_solo_title = tk.Label(
            self.header,
            text="OFFLINE MODE",
            fg="#8c8c9a",
            bg="#1a1a24",
            font=self.score_font
        )
        lbl_solo_title.pack(side="left", padx=20, pady=15)

        self.lbl_pos = tk.Label(
            self.header, 
            text=f"POSITION: ({self.player_c}, {self.player_r})", 
            fg="#ffd24d", 
            bg="#1a1a24", 
            font=self.score_font
        )
        self.lbl_pos.pack(side="left", padx=10, pady=15)

        self.lbl_moves = tk.Label(
            self.header, 
            text="MOVES: 0", 
            fg="#00d2ff", 
            bg="#1a1a24", 
            font=self.score_font
        )
        self.lbl_moves.pack(side="left", padx=10, pady=15)

        self.lbl_items = tk.Label(
            self.header, 
            text=f"ITEMS: 0/{self.items_per_player}",
            fg="#55ff55", 
            bg="#1a1a24", 
            font=self.score_font
        )
        self.lbl_items.pack(side="left", padx=10, pady=15)

        self.btn_back = tk.Button(
            self.header,
            text="MAIN MENU",
            command=self.show_title_screen,
            bg="#ff4d4d",
            fg="#ffffff",
            activebackground="#cc3333",
            activeforeground="#ffffff",
            bd=0,
            padx=15,
            pady=5,
            font=self.score_font,
            cursor="hand2"
        )
        self.btn_back.pack(side="right", padx=20, pady=12)

        self.btn_reset = tk.Button(
            self.header,
            text="RESET",
            command=self.reset_game,
            bg="#313143",
            fg="#ffffff",
            activebackground="#42425b",
            activeforeground="#ffffff",
            bd=0,
            padx=15,
            pady=5,
            font=self.score_font,
            cursor="hand2"
        )
        self.btn_reset.pack(side="right", padx=10, pady=12)

        self.btn_lock = tk.Button(
            self.header,
            text="\U0001f512 OPEN LOCK",
            command=self.open_lock_dialog_solo,
            bg="#2d2d37",
            fg="#ffd24d",
            activebackground="#ffd24d",
            activeforeground="#121214",
            bd=0,
            padx=15,
            pady=5,
            font=self.score_font,
            cursor="hand2"
        )
        self.btn_lock.pack(side="right", padx=10, pady=12)

        # --- Powerup Bar (solo) ---
        self.powerup_bar = tk.Frame(self.header, bg="#1a1a24")
        self.powerup_bar.pack(side="right", padx=10, pady=5)

        tk.Label(self.powerup_bar, text="POWERUPS:",
                 fg="#5f5f6e", bg="#1a1a24",
                 font=("Segoe UI", 9, "bold")
                 ).pack(side="left", padx=(0, 4), pady=5)

        self.powerup_slot_frames = []
        self.powerup_slot_labels = []
        for slot_i in range(3):
            slot_key = str(slot_i + 1)
            sf = tk.Frame(self.powerup_bar, bg="#1a1a24",
                          bd=0, highlightthickness=2,
                          highlightbackground="#2d2d37",
                          width=115, height=34)
            sf.pack(side="left", padx=4, pady=5)
            sf.pack_propagate(False)
            lbl = tk.Label(sf, text=f"[{slot_key}] EMPTY",
                           fg="#3a3a4a", bg="#1a1a24",
                           font=("Segoe UI", 8))
            lbl.pack(expand=True)
            sf.bind("<Button-1>", lambda e, i=slot_i: self.select_powerup_slot(i))
            lbl.bind("<Button-1>", lambda e, i=slot_i: self.select_powerup_slot(i))
            self.powerup_slot_frames.append(sf)
            self.powerup_slot_labels.append(lbl)

        self.canvas = tk.Canvas(
            self.current_frame,
            width=CANVAS_WIDTH,
            height=CANVAS_HEIGHT,
            bg="#1e1e24",
            highlightthickness=0
        )
        self.canvas.pack(padx=60, pady=30)

        self.footer = tk.Label(
            self.current_frame,
            text="Arrow keys / WASD to move  •  1 / 2 / 3 to select powerup  •  E to use",
            fg="#8c8c9a",
            bg="#121214",
            font=self.hint_font
        )
        self.footer.pack(side="bottom", pady=10)

        # Key bindings for powerup slot selection
        self.root.bind("<Key-1>", lambda e: self.select_powerup_slot(0))
        self.root.bind("<Key-2>", lambda e: self.select_powerup_slot(1))
        self.root.bind("<Key-3>", lambda e: self.select_powerup_slot(2))
        self.root.bind("<Key-e>", lambda e: self.use_selected_powerup())
        self.root.bind("<Key-E>", lambda e: self.use_selected_powerup())

        self.draw_grid()
        self.draw_elements()
        self.update_powerup_bar()
        self.start_solo_spawner_timer()

    # ------------------ CANVAS DRAWING & CORE MOVEMENT ------------------

    def draw_grid(self):
        if hasattr(self, 'is_host') and self.is_host:
            return
        self.canvas.delete("grid_line")
        # Verticals
        for i in range(GRID_COLS + 1):
            x = i * CELL_SIZE
            self.canvas.create_line(x, 0, x, CANVAS_HEIGHT, fill="#2d2d37", width=1, tags="grid_line")
        # Horizontals
        for i in range(GRID_ROWS + 1):
            y = i * CELL_SIZE
            self.canvas.create_line(0, y, CANVAS_WIDTH, y, fill="#2d2d37", width=1, tags="grid_line")

    def visible_map_players(self):
        """Return active characters visible on a player's map."""
        if not self.client:
            return self.players
        finished = set(self.client.finished_players)
        return {p_id: player for p_id, player in self.players.items() if p_id not in finished}

    def draw_elements(self):
        if not self.in_active_game and not self.my_player_id == "solo":
            return

        if hasattr(self, 'is_host') and self.is_host:
            max_p = getattr(self, "max_players", 6)
            focused = getattr(self, "focused_slot", None)
            
            for slot_id in range(1, max_p + 1):
                card = self.spectator_cards.get(slot_id)
                if not card:
                    continue
                canvas = card["canvas"]
                lbl_title = card["title_label"]
                lbl_stats = card["stats_label"]

                p_id = slot_id
                p_info = self.players.get(p_id)
                p_data = self.per_player_data.get(p_id, {})

                # Determine sizes based on split_size
                max_p = getattr(self, "max_players", 6)
                default_split_size = 17 if max_p > 5 else 22
                if focused is None:
                    split_size = default_split_size
                elif slot_id == focused:
                    split_size = 32 if max_p > 5 else 36
                else:
                    split_size = 8 if max_p > 5 else 14

                split_w = 20 * split_size
                split_h = 10 * split_size
                canvas.config(width=split_w, height=split_h)

                if not p_info:
                    canvas.delete("all")
                    canvas.create_rectangle(0, 0, split_w, split_h, fill="#121214", outline="#1a1a24")
                    empty_font = ("Segoe UI", 12 if split_size == 36 else (10 if split_size == 32 else (9 if split_size == 22 else (8 if split_size == 17 else 5))), "bold")
                    canvas.create_text(
                        10 * split_size, 5 * split_size,
                        text="SLOT " + str(slot_id) + " EMPTY\nWAITING FOR PLAYER" if split_size > 14 else "EMPTY",
                        fill="#3a3a4a", font=empty_font, justify="center"
                    )
                    lbl_title.config(text="SLOT " + str(slot_id) + " - EMPTY", fg="#5f5f6e")
                    lbl_stats.config(text="")
                else:
                    canvas.delete("all")
                    for i in range(GRID_COLS + 1):
                        x = i * split_size
                        canvas.create_line(x, 0, x, 10 * split_size, fill="#23232c", width=1)
                    for i in range(GRID_ROWS + 1):
                        y = i * split_size
                        canvas.create_line(0, y, 20 * split_size, y, fill="#23232c", width=1)

                    visited = p_data.get("visited", set())
                    items = p_data.get("items", set())
                    collected = p_data.get("collected", {})
                    p_color = p_info["color"]
                    color_name = COLOR_NAMES[(p_id - 1) % len(COLORS)]

                    # Determine text and token sizes based on split_size
                    if split_size == 36:
                        flag_font = ("Segoe UI", 12, "bold")
                        arrow_font = ("Segoe UI", 14, "bold")
                        p_margin = 5
                        flare_offset = 7
                        ring_w = 2
                    elif split_size == 32:
                        flag_font = ("Segoe UI", 10, "bold")
                        arrow_font = ("Segoe UI", 12, "bold")
                        p_margin = 4
                        flare_offset = 6
                        ring_w = 2
                    elif split_size == 22:
                        flag_font = ("Segoe UI", 8, "bold")
                        arrow_font = ("Segoe UI", 10, "bold")
                        p_margin = 3
                        flare_offset = 4
                        ring_w = 1
                    elif split_size == 17:
                        flag_font = ("Segoe UI", 7, "bold")
                        arrow_font = ("Segoe UI", 8, "bold")
                        p_margin = 2
                        flare_offset = 3
                        ring_w = 1
                    else:  # 14 or smaller (e.g. 8)
                        flag_font = ("Segoe UI", 5 if split_size < 12 else 6, "bold")
                        arrow_font = ("Segoe UI", 5 if split_size < 12 else 7, "bold")
                        p_margin = 1 if split_size < 12 else 2
                        flare_offset = 1 if split_size < 12 else 3
                        ring_w = 1

                    undiscovered = {item for item in items if item not in visited}

                    for (r, c) in visited:
                        vx1 = c * split_size + 1
                        vy1 = r * split_size + 1
                        vx2 = (c + 1) * split_size - 1
                        vy2 = (r + 1) * split_size - 1
                        cx_cell = c * split_size + split_size // 2
                        cy_cell = r * split_size + split_size // 2

                        if (r, c) in collected:
                            cell_color = collected[(r, c)]
                            canvas.create_rectangle(
                                vx1, vy1, vx2, vy2,
                                fill=cell_color, outline=cell_color, width=1
                            )
                            canvas.create_rectangle(
                                vx1 + 1, vy1 + 1, vx2 - 1, vy2 - 1,
                                fill="#1a1a24", outline=""
                            )
                            canvas.create_text(
                                cx_cell, cy_cell,
                                text="🚩", fill=cell_color,
                                font=flag_font
                            )
                        else:
                            canvas.create_rectangle(
                                vx1, vy1, vx2, vy2,
                                fill=blend_color(p_color), outline=p_color, width=1
                            )
                            arrow_char = self.get_closest_item_arrow(r, c, undiscovered)
                            if arrow_char:
                                canvas.create_text(
                                    cx_cell, cy_cell,
                                    text=arrow_char, fill="#ffd24d",
                                    font=arrow_font
                                )

                    pr, pc = p_info["r"], p_info["c"]
                    px1 = pc * split_size + p_margin
                    py1 = pr * split_size + p_margin
                    px2 = (pc + 1) * split_size - p_margin
                    py2 = (pr + 1) * split_size - p_margin

                    canvas.create_oval(
                        px1 - 1, py1 - 1, px2 + 1, py2 + 1,
                        fill="", outline=p_color, width=ring_w
                    )
                    canvas.create_oval(
                        px1, py1, px2, py2,
                        fill=p_color, outline=""
                    )
                    canvas.create_oval(
                        px1 + flare_offset, py1 + flare_offset, px2 - flare_offset, py2 - flare_offset,
                        fill="#ffffff", outline=""
                    )

                    lbl_title.config(text="PLAYER " + str(p_id) + " (" + color_name + ")", fg=p_color)
                    moves = p_info.get("moves", 0)
                    items_found = len(collected)
                    lbl_stats.config(
                        text="Moves: " + str(moves) + " | Items: "
                        + str(items_found) + "/" + str(self.items_per_player)
                    )
            return

        self.canvas.delete("visited_element")
        self.canvas.delete("shared_item_element")
        self.canvas.delete("powerup_element")
        self.canvas.delete("player_element")
        self.canvas.delete("qte_element")

        # 1. Trails – per-player in multiplayer, shared set in solo
        if self.my_player_id == "solo":
            self._draw_player_cells(
                self.visited_cells, self.hidden_items,
                self.collected_item_cells, "#16293d", "#253e56",
                item_keys=getattr(self, 'solo_item_keys', {}),
                cell_arrows=getattr(self, 'solo_cell_arrows', {}),
                is_me=True
            )
        else:
            my_id = self.my_player_id
            p_data = self.per_player_data.get(my_id, {})
            if my_id in self.players:
                p_color = self.players[my_id]["color"]
                self._draw_player_cells(
                    p_data.get("visited", set()),
                    p_data.get("items", set()),
                    p_data.get("collected", {}),
                    blend_color(p_color), p_color,
                    item_keys=p_data.get("item_keys", {}),
                    cell_arrows=self.client_cell_arrows,
                    is_me=True
                )
            self._draw_shared_items()
            self._draw_map_powerups()

        # 2. Players
        for p_id, p in self.visible_map_players().items():
            r = p["r"]
            c = p["c"]
            color = p["color"]

            p_margin = 8
            px1 = c * CELL_SIZE + p_margin
            py1 = r * CELL_SIZE + p_margin
            px2 = (c + 1) * CELL_SIZE - p_margin
            py2 = (r + 1) * CELL_SIZE - p_margin

            # Glow
            self.canvas.create_oval(
                px1-3, py1-3, px2+3, py2+3, 
                fill="", outline=color, width=2, tags="player_element"
            )
            # Center fill
            self.canvas.create_oval(
                px1, py1, px2, py2, 
                fill=color, outline="", width=0, tags="player_element"
            )
            # Light flare
            self.canvas.create_oval(
                px1+10, py1+10, px2-10, py2-10,
                fill="#ffffff", outline="", tags="player_element"
            )

        # 3. QTE Overlay
        if self.qte_active:
            cx = CANVAS_WIDTH // 2
            cy = CANVAS_HEIGHT // 2
            
            width = 460
            height = 145
            x1 = cx - width // 2
            y1 = cy - height // 2
            x2 = cx + width // 2
            y2 = cy + height // 2
            
            self.canvas.create_rectangle(
                x1 - 4, y1 - 4, x2 + 4, y2 + 4,
                fill="", outline="#00d2ff", width=2, tags="qte_element"
            )
            self.canvas.create_rectangle(
                x1, y1, x2, y2,
                fill="#15151e", outline="#ffd24d", width=2, tags="qte_element"
            )
            
            self.canvas.create_text(
                cx, y1 + 25,
                text="GRID SECURITY LOCK - INPUT KEY SEQUENCE",
                fill="#ffd24d", font=("Segoe UI", 12, "bold"), tags="qte_element"
            )
            
            key_width = 45
            key_height = 45
            spacing = 15
            total_keys_width = 5 * key_width + 4 * spacing
            start_x = cx - total_keys_width // 2
            key_y = y1 + 55
            
            for i, dir_tuple in enumerate(self.qte_sequence):
                kx1 = start_x + i * (key_width + spacing)
                ky1 = key_y
                kx2 = kx1 + key_width
                ky2 = ky1 + key_height
                
                arrow_char = ""
                if dir_tuple == (-1, 0):
                    arrow_char = "↑"
                elif dir_tuple == (1, 0):
                    arrow_char = "↓"
                elif dir_tuple == (0, -1):
                    arrow_char = "←"
                elif dir_tuple == (0, 1):
                    arrow_char = "→"
                
                if i < self.qte_progress:
                    bg_color = "#00d2ff"
                    fg_color = "#121214"
                    border_color = "#00d2ff"
                elif i == self.qte_progress:
                    bg_color = "#2d2d37"
                    fg_color = "#ffd24d"
                    border_color = "#ffd24d"
                else:
                    bg_color = "#1a1a24"
                    fg_color = "#5f5f6e"
                    border_color = "#2d2d37"
                
                self.canvas.create_rectangle(
                    kx1, ky1, kx2, ky2,
                    fill=bg_color, outline=border_color, width=2, tags="qte_element"
                )
                self.canvas.create_text(
                    (kx1 + kx2) // 2, (ky1 + ky2) // 2,
                    text=arrow_char, fill=fg_color, font=("Segoe UI", 18, "bold"), tags="qte_element"
                )
            
            self.canvas.create_text(
                cx, y2 - 18,
                text="Press corresponding Arrow / WASD keys to unlock",
                fill="#8c8c9a", font=("Segoe UI", 9), tags="qte_element"
            )
            self.canvas.create_rectangle(
                x2 - 34, y1 + 8, x2 - 8, y1 + 34,
                fill="#2d2d37", outline="#ff4d4d", width=1,
                tags=("qte_element", "qte_cancel")
            )
            self.canvas.create_text(
                x2 - 21, y1 + 21, text="X", fill="#ff4d4d",
                font=("Segoe UI", 10, "bold"),
                tags=("qte_element", "qte_cancel")
            )
            self.canvas.tag_bind("qte_cancel", "<Button-1>", lambda e: self.cancel_qte())

    def cancel_qte(self):
        if not self.qte_active:
            return
        self.qte_active = False
        self.qte_sequence = []
        self.qte_progress = 0
        self.qte_target_move = (0, 0)
        play_sound("click")
        if hasattr(self, "canvas") and self.canvas.winfo_exists():
            self.draw_elements()

    def move_player(self, dr, dc):
        if not self.in_game:
            return

        current_time = time.time()

        if self.qte_active:
            if current_time - self.last_qte_key_time < 0.15:
                return
            self.last_qte_key_time = current_time
            expected_dr, expected_dc = self.qte_sequence[self.qte_progress]
            if (dr, dc) == (expected_dr, expected_dc):
                self.qte_progress += 1
                if self.qte_progress >= 5:
                    self.qte_active = False
                    play_sound("qte_success")
                    actual_dr, actual_dc = self.qte_target_move
                    self.execute_actual_move(actual_dr, actual_dc)
                else:
                    play_sound("qte_correct")
                    self.draw_elements()
            else:
                self.qte_progress = 0
                play_sound("qte_wrong")
                self.draw_elements()
            return

        if current_time - self.last_move_time < 0.25:
            return

        if self.is_client:
            if not self.in_active_game or not self.my_player_id:
                return
            # Finished players are locked — no more movement
            finished = getattr(self.client, "finished_players", []) if self.client else []
            if self.my_player_id in finished:
                return
            p_info = self.players.get(self.my_player_id)
            if not p_info:
                return
            r, c = p_info["r"], p_info["c"]
        elif self.my_player_id == "solo":
            # Solo: lock after all items collected
            if len(getattr(self, 'collected_item_cells', {})) >= self.items_per_player:
                return
            r, c = self.player_r, self.player_c
        else:
            return

        new_r = r + dr
        new_c = c + dc

        if not (0 <= new_r < GRID_ROWS and 0 <= new_c < GRID_COLS):
            return

        # --- Per-player visited check ---
        if self.is_client and self.client:
            my_visited = self.client.get_my_visited()
            needs_qte = (new_r, new_c) not in my_visited
        else:
            # Solo mode
            needs_qte = (new_r, new_c) not in self.visited_cells

        if needs_qte:
            self.qte_active = True
            self.qte_target_move = (dr, dc)
            self.qte_sequence = [random.choice([(-1, 0), (1, 0), (0, -1), (0, 1)]) for _ in range(5)]
            self.qte_progress = 0
            self.last_qte_key_time = current_time
            play_sound("click")
            self.draw_elements()
            return

        self.execute_actual_move(dr, dc)

    def execute_actual_move(self, dr, dc):
        current_time = time.time()
        self.last_move_time = current_time
        
        if self.is_client:
            self.moves += 1
            self.lbl_moves.config(text=f"MOVES: {self.moves}")
            if self.client:
                self.client.send_move(dr, dc)
        elif self.my_player_id == "solo":
            new_r = self.player_r + dr
            new_c = self.player_c + dc
            self.player_r = new_r
            self.player_c = new_c
            self.moves += 1
            self.players["solo"]["r"] = new_r
            self.players["solo"]["c"] = new_c

            cell = (new_r, new_c)
            # Detect if solo player finds their hidden item for the first time
            item_found = False
            if cell in self.hidden_items and cell not in self.visited_cells:
                item_found = True

            self.visited_cells.add(cell)

            # Auto-collect powerup if solo player steps on one
            map_powerups = getattr(self, 'solo_map_powerups', {})
            if cell in map_powerups:
                pu_id = map_powerups.pop(cell)
                slots = getattr(self, 'solo_powerups', [None, None, None])
                slots[0] = pu_id
                play_sound("collect")
                self.update_powerup_bar()
            elif item_found:
                play_sound("item_found")
            else:
                play_sound("move")

            # Freeze arrow direction at moment of first visit
            if cell not in self.solo_cell_arrows and cell not in self.collected_item_cells:
                undiscovered = {item for item in self.hidden_items if item not in self.visited_cells}
                self.solo_cell_arrows[cell] = self.get_closest_item_arrow(new_r, new_c, undiscovered)

            self.lbl_moves.config(text=f"MOVES: {self.moves}")
            self.lbl_pos.config(text=f"POSITION: ({self.player_c}, {self.player_r})")
            self.draw_elements()

    def reset_game(self):
        if not self.in_game:
            return
        if self.my_player_id == "solo":
            self.player_r = random.randint(0, GRID_ROWS - 1)
            self.player_c = random.randint(0, GRID_COLS - 1)
            self.moves = 0
            self.players["solo"]["r"] = self.player_r
            self.players["solo"]["c"] = self.player_c
            self.visited_cells = {(self.player_r, self.player_c)}
            
            self.qte_active = False
            self.qte_sequence = []
            self.qte_progress = 0
            self.qte_target_move = (0, 0)
            self.solo_item_keys = {}
            self.solo_cell_arrows = {}
            self.spawn_solo_hidden_items()
            self.collected_item_cells = {}

            # Reset solo powerups
            self.solo_powerups = [None, None, None]
            self.selected_powerup_slot = None
            self.solo_map_powerups = self._spawn_solo_powerups()
            self.update_powerup_bar()
            self.start_solo_spawner_timer()

            self.lbl_moves.config(text="MOVES: 0")
            self.lbl_pos.config(text=f"POSITION: ({self.player_c}, {self.player_r})")

            collected = self.items_per_player - len(self.hidden_items)
            if hasattr(self, 'lbl_items'):
                self.lbl_items.config(text=f"ITEMS: {collected}/{self.items_per_player}")

            # Restart hard-mode cell-close timer
            self.solo_cell_close_active = False
            if self.difficulty == "hard":
                self._start_solo_cell_close_timer()

            play_sound("reset")
            self.draw_elements()

    def spawn_solo_hidden_items(self):
        self.hidden_items.clear()
        if not hasattr(self, 'solo_item_keys'):
            self.solo_item_keys = {}
        self.solo_item_keys.clear()
        while len(self.hidden_items) < self.items_per_player:
            r = random.randint(0, GRID_ROWS - 1)
            c = random.randint(0, GRID_COLS - 1)
            if (r, c) != (self.player_r, self.player_c):
                self.hidden_items.add((r, c))
                self.solo_item_keys[(r, c)] = make_caesar_clue(self.difficulty)

    def _start_solo_cell_close_timer(self):
        """Hard mode: every 30 s re-close 2-5 visited cells in solo."""
        import threading
        self.solo_cell_close_active = True
        def _tick():
            if not self.in_game or self.my_player_id != "solo" or not self.solo_cell_close_active:
                return
            self._solo_close_random_cells()
            threading.Timer(30.0, _tick).start()
        threading.Timer(30.0, _tick).start()

    def _solo_close_random_cells(self):
        player_pos    = (self.player_r, self.player_c)
        collected_pos = set(self.collected_item_cells.keys())
        eligible = list(self.visited_cells - {player_pos} - self.hidden_items - collected_pos)
        if len(eligible) < 2:
            return
        count = random.randint(2, min(5, len(eligible)))
        for cell in random.sample(eligible, count):
            self.visited_cells.discard(cell)
        play_sound("reset")
        self.root.after(0, self.draw_elements)

    def open_lock_dialog_solo(self):
        """Open the 3-keyhole vault screen for solo mode."""
        item_keys   = getattr(self, 'solo_item_keys', {})
        visited     = self.visited_cells
        remaining   = self.hidden_items
        collected   = self.collected_item_cells   # (r,c) -> color

        # Build full sorted list of all items (3 or 4 depending on difficulty)
        player_pos = (self.player_r, self.player_c)
        all_positions = sorted(list(remaining) + list(collected.keys()))

        items_data = []
        for i, pos in enumerate(all_positions[:self.items_per_player]):
            items_data.append({
                "index":      i + 1,
                "pos":        pos,
                "key":        item_keys.get(pos),
                "collected":  pos in collected,
                "discovered": pos in visited,
                "is_at":      pos == player_pos,
            })

        def on_submit(pos, entered_key):
            # Enforce standing-on rule in solo too
            if (self.player_r, self.player_c) != pos:
                return False
            stored_key = item_keys.get(pos)
            correct_word = ""
            if stored_key and "|" in stored_key:
                correct_word = stored_key.split("|")[0]
            else:
                correct_word = str(stored_key)

            if str(entered_key).strip().upper() == correct_word.upper():
                self.hidden_items.discard(pos)
                if pos in self.solo_item_keys:
                    del self.solo_item_keys[pos]
                self.collected_item_cells[pos] = self.players["solo"]["color"]
                play_sound("collect")
                count = self.items_per_player - len(self.hidden_items)
                if hasattr(self, 'lbl_items'):
                    self.lbl_items.config(text=f"ITEMS: {count}/{self.items_per_player}")
                self.draw_elements()
                return True
            else:
                play_sound("qte_wrong")
                return False

        LockScreenDialog(self.root, self.button_font, items_data, on_submit).show()



    def _spawn_solo_powerups(self):
        """Place 2 Reveal powerups randomly on the grid for solo play."""
        powerups_map = {}
        all_occupied = {(self.player_r, self.player_c)} | getattr(self, 'hidden_items', set())

        for _ in range(2):
            attempts = 0
            while attempts < 1000:
                r = random.randint(0, GRID_ROWS - 1)
                c = random.randint(0, GRID_COLS - 1)
                if (r, c) not in all_occupied and (r, c) not in powerups_map:
                    powerups_map[(r, c)] = "reveal"
                    all_occupied.add((r, c))
                    break
        return powerups_map

    def start_solo_spawner_timer(self):
        # Cancel any existing timer if any
        if hasattr(self, "_solo_spawner_after_id") and self._solo_spawner_after_id:
            try:
                self.root.after_cancel(self._solo_spawner_after_id)
            except Exception:
                pass
        
        def tick():
            if not self.in_game or self.my_player_id != "solo":
                return
            
            # Solo: spawn 1 Reveal powerup anywhere on the grid
            map_powerups = getattr(self, 'solo_map_powerups', {})
            attempts = 0
            while attempts < 1000:
                attempts += 1
                r = random.randint(0, GRID_ROWS - 1)
                c = random.randint(0, GRID_COLS - 1)
                if (r, c) not in map_powerups:
                    map_powerups[(r, c)] = "reveal"
                    break
            
            self.draw_elements()
            # Schedule next spawn in 60 seconds
            self._solo_spawner_after_id = self.root.after(60000, tick)

        self._solo_spawner_after_id = self.root.after(60000, tick)

    def get_closest_item_arrow(self, pr, pc, items=None):
        if items is None:
            items = self.hidden_items
        if not items:
            return ""
        closest_item = min(items, key=lambda item: (item[0] - pr)**2 + (item[1] - pc)**2)
        ir, ic = closest_item
        dr = ir - pr
        dc = ic - pc
        if dr == 0 and dc == 0:
            return ""
        # 4-directional mapping based on dominant coordinate offset
        if abs(dr) >= abs(dc):
            return "\u2191" if dr < 0 else "\u2193"
        else:
            return "\u2190" if dc < 0 else "\u2192"

    def _draw_shared_items(self):
        """Draw every remaining item without exposing another player's vault clue."""
        my_data = self.per_player_data.get(self.my_player_id, {})
        my_visited = my_data.get("visited", set())
        for owner_id, data in self.per_player_data.items():
            color = self.players.get(owner_id, {}).get("color", "#888888")
            for r, c in data.get("items", set()):
                if (r, c) not in my_visited:
                    continue
                if owner_id == self.my_player_id and (r, c) in my_visited:
                    continue
                margin = 13
                x1 = c * CELL_SIZE + margin
                y1 = r * CELL_SIZE + margin
                x2 = (c + 1) * CELL_SIZE - margin
                y2 = (r + 1) * CELL_SIZE - margin
                self.canvas.create_rectangle(
                    x1, y1, x2, y2, fill="#1a1a24", outline=color,
                    width=3, tags="shared_item_element"
                )
                self.canvas.create_text(
                    (x1 + x2) // 2, (y1 + y2) // 2,
                    text=f"P{owner_id}", fill=color,
                    font=("Segoe UI", 9, "bold"), tags="shared_item_element"
                )

    def _draw_map_powerups(self):
        """Draw all uncollected multiplayer powerups as shared map objects."""
        if not self.client:
            return
        my_visited = self.client.get_my_visited()
        for (r, c), powerup_id in self.client.map_powerups.items():
            if (r, c) not in my_visited:
                continue
            meta = POWERUP_META.get(powerup_id, {})
            cx = c * CELL_SIZE + CELL_SIZE // 2
            cy = r * CELL_SIZE + CELL_SIZE // 2
            color = meta.get("color", "#ffffff")
            self.canvas.create_oval(
                cx - 13, cy - 13, cx + 13, cy + 13,
                fill="#1a1a24", outline=color, width=3,
                tags="powerup_element"
            )
            self.canvas.create_text(
                cx, cy, text=str({"reveal": 1, "shield": 2, "speed": 3}.get(powerup_id, "?")),
                fill=color, font=("Segoe UI", 10, "bold"), tags="powerup_element"
            )

    def _draw_player_cells(self, visited, items, collected, trail_fill, trail_outline,
                            item_keys=None, cell_arrows=None, is_me=False):
        """Render one player's visited cells. Arrows are frozen from time-of-visit."""
        if item_keys is None:
            item_keys = {}
        if cell_arrows is None:
            cell_arrows = {}
        for (r, c) in visited:
            vx1 = c * CELL_SIZE + 2
            vy1 = r * CELL_SIZE + 2
            vx2 = (c + 1) * CELL_SIZE - 2
            vy2 = (r + 1) * CELL_SIZE - 2
            cx_cell = c * CELL_SIZE + CELL_SIZE // 2
            cy_cell = r * CELL_SIZE + CELL_SIZE // 2

            if (r, c) in collected:
                # Collected item cell — show flag only (no arrow)
                cell_color = collected[(r, c)]
                self.canvas.create_rectangle(
                    vx1, vy1, vx2, vy2,
                    fill=cell_color, outline=cell_color, width=2, tags="visited_element"
                )
                self.canvas.create_rectangle(
                    vx1 + 2, vy1 + 2, vx2 - 2, vy2 - 2,
                    fill="#1a1a24", outline="", tags="visited_element"
                )
                self.canvas.create_text(
                    cx_cell, cy_cell,
                    text="\U0001f6a9", fill=cell_color,
                    font=("Segoe UI", 14, "bold"), tags="visited_element"
                )
            elif (r, c) in items:
                if is_me:
                    # Remaining item tile for ME — show lock icon
                    key = item_keys.get((r, c))
                    self.canvas.create_rectangle(
                        vx1, vy1, vx2, vy2,
                        fill="#1a1a1f", outline="#ffd24d", width=2, tags="visited_element"
                    )
                    if key:
                        self.canvas.create_text(
                            cx_cell, cy_cell - 14,
                            text="\U0001f513", fill="#ffd24d",
                            font=("Segoe UI", 12), tags="visited_element"
                        )
                        if "|" in key:
                            parts = key.split("|", 2)
                            if len(parts) == 3:
                                orig_w, cipher_w, shift_str = parts
                                shift = int(shift_str)
                                sign = "-" if shift > 0 else "+"
                                formula = f"C{sign}{abs(shift)}"
                                self.canvas.create_text(
                                    cx_cell, cy_cell + 4,
                                    text=cipher_w, fill="#ffd24d",
                                    font=("Segoe UI", 8, "bold"), tags="visited_element"
                                )
                                self.canvas.create_text(
                                    cx_cell, cy_cell + 16,
                                    text=formula, fill="#00d2ff",
                                    font=("Segoe UI", 7, "bold"), tags="visited_element"
                                )
                            else:
                                self.canvas.create_text(
                                    cx_cell, cy_cell + 10,
                                    text=key, fill="#ffd24d",
                                    font=("Segoe UI", 9, "bold"), tags="visited_element"
                                )
                        else:
                            self.canvas.create_text(
                                cx_cell, cy_cell + 10,
                                text=key, fill="#ffd24d",
                                font=("Segoe UI", 9, "bold"), tags="visited_element"
                            )
                    else:
                        self.canvas.create_text(
                            cx_cell, cy_cell,
                            text="\U0001f512", fill="#ffd24d",
                            font=("Segoe UI", 14), tags="visited_element"
                        )
                else:
                    # For other players: change the color of the grid cell to that team's color (no lock icon)
                    self.canvas.create_rectangle(
                        vx1, vy1, vx2, vy2,
                        fill=trail_fill, outline=trail_outline, width=2, tags="visited_element"
                    )
            else:
                # Regular trail cell — use frozen arrow (pointing to nearest unfound item at visit time)
                self.canvas.create_rectangle(
                    vx1, vy1, vx2, vy2,
                    fill=trail_fill, outline=trail_outline, width=1, tags="visited_element"
                )
                arrow_char = cell_arrows.get((r, c), "")
                if not arrow_char:
                    # Fallback: compute live (e.g. first visit before cache is ready)
                    arrow_char = self.get_closest_item_arrow(r, c, items)
                if arrow_char:
                    self.canvas.create_text(
                        cx_cell, cy_cell,
                        text=arrow_char, fill="#ffd24d",
                        font=("Segoe UI", 18, "bold"), tags="visited_element"
                    )

