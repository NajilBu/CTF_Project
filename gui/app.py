import tkinter as tk
from tkinter import font, messagebox
import os
import random
import sys
import time
from config import (
    WINDOW_WIDTH, WINDOW_HEIGHT, GRID_ROWS, GRID_COLS, CELL_SIZE,
    CANVAS_WIDTH, CANVAS_HEIGHT, COLORS, COLOR_NAMES, play_sound
)
from network import GridServer, GridClient
from gui.dialogs import (CustomDifficultyDialog, CustomIPDialog, CustomLockDialog,
                         CustomPlayerCountDialog, LockScreenDialog, PlayerProfileDialog,
                         TeleportDialog)

# Powerup display metadata (mirrors POWERUPS list in server.py)
POWERUP_META = {
    "speed":  {
        "label": "Teleport", "icon": "\u26a1", "color": "#ffd24d",
        "description": "Teleport any player to a random grid they have not discovered.",
    },
    "shield": {
        "label": "Move Item", "icon": "\U0001f6e1", "color": "#00d2ff",
        "description": "Move one of an opponent's discovered items to a new hidden grid.",
    },
    "reveal": {
        "label": "Reveal", "icon": "\U0001f50d", "color": "#ff9f1a",
        "description": "Reveal one of your undiscovered vault items instantly.",
    },
}

GAME_MODE_SOLO = "solo"
GAME_MODE_DUO = "duo"
ROLE_SOLO = "solo"
ROLE_NEUTRAL = "neutral"
ROLE_DECRYPT = "decrypt"
ROLE_POWERUPS = "powerups"
ROLE_LABELS = {
    ROLE_SOLO: "SOLO",
    ROLE_NEUTRAL: "NEUTRAL",
    ROLE_DECRYPT: "DECRYTOR",
    ROLE_POWERUPS: "SABOTAGEE",
}
DUO_TEAM_COLORS = ("#00d2ff", "#ff4d4d", "#ffd24d")
DUO_NEUTRAL_COLOR = "#8c8c9a"

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
        self.set_window_icon()
        self.root.configure(bg="#121214")
        self.root.resizable(True, True)
        self.root.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}+0+0")
        try:
            self.root.state("zoomed")   # Maximized on Windows
        except Exception:
            self.root.attributes("-fullscreen", True)
        self.root.protocol("WM_DELETE_WINDOW", self.close_app)


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
        self.viewing_postgame_lobby = False
        self.blocked_from_joining = False

        # Network Game States
        self.is_host = False
        self.is_client = False
        self.my_player_id = None
        self.game_started = False
        self.in_active_game = False
        
        self.server = None
        self.client = None
        self.players = {}
        # Difficulty
        self.difficulty       = "easy"
        self.game_mode        = GAME_MODE_SOLO
        self.team_colors      = {}
        self.items_per_player = 3
        self.preferred_name = "Player"
        self.preferred_color = COLORS[0]
        self.profile_customized = False

        # Fonts
        self.title_font = font.Font(family="Segoe UI", size=32, weight="bold")
        self.subtitle_font = font.Font(family="Segoe UI", size=12)
        self.score_font = font.Font(family="Segoe UI", size=12, weight="bold")
        self.button_font = font.Font(family="Segoe UI", size=11, weight="bold")
        self.hint_font = font.Font(family="Segoe UI", size=10)

        # UI view structures
        self.current_frame = None
        self.slot_status_labels = []
        self.slot_title_labels = []
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

    def asset_path(self, filename):
        base_path = getattr(
            sys,
            "_MEIPASS",
            os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        )
        return os.path.join(base_path, "assets", filename)

    def set_window_icon(self):
        try:
            ico_path = self.asset_path("grid_explorer_icon.ico")
            if os.path.exists(ico_path):
                self.root.iconbitmap(ico_path)
        except Exception:
            pass
        try:
            png_path = self.asset_path("grid_explorer_icon.png")
            if os.path.exists(png_path):
                self.window_icon = tk.PhotoImage(file=png_path)
                self.root.iconphoto(True, self.window_icon)
        except Exception:
            pass

    def clear_screen(self):
        self.hide_powerup_tooltip()
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

    def close_app(self):
        self.cleanup_network()
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def show_title_screen(self):
        self.in_game = False
        self.is_host = False
        self.is_client = False
        self.game_started = False
        self.in_active_game = False
        self.game_mode = GAME_MODE_SOLO
        self.team_colors = {}
        self.my_player_id = None
        self.qte_active = False
        self.qte_sequence = []
        self.qte_progress = 0
        self.qte_target_move = (0, 0)
        self.last_known_server_pos = None
        self.per_player_data = {}
        self.showing_finish_screen = False
        self.finish_screen_match_complete = False
        self.viewing_postgame_lobby = False
        self.blocked_from_joining = getattr(self, "blocked_from_joining", False)
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
            backdrop.create_text(38, h-35, text="CTF GRID NETWORK  \u2022  PORT 5555  \u2022  ENCRYPTED",
                                 fill="#385064", anchor="w", font=("Consolas", 9), tags="menu_art")
        backdrop.bind("<Configure>", draw_backdrop)

        shell = tk.Frame(self.current_frame, bg="#0d141e", highlightthickness=1,
                         highlightbackground="#1b4055")
        shell.place(relx=.5, rely=.49, anchor="center", width=760, height=710)
        tk.Frame(shell, bg="#00d2ff", height=4).pack(fill="x")
        tk.Label(shell, text="\u25c6  CTF OPERATIONS CONSOLE  /  NODE 01", fg="#5f8197",
                 bg="#0d141e", font=("Consolas", 9, "bold"), anchor="w").pack(
                     fill="x", padx=38, pady=(24, 8))
        tk.Label(shell, text="GRID EXPLORER", fg="#eafaff", bg="#0d141e",
                 font=("Segoe UI", 38, "bold")).pack()
        tk.Label(shell, text="CAPTURE  \u2022  DECRYPT  \u2022  DOMINATE", fg="#ffd24d", bg="#0d141e",
                 font=("Consolas", 12, "bold")).pack(pady=(2, 10))
        tk.Label(shell, text="Navigate the encrypted grid, recover hidden flags,\nand outmaneuver rival operators.",
                 fg="#8fa6b6", bg="#0d141e", justify="center",
                 font=self.subtitle_font).pack(pady=(0, 20))

        status = tk.Frame(shell, bg="#111d29", highlightthickness=1, highlightbackground="#1e3344")
        status.pack(fill="x", padx=38, pady=(0, 18))
        for label, color in (("\u25cf NETWORK READY", "#55ff55"), ("\u2691 FLAGS ARMED", "#ffd24d"),
                             ("\u25c7 GRID 20 \u00d7 10", "#00d2ff")):
            tk.Label(status, text=label, fg=color, bg="#111d29",
                     font=("Consolas", 9, "bold")).pack(side="left", expand=True, pady=10)

        btn_container = tk.Frame(shell, bg="#0d141e")
        btn_container.pack(fill="x", padx=72)

        def add_hover(button, normal, hover):
            button.bind("<Enter>", lambda e: button.config(bg=hover))
            button.bind("<Leave>", lambda e: button.config(bg=normal))

        # Host
        btn_host = tk.Button(
            btn_container,
            text="01   HOST OPERATIONS ROOM                            \u203a",
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
        join_locked = getattr(self, "blocked_from_joining", False)
        btn_join = tk.Button(
            btn_container,
            text="02   JOIN LOCKED - OPERATOR ELIMINATED" if join_locked else "02   JOIN STRIKE TEAM                                     \u203a",
            command=self.join_game_action,
            bg="#212128" if join_locked else "#313143",
            fg="#5f5f6e" if join_locked else "#ffffff",
            activebackground="#ffd24d",
            activeforeground="#121214",
            font=self.button_font,
            bd=0,
            anchor="w",
            pady=12,
            cursor="arrow" if join_locked else "hand2",
            state="disabled" if join_locked else "normal"
        )
        btn_join.pack(fill="x", pady=6)
        if not join_locked:
            add_hover(btn_join, "#313143", "#42425b")

        btn_profile = tk.Button(
            btn_container,
            text="\u270e   EDIT OPERATOR PROFILE",
            command=self.edit_title_profile,
            bg="#1b2836", fg="#ffd24d", activebackground="#32485e",
            activeforeground="#ffffff", font=self.button_font, bd=0,
            anchor="w", pady=12, cursor="hand2"
        )
        btn_profile.pack(fill="x", pady=6)
        add_hover(btn_profile, "#1b2836", "#32485e")

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
        setup = CustomPlayerCountDialog(self.root, self.button_font).show()
        if not setup:
            return
        max_p, selected_mode = setup
        self.max_players = max_p
        self.game_mode = selected_mode
        self.team_colors = {}
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
        self.build_lobby_chat_ui()

        # Init Server Model
        self.server = GridServer(
            port=5555,
            max_players=self.max_players,
            on_lobby_update=lambda: self.root.after(0, self.update_lobby_ui),
            on_game_update=lambda: self.root.after(0, self.on_server_game_update)
        )
        self.server.game_mode = self.game_mode
        self.server.assign_duo_roles()
        if not self.server.start():
            self.lbl_ips.config(text="Server Port bind failed! Ensure port 5555 is free.", fg="#ff4d4d")
            return
        
        self.lbl_ips.config(text="Listening on port 5555. Share your Radmin VPN IP address with players!")

    def current_game_mode(self):
        fallback = getattr(self, "game_mode", GAME_MODE_SOLO)
        if getattr(self, "is_host", False) and getattr(self, "server", None):
            return getattr(self.server, "game_mode", fallback)
        if getattr(self, "is_client", False) and getattr(self, "client", None):
            return getattr(self.client, "game_mode", fallback)
        return fallback

    def duo_team_count(self):
        return max(1, (getattr(self, "max_players", 6) + 1) // 2)

    def join_duo_team(self, team_id, role=None):
        if self.is_client and self.client:
            self.client_is_ready = False
            if hasattr(self, "btn_ready"):
                self.btn_ready.config(text="READY", bg="#55ff55", fg="#121214")
            self.client.send_team(team_id, role)

    def neutral_duo_action(self):
        if not self.is_client or not self.my_player_id:
            return
        mine = self.players.get(self.my_player_id, {})
        if mine.get("team") is None:
            self.edit_profile_action()
        else:
            self.join_duo_team(0)

    def build_lobby_slots_ui(self):
        if hasattr(self, 'lobby_body_frame') and self.lobby_body_frame:
            try:
                self.lobby_body_frame.destroy()
            except Exception:
                pass
        self.lobby_body_frame = tk.Frame(self.current_frame, bg="#121214")
        self.lobby_body_frame.pack(fill="both", expand=True, padx=20, pady=12)
        self.lobby_container = tk.Frame(self.lobby_body_frame, bg="#121214")
        self.lobby_container.pack(side="left", fill="both", expand=True)
        self.lobby_layout_mode = self.current_game_mode()

        self.team_status_labels = {}
        self.team_join_buttons = {}
        self.team_title_labels = {}
        self.team_role_title_labels = {}
        self.team_color_swatches = {}
        self.team_color_value_labels = {}
        self.neutral_click_widgets = []
        if self.lobby_layout_mode == GAME_MODE_DUO:
            self.build_duo_team_picker_ui()
            self.slot_status_labels = []
            self.slot_title_labels = []
            return

        self.lobby_slots_grid = tk.Frame(self.lobby_container, bg="#121214")
        self.lobby_slots_grid.pack(fill="both", expand=True)

        self.slot_status_labels = []
        self.slot_title_labels = []
        max_p = getattr(self, "max_players", 6)

        for i in range(1, max_p + 1):
            row = (i - 1) // 2
            col = (i - 1) % 2
            
            card = tk.Frame(
                self.lobby_slots_grid,
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
            self.slot_title_labels.append(lbl_title)

            lbl_status = tk.Label(
                card,
                text="Waiting for player...",
                fg="#5f5f6e",
                bg="#1a1a24",
                font=self.hint_font
            )
            lbl_status.pack(anchor="w", padx=20)
            self.slot_status_labels.append(lbl_status)

    def build_duo_team_picker_ui(self):
        team_panel = tk.Frame(self.lobby_container, bg="#121214")
        team_panel.pack(fill="x", padx=4, pady=(0, 12))

        tk.Label(
            team_panel,
            text="DUO TEAMS - pick a team before readying up",
            fg="#ffd24d",
            bg="#121214",
            font=("Segoe UI", 10, "bold")
        ).pack(anchor="w", padx=4, pady=(0, 6))

        row = tk.Frame(team_panel, bg="#121214")
        row.pack(fill="x")

        for team_id in range(1, self.duo_team_count() + 1):
            color = self.duo_team_color(team_id)
            card = tk.Frame(row, bg="#1a1a24", bd=1, relief="solid", width=310, height=190)
            card.pack(side="left", padx=8)
            card.pack_propagate(False)

            team_header = tk.Frame(card, bg="#1a1a24")
            team_header.pack(fill="x", padx=10, pady=(8, 2))
            team_title = tk.Label(team_header, text=self.duo_team_name(team_id).upper(), fg=color, bg="#1a1a24",
                                  font=("Segoe UI", 11, "bold"))
            team_title.pack(side="left")
            self.team_title_labels[team_id] = team_title
            swatch = tk.Label(
                team_header, text=" ", bg=color, width=2,
                highlightthickness=1, highlightbackground="#d7d7df"
            )
            swatch.pack(side="right", padx=(6, 0))
            self.team_color_swatches[team_id] = swatch
            color_value = tk.Label(
                team_header, text=color.upper(), fg=color, bg="#1a1a24",
                font=("Segoe UI", 8, "bold")
            )
            color_value.pack(side="right")
            self.team_color_value_labels[team_id] = color_value

            role_row = tk.Frame(card, bg="#1a1a24")
            role_row.pack(fill="both", expand=True, padx=10, pady=(8, 12))
            for role, label_text in ((ROLE_DECRYPT, "DECRYTOR"), (ROLE_POWERUPS, "SABOTAGEE")):
                role_box = tk.Frame(
                    role_row, bg="#212128", bd=1, relief="solid",
                    highlightthickness=1, highlightbackground="#313143",
                    width=136, height=128,
                )
                role_box.pack(side="left", fill="both", expand=True, padx=5)
                role_box.pack_propagate(False)

                title = tk.Label(
                    role_box, text=label_text, fg=color, bg="#212128",
                    font=("Segoe UI", 9, "bold")
                )
                title.pack(anchor="w", padx=10, pady=(8, 3))
                self.team_role_title_labels[(team_id, role)] = title
                occupant = tk.Label(
                    role_box, text="open", fg="#d7d7df", bg="#212128",
                    font=("Segoe UI", 9), anchor="w", justify="left",
                    wraplength=118,
                )
                occupant.pack(anchor="w", padx=10)
                self.team_status_labels[(team_id, role)] = occupant

                if self.is_client:
                    btn = tk.Button(
                        role_box, text="SELECT",
                        command=lambda team=team_id, selected_role=role: self.join_duo_team(team, selected_role),
                        bg="#313143", fg="#ffffff", activebackground=color,
                        activeforeground="#121214", bd=0, font=("Segoe UI", 8, "bold"),
                        cursor="hand2",
                    )
                    btn.pack(anchor="e", padx=10, pady=(10, 0))
                    for widget in (role_box, title, occupant):
                        widget.bind(
                            "<Button-1>",
                            lambda e, team=team_id, selected_role=role: self.join_duo_team(team, selected_role)
                        )
                    self.team_join_buttons[(team_id, role)] = btn

        neutral_panel = tk.Frame(
            self.lobby_container, bg="#1a1a24", bd=1, relief="solid",
            highlightbackground="#2d2d37", highlightthickness=1,
        )
        neutral_panel.pack(fill="both", expand=True, padx=8, pady=(2, 0))
        if self.is_client:
            neutral_panel.config(cursor="hand2")
            neutral_panel.bind("<Button-1>", lambda e: self.neutral_duo_action())
            self.neutral_click_widgets.append(neutral_panel)

        neutral_header = tk.Frame(neutral_panel, bg="#15151e")
        neutral_header.pack(fill="x")
        if self.is_client:
            neutral_header.config(cursor="hand2")
            neutral_header.bind("<Button-1>", lambda e: self.neutral_duo_action())
            self.neutral_click_widgets.append(neutral_header)
        neutral_title = tk.Label(
            neutral_header,
            text="NEUTRAL PLAYERS",
            fg="#8c8c9a",
            bg="#15151e",
            font=("Segoe UI", 10, "bold")
        )
        neutral_title.pack(side="left", padx=12, pady=8)
        if self.is_client:
            neutral_title.config(cursor="hand2")
            neutral_title.bind("<Button-1>", lambda e: self.neutral_duo_action())
            self.neutral_click_widgets.append(neutral_title)
        if self.is_client:
            btn = tk.Button(
                neutral_header, text="MOVE TO NEUTRAL", command=self.neutral_duo_action,
                bg="#313143", fg="#ffffff", activebackground="#42425b",
                activeforeground="#ffffff", bd=0, font=("Segoe UI", 8, "bold"),
                cursor="hand2", padx=12, pady=4
            )
            btn.pack(side="right", padx=12, pady=6)
            self.team_join_buttons[0] = btn

        self.team_status_labels[0] = tk.Label(
            neutral_panel,
            text="Players who have not picked a team yet will appear here.",
            fg="#d7d7df",
            bg="#1a1a24",
            font=("Segoe UI", 9),
            justify="left",
            anchor="nw",
            wraplength=720,
        )
        self.team_status_labels[0].pack(fill="both", expand=True, padx=14, pady=12)
        if self.is_client:
            self.team_status_labels[0].config(cursor="hand2")
            self.team_status_labels[0].bind("<Button-1>", lambda e: self.neutral_duo_action())
            self.neutral_click_widgets.append(self.team_status_labels[0])

    def build_lobby_chat_ui(self):
        if hasattr(self, "chat_frame") and self.chat_frame:
            try:
                self.chat_frame.destroy()
            except Exception:
                pass
        parent = self.lobby_body_frame if hasattr(self, "lobby_body_frame") else self.current_frame
        self.chat_frame = tk.Frame(parent, bg="#1a1a24", bd=1, relief="solid", width=390)
        self.chat_frame.pack(side="right", fill="y", padx=(12, 0), pady=4)
        self.chat_frame.pack_propagate(False)
        tk.Label(self.chat_frame, text="LOBBY CHAT", fg="#ffd24d", bg="#1a1a24",
                 font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=12, pady=(8, 3))
        self.chat_text = tk.Text(
            self.chat_frame, height=6, bg="#121214", fg="#ffffff",
            bd=0, wrap="word", state="disabled", font=("Segoe UI", 9)
        )
        self.chat_text.pack(fill="both", expand=True, padx=12, pady=4)
        entry_row = tk.Frame(self.chat_frame, bg="#1a1a24")
        entry_row.pack(fill="x", padx=12, pady=(2, 10))
        self.chat_entry = tk.Entry(
            entry_row, bg="#212128", fg="#ffffff", insertbackground="#ffffff",
            bd=0, font=("Segoe UI", 10)
        )
        self.chat_entry.pack(side="left", fill="x", expand=True, ipady=7)
        self.chat_entry.bind("<Return>", lambda e: self.send_lobby_chat())
        tk.Button(
            entry_row, text="SEND", command=self.send_lobby_chat,
            bg="#00d2ff", fg="#121214", activebackground="#00a3cc",
            activeforeground="#121214", bd=0, padx=18, pady=7,
            font=self.button_font, cursor="hand2"
        ).pack(side="right", padx=(8, 0))
        self.update_chat_ui()

    def current_chat_history(self):
        if self.is_host and self.server:
            return self.server.chat_history
        if self.is_client and self.client:
            return self.client.chat_history
        return []

    def update_chat_ui(self):
        if not hasattr(self, "chat_text") or not self.chat_text.winfo_exists():
            return
        self.chat_text.config(state="normal")
        self.chat_text.delete("1.0", tk.END)
        for index, message in enumerate(self.current_chat_history()):
            tag = f"chat_{index}"
            self.chat_text.tag_config(tag, foreground=message.get("color", "#ffffff"))
            prefix = "" if message.get("kind") == "system" else f"{message.get('name', 'Player')}: "
            self.chat_text.insert(tk.END, prefix + message.get("text", "") + "\n", tag)
        self.chat_text.config(state="disabled")
        self.chat_text.see(tk.END)

    def send_lobby_chat(self):
        if not hasattr(self, "chat_entry"):
            return
        text = self.chat_entry.get().strip()
        if not text:
            return
        self.chat_entry.delete(0, tk.END)
        if self.is_host and self.server:
            self.server.send_host_chat(text)
        elif self.is_client and self.client:
            self.client.send_chat(text)

    def build_ingame_chat_ui(self):
        """Create the transient in-game chat notification stack."""
        self.ingame_chat_notifications = []
        self.ingame_chat_snapshot = list(self.current_chat_history())

        self.chat_notification_frame = tk.Frame(self.current_frame, bg="#121214")
        self.chat_notification_frame.place(relx=1.0, rely=1.0, x=-20, y=-20, anchor="se")

    def update_ingame_chat(self):
        """Show notifications for messages added since the last state update."""
        if not self.in_active_game or not hasattr(self, "chat_notification_frame"):
            return
        history = list(self.current_chat_history())
        previous = getattr(self, "ingame_chat_snapshot", [])
        overlap = min(len(previous), len(history))
        while overlap and previous[-overlap:] != history[:overlap]:
            overlap -= 1
        for message in history[overlap:]:
            self.show_chat_notification(message)
        self.ingame_chat_snapshot = history

    def show_chat_notification(self, message):
        if len(self.ingame_chat_notifications) >= 7:
            self.remove_chat_notification(self.ingame_chat_notifications[0])
        card = tk.Frame(
            self.chat_notification_frame, bg="#1a1a24", bd=1, relief="solid",
            highlightthickness=1, highlightbackground=message.get("color", "#8c8c9a"),
        )
        card.pack(side="bottom", anchor="e", pady=3)
        prefix = "" if message.get("kind") == "system" else f"{message.get('name', 'Player')}: "
        tk.Label(
            card, text=prefix + message.get("text", ""),
            fg=message.get("color", "#ffffff"), bg="#1a1a24",
            font=("Segoe UI", 9), wraplength=330, justify="left",
            padx=12, pady=8,
        ).pack()
        self.ingame_chat_notifications.append(card)
        card._expiry_id = self.root.after(5000, lambda item=card: self.remove_chat_notification(item))

    def remove_chat_notification(self, card):
        if card in getattr(self, "ingame_chat_notifications", []):
            self.ingame_chat_notifications.remove(card)
        try:
            card.destroy()
        except Exception:
            pass

    def role_label(self, player):
        return ROLE_LABELS.get(player.get("role", ROLE_SOLO), "SOLO")

    def duo_team_color(self, team_id):
        try:
            team_id = int(team_id)
        except (TypeError, ValueError):
            return DUO_NEUTRAL_COLOR
        if team_id < 1:
            return DUO_NEUTRAL_COLOR
        source = self
        if getattr(self, "is_host", False) and getattr(self, "server", None):
            source = self.server
        elif getattr(self, "is_client", False) and getattr(self, "client", None):
            source = self.client
        team_colors = getattr(source, "team_colors", {})
        return (
            team_colors.get(team_id)
            or team_colors.get(str(team_id))
            or DUO_TEAM_COLORS[(team_id - 1) % len(DUO_TEAM_COLORS)]
        )

    def display_player_color(self, p_id, player=None):
        player = player if player is not None else getattr(self, "players", {}).get(p_id, {})
        if self.current_game_mode() == GAME_MODE_DUO:
            return self.duo_team_color(player.get("team"))
        return player.get("color", COLORS[(p_id - 1) % len(COLORS)])

    def duo_team_name(self, team_id):
        source = self
        if getattr(self, "is_host", False) and getattr(self, "server", None):
            source = self.server
        elif getattr(self, "is_client", False) and getattr(self, "client", None):
            source = self.client
        names = getattr(source, "team_names", {})
        return names.get(team_id) or names.get(str(team_id)) or f"Team {team_id}"

    def my_role(self):
        players = getattr(self, "players", {})
        if getattr(self, "my_player_id", None) in players:
            return players[self.my_player_id].get("role", ROLE_SOLO)
        return ROLE_SOLO

    def my_can_decrypt(self):
        return self.current_game_mode() == GAME_MODE_SOLO or self.my_role() == ROLE_DECRYPT

    def my_can_use_powerups(self):
        return self.current_game_mode() == GAME_MODE_SOLO or self.my_role() == ROLE_POWERUPS

    def update_duo_team_ui(self, current_players):
        if self.current_game_mode() != GAME_MODE_DUO or not getattr(self, "team_status_labels", None):
            return

        neutral_names = []
        for p_id, player in sorted(current_players.items()):
            if player.get("team") is not None:
                continue
            suffix = " - YOU" if self.is_client and p_id == self.my_player_id else ""
            ready_text = "READY" if player.get("ready", False) else "NOT READY"
            neutral_names.append(
                f"{player.get('name', f'Player {p_id}')} (P{p_id}){suffix} - {ready_text}"
            )
        neutral_text = "\n".join(neutral_names) if neutral_names else "No neutral players"
        if 0 in self.team_status_labels:
            self.team_status_labels[0].config(text=neutral_text)

        my_team = None
        my_role = None
        if self.is_client and self.my_player_id in current_players:
            my_team = current_players[self.my_player_id].get("team")
            my_role = current_players[self.my_player_id].get("role")

        for team_id in range(1, self.duo_team_count() + 1):
            team_color = self.duo_team_color(team_id)
            if team_id in getattr(self, "team_title_labels", {}):
                self.team_title_labels[team_id].config(
                    text=self.duo_team_name(team_id).upper(), fg=team_color)
            if team_id in getattr(self, "team_color_swatches", {}):
                self.team_color_swatches[team_id].config(bg=team_color)
            if team_id in getattr(self, "team_color_value_labels", {}):
                self.team_color_value_labels[team_id].config(
                    text=team_color.upper(),
                    fg=team_color,
                )
            members = [
                (p_id, player) for p_id, player in sorted(current_players.items())
                if player.get("team") == team_id
            ]
            occupants = {
                player.get("role"): (p_id, player)
                for p_id, player in members
                if player.get("role") in (ROLE_DECRYPT, ROLE_POWERUPS)
            }
            for role in (ROLE_DECRYPT, ROLE_POWERUPS):
                if (team_id, role) in getattr(self, "team_role_title_labels", {}):
                    self.team_role_title_labels[(team_id, role)].config(fg=team_color)
                occupant = occupants.get(role)
                if (team_id, role) in self.team_status_labels:
                    if occupant:
                        p_id, player = occupant
                        suffix = " - YOU" if self.is_client and p_id == self.my_player_id else ""
                        ready_text = "READY" if player.get("ready", False) else "NOT READY"
                        ready_color = "#55ff55" if player.get("ready", False) else "#ff7474"
                        self.team_status_labels[(team_id, role)].config(
                            text=(
                                f"{player.get('name', f'Player {p_id}')} (P{p_id}){suffix}"
                                f"\n{ready_text}"
                            ),
                            fg=ready_color,
                        )
                    else:
                        self.team_status_labels[(team_id, role)].config(
                            text="open",
                            fg="#d7d7df",
                        )
                if (team_id, role) in self.team_join_buttons:
                    selected = my_team == team_id and my_role == role
                    taken_by_other = occupant is not None and not selected
                    self.team_join_buttons[(team_id, role)].config(
                        state="disabled" if taken_by_other else "normal",
                        text="JOINED" if selected else ("TAKEN" if taken_by_other else "SELECT"),
                        bg=team_color if selected else "#313143",
                        fg="#121214" if selected else "#ffffff",
                        activebackground=team_color,
                    )
        if 0 in self.team_join_buttons:
            is_neutral = my_team is None
            self.team_join_buttons[0].config(
                text="EDIT NAME" if is_neutral else "MOVE TO NEUTRAL",
                state="normal",
                bg="#00d2ff" if is_neutral else "#313143",
                fg="#121214" if is_neutral else "#ffffff",
                activebackground="#00a3cc" if is_neutral else "#42425b",
            )

    def lobby_can_start(self, current_players):
        if not current_players:
            return False
        if not all(info.get("ready", False) for info in current_players.values()):
            return False
        if self.current_game_mode() == GAME_MODE_SOLO:
            return True
        if len(current_players) % 2:
            return False
        assigned = [info for info in current_players.values() if info.get("team") is not None]
        if len(assigned) != len(current_players):
            return False
        for team_id in {info.get("team") for info in assigned}:
            team_members = [info for info in assigned if info.get("team") == team_id]
            if len(team_members) != 2:
                return False
            if {info.get("role") for info in team_members} != {ROLE_DECRYPT, ROLE_POWERUPS}:
                return False
        return True

    def update_lobby_ui(self):
        mode = self.current_game_mode()
        if (hasattr(self, "lobby_body_frame")
                and getattr(self, "lobby_layout_mode", mode) != mode):
            self.build_lobby_slots_ui()
            self.build_lobby_chat_ui()
        
        # Pull data from model
        current_players = self.server.players if self.is_host else self.client.players
        self.game_mode = mode
        self.update_duo_team_ui(current_players)
        
        max_p = getattr(self, "max_players", 6)
        if mode == GAME_MODE_SOLO:
            if not hasattr(self, 'slot_status_labels') or not self.slot_status_labels:
                return
            for i in range(1, max_p + 1):
                if i - 1 >= len(self.slot_status_labels):
                    break
                lbl_status = self.slot_status_labels[i - 1]
                if i in current_players:
                    p_info = current_players[i]
                    if i - 1 < len(self.slot_title_labels):
                        self.slot_title_labels[i - 1].config(
                            text=f"{p_info.get('name', f'Player {i}')} (P{i})",
                            fg=self.display_player_color(i, p_info)
                        )
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
                    if i - 1 < len(self.slot_title_labels):
                        self.slot_title_labels[i - 1].config(
                            text=f"PLAYER {i} ({COLOR_NAMES[(i - 1) % len(COLOR_NAMES)]})",
                            fg=COLORS[(i - 1) % len(COLORS)]
                        )
                    lbl_status.config(
                        text="Waiting for player...",
                        fg="#5f5f6e"
                    )

        if self.is_host:
            num_players = len(current_players)
            if self.lobby_can_start(current_players):
                self.btn_start.config(state="normal", bg="#55ff55", fg="#121214")
            else:
                self.btn_start.config(state="disabled", bg="#313143", fg="#5f5f6e")

            if mode == GAME_MODE_DUO:
                total_teams = self.duo_team_count()
                complete_teams = sum(
                    1 for team_id in range(1, total_teams + 1)
                    if {info.get("role") for info in current_players.values()
                        if info.get("team") == team_id} == {ROLE_DECRYPT, ROLE_POWERUPS}
                )
                self.lbl_host_status.config(
                    text=f"HOST LOBBY ROOM [DUO] - TEAMS: {complete_teams}/{total_teams} | PLAYERS: {num_players}/{max_p}"
                )
            else:
                self.lbl_host_status.config(
                    text=f"HOST LOBBY ROOM [SOLO] - ACTIVE PLAYERS: {num_players}/{max_p}"
                )
            ip_list = [f"P{p_id}: {info['ip']}" for p_id, info in current_players.items()]
            ips_text = " | ".join(ip_list) if ip_list else "Waiting for connections..."
            self.lbl_ips.config(text=f"Connected: {ips_text}")
        elif self.my_player_id in current_players and hasattr(self, "lbl_lobby_title"):
            mine = current_players[self.my_player_id]
            server_ready = bool(mine.get("ready", False))
            if (hasattr(self, "btn_ready")
                    and not getattr(self, "viewing_postgame_lobby", False)
                    and self.client_is_ready != server_ready):
                self.client_is_ready = server_ready
                if server_ready:
                    self.btn_ready.config(text="UNREADY", bg="#ff4d4d", fg="#ffffff")
                else:
                    self.btn_ready.config(text="READY", bg="#55ff55", fg="#121214")
            role_suffix = ""
            if mode == GAME_MODE_DUO:
                team_text = self.duo_team_name(mine.get("team")) if mine.get("team") else "NEUTRAL"
                role_suffix = f" - {team_text} / {self.role_label(mine)}"
                if hasattr(self, "lbl_status_desc"):
                    self.lbl_status_desc.config(text="Pick a duo team, then ready up.")
                if hasattr(self, "btn_profile"):
                    if mine.get("role") == ROLE_DECRYPT and mine.get("team") is not None:
                        self.btn_profile.config(text="EDIT TEAM COLOR")
                    elif mine.get("team") is None:
                        self.btn_profile.config(text="EDIT NAME")
                    else:
                        self.btn_profile.config(text="EDIT PROFILE")
            elif hasattr(self, "lbl_status_desc"):
                self.lbl_status_desc.config(text="Toggle ready status to let the Host start...")
                if hasattr(self, "btn_profile"):
                    self.btn_profile.config(text="EDIT PROFILE")
            self.lbl_lobby_title.config(
                text=f"MULTIPLAYER LOBBY - {mine.get('name', f'Player {self.my_player_id}')} (P{self.my_player_id}){role_suffix}",
                fg=self.display_player_color(self.my_player_id, mine)
            )
        self.update_chat_ui()

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
            if self.server.match_finished:
                if not self.showing_finish_screen:
                    self.show_game_finished_screen(True)
                return
            self.update_host_ui_stats()
            self.draw_elements()
            self.update_ingame_chat()

    def start_host_active_game_screen(self):
        play_sound("click")
        if self.server and not self.server.can_start_game():
            messagebox.showwarning(
                "Lobby Not Ready",
                "Duo mode needs complete two-player teams, and every player must be ready."
            )
            self.update_lobby_ui()
            return
        # Ask difficulty before starting
        diff = CustomDifficultyDialog(self.root, self.button_font).show()
        if not diff:
            return
        self.difficulty       = diff
        self.items_per_player = 4 if diff == "hard" else 3

        self.countdown_active = True
        self.btn_start.config(state="disabled")
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
            tk.Label(self.countdown_overlay, text="\u2691  MISSION DEPLOYMENT",
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
            text="\U0001f451 LEADERBOARD",
            fg="#ffd24d",
            bg="#1a1a24",
            font=("Segoe UI", 14, "bold")
        )
        lbl_leaderboard_title.pack(pady=15, padx=20, anchor="w")

        self.leaderboard_rows_frame = tk.Frame(self.leaderboard_frame, bg="#1a1a24")
        self.leaderboard_rows_frame.pack(fill="both", expand=True)

        self.focused_slot = None
        self.spectator_cards = {}
        max_p = (self.duo_team_count() if self.current_game_mode() == GAME_MODE_DUO
                 else getattr(self, "max_players", 6))
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
        self.build_ingame_chat_ui()

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
        ip_list = [f"{info.get('name', f'Player {p_id}')} (P{p_id}): {info['ip']}"
                   for p_id, info in self.players.items()]
        ips_text = " | ".join(ip_list) if ip_list else "Waiting for connections..."
        self.lbl_ips.config(text=ips_text)
        self.update_leaderboard()

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

        # Gather player or shared duo-team data.
        scores = []
        if self.current_game_mode() == GAME_MODE_DUO:
            for team_id in range(1, self.duo_team_count() + 1):
                members = [p_id for p_id, info in self.players.items()
                           if info.get("team") == team_id]
                if not members:
                    continue
                collected = set().union(*(
                    set(self.per_player_data.get(p_id, {}).get("collected", {}))
                    for p_id in members
                ))
                names = " / ".join(self.players[p_id].get("name", f"P{p_id}") for p_id in members)
                scores.append({
                    "id": tuple(members), "name": f"{self.duo_team_name(team_id)}: {names}",
                    "color": self.duo_team_color(team_id),
                    "moves": sum(self.players[p_id].get("moves", 0) for p_id in members),
                    "items": len(collected),
                })
        else:
            for p_id, p_info in self.players.items():
                p_data = self.per_player_data.get(p_id, {})
                scores.append({
                    "id": p_id,
                    "name": p_info.get("name", f"Player {p_id}"),
                    "color": self.display_player_color(p_id, p_info),
                    "moves": p_info.get("moves", 0),
                    "items": len(p_data.get("collected", {})),
                })

        # Finished players lock their rank by completion order;
        # unfinished players sort below them by items desc, moves asc.
        finished_list = (
            self.server.finished_players if self.is_host and self.server
            else getattr(self.client, "finished_players", []) if self.client else []
        )

        def sort_key(item):
            p_id = item["id"]
            member_ids = p_id if isinstance(p_id, tuple) else (p_id,)
            finish_indexes = [finished_list.index(member) for member in member_ids
                              if member in finished_list]
            if finish_indexes:
                return (0, min(finish_indexes), 0)
            return (1, -item["items"], item["moves"])

        scores.sort(key=sort_key)

        # Draw rows
        for rank, item in enumerate(scores, 1):
            p_id = item["id"]
            p_color = item["color"]
            moves = item["moves"]
            items_found = item["items"]
            member_ids = p_id if isinstance(p_id, tuple) else (p_id,)
            is_finished = any(member in finished_list for member in member_ids)

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
                text="\u2b24",
                fg=p_color,
                bg=row_frame["bg"],
                font=("Segoe UI", 12)
            )
            lbl_dot.pack(side="left", padx=5)

            lbl_player = tk.Label(
                row_frame,
                text=item["name"],
                fg="#ffffff",
                bg=row_frame["bg"],
                font=("Segoe UI", 10, "bold")
            )
            lbl_player.pack(side="left", padx=5)

            if is_finished:
                # Locked badge - rank is permanently sealed
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
        if getattr(self, "blocked_from_joining", False):
            messagebox.showwarning("Lobby Locked", "This operator has been eliminated and cannot rejoin the lobby.")
            return
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
        self.profile_prompted = False
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

        self.btn_profile = tk.Button(
            self.header, text="EDIT PROFILE", command=self.edit_profile_action,
            bg="#313143", fg="#ffffff", activebackground="#42425b",
            activeforeground="#ffffff", state="disabled", bd=0,
            padx=15, pady=5, font=self.score_font, cursor="hand2"
        )
        self.btn_profile.pack(side="right", padx=5, pady=12)

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
            on_unlock_result=lambda success: self.root.after(0, lambda: self.on_unlock_result_received(success)),
            on_profile_result=lambda success, reason: self.root.after(
                0, lambda: self.on_profile_result_received(success, reason)
            )
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
        self.btn_profile.config(state="normal")
        self.build_lobby_slots_ui()
        self.build_lobby_chat_ui()
        if not self.profile_prompted:
            self.profile_prompted = True
            if self.profile_customized:
                self.client.send_profile(self.preferred_name, self.preferred_color)
            else:
                self.root.after(100, self.edit_profile_action)

    def edit_title_profile(self):
        result = PlayerProfileDialog(
            self.root, self.button_font,
            self.preferred_name, self.preferred_color, COLORS,
        ).show()
        if result:
            self.preferred_name, self.preferred_color = result
            self.profile_customized = True

    def edit_profile_action(self):
        if (not self.client or not self.my_player_id
                or (self.game_started and not self.client.match_finished
                    and self.my_player_id not in self.client.finished_players)):
            return
        player = self.players.get(self.my_player_id, {})
        mode = self.current_game_mode()
        is_duo_decryptor = (
            mode == GAME_MODE_DUO
            and player.get("role") == ROLE_DECRYPT
            and player.get("team") is not None
        )
        allow_color = mode == GAME_MODE_SOLO or is_duo_decryptor
        if is_duo_decryptor:
            team_id = player.get("team")
            profile_name = self.duo_team_name(team_id)
            profile_color = self.duo_team_color(team_id)
            unavailable_colors = {
                self.duo_team_color(other_team).lower()
                for other_team in range(1, self.duo_team_count() + 1)
                if other_team != team_id
            }
            title = "DUO TEAM SETTINGS"
            color_label = "TEAM COLOR"
            save_label = "SAVE TEAM"
            allow_name = True
            name_label = "TEAM NAME"
        elif mode == GAME_MODE_DUO and player.get("team") is None:
            profile_color = player.get(
                "profile_color",
                player.get("color", COLORS[(self.my_player_id - 1) % len(COLORS)])
            )
            unavailable_colors = set()
            title = "NEUTRAL PLAYER NAME"
            color_label = "PLAYER COLOR"
            save_label = "SAVE NAME"
            allow_name = True
            name_label = "DISPLAY NAME"
        else:
            profile_color = player.get(
                "profile_color",
                player.get("color", COLORS[(self.my_player_id - 1) % len(COLORS)])
            )
            unavailable_colors = {
                info.get("profile_color", info.get("color", "")).lower()
                for player_id, info in self.players.items()
                if player_id != self.my_player_id and info.get("profile_color", info.get("color"))
            } if allow_color else set()
            title = "PLAYER PROFILE"
            color_label = "PLAYER COLOR"
            save_label = "SAVE PROFILE"
            allow_name = True
            name_label = "DISPLAY NAME"
        result = PlayerProfileDialog(
            self.root, self.button_font,
            profile_name if is_duo_decryptor else player.get("name", f"Player {self.my_player_id}"),
            profile_color,
            COLORS,
            unavailable_colors=unavailable_colors,
            title=title,
            color_label=color_label,
            save_label=save_label,
            allow_color=allow_color,
            allow_name=allow_name,
            name_label=name_label,
        ).show()
        if result:
            if not is_duo_decryptor:
                self.preferred_name = result[0]
                self.preferred_color = result[1]
            self.profile_customized = True
            self.client.send_profile(*result)

    def on_profile_result_received(self, success, reason):
        if not success:
            messagebox.showerror("Profile Not Updated", reason or "The host rejected that profile.")

    def on_client_lobby_full(self):
        messagebox.showerror("Lobby Full", "The server lobby is currently full (max 6 players).")
        self.show_title_screen()

    def on_client_state_update(self):
        if self.client:
            self.players = self.client.players
            self.per_player_data = self.client.per_player_data
            self.game_started = self.client.game_started
            self.difficulty = getattr(self.client, "difficulty", getattr(self, "difficulty", "easy"))
            self.items_per_player = getattr(self.client, "items_per_player", getattr(self, "items_per_player", 3))
            self.game_mode = getattr(self.client, "game_mode", getattr(self, "game_mode", GAME_MODE_SOLO))
            self.team_colors = getattr(self.client, "team_colors", {})
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
                if self.viewing_postgame_lobby and (self.client.match_finished or local_finished):
                    self.update_lobby_ui()
                elif self.viewing_postgame_lobby:
                    self.viewing_postgame_lobby = False
                    self.start_client_active_game_screen()
                elif self.client.match_finished or local_finished:
                    if (not self.showing_finish_screen
                            or self.finish_screen_match_complete != self.client.match_finished):
                        self.show_game_finished_screen(self.client.match_finished)
                elif not self.in_active_game or self.showing_finish_screen:
                    self.start_client_active_game_screen()
                else:
                    self.update_client_ui_stats()
                    self.draw_elements()
                    self.update_ingame_chat()
            else:
                self.update_lobby_ui()

    def on_client_disconnect(self):
        messagebox.showwarning("Connection Lost", "Disconnected from server host.")
        self.show_title_screen()

    def toggle_ready_action(self):
        play_sound("click")
        if self.current_game_mode() == GAME_MODE_DUO:
            mine = self.players.get(self.my_player_id, {})
            if mine.get("team") is None:
                messagebox.showwarning("Pick A Team", "Join a duo team before readying up.")
                return
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
            text="\U0001f512 OPEN LOCK",
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
            sf.bind("<Enter>", lambda e, i=slot_i: self.show_powerup_tooltip(i))
            lbl.bind("<Enter>", lambda e, i=slot_i: self.show_powerup_tooltip(i))
            sf.bind("<Leave>", self.schedule_powerup_tooltip_hide)
            lbl.bind("<Leave>", self.schedule_powerup_tooltip_hide)
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
            text="Arrow keys / WASD to move  \u2022  1 / 2 / 3 to select powerup  \u2022  E to use",
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
        self.build_ingame_chat_ui()

    def _format_finish_time(self, seconds):
        if seconds is None:
            return "--:--"
        seconds = max(0, int(round(seconds)))
        return f"{seconds // 60:02d}:{seconds % 60:02d}"

    def _rank_color(self, rank):
        return {1: "#ffd24d", 2: "#cfd3dc", 3: "#cd7f32"}.get(rank, "#8c8c9a")

    def _player_keys_solved(self, p_id):
        if (self.current_game_mode() == GAME_MODE_DUO
                and self.players.get(p_id, {}).get("role") != ROLE_DECRYPT):
            return 0
        data = self.per_player_data.get(p_id, {})
        remaining = data.get("items", set())
        if remaining is not None:
            return max(0, self.items_per_player - len(remaining))
        return len(data.get("collected", {}))

    def _display_groups_for_results(self):
        player_ids = sorted(self.players.keys())
        if self.current_game_mode() == GAME_MODE_DUO:
            groups = []
            for team_id in sorted({
                info.get("team") for info in self.players.values()
                if info.get("team") is not None
            }):
                members = [
                    p_id for p_id in player_ids
                    if self.players.get(p_id, {}).get("team") == team_id
                ]
                if not members:
                    continue
                color = self.duo_team_color(team_id)
                groups.append((self.duo_team_name(team_id), members, color))
            return groups
        if self.difficulty == "medium" and len(player_ids) >= 6:
            return [
                ("Group 1", player_ids[0:2], "#00d2ff"),
                ("Group 2", player_ids[2:4], "#ffd24d"),
                ("Group 3", player_ids[4:6], "#d800ff"),
            ]
        if self.difficulty == "hard" and len(player_ids) >= 4:
            return [
                ("Group 1", player_ids[0:2], "#00d2ff"),
                ("Group 2", player_ids[2:4], "#ff4d4d"),
            ]
        return []

    def _build_finish_results(self):
        match = self.server if self.is_host else self.client
        finished = list(getattr(match, "finished_players", []))
        finish_times = getattr(match, "finish_times", {})

        groups = self._display_groups_for_results()
        if groups and (self.current_game_mode() == GAME_MODE_DUO or self.difficulty in ("medium", "hard")):
            rows = []
            for name, members, color in groups:
                keys = sum(self._player_keys_solved(p_id) for p_id in members)
                objective_members = [
                    p_id for p_id in members
                    if self.current_game_mode() != GAME_MODE_DUO
                    or self.players.get(p_id, {}).get("role") == ROLE_DECRYPT
                ]
                goal = self.items_per_player * max(1, len(objective_members))
                member_times = [finish_times[p_id] for p_id in objective_members if p_id in finish_times]
                complete = len(member_times) == len(objective_members)
                moves = sum(self.players.get(p_id, {}).get("moves", 0) for p_id in members)
                rows.append({
                    "name": name,
                    "members": members,
                    "color": color,
                    "keys": keys,
                    "goal": goal,
                    "moves": moves,
                    "finish_time": max(member_times) if complete else None,
                    "sort": (0, max(member_times)) if complete else (1, -keys, moves),
                })
            rows.sort(key=lambda row: row["sort"])
            if self.current_game_mode() == GAME_MODE_DUO:
                winner_limit = getattr(match, "finish_target", 1)
            else:
                winner_limit = 2 if self.difficulty == "medium" else 1
            for index, row in enumerate(rows, 1):
                row["rank"] = index
                row["winner"] = index <= winner_limit
            return rows[:winner_limit], rows[winner_limit:]

        rows = []
        for p_id, info in self.players.items():
            keys = self._player_keys_solved(p_id)
            order = finished.index(p_id) if p_id in finished else 999
            rows.append({
                "name": info.get("name", f"Player {p_id}"),
                "members": [p_id],
                "color": self.display_player_color(p_id, info),
                "keys": keys,
                "goal": self.items_per_player if self.current_game_mode() != GAME_MODE_DUO or info.get("role") == ROLE_DECRYPT else 0,
                "moves": info.get("moves", 0),
                "finish_time": finish_times.get(p_id),
                "sort": (0, order) if p_id in finished else (1, -keys, info.get("moves", 0)),
            })
        rows.sort(key=lambda row: row["sort"])
        for index, row in enumerate(rows, 1):
            row["rank"] = index
            row["winner"] = index <= match.finish_target
        return rows[:match.finish_target], rows[match.finish_target:]

    def _draw_place_badge(self, parent, rank, size):
        color = self._rank_color(rank)
        canvas = tk.Canvas(parent, width=size, height=size, bg="#111d29", highlightthickness=0)
        canvas.pack(pady=(10, 2))
        canvas.create_oval(5, 5, size - 5, size - 5, fill="#0d141e", outline=color, width=4)
        canvas.create_oval(15, 15, size - 15, size - 15, fill="#151b29", outline="#26364a", width=1)
        canvas.create_text(size // 2, size // 2, text=str(rank), fill=color,
                           font=("Segoe UI", max(28, size // 2), "bold"))

    def _build_finish_podium_card(self, parent, row, width, height, big=False):
        frame = tk.Frame(parent, bg="#111d29", highlightbackground=self._rank_color(row["rank"]),
                         highlightthickness=2, width=width, height=height)
        frame.pack_propagate(False)
        self._draw_place_badge(frame, row["rank"], 94 if big else 72)
        tk.Label(frame, text=row["name"].upper(), fg="#eafaff", bg="#111d29",
                 font=("Segoe UI", 14 if big else 12, "bold")).pack(pady=(0, 2))
        member_names = " / ".join(
            f"{self.players.get(p_id, {}).get('name', f'Player {p_id}')} (P{p_id})"
            for p_id in row["members"]
        )
        tk.Label(frame, text=member_names,
                 fg=row["color"], bg="#111d29", font=("Consolas", 10, "bold")).pack()
        tk.Label(frame, text=f"{row['keys']}/{row['goal']} KEYS", fg="#55ff55",
                 bg="#111d29", font=("Segoe UI", 11, "bold")).pack(pady=(8, 2))
        tk.Label(frame, text=f"TIME {self._format_finish_time(row['finish_time'])}  |  MOVES {row['moves']}",
                 fg="#8fa6b6", bg="#111d29", font=("Segoe UI", 9, "bold")).pack()
        return frame

    def _build_finish_participant_row(self, parent, row):
        frame = tk.Frame(parent, bg="#0d141e", height=28)
        frame.pack(fill="x", pady=2)
        frame.pack_propagate(False)
        tk.Label(frame, text=f"#{row['rank']}", fg="#8fa6b6", bg="#0d141e",
                 font=("Segoe UI", 10, "bold"), width=5).pack(side="left", padx=(10, 4))
        tk.Label(frame, text=row["name"], fg="#eafaff", bg="#0d141e",
                 font=("Segoe UI", 10, "bold"), width=18, anchor="w").pack(side="left")
        member_names = " / ".join(
            f"{self.players.get(p_id, {}).get('name', f'Player {p_id}')} (P{p_id})"
            for p_id in row["members"]
        )
        tk.Label(frame, text=member_names,
                 fg=row["color"], bg="#0d141e", font=("Consolas", 9, "bold"),
                 width=30, anchor="w").pack(side="left")
        tk.Label(frame, text=f"{row['keys']}/{row['goal']} KEYS",
                 fg="#ffd24d" if row["keys"] else "#8c8c9a", bg="#0d141e",
                 font=("Segoe UI", 9, "bold"), width=12, anchor="e").pack(side="right", padx=(4, 12))
        tk.Label(frame, text=f"TIME {self._format_finish_time(row['finish_time'])}",
                 fg="#8fa6b6", bg="#0d141e", font=("Segoe UI", 9),
                 width=14, anchor="e").pack(side="right")

    def return_loser_to_main_menu(self):
        self.blocked_from_joining = True
        self.show_title_screen()

    def show_game_finished_screen(self, match_complete):
        self.in_active_game = True
        self.showing_finish_screen = True
        self.finish_screen_match_complete = match_complete
        self.qte_active = False
        self.clear_screen()

        winners, participants = self._build_finish_results()
        finished = (not self.is_host
                    and self.my_player_id in self.client.finished_players)

        self.current_frame = tk.Frame(self.root, bg="#090d14")
        self.current_frame.pack(fill="both", expand=True)
        shell = tk.Frame(self.current_frame, bg="#0d141e", highlightthickness=1,
                         highlightbackground="#1b4055")
        shell.place(relx=0.5, rely=0.5, anchor="center", width=1040, height=720)
        tk.Frame(shell, bg="#00d2ff", height=4).pack(fill="x")
        tk.Label(shell, text=f"{self.difficulty.upper()} ROUND COMPLETE", fg="#ffd24d",
                 bg="#0d141e", font=("Consolas", 12, "bold")).pack(pady=(18, 2))
        tk.Label(shell, text="GRID EXPLORER", fg="#eafaff", bg="#0d141e",
                 font=("Segoe UI", 34, "bold")).pack()
        tk.Label(shell, text="FINAL LEADERBOARD  /  KEYS SOLVED  /  FINISH TIME",
                 fg="#8fa6b6", bg="#0d141e", font=("Consolas", 10, "bold")).pack(pady=(2, 12))

        podium = tk.Frame(shell, bg="#0d141e")
        podium.pack()
        if self.difficulty == "easy" and len(winners) >= 3:
            by_rank = {row["rank"]: row for row in winners}
            order = [(2, 250, 220, False), (1, 300, 250, True), (3, 250, 220, False)]
            for col, (rank, width, height, big) in enumerate(order):
                holder = tk.Frame(podium, bg="#0d141e", width=width, height=height)
                holder.grid(row=0, column=col, padx=12, sticky="s")
                holder.grid_propagate(False)
                if rank in by_rank:
                    self._build_finish_podium_card(holder, by_rank[rank], width, height, big).pack(side="bottom")
        else:
            for col, row in enumerate(winners):
                width = 300 if row["rank"] == 1 else 270
                height = 250 if row["rank"] == 1 else 220
                holder = tk.Frame(podium, bg="#0d141e", width=width, height=height)
                holder.grid(row=0, column=col, padx=14, sticky="s")
                holder.grid_propagate(False)
                self._build_finish_podium_card(holder, row, width, height, row["rank"] == 1).pack(side="bottom")

        list_panel = tk.Frame(shell, bg="#111d29", highlightbackground="#26364a",
                              highlightthickness=1, width=850, height=142)
        list_panel.pack(pady=(10, 8))
        list_panel.pack_propagate(False)
        tk.Label(list_panel, text="PARTICIPANTS WHO DID NOT WIN", fg="#8fa6b6",
                 bg="#111d29", font=("Segoe UI", 11, "bold")).pack(anchor="w", padx=16, pady=(6, 3))
        list_body = tk.Frame(list_panel, bg="#111d29")
        list_body.pack(fill="both", expand=True, padx=14, pady=(0, 6))
        for row in participants:
            self._build_finish_participant_row(list_body, row)

        if self.is_host:
            btn_text = "RETURN TO MAIN MENU"
            btn_command = self.show_title_screen
            btn_bg = "#00d2ff"
            btn_fg = "#121214"
        elif finished:
            btn_text = "RETURN TO LOBBY"
            btn_command = self.show_postgame_lobby
            btn_bg = "#00d2ff"
            btn_fg = "#121214"
        else:
            btn_text = "RETURN TO MAIN MENU"
            btn_command = self.return_loser_to_main_menu
            btn_bg = "#ff4d4d"
            btn_fg = "#ffffff"
        tk.Button(shell, text=btn_text, command=btn_command, bg=btn_bg, fg=btn_fg,
                  activebackground="#ffd24d", activeforeground="#121214",
                  font=self.button_font, bd=0, width=28, pady=9,
                  cursor="hand2").pack(pady=(0, 12))

    def show_postgame_lobby(self):
        if not self.client or not self.client.client_running:
            return
        self.viewing_postgame_lobby = True
        self.showing_finish_screen = False
        self.in_active_game = False
        self.qte_active = False
        self.clear_screen()

        self.current_frame = tk.Frame(self.root, bg="#121214")
        self.current_frame.pack(fill="both", expand=True)
        self.header = tk.Frame(self.current_frame, bg="#1a1a24", height=75)
        self.header.pack(fill="x", side="top")
        self.lbl_lobby_title = tk.Label(
            self.header, text="MATCH COMPLETE - LOBBY", fg="#ffd24d",
            bg="#1a1a24", font=self.score_font
        )
        self.lbl_lobby_title.pack(side="left", padx=20, pady=15)
        self.client_is_ready = False
        self.btn_ready = tk.Button(
            self.header, text="WAITING FOR HOST", state="disabled",
            bg="#313143", fg="#8c8c9a", bd=0, padx=20, pady=5,
            font=self.score_font
        )
        self.btn_ready.pack(side="right", padx=10, pady=12)
        self.btn_profile = tk.Button(
            self.header, text="EDIT PROFILE", command=self.edit_profile_action,
            bg="#313143", fg="#ffffff", activebackground="#42425b",
            activeforeground="#ffffff", bd=0, padx=15, pady=5,
            font=self.score_font, cursor="hand2"
        )
        self.btn_profile.pack(side="right", padx=10, pady=12)
        self.sub_header = tk.Frame(self.current_frame, bg="#15151e", height=30)
        self.sub_header.pack(fill="x")
        self.lbl_status_desc = tk.Label(
            self.sub_header, text="Waiting for the host to start the next round...",
            fg="#8c8c9a", bg="#15151e", font=self.hint_font
        )
        self.lbl_status_desc.pack(padx=20, pady=3, anchor="w")
        self.build_lobby_slots_ui()
        self.build_lobby_chat_ui()
        self.update_lobby_ui()

    def update_client_ui_stats(self):
        if not self.in_active_game or not self.my_player_id:
            return
        
        my_id = self.my_player_id
        if my_id in self.players:
            info = self.players[my_id]
            self.lbl_pos.config(text=f"POSITION: ({info['c']}, {info['r']})")
            role_suffix = ""
            if self.current_game_mode() == GAME_MODE_DUO:
                team_text = f"T{info.get('team')}" if info.get("team") else "NEUTRAL"
                role_suffix = f" [{team_text} {self.role_label(info)}]"
            
            self.lbl_player_id.config(
                text=f"{info.get('name', f'Player {my_id}')} (P{my_id}){role_suffix}",
                fg=self.display_player_color(my_id, info)
            )
            
        self.lbl_moves.config(text=f"MOVES: {self.moves}")
        if hasattr(self, 'lbl_items') and self.my_player_id in self.per_player_data:
            my_data = self.per_player_data[self.my_player_id]
            found = len(my_data.get("collected", {}))
            self.lbl_items.config(text=f"ITEMS: {found}/{self.items_per_player}")

        # Lock button always available (gold)
        if hasattr(self, 'btn_lock'):
            if self.my_can_decrypt():
                self.btn_lock.config(
                    bg="#ffd24d", fg="#121214", text="\U0001f512 VAULT",
                    state="normal"
                )
            else:
                self.btn_lock.config(
                    bg="#313143", fg="#8c8c9a", text="\U0001f512 DECRYTOR ONLY",
                    state="disabled"
                )

        self.update_powerup_bar()

    def select_powerup_slot(self, slot_index):
        """Highlight the selected powerup slot (0-based). No-op if slot is empty."""
        if not self.my_can_use_powerups():
            return
        if not hasattr(self, 'powerup_slot_frames'):
            return
        # Get current slots for this player
        slots = [None, None, None]
        if self.my_player_id and self.my_player_id in self.per_player_data:
            slots = self.per_player_data[self.my_player_id].get("powerups", [None, None, None])

        if slots[slot_index] is None:
            return  # empty slot - nothing to select

        self.selected_powerup_slot = slot_index
        play_sound("click")
        self.update_powerup_bar()

    def update_powerup_bar(self):
        """Refresh the 3 powerup slot boxes to reflect current inventory."""
        if not hasattr(self, 'powerup_slot_frames'):
            return

        if not self.my_can_use_powerups():
            for sf, lbl in zip(self.powerup_slot_frames, self.powerup_slot_labels):
                sf.config(highlightbackground="#313143")
                lbl.config(text="SABOTAGEE ONLY", fg="#5f5f6e")
            return

        slots = [None, None, None]
        if self.my_player_id and self.my_player_id in self.per_player_data:
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

    def powerup_tooltip_content(self, slot_index):
        """Return display metadata for a powerup inventory slot."""
        slot_types = ("reveal", "shield", "speed")
        slots = [None, None, None]
        if self.my_player_id and self.my_player_id in self.per_player_data:
            slots = self.per_player_data[self.my_player_id].get("powerups", slots)
        pu_id = slots[slot_index] if slot_index < len(slots) else None
        expected_id = slot_types[slot_index]
        meta = POWERUP_META.get(pu_id or expected_id, {})
        status = "Press E to use after selecting." if pu_id else "EMPTY — discover this pickup on the grid."
        return meta, status

    def show_powerup_tooltip(self, slot_index):
        """Show contextual powerup information next to the pointer."""
        pending = getattr(self, "powerup_tooltip_hide_after", None)
        if pending is not None:
            self.root.after_cancel(pending)
            self.powerup_tooltip_hide_after = None
        self.hide_powerup_tooltip()
        meta, status = self.powerup_tooltip_content(slot_index)

        tooltip = tk.Toplevel(self.root)
        tooltip.wm_overrideredirect(True)
        tooltip.attributes("-topmost", True)
        panel = tk.Frame(
            tooltip, bg="#101018", bd=1, relief="solid",
            highlightthickness=1, highlightbackground=meta.get("color", "#ffffff"),
        )
        panel.pack()
        tk.Label(
            panel, text=f"{meta.get('icon', '?')}  {meta.get('label', 'Powerup')}",
            fg=meta.get("color", "#ffffff"), bg="#101018",
            font=("Segoe UI", 10, "bold"), anchor="w",
        ).pack(fill="x", padx=12, pady=(9, 3))
        tk.Label(
            panel, text=meta.get("description", "No information available."),
            fg="#e8e8ee", bg="#101018", font=("Segoe UI", 9),
            justify="left", wraplength=290, anchor="w",
        ).pack(fill="x", padx=12, pady=2)
        tk.Label(
            panel, text=status, fg="#8c8c9a", bg="#101018",
            font=("Segoe UI", 8, "italic"), anchor="w",
        ).pack(fill="x", padx=12, pady=(3, 9))

        tooltip.update_idletasks()
        x = self.root.winfo_pointerx() + 14
        y = self.root.winfo_pointery() + 16
        x = min(x, tooltip.winfo_screenwidth() - tooltip.winfo_reqwidth() - 8)
        y = min(y, tooltip.winfo_screenheight() - tooltip.winfo_reqheight() - 8)
        tooltip.wm_geometry(f"+{max(0, x)}+{max(0, y)}")
        self.powerup_tooltip = tooltip

    def schedule_powerup_tooltip_hide(self, event=None):
        pending = getattr(self, "powerup_tooltip_hide_after", None)
        if pending is not None:
            self.root.after_cancel(pending)
        self.powerup_tooltip_hide_after = self.root.after(80, self.hide_powerup_tooltip)

    def hide_powerup_tooltip(self):
        tooltip = getattr(self, "powerup_tooltip", None)
        if tooltip is not None:
            try:
                tooltip.destroy()
            except Exception:
                pass
            self.powerup_tooltip = None

    def open_lock_dialog(self):
        """Open the 3-keyhole vault screen for multiplayer client."""
        if not self.is_client or not self.my_player_id:
            return
        if not self.my_can_decrypt():
            play_sound("qte_wrong")
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
            return None  # async - dialog closes itself

        LockScreenDialog(self.root, self.button_font, items_data, on_submit).show()

    def open_vault_at_current_item(self):
        """Open the vault only when standing on one of the local player's items."""
        if not self.my_can_decrypt():
            return
        if not self.in_active_game or self.qte_active:
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
        if not self.my_can_use_powerups():
            play_sound("qte_wrong")
            return
        if self.selected_powerup_slot is None:
            return

        slot = self.selected_powerup_slot

        my_id = self.my_player_id
        if not my_id or my_id not in self.per_player_data:
            return
        slots_list = self.per_player_data[my_id].get("powerups", [None, None, None])
        pu = slots_list[slot] if slot < len(slots_list) else None
        if not pu:
            return

        if pu == "speed":
            self.show_player_teleport_selection_dialog(slot)
        elif pu == "shield":
            self.show_item_displacement_selection_dialog(slot)
        else:
            self.send_powerup_use(slot, None)

    def show_item_displacement_selection_dialog(self, slot):
        eligible_players = self.eligible_item_displacement_players()
        if not eligible_players:
            play_sound("qte_wrong")
            messagebox.showinfo(
                "No Discovered Items",
                "No opponent currently has an item discovered by any player."
            )
            return
        TeleportDialog(
            self.root, self.button_font, eligible_players, self.my_player_id,
            lambda target_id: self.send_powerup_use(slot, target_id),
            COLORS, COLOR_NAMES, title="CHOOSE PLAYER WHOSE ITEM WILL MOVE"
        )

    def eligible_item_displacement_players(self):
        eligible_ids = self.client.move_item_targets if self.client else set()
        return {
            p_id: player
            for p_id, player in self.players.items()
            if p_id in eligible_ids
        }

    def show_player_teleport_selection_dialog(self, slot):
        TeleportDialog(
            self.root,
            self.button_font,
            self.players,
            self.my_player_id,
            lambda target_id: self.send_powerup_use(slot, target_id),
            COLORS,
            COLOR_NAMES,
            include_self=True
        )

    def send_powerup_use(self, slot, target_id=None):
        if self.client:
            self.client.send_powerup_use(slot, target_id)



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

    def host_visible_items(self):
        if not self.server:
            return set()
        remaining = set().union(*self.server.player_items.values()) if self.server.player_items else set()
        return self.server.host_discovered_items & remaining

    def draw_elements(self):
        if not self.in_active_game:
            return

        if hasattr(self, 'is_host') and self.is_host:
            duo_mode = self.current_game_mode() == GAME_MODE_DUO
            max_p = self.duo_team_count() if duo_mode else getattr(self, "max_players", 6)
            focused = getattr(self, "focused_slot", None)
            host_items = self.host_visible_items()
            
            for slot_id in range(1, max_p + 1):
                card = self.spectator_cards.get(slot_id)
                if not card:
                    continue
                canvas = card["canvas"]
                lbl_title = card["title_label"]
                lbl_stats = card["stats_label"]

                if duo_mode:
                    p_ids = [p_id for p_id, info in self.players.items()
                             if info.get("team") == slot_id]
                else:
                    p_ids = [slot_id] if slot_id in self.players else []
                p_id = p_ids[0] if p_ids else slot_id
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

                    visited = set().union(*(
                        self.per_player_data.get(member_id, {}).get("visited", set())
                        for member_id in p_ids
                    ))
                    items = set().union(*(
                        self.per_player_data.get(member_id, {}).get("items", set())
                        for member_id in p_ids
                    ))
                    collected = {}
                    for member_id in p_ids:
                        collected.update(self.per_player_data.get(member_id, {}).get("collected", {}))
                    p_color = self.display_player_color(p_id, p_info)
                    player_names = " / ".join(
                        self.players[member_id].get("name", f"P{member_id}")
                        for member_id in p_ids
                    )
                    player_name = f"{self.duo_team_name(slot_id).upper()}: {player_names}" if duo_mode else player_names

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
                                text="\U0001f6a9", fill=cell_color,
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

                    # Host-only neutral markers reveal no item ownership.
                    for r, c in host_items:
                        margin = max(2, split_size // 4)
                        ix1 = c * split_size + margin
                        iy1 = r * split_size + margin
                        ix2 = (c + 1) * split_size - margin
                        iy2 = (r + 1) * split_size - margin
                        canvas.create_rectangle(
                            ix1, iy1, ix2, iy2,
                            fill="#1a1a24", outline="#d7d7df", width=2
                        )
                        canvas.create_text(
                            (ix1 + ix2) // 2, (iy1 + iy2) // 2,
                            text="?", fill="#d7d7df", font=flag_font
                        )

                    for (r, c), powerup_id in self.server.powerups.items():
                        # Spectators can see pickup locations, but never their
                        # identities. Only a player who discovered the cell can
                        # see the corresponding powerup icon on their own grid.
                        marker_color = "#8c8c9a"
                        marker_text = "?"
                        pcx = c * split_size + split_size // 2
                        pcy = r * split_size + split_size // 2
                        radius = max(3, split_size // 4)
                        canvas.create_oval(
                            pcx - radius, pcy - radius, pcx + radius, pcy + radius,
                            fill="#1a1a24", outline=marker_color, width=1
                        )
                        canvas.create_text(
                            pcx, pcy, text=marker_text, fill=marker_color, font=flag_font
                        )

                    for marker_index, member_id in enumerate(p_ids):
                        member = self.players[member_id]
                        pr, pc = member["r"], member["c"]
                        inset = p_margin + marker_index * max(1, split_size // 5)
                        px1 = pc * split_size + inset
                        py1 = pr * split_size + inset
                        px2 = (pc + 1) * split_size - inset
                        py2 = (pr + 1) * split_size - inset
                        canvas.create_oval(px1 - 1, py1 - 1, px2 + 1, py2 + 1,
                                           fill="", outline=p_color, width=ring_w)
                        canvas.create_oval(px1, py1, px2, py2, fill=p_color, outline="")
                        canvas.create_text((px1 + px2) // 2, (py1 + py2) // 2,
                                           text=f"P{member_id}", fill="#121214",
                                           font=("Segoe UI", max(5, split_size // 4), "bold"))

                    player_ids = " / ".join(f"P{member_id}" for member_id in p_ids)
                    lbl_title.config(text=f"{player_name} ({player_ids})", fg=p_color)
                    moves = sum(self.players[member_id].get("moves", 0) for member_id in p_ids)
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

        my_id = self.my_player_id
        p_data = self.per_player_data.get(my_id, {})
        if my_id in self.players:
            p_color = self.display_player_color(my_id, self.players[my_id])
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
            color = self.display_player_color(p_id, p)

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
            self.canvas.create_text(
                (px1 + px2) // 2, (py1 + py2) // 2,
                text=p.get("name", f"P{p_id}")[:2].upper(), fill="#121214",
                font=("Segoe UI", 8, "bold"), tags="player_element"
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
                    arrow_char = "\u2191"
                elif dir_tuple == (1, 0):
                    arrow_char = "\u2193"
                elif dir_tuple == (0, -1):
                    arrow_char = "\u2190"
                elif dir_tuple == (0, 1):
                    arrow_char = "\u2192"
                
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

        if not self.is_client or not self.in_active_game or not self.my_player_id:
            return
        finished = getattr(self.client, "finished_players", []) if self.client else []
        if self.my_player_id in finished:
            return
        p_info = self.players.get(self.my_player_id)
        if not p_info:
            return
        r, c = p_info["r"], p_info["c"]

        new_r = r + dr
        new_c = c + dc

        if not (0 <= new_r < GRID_ROWS and 0 <= new_c < GRID_COLS):
            return

        my_visited = self.client.get_my_visited()
        needs_qte = (new_r, new_c) not in my_visited

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
        
        if not self.is_client:
            return
        self.moves += 1
        self.lbl_moves.config(text=f"MOVES: {self.moves}")
        if self.client:
            self.client.send_move(dr, dc)

    def get_closest_item_arrow(self, pr, pc, items=None):
        if items is None:
            items = set()
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
            color = self.display_player_color(owner_id, self.players.get(owner_id, {}))
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
                    text=self.players.get(owner_id, {}).get("name", f"P{owner_id}")[:6], fill=color,
                    font=("Segoe UI", 9, "bold"), tags="shared_item_element"
                )

    def _draw_map_powerups(self):
        """Draw all uncollected multiplayer powerups as shared map objects."""
        if not self.client:
            return
        self._draw_powerup_markers(self.client.map_powerups, self.client.get_my_visited())

    def _draw_powerup_markers(self, powerups, visited):
        """Show every pickup, revealing its identity only on locally visited cells."""
        for (r, c), powerup_id in powerups.items():
            discovered = (r, c) in visited
            meta = POWERUP_META.get(powerup_id, {})
            cx = c * CELL_SIZE + CELL_SIZE // 2
            cy = r * CELL_SIZE + CELL_SIZE // 2
            color = meta.get("color", "#ffffff") if discovered else "#8c8c9a"
            marker = meta.get("icon", "?") if discovered else "?"
            self.canvas.create_oval(
                cx - 13, cy - 13, cx + 13, cy + 13,
                fill="#1a1a24", outline=color, width=3,
                tags="powerup_element"
            )
            self.canvas.create_text(
                cx, cy, text=marker,
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
                # Collected item cell - show flag only (no arrow)
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
                    # Remaining item tile for ME - show lock icon
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
                            parts = key.split("|")
                            if len(parts) >= 3:
                                orig_w, cipher_w, shift_str = parts[:3]
                                mode = parts[3] if len(parts) >= 4 else "decrypt"
                                shift = int(shift_str)
                                if mode == "encrypt":
                                    display_word = orig_w
                                    sign = "+" if shift > 0 else "-"
                                    formula = f"P{sign}{abs(shift)}"
                                else:
                                    display_word = cipher_w
                                    sign = "-" if shift > 0 else "+"
                                    formula = f"C{sign}{abs(shift)}"
                                self.canvas.create_text(
                                    cx_cell, cy_cell + 4,
                                    text=display_word, fill="#ffd24d",
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
                # Regular trail cell - use frozen arrow (pointing to nearest unfound item at visit time)
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
