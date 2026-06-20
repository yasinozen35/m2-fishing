"""
ui_overlay.py — Oyun penceresi üzerine çizilen şeffaf hizalama şablonu.
Kullanıcının Zırh, Sohbet ve Çöp kutularını görsel olarak oyuna oturtmasını sağlar.
"""
import tkinter as tk
from fishing_bot.config import AutoBotConfig
from fishing_bot.window_utils import GameWindow

class AlignmentOverlay:
    def __init__(self, parent_tk: tk.Tk, config: AutoBotConfig):
        self.parent = parent_tk
        self.config = config
        self.overlays = []

    def show(self, windows: list[GameWindow]):
        self.hide() # Varsa eskileri kapat

        if not windows:
            return

        for w in windows:
            top = tk.Toplevel(self.parent)
            top.title(f"Overlay - {w.title}")
            
            # Şeffaf ve pencere çerçevesiz
            top.attributes('-alpha', 0.8)
            top.attributes('-topmost', True)
            top.overrideredirect(True)
            top.geometry(f"{w.width}x{w.height}+{w.left}+{w.top}")
            
            try:
                # Sadece beyaz rengi tamamen şeffaf ve tıklama geçirgen (click-through) yapar
                top.wm_attributes("-transparentcolor", "white")
            except Exception:
                pass

            canvas = tk.Canvas(top, bg='white', highlightthickness=0)
            canvas.pack(fill='both', expand=True)

            # --- SOHBET ---
            cx, cy = self.config.rel_chat_x, self.config.rel_chat_y
            cw, ch = self.config.rel_chat_w, self.config.rel_chat_h
            canvas.create_rectangle(cx, cy, cx+cw, cy+ch, outline='red', width=3)
            canvas.create_text(cx + cw//2, cy + ch//2, text="Sohbet (Chat)\nBuraya Hizalayin", fill='red', font=('Arial', 14, 'bold'))

            # --- ZIRH ---
            ax, ay = self.config.rel_armor_x, self.config.rel_armor_y
            canvas.create_rectangle(ax-18, ay-18, ax+18, ay+18, outline='green', width=3)
            canvas.create_text(ax, ay-30, text="Zırh Slotu", fill='green', font=('Arial', 12, 'bold'))


            
            # Ekranın ortasına bilgi yazısı
            canvas.create_text(w.width//2, 50, text="HİZALAMA MODU AKTİF", fill='blue', font=('Arial', 20, 'bold'))
            canvas.create_text(w.width//2, 80, text="Oyun içi pencereleri (Envanter, Sohbet) ilgili kutulara sürükleyin.", fill='blue', font=('Arial', 12))
            
            self.overlays.append(top)

    def hide(self):
        for top in self.overlays:
            try:
                top.destroy()
            except Exception:
                pass
        self.overlays.clear()
