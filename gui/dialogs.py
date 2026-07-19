import tkinter as tk
from tkinter import colorchooser, font
import threading

from network.discovery import discover_games


class PlayerProfileDialog:
    def __init__(self, parent, button_font, name, color, preset_colors,
                 unavailable_colors=None):
        self.parent = parent
        self.button_font = button_font
        self.name = name
        self.color = color
        self.preset_colors = preset_colors
        self.unavailable_colors = {
            str(value).lower() for value in (unavailable_colors or [])
        }

    def show(self):
        result = {"value": None}
        selected_color = tk.StringVar(value=self.color)
        dialog = tk.Toplevel(self.parent)
        dialog.title("Player Profile")
        dialog.configure(bg="#121214")
        dialog.resizable(False, False)

        width, height = 480, 395
        x = self.parent.winfo_x() + self.parent.winfo_width() // 2 - width // 2
        y = self.parent.winfo_y() + self.parent.winfo_height() // 2 - height // 2
        dialog.geometry(f"{width}x{height}+{x}+{y}")
        dialog.transient(self.parent)
        dialog.grab_set()

        tk.Label(dialog, text="PLAYER PROFILE", fg="#00d2ff", bg="#121214",
                 font=font.Font(family="Segoe UI", size=16, weight="bold")).pack(pady=(22, 16))
        tk.Label(dialog, text="DISPLAY NAME", fg="#8c8c9a", bg="#121214",
                 font=font.Font(family="Segoe UI", size=9, weight="bold")).pack()
        entry = tk.Entry(dialog, bg="#1a1a24", fg="#ffffff", insertbackground="#ffffff",
                         justify="center", bd=0,
                         font=font.Font(family="Segoe UI", size=12))
        entry.pack(fill="x", padx=55, pady=(5, 18), ipady=8)
        entry.insert(0, self.name)
        entry.select_range(0, tk.END)

        tk.Label(dialog, text="PLAYER COLOR", fg="#8c8c9a", bg="#121214",
                 font=font.Font(family="Segoe UI", size=9, weight="bold")).pack()
        color_error = tk.Label(
            dialog, text="", fg="#ff4d4d", bg="#121214",
            font=font.Font(family="Segoe UI", size=9),
        )
        swatches = tk.Frame(dialog, bg="#121214")
        swatches.pack(pady=10)
        preview = tk.Label(dialog, text=selected_color.get().upper(), fg="#121214",
                           bg=selected_color.get(), width=18, pady=5,
                           font=font.Font(family="Segoe UI", size=9, weight="bold"))

        def choose(value):
            normalized = value.lower()
            if normalized in self.unavailable_colors:
                color_error.config(text="That color is already used by another player.")
                return
            color_error.config(text="")
            selected_color.set(normalized)
            preview.config(text=value.upper(), bg=value)

        for value in self.preset_colors:
            unavailable = value.lower() in self.unavailable_colors
            tk.Button(
                swatches, bg=value, activebackground=value, disabledforeground="#555555",
                bd=0, width=4, height=2, cursor="arrow" if unavailable else "hand2",
                state="disabled" if unavailable else "normal",
                command=lambda v=value: choose(v),
            ).pack(side="left", padx=5)

        def choose_custom():
            picked = colorchooser.askcolor(color=selected_color.get(), parent=dialog)[1]
            if picked:
                choose(picked)

        tk.Button(swatches, text="+", command=choose_custom, bg="#313143", fg="#ffffff",
                  activebackground="#42425b", activeforeground="#ffffff", bd=0,
                  width=4, height=2, cursor="hand2", font=self.button_font).pack(side="left", padx=5)
        preview.pack(pady=(0, 15))
        color_error.pack()

        def close():
            dialog.destroy()

        def save():
            name = " ".join(entry.get().split())[:16]
            if selected_color.get().lower() in self.unavailable_colors:
                color_error.config(text="That color is already used by another player.")
            elif name:
                result["value"] = (name, selected_color.get())
                dialog.destroy()

        buttons = tk.Frame(dialog, bg="#121214")
        buttons.pack(fill="x", padx=55, pady=6)
        tk.Button(buttons, text="CANCEL", command=close, bg="#212128", fg="#8c8c9a",
                  activebackground="#ff4d4d", activeforeground="#ffffff", bd=0,
                  width=15, pady=8, cursor="hand2", font=self.button_font).pack(side="left")
        tk.Button(buttons, text="SAVE PROFILE", command=save, bg="#00d2ff", fg="#121214",
                  activebackground="#00a3cc", activeforeground="#121214", bd=0,
                  width=15, pady=8, cursor="hand2", font=self.button_font).pack(side="right")

        entry.bind("<Return>", lambda e: save())
        entry.bind("<Escape>", lambda e: close())
        dialog.protocol("WM_DELETE_WINDOW", close)
        entry.focus_set()
        self.parent.wait_window(dialog)
        return result["value"]

class CustomIPDialog:
    def __init__(self, parent, button_font):
        self.parent = parent
        self.button_font = button_font

    def show(self):
        result_var = tk.StringVar(value="")
        discovered = []
        
        dialog = tk.Toplevel(self.parent)
        dialog.title("Join Lobby")
        dialog.configure(bg="#121214")
        dialog.resizable(False, False)
        
        # Center dialog relative to parent window
        dialog_width = 560
        dialog_height = 470
        main_x = self.parent.winfo_x()
        main_y = self.parent.winfo_y()
        main_width = self.parent.winfo_width()
        main_height = self.parent.winfo_height()
        x = main_x + (main_width // 2) - (dialog_width // 2)
        y = main_y + (main_height // 2) - (dialog_height // 2)
        dialog.geometry(f"{dialog_width}x{dialog_height}+{x}+{y}")
        
        # Modal setup
        dialog.transient(self.parent)
        dialog.grab_set()
        
        # Header Label
        lbl_header = tk.Label(
            dialog,
            text="JOIN MULTIPLAYER ROOM",
            fg="#00d2ff",
            bg="#121214",
            font=font.Font(family="Segoe UI", size=14, weight="bold")
        )
        lbl_header.pack(pady=(20, 5))
        
        lbl_desc = tk.Label(
            dialog,
            text="Available games on your LAN or VPN network",
            fg="#8c8c9a",
            bg="#121214",
            font=font.Font(family="Segoe UI", size=10)
        )
        lbl_desc.pack(pady=(0, 10))

        list_frame = tk.Frame(dialog, bg="#1a1a24", highlightthickness=1,
                              highlightbackground="#2d2d37")
        list_frame.pack(fill="both", expand=True, padx=40, pady=5)

        game_list = tk.Listbox(
            list_frame, bg="#1a1a24", fg="#ffffff",
            selectbackground="#00d2ff", selectforeground="#121214",
            font=font.Font(family="Segoe UI", size=10), bd=0,
            highlightthickness=0, activestyle="none"
        )
        game_list.pack(fill="both", expand=True, padx=8, pady=8)

        status = tk.Label(dialog, text="Searching for games...", fg="#8c8c9a",
                          bg="#121214", font=font.Font(family="Segoe UI", size=9))
        status.pack(pady=(2, 4))
        
        # Modern Styled Text Input Box
        entry_frame = tk.Frame(
            dialog, 
            bg="#1a1a24",
            highlightthickness=1, 
            highlightbackground="#2d2d37", 
            highlightcolor="#00d2ff"
        )
        entry_frame.pack(fill="x", padx=40, pady=5)
        
        entry = tk.Entry(
            entry_frame,
            bg="#1a1a24",
            fg="#ffffff",
            font=font.Font(family="Segoe UI", size=12),
            insertbackground="#ffffff",
            bd=0,
            justify="center"
        )
        entry.pack(fill="x", padx=10, pady=8)
        entry.insert(0, "127.0.0.1")
        
        # Button panel
        btn_frame = tk.Frame(dialog, bg="#121214")
        btn_frame.pack(fill="x", padx=40, pady=(8, 18))

        def apply_results(games):
            if not dialog.winfo_exists():
                return
            discovered[:] = games
            game_list.delete(0, tk.END)
            joinable_count = 0
            for game in games:
                joinable = not game.get("game_started", False)
                if joinable:
                    joinable_count += 1
                state = "JOINABLE" if joinable else "IN GAME"
                game_list.insert(
                    tk.END,
                    f"{game.get('host', 'Host')}  |  {game['ip']}  |  "
                    f"{game.get('players', 0)}/{game.get('max_players', '?')} players  |  {state}"
                )
            if games:
                status.config(text=f"Found {len(games)} game(s), {joinable_count} joinable")
                for index, game in enumerate(games):
                    if not game.get("game_started", False):
                        game_list.selection_set(index)
                        game_list.activate(index)
                        entry.delete(0, tk.END)
                        entry.insert(0, game["ip"])
                        break
            else:
                status.config(text="No games found. Refresh or enter an IP address.")

        def refresh_games():
            status.config(text="Searching for games...")
            refresh_button.config(state="disabled")

            def worker():
                games = discover_games()
                if dialog.winfo_exists():
                    dialog.after(0, lambda: (apply_results(games), refresh_button.config(state="normal")))

            threading.Thread(target=worker, daemon=True).start()

        def on_select(_event=None):
            selection = game_list.curselection()
            if selection:
                game = discovered[selection[0]]
                entry.delete(0, tk.END)
                entry.insert(0, game["ip"])
        
        def on_cancel():
            result_var.set("")
            dialog.destroy()
            
        def on_join():
            selection = game_list.curselection()
            if selection and discovered[selection[0]].get("game_started", False):
                status.config(text="That game has already started.", fg="#ff4d4d")
                return
            val = entry.get().strip()
            if val:
                result_var.set(val)
                dialog.destroy()
                
        # Key bindings
        entry.bind("<Return>", lambda e: on_join())
        entry.bind("<Escape>", lambda e: on_cancel())
        game_list.bind("<<ListboxSelect>>", on_select)
        game_list.bind("<Double-Button-1>", lambda e: on_join())
        dialog.protocol("WM_DELETE_WINDOW", on_cancel)

        btn_cancel = tk.Button(
            btn_frame,
            text="CANCEL",
            command=on_cancel,
            bg="#212128",
            fg="#8c8c9a",
            activebackground="#ff4d4d",
            activeforeground="#ffffff",
            font=self.button_font,
            bd=0,
            width=15,
            pady=8,
            cursor="hand2"
        )
        btn_cancel.pack(side="left")

        refresh_button = tk.Button(
            btn_frame, text="REFRESH", command=refresh_games,
            bg="#313143", fg="#ffffff", activebackground="#42425b",
            activeforeground="#ffffff", font=self.button_font, bd=0,
            width=12, pady=8, cursor="hand2"
        )
        refresh_button.pack(side="left", padx=12)

        btn_join = tk.Button(
            btn_frame,
            text="CONNECT",
            command=on_join,
            bg="#00d2ff",
            fg="#121214",
            activebackground="#00a3cc",
            activeforeground="#121214",
            font=self.button_font,
            bd=0,
            width=15,
            pady=8,
            cursor="hand2"
        )
        btn_join.pack(side="right")

        refresh_games()
        
        self.parent.wait_window(dialog)
        return result_var.get()


class CustomPlayerCountDialog:
    def __init__(self, parent, button_font):
        self.parent = parent
        self.button_font = button_font

    def show(self):
        result_var = tk.StringVar(value="")
        mode_var = tk.StringVar(value="solo")
        
        dialog = tk.Toplevel(self.parent)
        dialog.title("Host Game")
        dialog.configure(bg="#121214")
        dialog.resizable(False, False)
        
        dialog_width = 440
        dialog_height = 340
        main_x = self.parent.winfo_x()
        main_y = self.parent.winfo_y()
        main_width = self.parent.winfo_width()
        main_height = self.parent.winfo_height()
        x = main_x + (main_width // 2) - (dialog_width // 2)
        y = main_y + (main_height // 2) - (dialog_height // 2)
        dialog.geometry(f"{dialog_width}x{dialog_height}+{x}+{y}")
        
        dialog.transient(self.parent)
        dialog.grab_set()
        
        lbl_header = tk.Label(
            dialog,
            text="HOST MULTIPLAYER GAME",
            fg="#ffd24d",
            bg="#121214",
            font=font.Font(family="Segoe UI", size=14, weight="bold")
        )
        lbl_header.pack(pady=(20, 5))
        
        lbl_desc = tk.Label(
            dialog,
            text="Enter maximum number of players (2 - 6):",
            fg="#8c8c9a",
            bg="#121214",
            font=font.Font(family="Segoe UI", size=10)
        )
        lbl_desc.pack(pady=(0, 10))
        
        entry_frame = tk.Frame(
            dialog, 
            bg="#1a1a24",
            highlightthickness=1, 
            highlightbackground="#2d2d37", 
            highlightcolor="#ffd24d"
        )
        entry_frame.pack(fill="x", padx=40, pady=5)
        
        entry = tk.Entry(
            entry_frame,
            bg="#1a1a24",
            fg="#ffffff",
            font=font.Font(family="Segoe UI", size=12),
            insertbackground="#ffffff",
            bd=0,
            justify="center"
        )
        entry.pack(fill="x", padx=10, pady=8)
        entry.insert(0, "4")
        entry.focus_set()
        entry.selection_range(0, tk.END)

        mode_label = tk.Label(
            dialog,
            text="Choose player mode:",
            fg="#8c8c9a",
            bg="#121214",
            font=font.Font(family="Segoe UI", size=10)
        )
        mode_label.pack(pady=(10, 6))

        mode_frame = tk.Frame(dialog, bg="#121214")
        mode_frame.pack(fill="x", padx=40)

        mode_buttons = {}

        def refresh_mode_buttons():
            selected = mode_var.get()
            for mode, button in mode_buttons.items():
                active = mode == selected
                color = "#55ff55" if mode == "solo" else "#00d2ff"
                button.config(
                    bg=color if active else "#212128",
                    fg="#121214" if active else "#ffffff",
                    highlightbackground=color if active else "#2d2d37",
                )

        def refresh_count_prompt():
            if mode_var.get() == "duo":
                lbl_desc.config(text="Enter number of duo teams (1 - 3):")
                if entry.get().strip() == "4":
                    entry.delete(0, tk.END)
                    entry.insert(0, "2")
            else:
                lbl_desc.config(text="Enter maximum number of players (2 - 6):")
                if entry.get().strip() == "2":
                    entry.delete(0, tk.END)
                    entry.insert(0, "4")
            lbl_error.config(text="")
            entry.selection_range(0, tk.END)
            entry.focus_set()

        def select_mode(mode):
            mode_var.set(mode)
            refresh_mode_buttons()
            refresh_count_prompt()

        mode_buttons["solo"] = tk.Button(
            mode_frame,
            text="SOLO\nAll actions",
            command=lambda: select_mode("solo"),
            bg="#55ff55",
            fg="#121214",
            activebackground="#55ff55",
            activeforeground="#121214",
            font=font.Font(family="Segoe UI", size=9, weight="bold"),
            bd=0,
            width=17,
            height=2,
            cursor="hand2",
            highlightthickness=1,
        )
        mode_buttons["solo"].pack(side="left", fill="x", expand=True, padx=(0, 6))

        mode_buttons["duo"] = tk.Button(
            mode_frame,
            text="DUO\nSplit roles",
            command=lambda: select_mode("duo"),
            bg="#212128",
            fg="#ffffff",
            activebackground="#00d2ff",
            activeforeground="#121214",
            font=font.Font(family="Segoe UI", size=9, weight="bold"),
            bd=0,
            width=17,
            height=2,
            cursor="hand2",
            highlightthickness=1,
        )
        mode_buttons["duo"].pack(side="right", fill="x", expand=True, padx=(6, 0))
        refresh_mode_buttons()
        
        lbl_error = tk.Label(dialog, text="", fg="#ff4d4d", bg="#121214", font=font.Font(family="Segoe UI", size=9))
        lbl_error.pack(pady=(2, 0))

        btn_frame = tk.Frame(dialog, bg="#121214")
        btn_frame.pack(fill="x", padx=40, pady=10)
        
        def on_cancel():
            result_var.set("")
            dialog.destroy()
            
        def on_submit():
            val = entry.get().strip()
            try:
                num = int(val)
                if mode_var.get() == "duo":
                    if 1 <= num <= 3:
                        result_var.set(str(num * 2))
                        dialog.destroy()
                    else:
                        lbl_error.config(text="Please enter a number of teams between 1 and 3.")
                else:
                    if 2 <= num <= 6:
                        result_var.set(str(num))
                        dialog.destroy()
                    else:
                        lbl_error.config(text="Please enter a number between 2 and 6.")
            except ValueError:
                lbl_error.config(text="Please enter a valid integer.")
                
        entry.bind("<Return>", lambda e: on_submit())
        entry.bind("<Escape>", lambda e: on_cancel())
        dialog.protocol("WM_DELETE_WINDOW", on_cancel)

        btn_cancel = tk.Button(
            btn_frame,
            text="CANCEL",
            command=on_cancel,
            bg="#212128",
            fg="#8c8c9a",
            activebackground="#ff4d4d",
            activeforeground="#ffffff",
            font=self.button_font,
            bd=0,
            width=15,
            pady=8,
            cursor="hand2"
        )
        btn_cancel.pack(side="left")

        btn_host = tk.Button(
            btn_frame,
            text="HOST",
            command=on_submit,
            bg="#ffd24d",
            fg="#121214",
            activebackground="#e6b800",
            activeforeground="#121214",
            font=self.button_font,
            bd=0,
            width=15,
            pady=8,
            cursor="hand2"
        )
        btn_host.pack(side="right")
        
        self.parent.wait_window(dialog)
        val = result_var.get()
        return (int(val), mode_var.get()) if val else None

class CustomDifficultyDialog:
    """Two-step difficulty picker: select -> confirm (or go back)."""
    def __init__(self, parent, button_font):
        self.parent = parent
        self.button_font = button_font

    def show(self):
        result_var = tk.StringVar(value="")

        dialog = tk.Toplevel(self.parent)
        dialog.title("Select Difficulty")
        dialog.configure(bg="#121214")
        dialog.resizable(False, False)

        dw, dh = 640, 340
        px = self.parent.winfo_x()
        py = self.parent.winfo_y()
        pw = self.parent.winfo_width()
        ph = self.parent.winfo_height()
        dialog.geometry(f"{dw}x{dh}+{px+pw//2-dw//2}+{py+ph//2-dh//2}")
        dialog.transient(self.parent)
        dialog.grab_set()

        LEVELS = {
            "easy":   ("\U0001f7e2 EASY",   "#55ff55", "#121214",
                       "Short words  •  Shift \xb11-5  •  3 keyholes",
                       "A relaxed cipher challenge \u2014 good for first-timers."),
            "medium": ("\U0001f7e1 MEDIUM", "#ffd24d", "#121214",
                       "Long words  •  Shift \xb11-13  •  3 keyholes",
                       "Harder words and wider shift range."),
            "hard":   ("\U0001f534 HARD",   "#ff4d4d", "#ffffff",
                       "Long words  •  Shift \xb11-13  •  4 keyholes  •  Cells close every 30 s",
                       "\u26a0\ufe0f  WARNING: Explored cells will randomly close every 30 seconds!"),
        }
        hard_level = LEVELS["hard"]
        LEVELS["hard"] = (
            hard_level[0], hard_level[1], hard_level[2],
            "Random letters  |  Shift +/-1-13  |  4 keyholes  |  Cells close every 30 s",
            hard_level[4],
        )

        # Main content container (swapped between selection and confirm views)
        container = tk.Frame(dialog, bg="#121214")
        container.pack(fill="both", expand=True)

        def clear():
            for w in container.winfo_children():
                w.destroy()

        def show_confirm(key):
            label, bg_col, fg_col, desc, warn = LEVELS[key]
            clear()

            tk.Label(container, text="CONFIRM DIFFICULTY",
                     fg="#ffd24d", bg="#121214",
                     font=font.Font(family="Segoe UI", size=14, weight="bold")
                     ).pack(pady=(24, 6))

            # Difficulty badge
            tk.Label(container, text=label,
                     fg=fg_col, bg=bg_col,
                     font=font.Font(family="Segoe UI", size=13, weight="bold"),
                     padx=18, pady=6
                     ).pack()

            tk.Label(container, text=desc,
                     fg="#8c8c9a", bg="#121214",
                     font=font.Font(family="Segoe UI", size=9)
                     ).pack(pady=(8, 2))

            tk.Label(container, text=warn,
                     fg="#ff9f1a" if key == "hard" else "#5f5f6e",
                     bg="#121214",
                     font=font.Font(family="Segoe UI", size=9, weight="bold" if key == "hard" else "normal"),
                     wraplength=420, justify="center"
                     ).pack(pady=(2, 16))

            btn_row = tk.Frame(container, bg="#121214")
            btn_row.pack()

            def go_back():
                show_select()

            def confirm():
                result_var.set(key)
                dialog.destroy()

            tk.Button(btn_row, text="\u2190  BACK",
                      command=go_back,
                      bg="#212128", fg="#8c8c9a",
                      activebackground="#2d2d37", activeforeground="#ffffff",
                      font=self.button_font, bd=0, width=12, pady=7, cursor="hand2"
                      ).pack(side="left", padx=(0, 12))

            tk.Button(btn_row, text="\u2714  CONFIRM",
                      command=confirm,
                      bg=bg_col, fg=fg_col,
                      activebackground=bg_col, activeforeground=fg_col,
                      font=self.button_font, bd=0, width=12, pady=7, cursor="hand2"
                      ).pack(side="left")

        def show_select():
            clear()

            tk.Label(container, text="SELECT DIFFICULTY",
                     fg="#ffd24d", bg="#121214",
                     font=font.Font(family="Segoe UI", size=14, weight="bold")
                     ).pack(pady=(22, 8))

            for key, (label, bg_col, fg_col, desc, _) in LEVELS.items():
                row = tk.Frame(container, bg="#121214")
                row.pack(fill="x", padx=30, pady=7)

                tk.Button(row, text=label,
                          command=lambda k=key: show_confirm(k),
                          bg=bg_col, fg=fg_col,
                          activebackground=bg_col, activeforeground=fg_col,
                          font=self.button_font, bd=0, width=14, pady=6, cursor="hand2"
                          ).pack(side="left")
                tk.Label(row, text=desc, fg="#8c8c9a", bg="#121214",
                         font=font.Font(family="Segoe UI", size=9), justify="left",
                         wraplength=440
                         ).pack(side="left", padx=12)

            tk.Button(container, text="CANCEL",
                      command=dialog.destroy,
                      bg="#212128", fg="#8c8c9a",
                      activebackground="#ff4d4d", activeforeground="#ffffff",
                      font=self.button_font, bd=0, pady=6, width=14, cursor="hand2"
                      ).pack(pady=(4, 16))

        show_select()   # start on the selection screen

        dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)
        self.parent.wait_window(dialog)
        return result_var.get() or None


class CustomLockDialog:
    def __init__(self, parent, button_font):
        self.parent = parent
        self.button_font = button_font

    def show(self):
        result_var = tk.StringVar(value="")
        
        dialog = tk.Toplevel(self.parent)
        dialog.title("Security Lock")
        dialog.configure(bg="#121214")
        dialog.resizable(False, False)
        
        dialog_width = 400
        dialog_height = 220
        main_x = self.parent.winfo_x()
        main_y = self.parent.winfo_y()
        main_width = self.parent.winfo_width()
        main_height = self.parent.winfo_height()
        x = main_x + (main_width // 2) - (dialog_width // 2)
        y = main_y + (main_height // 2) - (dialog_height // 2)
        dialog.geometry(f"{dialog_width}x{dialog_height}+{x}+{y}")
        
        dialog.transient(self.parent)
        dialog.grab_set()
        
        lbl_header = tk.Label(
            dialog,
            text="🔓 ENTER ITEM DECRYPT KEY",
            fg="#ffd24d",
            bg="#121214",
            font=font.Font(family="Segoe UI", size=13, weight="bold")
        )
        lbl_header.pack(pady=(20, 5))
        
        lbl_desc = tk.Label(
            dialog,
            text="Enter the numeric key discovered on the grid:",
            fg="#8c8c9a",
            bg="#121214",
            font=font.Font(family="Segoe UI", size=9)
        )
        lbl_desc.pack(pady=(0, 10))
        
        entry_frame = tk.Frame(
            dialog, 
            bg="#1a1a24",
            highlightthickness=1, 
            highlightbackground="#2d2d37", 
            highlightcolor="#ffd24d"
        )
        entry_frame.pack(fill="x", padx=50, pady=5)
        
        entry = tk.Entry(
            entry_frame,
            bg="#1a1a24",
            fg="#ffffff",
            font=font.Font(family="Segoe UI", size=14, weight="bold"),
            insertbackground="#ffffff",
            bd=0,
            justify="center"
        )
        entry.pack(fill="x", padx=10, pady=8)
        entry.focus_set()
        
        btn_frame = tk.Frame(dialog, bg="#121214")
        btn_frame.pack(fill="x", padx=50, pady=15)
        
        def on_cancel():
            result_var.set("")
            dialog.destroy()
            
        def on_submit():
            val = entry.get().strip()
            if val.isdigit():
                result_var.set(val)
                dialog.destroy()
            else:
                from tkinter import messagebox
                messagebox.showerror("Invalid Input", "Please enter a valid numeric key sequence!")
                
        entry.bind("<Return>", lambda e: on_submit())
        entry.bind("<Escape>", lambda e: on_cancel())
        dialog.protocol("WM_DELETE_WINDOW", on_cancel)
        
        btn_cancel = tk.Button(
            btn_frame,
            text="CANCEL",
            command=on_cancel,
            bg="#212128",
            fg="#8c8c9a",
            activebackground="#ff4d4d",
            activeforeground="#ffffff",
            bd=0,
            padx=15,
            pady=5,
            font=self.button_font,
            cursor="hand2"
        )
        btn_cancel.pack(side="left", fill="x", expand=True, padx=(0, 10))
        
        btn_submit = tk.Button(
            btn_frame,
            text="SUBMIT KEY",
            command=on_submit,
            bg="#ffd24d",
            fg="#121214",
            activebackground="#e6b800",
            activeforeground="#121214",
            bd=0,
            padx=15,
            pady=5,
            font=self.button_font,
            cursor="hand2"
        )
        btn_submit.pack(side="right", fill="x", expand=True, padx=(10, 0))
        
        self.parent.wait_window(dialog)
        return result_var.get()


class LockScreenDialog:
    """Dynamic vault screen for three or four item keyholes.

    items_data entries contain:
      { "index": int, "pos": (r,c), "key": str|None, "collected": bool, "discovered": bool }
    on_submit(pos, entered_key) should return True (success), False (wrong), or None (async).
    """
    def __init__(self, parent, button_font, items_data, on_submit):
        self.parent = parent
        self.button_font = button_font
        self.items_data = items_data
        self.on_submit = on_submit

    @staticmethod
    def panel_grid_positions(item_count):
        columns = 2 if item_count == 4 else max(1, item_count)
        return [(index // columns, index % columns) for index in range(item_count)]

    def show(self):
        dialog = tk.Toplevel(self.parent)
        dialog.title("Security Vault")
        dialog.configure(bg="#0e0e16")
        dialog.resizable(False, False)

        n   = len(self.items_data)
        four_key_mode = n == 4
        dw = 500 if four_key_mode else max(680, 200 * n + 80)
        dh = 690 if four_key_mode else 400
        px  = self.parent.winfo_x()
        py  = self.parent.winfo_y()
        pw  = self.parent.winfo_width()
        ph  = self.parent.winfo_height()
        dialog.geometry(f"{dw}x{dh}+{px + pw//2 - dw//2}+{py + ph//2 - dh//2}")
        dialog.transient(self.parent)
        dialog.grab_set()

        # Header
        tk.Label(dialog, text="\U0001f512 SECURITY VAULT",
                 fg="#ffd24d", bg="#0e0e16",
                 font=font.Font(family="Segoe UI", size=16, weight="bold")
                 ).pack(pady=(18, 2))
        tk.Label(dialog, text="Explore the map to discover keys, then enter them to collect items.",
                 fg="#5f5f6e", bg="#0e0e16",
                 font=font.Font(family="Segoe UI", size=9)
                 ).pack(pady=(0, 14))

        # Dynamic keyhole panels
        panel_grid = tk.Frame(dialog, bg="#0e0e16")
        panel_grid.pack(fill="both", expand=True, padx=18)
        column_count = 2 if four_key_mode else max(1, n)
        row_count = 2 if four_key_mode else 1
        for col in range(column_count):
            panel_grid.columnconfigure(col, weight=1, uniform="keyhole")
        for row in range(row_count):
            panel_grid.rowconfigure(row, weight=1, uniform="keyhole_row")

        for item, (row, col) in zip(self.items_data, self.panel_grid_positions(n)):
            self._build_panel(panel_grid, item, dialog, row=row, col=col)

        # Close
        tk.Button(dialog, text="CLOSE", command=dialog.destroy,
                  bg="#1a1a24", fg="#8c8c9a",
                  activebackground="#2d2d37", activeforeground="#ffffff",
                  bd=0, padx=20, pady=7,
                  font=self.button_font, cursor="hand2"
                  ).pack(pady=16)

        self.parent.wait_window(dialog)

    def _build_panel(self, parent, item, dialog, row=0, col=0):
        idx        = item["index"]
        pos        = item["pos"]
        key        = item["key"]
        collected  = item["collected"]
        discovered = item["discovered"]
        is_at      = item.get("is_at", False)  # player is standing on this item

        # Fixed-size panel so all keyholes are identical regardless of content.
        panel = tk.Frame(parent, bg="#1a1a24", bd=2, relief="groove",
                         width=180, height=260)
        panel.grid(row=row, column=col, sticky="nsew", padx=7, pady=4)
        panel.pack_propagate(False)   # prevent content from resizing the frame

        tk.Label(panel, text=f"KEYHOLE  #{idx}",
                 fg="#8c8c9a", bg="#1a1a24",
                 font=font.Font(family="Segoe UI", size=9, weight="bold")
                 ).pack(pady=(10, 4))

        if collected:
            tk.Label(panel, text="\u2705", bg="#1a1a24",
                     font=font.Font(family="Segoe UI", size=28)).pack()
            tk.Label(panel, text="COLLECTED", fg="#55ff55", bg="#1a1a24",
                     font=font.Font(family="Segoe UI", size=10, weight="bold")
                     ).pack(pady=(4, 14))
            return

        # Parse key for Caesar cipher clues
        cipher_clue = ""
        formula_clue = ""
        if key and "|" in key:
            parts = key.split("|")
            if len(parts) >= 3:
                orig_w, cipher_w, shift_str = parts[:3]
                mode = parts[3] if len(parts) >= 4 else "decrypt"
                shift = int(shift_str)
                if mode == "encrypt":
                    sign = "+" if shift > 0 else "-"
                    cipher_clue = f"Encrypt: {orig_w}"
                    formula_clue = f"Formula: P {sign} {abs(shift)}"
                else:
                    sign = "-" if shift > 0 else "+"
                    cipher_clue = f"Decrypt: {cipher_w}"
                    formula_clue = f"Formula: C {sign} {abs(shift)}"

        if not discovered:
            # Not yet found on the map
            tk.Label(panel, text="\U0001f512", bg="#1a1a24",
                     font=font.Font(family="Segoe UI", size=28)).pack()
            tk.Label(panel, text="Explore the map\nto find this key",
                     fg="#5f5f6e", bg="#1a1a24",
                     font=font.Font(family="Segoe UI", size=8), justify="center"
                     ).pack(pady=(2, 14))
            return

        if not is_at:
            # Discovered but player is not standing on it
            tk.Label(panel, text="\U0001f4cd", bg="#1a1a24",
                     font=font.Font(family="Segoe UI", size=24)).pack()
            if cipher_clue:
                tk.Label(panel, text=cipher_clue, fg="#ffd24d", bg="#1a1a24",
                         font=font.Font(family="Segoe UI", size=9, weight="bold")).pack()
                tk.Label(panel, text=formula_clue, fg="#00d2ff", bg="#1a1a24",
                         font=font.Font(family="Segoe UI", size=8, weight="bold")).pack()
            tk.Label(panel, text="Stand on item\nto unlock",
                     fg="#ff9f1a", bg="#1a1a24",
                     font=font.Font(family="Segoe UI", size=8), justify="center"
                     ).pack(pady=(4, 14))
            return

        # Player is standing on a discovered item — show unlock entry
        tk.Label(panel, text="\U0001f513", bg="#1a1a24",
                 font=font.Font(family="Segoe UI", size=24)).pack()
        if cipher_clue:
            tk.Label(panel, text=cipher_clue, fg="#ffd24d", bg="#1a1a24",
                     font=font.Font(family="Segoe UI", size=9, weight="bold")).pack()
            tk.Label(panel, text=formula_clue, fg="#00d2ff", bg="#1a1a24",
                     font=font.Font(family="Segoe UI", size=8, weight="bold")).pack()
        else:
            tk.Label(panel, text="You're here! Enter word:",
                     fg="#ffd24d", bg="#1a1a24",
                     font=font.Font(family="Segoe UI", size=8)
                     ).pack(pady=(2, 4))

        ef = tk.Frame(panel, bg="#0e0e16",
                      highlightthickness=1,
                      highlightbackground="#2d2d37",
                      highlightcolor="#ffd24d")
        ef.pack(fill="x", padx=12, pady=(2, 4))
        entry = tk.Entry(ef, bg="#0e0e16", fg="#ffffff", bd=0,
                         font=font.Font(family="Segoe UI", size=10, weight="bold"),
                         insertbackground="#ffffff", justify="center",
                         validate="key",
                         validatecommand=(ef.register(lambda s: s.isalpha() or s == ""), "%P"))
        entry.pack(fill="x", padx=8, pady=4)

        res_lbl = tk.Label(panel, text="", bg="#1a1a24",
                           font=font.Font(family="Segoe UI", size=8))
        res_lbl.pack()

        # Rebuild panel widgets on success
        def on_success(pnl=panel, i=idx):
            for w in pnl.winfo_children():
                w.destroy()
            pnl.pack_propagate(False)   # keep fixed size after rebuild
            tk.Label(pnl, text=f"KEYHOLE  #{i}",
                     fg="#8c8c9a", bg="#1a1a24",
                     font=font.Font(family="Segoe UI", size=9, weight="bold")
                     ).pack(pady=(14, 4))
            tk.Label(pnl, text="\u2705", bg="#1a1a24",
                     font=font.Font(family="Segoe UI", size=28)).pack()
            tk.Label(pnl, text="COLLECTED!", fg="#55ff55", bg="#1a1a24",
                     font=font.Font(family="Segoe UI", size=10, weight="bold")
                     ).pack(pady=(4, 14))

        def submit(p=pos, e=entry, rl=res_lbl, dlg=dialog):
            val = e.get().strip().upper()
            if not val:
                return
            result = self.on_submit(p, val)
            if result is True:
                on_success()
            elif result is False:
                rl.config(text="\u274c Wrong key! Try again.", fg="#ff4d4d")
                e.delete(0, tk.END)
            else:
                # Async (multiplayer) — close dialog
                dlg.destroy()

        btn = tk.Button(panel, text="UNLOCK",
                        command=submit,
                        bg="#ffd24d", fg="#121214",
                        activebackground="#e6b800", activeforeground="#121214",
                        bd=0, padx=10, pady=4,
                        font=self.button_font, cursor="hand2")
        btn.pack(pady=(2, 10))
        entry.bind("<Return>", lambda e: submit())


class TeleportDialog:
    def __init__(self, parent, button_font, players_info, my_id, on_select, colors, color_names,
                 title="CHOOSE PLAYER TO TELEPORT", include_self=False):
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("Teleport Powerup")
        self.dialog.geometry("380x350")
        self.dialog.configure(bg="#121214")
        self.dialog.resizable(False, False)
        self.dialog.transient(parent)
        self.dialog.grab_set()

        # Center dialog
        self.dialog.update_idletasks()
        width = 380
        height = 350
        main_x = parent.winfo_x()
        main_y = parent.winfo_y()
        main_width = parent.winfo_width()
        main_height = parent.winfo_height()
        x = main_x + (main_width // 2) - (width // 2)
        y = main_y + (main_height // 2) - (height // 2)
        self.dialog.geometry(f"{width}x{height}+{x}+{y}")

        lbl_title = tk.Label(
            self.dialog,
            text=title,
            fg="#ffd24d",
            bg="#121214",
            font=font.Font(family="Segoe UI", size=13, weight="bold")
        )
        lbl_title.pack(pady=(20, 10))

        lbl_desc = tk.Label(
            self.dialog,
            text="Target will be moved to a random undiscovered cell.",
            fg="#8c8c9a",
            bg="#121214",
            font=font.Font(family="Segoe UI", size=9)
        )
        lbl_desc.pack(pady=(0, 15))

        other_players = []
        for pid, pinfo in players_info.items():
            try:
                p_id_int = int(pid)
                my_id_int = int(my_id)
            except (ValueError, TypeError):
                p_id_int = pid
                my_id_int = my_id
                
            if include_self or p_id_int != my_id_int:
                other_players.append((p_id_int, pinfo))

        if not other_players:
            lbl_none = tk.Label(
                self.dialog,
                text="No other players in game!",
                fg="#ff4d4d",
                bg="#121214",
                font=font.Font(family="Segoe UI", size=10, weight="bold")
            )
            lbl_none.pack(pady=40)
            
            btn_close = tk.Button(
                self.dialog,
                text="CANCEL",
                bg="#2a2a36",
                fg="#ffffff",
                relief="flat",
                font=button_font,
                command=self.dialog.destroy,
                bd=0,
                width=15,
                pady=6,
                cursor="hand2"
            )
            btn_close.pack(pady=10)
        else:
            frame_buttons = tk.Frame(self.dialog, bg="#121214")
            frame_buttons.pack(pady=5, fill="both", expand=True)

            for pid, pinfo in other_players:
                color_hex = pinfo.get("color", colors[(pid - 1) % len(colors)])
                player_name = pinfo.get("name", f"Player {pid}")
                
                btn = tk.Button(
                    frame_buttons,
                    text=f"{player_name} (P{pid})" + (" - YOU" if str(pid) == str(my_id) else ""),
                    bg=color_hex,
                    fg="#121214" if color_hex != "#121214" else "#ffffff",
                    activebackground=color_hex,
                    activeforeground="#121214",
                    font=font.Font(family="Segoe UI", size=10, weight="bold"),
                    relief="flat",
                    bd=0,
                    height=2,
                    cursor="hand2",
                    command=lambda p=pid: [on_select(p), self.dialog.destroy()]
                )
                btn.pack(pady=5, padx=40, fill="x")

            btn_cancel = tk.Button(
                self.dialog,
                text="CANCEL",
                bg="#212128",
                fg="#8c8c9a",
                activebackground="#ff4d4d",
                activeforeground="#ffffff",
                relief="flat",
                font=button_font,
                bd=0,
                width=15,
                pady=6,
                cursor="hand2",
                command=self.dialog.destroy
            )
            btn_cancel.pack(pady=15)
