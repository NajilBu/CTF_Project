import tkinter as tk
from tkinter import font

class CustomIPDialog:
    def __init__(self, parent, button_font):
        self.parent = parent
        self.button_font = button_font

    def show(self):
        result_var = tk.StringVar(value="")
        
        dialog = tk.Toplevel(self.parent)
        dialog.title("Join Lobby")
        dialog.configure(bg="#121214")
        dialog.resizable(False, False)
        
        # Center dialog relative to parent window
        dialog_width = 440
        dialog_height = 240
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
            text="Enter Host Radmin VPN or LAN IP address:",
            fg="#8c8c9a",
            bg="#121214",
            font=font.Font(family="Segoe UI", size=10)
        )
        lbl_desc.pack(pady=(0, 15))
        
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
        entry.focus_set()
        entry.selection_range(0, tk.END)
        
        # Button panel
        btn_frame = tk.Frame(dialog, bg="#121214")
        btn_frame.pack(fill="x", padx=40, pady=25)
        
        def on_cancel():
            result_var.set("")
            dialog.destroy()
            
        def on_join():
            val = entry.get().strip()
            if val:
                result_var.set(val)
                dialog.destroy()
                
        # Key bindings
        entry.bind("<Return>", lambda e: on_join())
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
        
        self.parent.wait_window(dialog)
        return result_var.get()


class CustomPlayerCountDialog:
    def __init__(self, parent, button_font):
        self.parent = parent
        self.button_font = button_font

    def show(self):
        result_var = tk.StringVar(value="")
        
        dialog = tk.Toplevel(self.parent)
        dialog.title("Host Game")
        dialog.configure(bg="#121214")
        dialog.resizable(False, False)
        
        dialog_width = 440
        dialog_height = 240
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
        lbl_desc.pack(pady=(0, 15))
        
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
        return int(val) if val else None

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
    """3-keyhole vault screen. items_data is a list of 3 dicts:
      { "index": int (1-3), "pos": (r,c), "key": str|None, "collected": bool, "discovered": bool }
    on_submit(pos, entered_key) should return True (success), False (wrong), or None (async).
    """
    def __init__(self, parent, button_font, items_data, on_submit):
        self.parent = parent
        self.button_font = button_font
        self.items_data = items_data
        self.on_submit = on_submit

    def show(self):
        dialog = tk.Toplevel(self.parent)
        dialog.title("Security Vault")
        dialog.configure(bg="#0e0e16")
        dialog.resizable(False, False)

        dw, dh = 680, 400
        px = self.parent.winfo_x()
        py = self.parent.winfo_y()
        pw = self.parent.winfo_width()
        ph = self.parent.winfo_height()
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

        # 3 keyhole panels — grid with uniform columns for equal sizing
        row = tk.Frame(dialog, bg="#0e0e16")
        row.pack(fill="x", padx=18)
        for col in range(3):
            row.columnconfigure(col, weight=1, uniform="keyhole")

        for i, item in enumerate(self.items_data):
            self._build_panel(row, item, dialog, col=i)

        # Close
        tk.Button(dialog, text="CLOSE", command=dialog.destroy,
                  bg="#1a1a24", fg="#8c8c9a",
                  activebackground="#2d2d37", activeforeground="#ffffff",
                  bd=0, padx=20, pady=7,
                  font=self.button_font, cursor="hand2"
                  ).pack(pady=16)

        self.parent.wait_window(dialog)

    def _build_panel(self, parent, item, dialog, col=0):
        idx        = item["index"]
        pos        = item["pos"]
        key        = item["key"]
        collected  = item["collected"]
        discovered = item["discovered"]

        # Fixed-size panel so all 3 are identical regardless of content
        panel = tk.Frame(parent, bg="#1a1a24", bd=2, relief="groove",
                         width=180, height=260)
        panel.grid(row=0, column=col, sticky="nsew", padx=7, pady=4)
        panel.pack_propagate(False)   # prevent content from resizing the frame

        tk.Label(panel, text=f"KEYHOLE  #{idx}",
                 fg="#8c8c9a", bg="#1a1a24",
                 font=font.Font(family="Segoe UI", size=9, weight="bold")
                 ).pack(pady=(14, 4))

        if collected:
            tk.Label(panel, text="\u2705", bg="#1a1a24",
                     font=font.Font(family="Segoe UI", size=28)).pack()
            tk.Label(panel, text="COLLECTED", fg="#55ff55", bg="#1a1a24",
                     font=font.Font(family="Segoe UI", size=10, weight="bold")
                     ).pack(pady=(4, 14))
            return

        # Both discovered and undiscovered show an entry field.
        # Icon and subtitle differ to hint the player.
        if discovered:
            tk.Label(panel, text="\U0001f513", bg="#1a1a24",
                     font=font.Font(family="Segoe UI", size=28)).pack()
            tk.Label(panel, text="Key discovered!",
                     fg="#ffd24d", bg="#1a1a24",
                     font=font.Font(family="Segoe UI", size=8)
                     ).pack(pady=(2, 4))
        else:
            tk.Label(panel, text="\U0001f512", bg="#1a1a24",
                     font=font.Font(family="Segoe UI", size=28)).pack()
            tk.Label(panel, text="Explore the map\nto find this key",
                     fg="#5f5f6e", bg="#1a1a24",
                     font=font.Font(family="Segoe UI", size=8), justify="center"
                     ).pack(pady=(2, 4))

        ef = tk.Frame(panel, bg="#0e0e16",
                      highlightthickness=1,
                      highlightbackground="#2d2d37",
                      highlightcolor="#ffd24d")
        ef.pack(fill="x", padx=12, pady=(0, 4))
        entry = tk.Entry(ef, bg="#0e0e16", fg="#ffffff", bd=0,
                         font=font.Font(family="Segoe UI", size=12, weight="bold"),
                         insertbackground="#ffffff", justify="center",
                         validate="key",
                         validatecommand=(ef.register(lambda s: s.isdigit() or s == ""), "%P"))
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
            val = e.get().strip()
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
        btn.pack(pady=(0, 14))
        entry.bind("<Return>", lambda e: submit())
