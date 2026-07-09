import os
import threading

# Window Sizing
WINDOW_WIDTH  = 1920
WINDOW_HEIGHT = 1080

# Grid Parameters
GRID_ROWS   = 10
GRID_COLS   = 20
CELL_SIZE   = 65
CANVAS_WIDTH  = GRID_COLS * CELL_SIZE   # 1300
CANVAS_HEIGHT = GRID_ROWS * CELL_SIZE   # 650



# Player Colors
COLORS = ["#00d2ff", "#ff4d4d", "#ffc837", "#55ff55", "#d800ff", "#ff9000"]
COLOR_NAMES = ["Cyan", "Red", "Yellow", "Green", "Magenta", "Orange"]

# Load winsound on Windows for audio beeps
if os.name == 'nt':
    import winsound
else:
    winsound = None

def play_sound(sound_type):
    """Play a cross-platform beep sound asynchronously."""
    if not winsound:
        return
    
    def beep():
        try:
            if sound_type == "move":
                winsound.Beep(300, 40)
            elif sound_type == "reset":
                winsound.Beep(600, 150)
            elif sound_type == "click":
                winsound.Beep(450, 60)
            elif sound_type == "qte_correct":
                winsound.Beep(800, 60)
            elif sound_type == "qte_wrong":
                winsound.Beep(200, 150)
            elif sound_type == "qte_success":
                winsound.Beep(900, 80)
                winsound.Beep(1200, 100)
            elif sound_type == "collect":
                winsound.Beep(1200, 80)
                winsound.Beep(1500, 120)
            elif sound_type == "item_found":
                winsound.Beep(750, 100)
                winsound.Beep(1000, 150)
        except Exception:
            pass

    threading.Thread(target=beep, daemon=True).start()
