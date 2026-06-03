"""
gui.py — Metin2 Balık Botu için Modern Masaüstü Arayüzü.

customtkinter tabanlıdır. Bot mantığını arka planda (Thread) çalıştırır.
"""

import sys
import threading
import time
from typing import Optional

import customtkinter as ctk
import pyautogui

from fishing_bot.config import Config
from fishing_bot.bot_logic import BotLogic
from fishing_bot.screen_capture import ScreenCapture
from fishing_bot.detector import Detector
from fishing_bot.clicker import HumanClicker
from fishing_bot.overlay import DebugOverlay

# Arayüz Teması
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")


class BotRunnerThread(threading.Thread):
    """Botu arka planda çalıştıran Thread."""
    
    def __init__(self, config: Config, log_callback, status_callback):
        super().__init__(daemon=True)
        self.config = config
        self.log_callback = log_callback
        self.status_callback = status_callback
        self.running = False
        
        # Bileşenler
        self.capture: Optional[ScreenCapture] = None
        self.detector: Optional[Detector] = None
        self.clicker: Optional[HumanClicker] = None
        self.overlay: Optional[DebugOverlay] = None
        self.bot_logic: Optional[BotLogic] = None

    def stop(self):
        self.running = False

    def run(self):
        self.running = True
        self.log_callback("Bot baslatiliyor...")
        
        try:
            self.capture = ScreenCapture(self.config.capture)
            self.detector = Detector(self.config.circle, self.config.fish)
            self.clicker = HumanClicker(self.config.human, self.config.capture)
            self.overlay = DebugOverlay() if self.config.debug_mode else None
            
            self.bot_logic = BotLogic(self.config.autobot, self.clicker, self.capture)
            self.bot_logic.start()
            
            self.log_callback("Bot calisiyor! (Otonom Mod)")
            
            frame_interval = 1.0 / self.config.target_fps
            
            while self.running:
                loop_start = time.time()
                
                frame = self.capture.grab_frame()
                result = self.detector.detect(frame)
                
                clicked, status_msg = self.bot_logic.update(result, detector=self.detector)
                
                # UI'ı güncelle (Çok sık olmaması için log yerine sadece status'u güncelle)
                self.status_callback(
                    status_msg, 
                    self.bot_logic.successful_catches, 
                    self.bot_logic.total_casts
                )
                
                if self.overlay:
                    self.overlay.render(frame, result, clicked=clicked)
                
                elapsed = time.time() - loop_start
                sleep_time = frame_interval - elapsed
                if sleep_time > 0:
                    time.sleep(sleep_time)
                    
        except Exception as e:
            self.log_callback(f"Hata: {str(e)}")
        finally:
            if self.capture:
                self.capture.close()
            if self.overlay:
                self.overlay.close()
            self.log_callback("Bot durduruldu.")


class FishingBotGUI(ctk.CTk):
    """Ana GUI Sınıfı"""
    
    def __init__(self):
        super().__init__()
        
        self.title("🎣 Metin2 Otonom Balık Botu V2")
        self.geometry("700x550")
        self.config = Config()
        self.bot_thread: Optional[BotRunnerThread] = None
        
        # Grid Yapılandırması
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        
        # ── Sol Menü (Kontroller) ──
        self.sidebar_frame = ctk.CTkFrame(self, width=200, corner_radius=0)
        self.sidebar_frame.grid(row=0, column=0, sticky="nsew")
        self.sidebar_frame.grid_rowconfigure(4, weight=1)
        
        self.logo_label = ctk.CTkLabel(self.sidebar_frame, text="FishBot V2", font=ctk.CTkFont(size=20, weight="bold"))
        self.logo_label.grid(row=0, column=0, padx=20, pady=(20, 10))
        
        self.btn_start = ctk.CTkButton(self.sidebar_frame, text="▶ Başlat", fg_color="green", hover_color="darkgreen", command=self.toggle_bot)
        self.btn_start.grid(row=1, column=0, padx=20, pady=10)
        
        self.btn_calibrate = ctk.CTkButton(self.sidebar_frame, text="🎯 Kalibrasyon", command=self.run_calibration)
        self.btn_calibrate.grid(row=2, column=0, padx=20, pady=10)
        
        self.switch_debug = ctk.CTkSwitch(self.sidebar_frame, text="Debug Görünümü")
        self.switch_debug.grid(row=3, column=0, padx=20, pady=10)
        self.switch_debug.select()
        
        # ── Sağ İçerik (Sekmeler) ──
        self.tabview = ctk.CTkTabview(self, width=500)
        self.tabview.grid(row=0, column=1, padx=20, pady=20, sticky="nsew")
        
        self.tabview.add("Ana Ekran")
        self.tabview.add("Ayarlar")
        self.tabview.add("Zırh & Ekstralar")
        
        self._build_dashboard_tab()
        self._build_settings_tab()
        self._build_extras_tab()
        
    def _build_dashboard_tab(self):
        tab = self.tabview.tab("Ana Ekran")
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(1, weight=1)
        
        # İstatistikler
        self.stats_frame = ctk.CTkFrame(tab)
        self.stats_frame.grid(row=0, column=0, padx=10, pady=10, sticky="ew")
        
        self.lbl_status = ctk.CTkLabel(self.stats_frame, text="Durum: Bekliyor", font=ctk.CTkFont(weight="bold"))
        self.lbl_status.grid(row=0, column=0, padx=20, pady=10)
        
        self.lbl_catches = ctk.CTkLabel(self.stats_frame, text="Tutan Balık: 0", text_color="green")
        self.lbl_catches.grid(row=0, column=1, padx=20, pady=10)
        
        self.lbl_casts = ctk.CTkLabel(self.stats_frame, text="Atış Sayısı: 0")
        self.lbl_casts.grid(row=0, column=2, padx=20, pady=10)
        
        # Konsol/Log
        self.log_textbox = ctk.CTkTextbox(tab, height=200)
        self.log_textbox.grid(row=1, column=0, padx=10, pady=10, sticky="nsew")
        self.log("Sistem basariyla yuklendi.")
        
    def _build_settings_tab(self):
        tab = self.tabview.tab("Ayarlar")
        
        ctk.CTkLabel(tab, text="Klavye Tuşları", font=ctk.CTkFont(weight="bold")).pack(pady=(10, 5))
        
        f1 = ctk.CTkFrame(tab)
        f1.pack(fill="x", padx=10, pady=5)
        ctk.CTkLabel(f1, text="Yem Tuşu:").pack(side="left", padx=10)
        self.entry_bait = ctk.CTkEntry(f1, width=50)
        self.entry_bait.insert(0, "1")
        self.entry_bait.pack(side="right", padx=10, pady=5)
        
        f2 = ctk.CTkFrame(tab)
        f2.pack(fill="x", padx=10, pady=5)
        ctk.CTkLabel(f2, text="Olta Tuşu:").pack(side="left", padx=10)
        self.entry_fish = ctk.CTkEntry(f2, width=80)
        self.entry_fish.insert(0, "space")
        self.entry_fish.pack(side="right", padx=10, pady=5)

    def _build_extras_tab(self):
        tab = self.tabview.tab("Zırh & Ekstralar")
        
        # Zırh Çıkar Tak
        ctk.CTkLabel(tab, text="Zırh Animasyon İptali (Çıkar/Tak)", font=ctk.CTkFont(weight="bold")).pack(pady=(10, 5))
        
        self.switch_armor = ctk.CTkSwitch(tab, text="Zırh Tricki Aktif")
        self.switch_armor.pack(pady=10)
        
        self.lbl_armor_pos = ctk.CTkLabel(tab, text="Zırh Konumu: Ayarlanmadı")
        self.lbl_armor_pos.pack(pady=5)
        
        self.btn_set_armor = ctk.CTkButton(tab, text="📍 Zırh Konumunu Seç", command=self.start_armor_pos_selection)
        self.btn_set_armor.pack(pady=5)
        
        ctk.CTkLabel(tab, text="Not: Butona basınca 3 saniye içinde mouse'u\nenvanterdeki zırhın üstüne götürün.", text_color="gray").pack(pady=5)

    # ── Metodlar ──
    
    def log(self, message: str):
        self.log_textbox.insert("end", f"[{time.strftime('%H:%M:%S')}] {message}\n")
        self.log_textbox.see("end")
        
    def update_status(self, status: str, catches: int, casts: int):
        # Arayüz güncellemeleri ana thread'de yapılmalı
        self.after(0, self._update_status_gui, status, catches, casts)
        
    def _update_status_gui(self, status: str, catches: int, casts: int):
        self.lbl_status.configure(text=f"Durum: {status}")
        self.lbl_catches.configure(text=f"Tutan Balık: {catches}")
        self.lbl_casts.configure(text=f"Atış Sayısı: {casts}")

    def toggle_bot(self):
        if self.bot_thread and self.bot_thread.running:
            # Durdur
            self.bot_thread.stop()
            self.bot_thread.join(timeout=2.0)
            self.btn_start.configure(text="▶ Başlat", fg_color="green", hover_color="darkgreen")
            self.btn_calibrate.configure(state="normal")
            self.log("Bot durduruluyor...")
        else:
            # Configleri arayüzden al
            self.config.debug_mode = self.switch_debug.get() == 1
            self.config.autobot.key_bait = self.entry_bait.get()
            self.config.autobot.key_fish = self.entry_fish.get()
            self.config.autobot.use_armor_trick = self.switch_armor.get() == 1
            
            # Başlat
            self.btn_start.configure(text="⏹ Durdur", fg_color="red", hover_color="darkred")
            self.btn_calibrate.configure(state="disabled")
            
            self.bot_thread = BotRunnerThread(self.config, self.log, self.update_status)
            self.bot_thread.start()

    def run_calibration(self):
        from fishing_bot.main import run_calibration as rc
        self.log("Kalibrasyon baslatildi. Tam ekran goruntusunden oyunu secin.")
        rc(self.config)
        self.log(f"Bolge ayarlandi: {self.config.capture.width}x{self.config.capture.height}")
        
    def start_armor_pos_selection(self):
        self.btn_set_armor.configure(state="disabled")
        self.log("Lutfen 3 saniye icinde mouse'u zirhin uzerine getirin...")
        # 3 saniye bekle (arka planda UI'ı kilitlemeden)
        self.after(3000, self.save_armor_pos)
        
    def save_armor_pos(self):
        x, y = pyautogui.position()
        self.config.autobot.armor_x = int(x)
        self.config.autobot.armor_y = int(y)
        self.lbl_armor_pos.configure(text=f"Zırh Konumu: X={x}, Y={y}")
        self.btn_set_armor.configure(state="normal")
        self.switch_armor.select() # Otomatik aktif et
        self.log(f"Zirh konumu kaydedildi: X={x}, Y={y}")

def launch_gui():
    import platform
    if platform.system() == "Windows":
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except:
            pass
            
    app = FishingBotGUI()
    app.mainloop()

if __name__ == "__main__":
    launch_gui()
