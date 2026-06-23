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
from fishing_bot.bot_logic import BotLogic, BotState
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
        self.log_callback("Bot hazirlaniyor... LUTFEN 3 SANIYE ICINDE OYUNA TIKLAYIN!")
        time.sleep(3)
        self.log_callback("Bot basliyor...")
        
        try:
            self.capture = ScreenCapture(self.config.capture)
            self.detector = Detector(self.config.circle, self.config.fish)
            self.clicker = HumanClicker(self.config.human, self.config.capture)
            self.overlay = DebugOverlay() if self.config.debug_mode else None
            
            self.bot_logic = BotLogic(self.config.autobot, self.clicker, self.capture)
            self.bot_logic.start()
            
            self.log_callback("Bot calisiyor! (RPM / Bellek Okuma Modu)")
            
            frame_interval = 1.0 / self.config.target_fps
            
            # RPM (Memory Reader) Entegrasyonu
            memory_reader = None
            try:
                from fishing_bot.memory_reader import MemoryReader
                memory_reader = MemoryReader("offsets.json")
                self.log_callback("✅ Bellek Okuyucu (RPM) aktif! %0.1 CPU kullanimi.")
            except Exception as e:
                self.log_callback(f"⚠️ RPM baslatilamadi, yuksek CPU'lu OpenCV kullanilacak: {e}")

            from fishing_bot.detector import DetectionResult, Circle, Fish

            while self.running:
                loop_start = time.time()
                
                frame = None
                result = None

                # Eger RPM modundaysak OpenCV detection YAPTIRMA
                if memory_reader and memory_reader.is_alive():
                    try:
                        state = memory_reader.get_fishing_state()
                        c_val = Circle(int(state.circle_x), int(state.circle_y), int(state.circle_radius)) if state.circle_visible else None
                        f_val = Fish(int(state.fish_x), int(state.fish_y), None, 0) if (state.circle_visible and state.fish_x > 0) else None
                        result = DetectionResult(c_val, f_val, state.is_fish_inside)
                        
                        if self.overlay:
                            frame = self.capture.grab_frame()
                    except Exception as mem_e:
                        self.log_callback(f"RPM Hatasi: {mem_e}")
                        result = DetectionResult(None, None, False)
                else:
                    # Fallback to old slow OpenCV
                    frame = self.capture.grab_frame()
                    result = self.detector.detect(frame)

                clicked, status_msg = self.bot_logic.update(result, detector=self.detector)

                # UI'ı güncelle
                self.status_callback(
                    status_msg,
                    self.bot_logic.successful_catches,
                    self.bot_logic.total_casts
                )
                
                if self.overlay and frame is not None:
                    self.overlay.render(frame, result, clicked=clicked)
                
                elapsed = time.time() - loop_start
                sleep_time = frame_interval - elapsed
                if sleep_time > 0:
                    time.sleep(sleep_time)
                    
        except Exception as e:
            import traceback
            trace = traceback.format_exc()
            self.log_callback(f"Hata: {str(e)}\n{trace}")
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
        
        self.title("🎣 Yasin2 Otonom Balık Botu V2")
        self.geometry("700x1000")
        self.config = Config()
        self.bot_thread: Optional[BotRunnerThread] = None
        
        # Grid Yapılandırması
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        
        # ── Sol Menü (Kontroller) ──
        self.sidebar_frame = ctk.CTkFrame(self, width=200, corner_radius=0)
        self.sidebar_frame.grid(row=0, column=0, sticky="nsew")
        self.sidebar_frame.grid_rowconfigure(4, weight=1)
        
        self.logo_label = ctk.CTkLabel(self.sidebar_frame, text="Yasin2 FishBot V2", font=ctk.CTkFont(size=20, weight="bold"))
        self.logo_label.grid(row=0, column=0, padx=20, pady=(20, 10))
        
        self.btn_start = ctk.CTkButton(self.sidebar_frame, text="▶ Başlat", fg_color="green", hover_color="darkgreen", command=self.toggle_bot)
        self.btn_start.grid(row=1, column=0, padx=20, pady=10)
        
        self.btn_calibrate = ctk.CTkButton(self.sidebar_frame, text="🎯 Kalibrasyon", command=self.run_calibration)
        self.btn_calibrate.grid(row=2, column=0, padx=20, pady=10)
        
        self.switch_debug = ctk.CTkSwitch(self.sidebar_frame, text="Debug Görünümü")
        self.switch_debug.grid(row=3, column=0, padx=20, pady=10)
        self.switch_debug.deselect() # Varsayılan olarak KAPALI (Focus çalmasını engellemek için)
        
        # ── Sağ İçerik Konteyneri ──
        self.right_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.right_frame.grid(row=0, column=1, sticky="nsew")
        self.right_frame.grid_columnconfigure(0, weight=1)
        self.right_frame.grid_rowconfigure(1, weight=1)
        
        # Üst Panel - Mod Butonları
        self.f_modes = ctk.CTkFrame(self.right_frame)
        self.f_modes.grid(row=0, column=0, padx=20, pady=(20, 0), sticky="ew")
        
        self.seg_modes_top = ctk.CTkSegmentedButton(self.f_modes, values=["Terminatör", "Adrenalin", "E-Sporcu", "Güvenli", "Auto Mod"], command=lambda v: self._apply_preset(v))
        self.seg_modes_top.pack(fill="x", padx=10, pady=5)
        self.seg_modes_top.set("Auto Mod")
        self.after(100, lambda: self._apply_preset("Auto Mod"))
        
        self.lbl_auto_status = ctk.CTkLabel(self.f_modes, text="", font=ctk.CTkFont(size=11, slant="italic"), text_color="cyan")
        self.lbl_auto_status.pack(pady=(0, 5))
        
        self.tabview = ctk.CTkTabview(self.right_frame, width=500)
        self.tabview.grid(row=1, column=0, padx=20, pady=10, sticky="nsew")
        
        self.tabview.add("Ana Ekran")
        self.tabview.add("Ayarlar")
        self.tabview.add("Zırh & Ekstralar")
        self.tabview.add("Balıklar")
        
        self._build_dashboard_tab()
        self._build_settings_tab()
        self._build_extras_tab()
        self._build_fishes_tab()

        # Tüm sekmeler oluştuktan sonra config'i slider'lara yükle
        self._load_sliders_from_config()
        
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
        
        # Alt Kısım: Log ve Sayaç
        self.bottom_frame = ctk.CTkFrame(tab)
        self.bottom_frame.grid(row=1, column=0, padx=10, pady=10, sticky="nsew")
        self.bottom_frame.grid_rowconfigure(0, weight=1)
        self.bottom_frame.grid_rowconfigure(1, weight=1)
        self.bottom_frame.grid_columnconfigure(0, weight=1)
        
        # Konsol/Log
        self.log_textbox = ctk.CTkTextbox(self.bottom_frame, height=100)
        self.log_textbox.grid(row=0, column=0, padx=0, pady=(0, 5), sticky="nsew")
        self.log("Sistem basariyla yuklendi.")
        
        # Balık Sayacı
        self.fish_counts_textbox = ctk.CTkTextbox(self.bottom_frame, height=100)
        self.fish_counts_textbox.grid(row=1, column=0, padx=0, pady=(5, 0), sticky="nsew")
        self.fish_counts_textbox.insert("end", "--- Görülen Balıklar ---\n")
        self.fish_counts_textbox.configure(state="disabled")
        
    def _build_settings_tab(self):
        parent_tab = self.tabview.tab("Ayarlar")
        tab = ctk.CTkScrollableFrame(parent_tab)
        tab.pack(fill="both", expand=True)
        
        # Bana bırak ayarı
        f_leave = ctk.CTkFrame(tab)
        f_leave.pack(fill="x", padx=10, pady=5)
        self.chk_leave_to_me = ctk.CTkCheckBox(
            f_leave, 
            text='Bana bırak (Yabbie Yengeci geldiğinde bot duraklar)',
            command=self._on_extras_toggle
        )
        self.chk_leave_to_me.pack(side="left", padx=10, pady=5)
        if self.config.autobot.leave_to_me_yabbie:
            self.chk_leave_to_me.select()
        else:
            self.chk_leave_to_me.deselect()
        
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

        # ── İnce Ayar Slider'ları ──
        ctk.CTkLabel(tab, text="İnce Ayar (Tıklama & Hedefleme)", font=ctk.CTkFont(weight="bold")).pack(pady=(15, 5))

        # 1. Reaksiyon Gecikmesi
        f_react = ctk.CTkFrame(tab)
        f_react.pack(fill="x", padx=10, pady=2)
        ctk.CTkLabel(f_react, text="Reaksiyon (ms):", width=120).pack(side="left", padx=5)
        self.slider_reaction = ctk.CTkSlider(f_react, from_=50, to=250, number_of_steps=40, width=200)
        self.slider_reaction.pack(side="left", padx=5)
        self.slider_reaction.set(140)
        self.lbl_reaction = ctk.CTkLabel(f_react, text="140", width=40)
        self.lbl_reaction.pack(side="left", padx=5)
        self.slider_reaction.configure(command=lambda v: self._on_slider_update(self.lbl_reaction, v, 0))

        # 2. Tıklama Cooldown
        f_cd = ctk.CTkFrame(tab)
        f_cd.pack(fill="x", padx=10, pady=2)
        ctk.CTkLabel(f_cd, text="Tık Aralığı (ms):", width=120).pack(side="left", padx=5)
        self.slider_cooldown = ctk.CTkSlider(f_cd, from_=200, to=600, number_of_steps=40, width=200)
        self.slider_cooldown.pack(side="left", padx=5)
        self.slider_cooldown.set(350)
        self.lbl_cooldown = ctk.CTkLabel(f_cd, text="350", width=40)
        self.lbl_cooldown.pack(side="left", padx=5)
        self.slider_cooldown.configure(command=lambda v: self._on_slider_update(self.lbl_cooldown, v, 0))

        # 3. Max Tıklama (minigame başına)
        f_maxclicks = ctk.CTkFrame(tab)
        f_maxclicks.pack(fill="x", padx=10, pady=2)
        ctk.CTkLabel(f_maxclicks, text="Maks Tıklama:", width=120).pack(side="left", padx=5)
        self.slider_maxclicks = ctk.CTkSlider(f_maxclicks, from_=3, to=15, number_of_steps=12, width=200)
        self.slider_maxclicks.pack(side="left", padx=5)
        self.slider_maxclicks.set(8)
        self.lbl_maxclicks = ctk.CTkLabel(f_maxclicks, text="8", width=40)
        self.lbl_maxclicks.pack(side="left", padx=5)
        self.slider_maxclicks.configure(command=lambda v: self._on_slider_update(self.lbl_maxclicks, v, 0))
        ctk.CTkLabel(tab, text="  Minigame başına max tık (3=min, 15=max)", text_color="gray").pack()

        # 3b. Bait Gecikmesi (yem sonrası bekleme)
        f_baitdelay = ctk.CTkFrame(tab)
        f_baitdelay.pack(fill="x", padx=10, pady=2)
        ctk.CTkLabel(f_baitdelay, text="Yem Gecikmesi (sn):", width=120).pack(side="left", padx=5)
        self.slider_baitdelay = ctk.CTkSlider(f_baitdelay, from_=0.5, to=3.0, number_of_steps=25, width=200)
        self.slider_baitdelay.pack(side="left", padx=5)
        self.slider_baitdelay.set(1.5)
        self.lbl_baitdelay = ctk.CTkLabel(f_baitdelay, text="1.5", width=40)
        self.lbl_baitdelay.pack(side="left", padx=5)
        self.slider_baitdelay.configure(command=lambda v: self._on_slider_update(self.lbl_baitdelay, v, 1))
        ctk.CTkLabel(tab, text="  Yeme bastıktan sonra oltayı atmadan önce bekleme", text_color="gray").pack()

        # 3c. Retry Zaman Aşımı
        f_retry = ctk.CTkFrame(tab)
        f_retry.pack(fill="x", padx=10, pady=2)
        ctk.CTkLabel(f_retry, text="Retry Aşımı (sn):", width=120).pack(side="left", padx=5)
        self.slider_retry = ctk.CTkSlider(f_retry, from_=5, to=30, number_of_steps=25, width=200)
        self.slider_retry.pack(side="left", padx=5)
        self.slider_retry.set(10)
        self.lbl_retry = ctk.CTkLabel(f_retry, text="10", width=40)
        self.lbl_retry.pack(side="left", padx=5)
        self.slider_retry.configure(command=lambda v: self._on_slider_update(self.lbl_retry, v, 0))
        ctk.CTkLabel(tab, text="  Minigame sonrası bu kadar saniyede başlamazsa space tekrar", text_color="gray").pack()

        # 4. Balık Vücut Ofseti
        f_body = ctk.CTkFrame(tab)
        f_body.pack(fill="x", padx=10, pady=2)
        ctk.CTkLabel(f_body, text="Vücut Ofseti (%):", width=120).pack(side="left", padx=5)
        self.slider_body_offset = ctk.CTkSlider(f_body, from_=20, to=80, number_of_steps=60, width=200)
        self.slider_body_offset.pack(side="left", padx=5)
        self.slider_body_offset.set(45)
        self.lbl_body_offset = ctk.CTkLabel(f_body, text="45", width=40)
        self.lbl_body_offset.pack(side="left", padx=5)
        self.slider_body_offset.configure(command=lambda v: self._on_slider_update(self.lbl_body_offset, v, 0))
        ctk.CTkLabel(tab, text="  DÜŞÜK = kafaya yakın / YÜKSEK = kuyruğa yakın", text_color="gray").pack()

        # 4. Yatay Jitter (balığın sağına/soluna rastgele tık)
        f_hjitter = ctk.CTkFrame(tab)
        f_hjitter.pack(fill="x", padx=10, pady=2)
        ctk.CTkLabel(f_hjitter, text="Yatay Sapma (px):", width=120).pack(side="left", padx=5)
        self.slider_hjitter = ctk.CTkSlider(f_hjitter, from_=0, to=20, number_of_steps=20, width=200)
        self.slider_hjitter.pack(side="left", padx=5)
        self.slider_hjitter.set(0)
        self.lbl_hjitter = ctk.CTkLabel(f_hjitter, text="0", width=40)
        self.lbl_hjitter.pack(side="left", padx=5)
        self.slider_hjitter.configure(command=lambda v: self._on_slider_update(self.lbl_hjitter, v, 0))
        ctk.CTkLabel(tab, text="  0=orta / 8=sağa-sola dağılır / 15=geniş dağılım", text_color="gray").pack()

        # 5. Prediction Lead (hız yönüne offset)
        f_lead = ctk.CTkFrame(tab)
        f_lead.pack(fill="x", padx=10, pady=2)
        ctk.CTkLabel(f_lead, text="Lead Çarpanı:", width=120).pack(side="left", padx=5)
        self.slider_lead = ctk.CTkSlider(f_lead, from_=0.30, to=1.20, number_of_steps=18, width=200)
        self.slider_lead.pack(side="left", padx=5)
        self.slider_lead.set(0.70)
        self.lbl_lead = ctk.CTkLabel(f_lead, text="0.70", width=40)
        self.lbl_lead.pack(side="left", padx=5)
        self.slider_lead.configure(command=lambda v: self._on_slider_update(self.lbl_lead, v, 2))
        ctk.CTkLabel(tab, text="  DÜŞÜK = balığın üstüne / YÜKSEK = balığın önüne", text_color="gray").pack()

        # 6. Max Lead (piksel)
        f_maxlead = ctk.CTkFrame(tab)
        f_maxlead.pack(fill="x", padx=10, pady=2)
        ctk.CTkLabel(f_maxlead, text="Max Lead (px):", width=120).pack(side="left", padx=5)
        self.slider_maxlead = ctk.CTkSlider(f_maxlead, from_=10, to=60, number_of_steps=50, width=200)
        self.slider_maxlead.pack(side="left", padx=5)
        self.slider_maxlead.set(35)
        self.lbl_maxlead = ctk.CTkLabel(f_maxlead, text="35", width=40)
        self.lbl_maxlead.pack(side="left", padx=5)
        self.slider_maxlead.configure(command=lambda v: self._on_slider_update(self.lbl_maxlead, v, 0))
        ctk.CTkLabel(tab, text="  Hızlı balıkta maksimum kaç px öne tıklanacağı", text_color="gray").pack()

        # 7. Prediction Eşiği (hangi hızda prediction başlasın)
        f_predth = ctk.CTkFrame(tab)
        f_predth.pack(fill="x", padx=10, pady=2)
        ctk.CTkLabel(f_predth, text="Tahmin Eşiği (px/s):", width=120).pack(side="left", padx=5)
        self.slider_predth = ctk.CTkSlider(f_predth, from_=20, to=150, number_of_steps=26, width=200)
        self.slider_predth.pack(side="left", padx=5)
        self.slider_predth.set(50)
        self.lbl_predth = ctk.CTkLabel(f_predth, text="50", width=40)
        self.lbl_predth.pack(side="left", padx=5)
        self.slider_predth.configure(command=lambda v: self._on_slider_update(self.lbl_predth, v, 0))
        ctk.CTkLabel(tab, text="  DÜŞÜK = her zaman tahmin / YÜKSEK = sadece hızlı balık", text_color="gray").pack()

        # 8. Çember İçi Sınır
        f_margin = ctk.CTkFrame(tab)
        f_margin.pack(fill="x", padx=10, pady=2)
        ctk.CTkLabel(f_margin, text="Çember Sınırı (%):", width=120).pack(side="left", padx=5)
        self.slider_margin = ctk.CTkSlider(f_margin, from_=75, to=95, number_of_steps=20, width=200)
        self.slider_margin.pack(side="left", padx=5)
        self.slider_margin.set(90)
        self.lbl_margin = ctk.CTkLabel(f_margin, text="90", width=40)
        self.lbl_margin.pack(side="left", padx=5)
        self.slider_margin.configure(command=lambda v: self._on_slider_update(self.lbl_margin, v, 0))
        ctk.CTkLabel(tab, text="  DÜŞÜK = çember merkezine yakın / YÜKSEK = kenara yakın", text_color="gray").pack()

        # 9. Tahmin Gürültüsü
        f_pnoise = ctk.CTkFrame(tab)
        f_pnoise.pack(fill="x", padx=10, pady=2)
        ctk.CTkLabel(f_pnoise, text="Tahmin Gürültüsü:", width=120).pack(side="left", padx=5)
        self.slider_pnoise = ctk.CTkSlider(f_pnoise, from_=0.0, to=0.50, number_of_steps=50, width=200)
        self.slider_pnoise.pack(side="left", padx=5)
        self.slider_pnoise.set(0.15)
        self.lbl_pnoise = ctk.CTkLabel(f_pnoise, text="0.15", width=40)
        self.lbl_pnoise.pack(side="left", padx=5)
        self.slider_pnoise.configure(command=lambda v: self._on_slider_update(self.lbl_pnoise, v, 2))
        ctk.CTkLabel(tab, text="  0 = Mükemmel nokta atışı / YÜKSEK = İnsani yanılma payı", text_color="gray").pack()

        # ── Auto Mod Süre ve Ağırlık Ayarları ──
        ctk.CTkLabel(tab, text="Auto Mod Konfigürasyonu", font=ctk.CTkFont(weight="bold")).pack(pady=(15, 5))
        
        f_auto1 = ctk.CTkFrame(tab)
        f_auto1.pack(fill="x", padx=10, pady=2)
        ctk.CTkLabel(f_auto1, text="Süre (Dk) Min:").pack(side="left", padx=5)
        self.entry_amin = ctk.CTkEntry(f_auto1, width=40)
        self.entry_amin.pack(side="left", padx=5)
        ctk.CTkLabel(f_auto1, text="Max:").pack(side="left", padx=5)
        self.entry_amax = ctk.CTkEntry(f_auto1, width=40)
        self.entry_amax.pack(side="left", padx=5)
        
        f_auto2 = ctk.CTkFrame(tab)
        f_auto2.pack(fill="x", padx=10, pady=2)
        ctk.CTkLabel(f_auto2, text="Kullanım (%) Terminatör:").pack(side="left", padx=5)
        self.entry_aterm = ctk.CTkEntry(f_auto2, width=35)
        self.entry_aterm.pack(side="left", padx=2)
        ctk.CTkLabel(f_auto2, text="E-Sporcu:").pack(side="left", padx=5)
        self.entry_aespo = ctk.CTkEntry(f_auto2, width=35)
        self.entry_aespo.pack(side="left", padx=2)
        ctk.CTkLabel(f_auto2, text="Güvenli:").pack(side="left", padx=5)
        self.entry_asafe = ctk.CTkEntry(f_auto2, width=35)
        self.entry_asafe.pack(side="left", padx=2)

        # ── Varsayılan & Kaydet ──
        f_reset = ctk.CTkFrame(tab)
        f_reset.pack(fill="x", padx=10, pady=(10, 5))
        self.btn_defaults = ctk.CTkButton(f_reset, text="↺ Varsayılana Döndür", fg_color="gray", hover_color="#555",
                                           command=self._reset_to_defaults)
        self.btn_defaults.pack(side="left", padx=10, pady=5)

    def _reset_to_defaults(self):
        """Tüm ince ayar slider'larını varsayılan değerlere döndürür ve kaydeder."""
        from fishing_bot.config import HumanConfig, FishDetectConfig, AutoBotConfig
        h = HumanConfig()
        f = FishDetectConfig()
        a = AutoBotConfig()

        self.slider_reaction.set(int(h.reaction_min * 1000))
        self.lbl_reaction.configure(text=str(int(h.reaction_min * 1000)))
        self.slider_cooldown.set(int(h.click_cooldown * 1000))
        self.lbl_cooldown.configure(text=str(int(h.click_cooldown * 1000)))
        self.slider_maxclicks.set(a.max_clicks_per_minigame)
        self.lbl_maxclicks.configure(text=str(a.max_clicks_per_minigame))
        self.slider_baitdelay.set(a.delay_after_bait)
        self.lbl_baitdelay.configure(text=f"{a.delay_after_bait:.1f}")
        self.slider_retry.set(int(a.retry_cast_timeout))
        self.lbl_retry.configure(text=str(int(a.retry_cast_timeout)))
        self.slider_body_offset.set(int(f.fish_body_offset_y * 100))
        self.lbl_body_offset.configure(text=str(int(f.fish_body_offset_y * 100)))
        self.slider_hjitter.set(h.horizontal_jitter_px)
        self.lbl_hjitter.configure(text=str(h.horizontal_jitter_px))
        self.slider_lead.set(h.prediction_lead_factor)
        self.lbl_lead.configure(text=f"{h.prediction_lead_factor:.2f}")
        self.slider_maxlead.set(h.prediction_max_lead_px)
        self.lbl_maxlead.configure(text=str(h.prediction_max_lead_px))
        self.slider_predth.set(int(h.prediction_speed_threshold))
        self.lbl_predth.configure(text=str(int(h.prediction_speed_threshold)))
        self.slider_margin.set(int(h.click_inner_margin * 100))
        self.lbl_margin.configure(text=str(int(h.click_inner_margin * 100)))
        self.slider_pnoise.set(h.prediction_noise_sigma)
        self.lbl_pnoise.configure(text=f"{h.prediction_noise_sigma:.2f}")
        
        self.slider_miss.set(int(h.intentional_miss_rate * 100))
        self.lbl_miss.configure(text=str(int(h.intentional_miss_rate * 100)))
        self.slider_fmiss.set(int(h.fast_fish_miss_rate * 100))
        self.lbl_fmiss.configure(text=str(int(h.fast_fish_miss_rate * 100)))

        # Tüm toggle'ları varsayılana döndür
        self.seg_targeting.set("Organik (Mouse Akıcı)")
        self.switch_armor.deselect()
        self.switch_fatigue.select()
        self.switch_trash.select()
        self.switch_open_fish.select()
        from fishing_bot.config import AutoBotConfig
        a = AutoBotConfig()
        self.entry_drop_x.delete(0, "end")
        self.entry_drop_x.insert(0, str(a.trash_drop_x))
        self.entry_drop_y.delete(0, "end")
        self.entry_drop_y.insert(0, str(a.trash_drop_y))
        
        self.entry_amin.delete(0, "end")
        self.entry_amin.insert(0, str(a.auto_mode_min_mins))
        self.entry_amax.delete(0, "end")
        self.entry_amax.insert(0, str(a.auto_mode_max_mins))
        self.entry_aterm.delete(0, "end")
        self.entry_aterm.insert(0, str(a.auto_weight_terminator))
        self.entry_aespo.delete(0, "end")
        self.entry_aespo.insert(0, str(a.auto_weight_esports))
        self.entry_asafe.delete(0, "end")
        self.entry_asafe.insert(0, str(a.auto_weight_safe))

        self.switch_gauss.select()
        self.switch_micro.select()
        self.switch_dynrhythm.select()
        self.switch_fpsjitter.select()

        self._apply_sliders_to_config()
        self.log("Tüm ayarlar varsayılana döndürüldü ve kaydedildi.")

    def _load_sliders_from_config(self):
        """Config'teki kayıtlı değerleri slider'lara geri yükler (başlangıçta)."""
        c = self.config
        self.slider_reaction.set(int(c.human.reaction_min * 1000))
        self.lbl_reaction.configure(text=str(int(c.human.reaction_min * 1000)))
        self.slider_cooldown.set(int(c.human.click_cooldown * 1000))
        self.lbl_cooldown.configure(text=str(int(c.human.click_cooldown * 1000)))
        self.slider_maxclicks.set(c.autobot.max_clicks_per_minigame)
        self.lbl_maxclicks.configure(text=str(c.autobot.max_clicks_per_minigame))
        self.slider_baitdelay.set(c.autobot.delay_after_bait)
        self.lbl_baitdelay.configure(text=f"{c.autobot.delay_after_bait:.1f}")
        self.slider_retry.set(int(c.autobot.retry_cast_timeout))
        self.lbl_retry.configure(text=str(int(c.autobot.retry_cast_timeout)))
        self.slider_body_offset.set(int(c.fish.fish_body_offset_y * 100))
        self.lbl_body_offset.configure(text=str(int(c.fish.fish_body_offset_y * 100)))
        self.slider_hjitter.set(c.human.horizontal_jitter_px)
        self.lbl_hjitter.configure(text=str(c.human.horizontal_jitter_px))
        self.slider_lead.set(c.human.prediction_lead_factor)
        self.lbl_lead.configure(text=f"{c.human.prediction_lead_factor:.2f}")
        self.slider_maxlead.set(c.human.prediction_max_lead_px)
        self.lbl_maxlead.configure(text=str(c.human.prediction_max_lead_px))
        self.slider_predth.set(int(c.human.prediction_speed_threshold))
        self.lbl_predth.configure(text=str(int(c.human.prediction_speed_threshold)))
        self.slider_margin.set(int(c.human.click_inner_margin * 100))
        self.lbl_margin.configure(text=str(int(c.human.click_inner_margin * 100)))
        self.slider_pnoise.set(c.human.prediction_noise_sigma)
        self.lbl_pnoise.configure(text=f"{c.human.prediction_noise_sigma:.2f}")
        
        self.slider_miss.set(int(c.human.intentional_miss_rate * 100))
        self.lbl_miss.configure(text=str(int(c.human.intentional_miss_rate * 100)))
        self.slider_fmiss.set(int(c.human.fast_fish_miss_rate * 100))
        self.lbl_fmiss.configure(text=str(int(c.human.fast_fish_miss_rate * 100)))
        # Zırh switch'i + konum label'ı
        if c.autobot.use_armor_trick:
            self.switch_armor.select()
        else:
            self.switch_armor.deselect()
        if c.autobot.armor_x > 0 and c.autobot.armor_y > 0:
            self.lbl_armor_pos.configure(text=f"Zırh Konumu: X={c.autobot.armor_x}, Y={c.autobot.armor_y}")
        else:
            self.lbl_armor_pos.configure(text="Zırh Konumu: Ayarlanmadı")

        # Otonom toggle'lar
        if c.human.targeting_mode == "terminator":
            self.seg_targeting.set("Terminatör (Mouse Işınlanır)")
        else:
            self.seg_targeting.set("Organik (Mouse Akıcı)")

        if c.autobot.use_fatigue_system:
            self.switch_fatigue.select()
        else:
            self.switch_fatigue.deselect()
        if c.autobot.auto_drop_trash:
            self.switch_trash.select()
        else:
            self.switch_trash.deselect()
        if c.autobot.auto_open_fishes:
            self.switch_open_fish.select()
        else:
            self.switch_open_fish.deselect()

        # Çöp atma hedef koordinatları ve Auto mod
        self.entry_drop_x.delete(0, "end")
        self.entry_drop_x.insert(0, str(c.autobot.trash_drop_x))
        self.entry_drop_y.delete(0, "end")
        self.entry_drop_y.insert(0, str(c.autobot.trash_drop_y))

        self.entry_amin.delete(0, "end")
        self.entry_amin.insert(0, str(c.autobot.auto_mode_min_mins))
        self.entry_amax.delete(0, "end")
        self.entry_amax.insert(0, str(c.autobot.auto_mode_max_mins))
        self.entry_aterm.delete(0, "end")
        self.entry_aterm.insert(0, str(c.autobot.auto_weight_terminator))
        self.entry_aespo.delete(0, "end")
        self.entry_aespo.insert(0, str(c.autobot.auto_weight_esports))
        self.entry_asafe.delete(0, "end")
        self.entry_asafe.insert(0, str(c.autobot.auto_weight_safe))

        # Anti-cheat toggle'lar
        if c.human.use_gaussian_jitter:
            self.switch_gauss.select()
        else:
            self.switch_gauss.deselect()
        if c.human.use_micro_movement:
            self.switch_micro.select()
        else:
            self.switch_micro.deselect()
        if c.human.use_dynamic_rhythm:
            self.switch_dynrhythm.select()
        else:
            self.switch_dynrhythm.deselect()
        if c.human.use_fps_jitter:
            self.switch_fpsjitter.select()
        else:
            self.switch_fpsjitter.deselect()

    def _build_extras_tab(self):
        parent_tab = self.tabview.tab("Zırh & Ekstralar")
        tab = ctk.CTkScrollableFrame(parent_tab)
        tab.pack(fill="both", expand=True)
        
        # Zırh Çıkar Tak
        ctk.CTkLabel(tab, text="Zırh Animasyon İptali (Çıkar/Tak)", font=ctk.CTkFont(weight="bold")).pack(pady=(10, 5))
        
        self.switch_armor = ctk.CTkSwitch(tab, text="Zırh Tricki Aktif",
                                           command=self._on_extras_toggle)
        self.switch_armor.pack(pady=10)

        armor_text = "Zırh Konumu: Ayarlanmadı"
        if self.config.autobot.armor_x > 0 or self.config.autobot.armor_y > 0:
            armor_text = f"Zırh Konumu: X={self.config.autobot.armor_x}, Y={self.config.autobot.armor_y}"
        self.lbl_armor_pos = ctk.CTkLabel(tab, text=armor_text)
        self.lbl_armor_pos.pack(pady=5)

        self.btn_set_armor = ctk.CTkButton(tab, text="📍 Zırh Konumunu Seç", command=self.start_armor_pos_selection)
        self.btn_set_armor.pack(pady=5)

        ctk.CTkLabel(tab, text="Not: Butona basınca 3 saniye içinde mouse'u\nenvanterdeki zırhın üstüne götürün.", text_color="gray").pack(pady=5)

        # Otonom İnsanlaştırma ve Envanter
        ctk.CTkLabel(tab, text="Yapay Zeka & Organik Davranış", font=ctk.CTkFont(weight="bold")).pack(pady=(15, 5))

        f_target = ctk.CTkFrame(tab)
        f_target.pack(fill="x", padx=10, pady=5)
        ctk.CTkLabel(f_target, text="Hedefleme Modu:", width=110).pack(side="left", padx=5)
        self.seg_targeting = ctk.CTkSegmentedButton(f_target, values=["Organik (Mouse Akıcı)", "Terminatör (Mouse Işınlanır)"], command=lambda v: self._on_extras_toggle())
        self.seg_targeting.pack(side="left", padx=5, fill="x", expand=True)
        self.seg_targeting.set("Organik (Mouse Akıcı)")

        self.switch_fatigue = ctk.CTkSwitch(tab, text="İnsan Yorulması (Mola Sistemi) Aktif",
                                             command=self._on_extras_toggle)
        self.switch_fatigue.pack(pady=5)
        self.switch_fatigue.select()
        ctk.CTkLabel(tab, text="  40-75dk çalışma sonrası 4-12dk AFK mola. Gerçek oyuncu gibi\nyorulup ara verir. 7/24 botlanmadığını gösterir.", text_color="#aaaaaa").pack()

        self.switch_trash = ctk.CTkSwitch(tab, text="Otomatik Çöpleri Yere At (Trash Drop)",
                                           command=self._on_extras_toggle)
        self.switch_trash.pack(pady=5)
        self.switch_trash.select()
        ctk.CTkLabel(tab, text="  Envanterdeki çöpleri template matching ile tespit eder,\nsürükle-bırak ile yere atar, Enter ile onaylar.", text_color="#aaaaaa").pack()

        f_drop = ctk.CTkFrame(tab)
        f_drop.pack(fill="x", padx=10, pady=2)
        ctk.CTkLabel(f_drop, text="Atma Hedef X:").pack(side="left", padx=5)
        self.entry_drop_x = ctk.CTkEntry(f_drop, width=50)
        self.entry_drop_x.insert(0, "400")
        self.entry_drop_x.pack(side="left", padx=5)
        ctk.CTkLabel(f_drop, text="Y:").pack(side="left", padx=5)
        self.entry_drop_y = ctk.CTkEntry(f_drop, width=50)
        self.entry_drop_y.insert(0, "300")
        self.entry_drop_y.pack(side="left", padx=5)
        ctk.CTkLabel(f_drop, text="oyun dünyası koordinatı", text_color="gray").pack(side="left", padx=5)

        self.switch_open_fish = ctk.CTkSwitch(tab, text="Otomatik Balıkları Aç",
                                               command=self._on_extras_toggle)
        self.switch_open_fish.pack(pady=5)
        self.switch_open_fish.select()
        ctk.CTkLabel(tab, text="  Envanterdeki balıkları template matching ile tespit eder,\nsağ tık ile açar.", text_color="#aaaaaa").pack()

        # ── Kasıtlı Iskalama ──
        f_miss = ctk.CTkFrame(tab)
        f_miss.pack(fill="x", padx=10, pady=2)
        ctk.CTkLabel(f_miss, text="Normal Iskalama (%):", width=140).pack(side="left", padx=5)
        self.slider_miss = ctk.CTkSlider(f_miss, from_=0, to=100, number_of_steps=100, width=180)
        self.slider_miss.pack(side="left", padx=5)
        self.slider_miss.set(8)
        self.lbl_miss = ctk.CTkLabel(f_miss, text="8", width=30)
        self.lbl_miss.pack(side="left", padx=5)
        self.slider_miss.configure(command=lambda v: self._on_slider_update(self.lbl_miss, v, 0))

        f_fmiss = ctk.CTkFrame(tab)
        f_fmiss.pack(fill="x", padx=10, pady=2)
        ctk.CTkLabel(f_fmiss, text="Hızlı Balık Iskalama (%):", width=140).pack(side="left", padx=5)
        self.slider_fmiss = ctk.CTkSlider(f_fmiss, from_=0, to=100, number_of_steps=100, width=180)
        self.slider_fmiss.pack(side="left", padx=5)
        self.slider_fmiss.set(18)
        self.lbl_fmiss = ctk.CTkLabel(f_fmiss, text="18", width=30)
        self.lbl_fmiss.pack(side="left", padx=5)
        self.slider_fmiss.configure(command=lambda v: self._on_slider_update(self.lbl_fmiss, v, 0))
        ctk.CTkLabel(tab, text="  0 = Asla bilerek kaçırma (Ban riski artar)", text_color="gray").pack(pady=(0, 5))

        # ── Anti-Cheat Koruma ──
        ctk.CTkLabel(tab, text="Anti-Cheat Koruma", font=ctk.CTkFont(weight="bold")).pack(pady=(15, 5))

        self.switch_micro = ctk.CTkSwitch(tab, text="🔴 Mikro Mouse Hareketi", command=self._on_extras_toggle)
        self.switch_micro.pack(pady=2)
        self.switch_micro.select()
        ctk.CTkLabel(tab, text="  Işınlanma yerine 3 adımlı hareket. EN KRİTİK koruma.", text_color="#ff6666").pack()

        self.switch_dynrhythm = ctk.CTkSwitch(tab, text="🔴 Dinamik Ritim", command=self._on_extras_toggle)
        self.switch_dynrhythm.pack(pady=2)
        self.switch_dynrhythm.select()
        ctk.CTkLabel(tab, text="  Sabit pattern yerine Gauss gürültülü prosedürel ritim. Tespit riski çok yüksek.", text_color="#ff6666").pack()

        self.switch_gauss = ctk.CTkSwitch(tab, text="🟡 Gaussian Jitter", command=self._on_extras_toggle)
        self.switch_gauss.pack(pady=2)
        self.switch_gauss.select()
        ctk.CTkLabel(tab, text="  Uniform yerine normal dağılımlı tıklama sapması. Önerilir.", text_color="#ffaa33").pack()

        self.switch_fpsjitter = ctk.CTkSwitch(tab, text="🟢 FPS Jitter", command=self._on_extras_toggle)
        self.switch_fpsjitter.pack(pady=2)
        self.switch_fpsjitter.select()
        ctk.CTkLabel(tab, text="  Frame'leri %3 rastgele geciktirir. Düşük öncelikli ama faydalı.", text_color="#66ff66").pack()

    # ── Metodlar ──
    
    def _auto_mode_loop(self):
        pass

    def _apply_preset(self, preset_name, is_auto=False):
        c = self.config
        
        if preset_name == "Auto Mod":
            self.log("[Auto Mod] Güvenli mod devrede, Yabbie Yengeci bekleniyor...")
            self._apply_preset("Güvenli", is_auto=True)
            return
            
        if not is_auto:
            self._auto_mode_running = False
            self.lbl_auto_status.configure(text="")
            
        if preset_name == "Terminatör":
            c.human.reaction_min = 0.01
            c.human.reaction_max = 0.04
            c.human.click_cooldown = 0.05
            c.human.horizontal_jitter_px = 0
            c.human.prediction_lead_factor = 0.25
            c.human.prediction_max_lead_px = 25
            c.human.prediction_speed_threshold = 150.0
            c.human.prediction_noise_sigma = 0.0
            c.human.click_inner_margin = 0.95
            c.human.intentional_miss_rate = 0.0
            c.human.fast_fish_miss_rate = 0.0
            c.human.targeting_mode = "terminator"
            
            c.human.use_micro_movement = True
            c.human.use_dynamic_rhythm = False
            c.human.use_gaussian_jitter = False
            c.human.use_fps_jitter = False
            
        elif preset_name == "Adrenalin":
            # Anti-cheat güvenli ama Yabbie yakalayabilecek Adrenalin
            c.human.reaction_min = 0.02
            c.human.reaction_max = 0.06
            c.human.click_cooldown = 0.08
            c.human.horizontal_jitter_px = 1
            c.human.prediction_lead_factor = 0.30
            c.human.prediction_max_lead_px = 30
            c.human.prediction_speed_threshold = 60.0
            c.human.prediction_noise_sigma = 0.02
            c.human.click_inner_margin = 0.95
            c.human.intentional_miss_rate = 0.0
            c.human.fast_fish_miss_rate = 0.0
            c.human.targeting_mode = "organic"
            
            c.human.use_micro_movement = True
            c.human.use_dynamic_rhythm = True
            c.human.use_gaussian_jitter = True
            c.human.use_fps_jitter = False

        elif preset_name == "E-Sporcu":
            c.human.reaction_min = 0.12
            c.human.reaction_max = 0.17
            c.human.click_cooldown = 0.33
            c.human.horizontal_jitter_px = 1
            c.human.prediction_lead_factor = 0.05
            c.human.prediction_max_lead_px = 10
            c.human.prediction_speed_threshold = 50.0
            c.human.prediction_noise_sigma = 0.02
            c.human.click_inner_margin = 0.90
            c.human.intentional_miss_rate = 0.0
            c.human.fast_fish_miss_rate = 0.0
            c.human.targeting_mode = "organic"
            
            c.human.use_micro_movement = True
            c.human.use_dynamic_rhythm = True
            c.human.use_gaussian_jitter = True
            c.human.use_fps_jitter = False
            
        elif preset_name == "Güvenli":
            c.human.reaction_min = 0.16
            c.human.reaction_max = 0.21
            c.human.click_cooldown = 0.38
            c.human.horizontal_jitter_px = 3
            c.human.prediction_lead_factor = 0.0
            c.human.prediction_max_lead_px = 0
            c.human.prediction_speed_threshold = 40.0
            c.human.prediction_noise_sigma = 0.15
            c.human.click_inner_margin = 0.85
            c.human.intentional_miss_rate = 0.02   # %2 — doğal kaçırmaların üstüne ufak ek
            c.human.fast_fish_miss_rate = 0.05     # %5 — hızlı balıklarda zaten çoğu kaçıyor
            c.human.targeting_mode = "organic"
            
            c.human.use_micro_movement = True
            c.human.use_dynamic_rhythm = True
            c.human.use_gaussian_jitter = True
            c.human.use_fps_jitter = True
            
        if is_auto:
            self.lbl_auto_status.configure(text=f"Auto Mod Aktif: Şu an [{preset_name}] devrede")
            
        self._load_sliders_from_config()
        self.config.save_calibration()

    def log(self, message: str):
        self.log_textbox.insert("end", f"[{time.strftime('%H:%M:%S')}] {message}\n")
        self.log_textbox.see("end")

    def _on_slider_update(self, label: ctk.CTkLabel, value: float, decimals: int):
        """Slider değeri değiştiğinde etiketi ve config'i CANLI günceller."""
        if decimals == 0:
            label.configure(text=str(int(value)))
        else:
            label.configure(text=f"{value:.{decimals}f}")
        # Config'e anında yaz — bot çalışırken değişiklikler hemen etki eder
        self._apply_sliders_to_config()

    def _build_fishes_tab(self):
        parent_tab = self.tabview.tab("Balıklar")
        tab = ctk.CTkScrollableFrame(parent_tab)
        tab.pack(fill="both", expand=True)
        
        c = self.config.autobot
        
        # Üst Kısım: Master Switch
        self.switch_use_fish_ocr = ctk.CTkSwitch(tab, text="Otomatik Balık İptal Sistemi Aktif (Chat OCR)", command=self._on_extras_toggle)
        self.switch_use_fish_ocr.pack(pady=(10, 5))
        if c.use_fish_ocr:
            self.switch_use_fish_ocr.select()
        else:
            self.switch_use_fish_ocr.deselect()

        # Özel Balık Ekleme
        f_add_fish = ctk.CTkFrame(tab)
        f_add_fish.pack(fill="x", padx=20, pady=5)
        
        self.entry_custom_fish = ctk.CTkEntry(f_add_fish, placeholder_text="Örn: Somon", width=200)
        self.entry_custom_fish.pack(side="left", padx=(10, 5), pady=5)
        
        btn_add_fish = ctk.CTkButton(f_add_fish, text="Balık Ekle", width=80, command=self.add_custom_fish)
        btn_add_fish.pack(side="left", padx=5, pady=5)
        
        ctk.CTkLabel(tab, text="İstenmeyen Balıkları Seçin (ESC ile İptal Edilir)", font=ctk.CTkFont(weight="bold")).pack(pady=(15, 5))
        
        # Fish Checkboxes
        self.fishes_frame = ctk.CTkScrollableFrame(tab, height=250)
        self.fishes_frame.pack(fill="both", expand=True, padx=20, pady=5)
        
        default_fishes = [
            "Minik Balık", "Sudak Balığı", "Büyük Sudak Balığı", "Altın Sudak", "Sazan",
            "Som Balığı", "Ot Sazanı", "Alabalık", "Dere Alabalığı", "Yılan Başı Balığı",
            "Şiraz Balığı", "Yayın Balığı", "Çopra", "Palamut", "Zargana", "Gümüş Balığı",
            "Uskumru", "Levrek", "Ringa Balığı", "Yabbie Yengeci", "Kadife Balığı", "Kurbağa Balığı",
            "Kral Yengeci", "Altın Yüzük", "Görünmezlik Pelerini", "Bilge Kralın Eldiveni",
            "Hırsızın Eldiveni", "Kaçak Pelerin", "Lucy'nin Yüzüğü", "Denizkızı Anahtarı", "Saç Boyası",
            "Lüfer Balığı"
        ]
        
        all_fishes = list(dict.fromkeys(default_fishes + c.custom_fishes))
        
        self.fish_vars = {}
        for fish in all_fishes:
            self._create_fish_checkbox(fish, (fish in c.ignored_fishes))
            
        # Chat Region Selection
        ctk.CTkLabel(tab, text="Sohbet Taraması Bölgesi (Chat OCR)", font=ctk.CTkFont(weight="bold")).pack(pady=(15, 5))
        
        f_region = ctk.CTkFrame(tab)
        f_region.pack(fill="x", padx=20, pady=5)
        
        self.lbl_chat_region = ctk.CTkLabel(f_region, text=f"Bölge: X={c.chat_region_x}, Y={c.chat_region_y}, W={c.chat_region_w}, H={c.chat_region_h}")
        self.lbl_chat_region.pack(side="left", padx=10, pady=10)
        
        self.btn_set_chat = ctk.CTkButton(f_region, text="📍 Bölge Seç", width=100, command=self.start_chat_region_selection)
        self.btn_set_chat.pack(side="right", padx=10, pady=10)

        ctk.CTkLabel(tab, text="Not: Butona bastıktan sonra ekrandan sohbet bölgesini fareyle sürükleyip seçin\nve ENTER tuşuna basarak onaylayın.", text_color="gray", font=ctk.CTkFont(size=11)).pack(pady=5)


    def _on_extras_toggle(self):
        """TÜM Zırh & Ekstralar toggle'larını CANLI olarak config'e yazar ve kaydeder."""
        c = self.config
        c.human.targeting_mode = "terminator" if self.seg_targeting.get() == "Terminatör (Mouse Işınlanır)" else "organic"
        c.autobot.use_armor_trick = self.switch_armor.get() == 1
        c.autobot.use_fatigue_system = self.switch_fatigue.get() == 1
        c.autobot.auto_drop_trash = self.switch_trash.get() == 1
        c.autobot.auto_open_fishes = self.switch_open_fish.get() == 1
        c.autobot.leave_to_me_yabbie = self.chk_leave_to_me.get() == 1
        c.human.use_gaussian_jitter = self.switch_gauss.get() == 1
        c.human.use_micro_movement = self.switch_micro.get() == 1
        c.human.use_dynamic_rhythm = self.switch_dynrhythm.get() == 1
        c.human.use_fps_jitter = self.switch_fpsjitter.get() == 1
        try:
            c.autobot.trash_drop_x = int(self.entry_drop_x.get())
            c.autobot.trash_drop_y = int(self.entry_drop_y.get())
        except ValueError:
            pass
        try:
            c.autobot.auto_mode_min_mins = int(self.entry_amin.get())
            c.autobot.auto_mode_max_mins = int(self.entry_amax.get())
            c.autobot.auto_weight_terminator = int(self.entry_aterm.get())
            c.autobot.auto_weight_esports = int(self.entry_aespo.get())
            c.autobot.auto_weight_safe = int(self.entry_asafe.get())
        except ValueError:
            pass
            
        if hasattr(self, 'switch_use_fish_ocr'):
            c.autobot.use_fish_ocr = self.switch_use_fish_ocr.get() == 1
            
        c.save_calibration()
        self.log("Ayarlar kaydedildi.")

    def add_custom_fish(self):
        new_fish = self.entry_custom_fish.get().strip()
        if new_fish and new_fish not in self.fish_vars:
            c = self.config.autobot
            if new_fish not in c.custom_fishes:
                c.custom_fishes.append(new_fish)
                self.config.save_calibration()
            self._create_fish_checkbox(new_fish, True)
            self._update_ignored_fishes()
            self.entry_custom_fish.delete(0, 'end')
            self.log(f"Yeni balık/eşya eklendi: {new_fish}")

    def _create_fish_checkbox(self, fish: str, is_checked: bool):
        var = ctk.BooleanVar(value=is_checked)
        self.fish_vars[fish] = var
        chk = ctk.CTkCheckBox(self.fishes_frame, text=fish, variable=var, command=self._update_ignored_fishes)
        chk.pack(anchor="w", pady=5, padx=10)

    def _apply_sliders_to_config(self):
        """Tüm slider değerlerini config nesnesine yazar ve OTOMATİK KAYDEDER."""
        reaction_ms = int(self.slider_reaction.get())
        self.config.human.reaction_min = reaction_ms / 1000.0
        self.config.human.reaction_max = (reaction_ms + 50) / 1000.0
        self.config.human.click_cooldown = self.slider_cooldown.get() / 1000.0
        self.config.autobot.max_clicks_per_minigame = int(self.slider_maxclicks.get())
        self.config.autobot.delay_after_bait = round(self.slider_baitdelay.get(), 1)
        self.config.autobot.retry_cast_timeout = int(self.slider_retry.get())
        self.config.fish.fish_body_offset_y = self.slider_body_offset.get() / 100.0
        self.config.human.horizontal_jitter_px = int(self.slider_hjitter.get())
        self.config.human.prediction_lead_factor = round(self.slider_lead.get(), 2)
        self.config.human.prediction_max_lead_px = int(self.slider_maxlead.get())
        self.config.human.prediction_speed_threshold = float(self.slider_predth.get())
        self.config.human.click_inner_margin = self.slider_margin.get() / 100.0
        self.config.human.prediction_noise_sigma = round(self.slider_pnoise.get(), 2)
        
        self.config.human.intentional_miss_rate = self.slider_miss.get() / 100.0
        self.config.human.fast_fish_miss_rate = self.slider_fmiss.get() / 100.0
        # Tüm toggle'ları da uygula (güvenlik: bot başlarken)
        self._on_extras_toggle()
        
    def update_status(self, status: str, catches: int, casts: int):
        # Arayüz güncellemeleri ana thread'de yapılmalı
        self.after(0, self._update_status_gui, status, catches, casts)
        
    def _update_status_gui(self, status: str, catches: int, casts: int):
        self.lbl_status.configure(text=f"Durum: {status}")
        self.lbl_catches.configure(text=f"Tutan Balık: {catches}")
        self.lbl_casts.configure(text=f"Atış Sayısı: {casts}")
        
        # Balık istatistiklerini güncelle ve Yabbie→Adrenalin oto-tetikleme
        self._last_yabbie_count = getattr(self, "_last_yabbie_count", 0)
        self._yabbie_adrenalin_active = getattr(self, "_yabbie_adrenalin_active", False)
        self._previous_preset = getattr(self, "_previous_preset", None)

        if self.bot_thread and hasattr(self.bot_thread, 'bot_logic') and self.bot_thread.bot_logic:
            bot = self.bot_thread.bot_logic
            encountered = bot.encountered_fishes
            if encountered:
                total_fishes = sum(encountered.values())
                self.fish_counts_textbox.configure(state="normal")
                self.fish_counts_textbox.delete("1.0", "end")
                self.fish_counts_textbox.insert("end", f"--- Görülen Balıklar --- Toplam Balık: {total_fishes}\n")
                for f, count in sorted(encountered.items(), key=lambda x: x[1], reverse=True):
                    self.fish_counts_textbox.insert("end", f"{f}: {count}\n")
                self.fish_counts_textbox.configure(state="disabled")
                
                # ── Otomatik Adrenalin Modu (Yabbie Yengeci için) ──
                # Yabbie tespit edildiğinde Güvenli → Adrenalin'e geçer.
                # Minigame bitince (POST_CATCH/PREPARE) Güvenli'ye döner.
                current_yabbie = encountered.get("Yabbie Yengeci", 0)
                if current_yabbie > self._last_yabbie_count:
                    self._last_yabbie_count = current_yabbie
                    
                    # --- YABBIE SESİ ÇAL ---
                    try:
                        import os
                        import ctypes
                        import threading
                        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
                        sound_path = os.path.join(base_dir, "src", "fishing_bot", "music", "submarine-sonar.mp3")
                        
                        if os.path.exists(sound_path):
                            def _play_yabbie_sound():
                                alias = "yabbie_sound"
                                ctypes.windll.winmm.mciSendStringW(f'close {alias}', None, 0, None)
                                ctypes.windll.winmm.mciSendStringW(f'open "{sound_path}" alias {alias}', None, 0, None)
                                ctypes.windll.winmm.mciSendStringW(f'play {alias}', None, 0, None)
                            
                            threading.Thread(target=_play_yabbie_sound, daemon=True).start()
                        else:
                            self.log("Uyarı: submarine-sonar.mp3 bulunamadı!")
                    except Exception as e:
                        self.log(f"Ses çalınırken hata: {e}")
                    # -----------------------

                    # Terminatör modundaysa dokunma (kullanıcı bilerek seçmiş)
                    if self.seg_modes_top.get() != "Terminatör" and not self._yabbie_adrenalin_active:
                        self._previous_preset = self.seg_modes_top.get()
                        self.log("🦀 Yabbie tespit edildi! Adrenalin moduna geçiliyor (minigame bitene kadar)...")
                        self.seg_modes_top.set("Adrenalin")
                        self._apply_preset("Adrenalin", is_auto=True)
                        self._yabbie_adrenalin_active = True
            
            # ── Minigame bitti mi kontrolü: Adrenalin → Güvenli'ye dön ──
            # Bot MINIGAME'den çıktıysa (POST_CATCH, PREPARE, WAITING, vb.) geri dön
            if self._yabbie_adrenalin_active:
                bot_state = bot.state
                if bot_state not in (BotState.MINIGAME,):
                    self._yabbie_adrenalin_active = False
                    previous = self._previous_preset or "Güvenli"
                    if self.seg_modes_top.get() == "Adrenalin":
                        self.log(f"✅ Yabbie minigame bitti. {previous} moduna dönülüyor.")
                        self.seg_modes_top.set(previous)
                        self._apply_preset(previous, is_auto=True)

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
            try:
                self.config.autobot.trash_drop_x = int(self.entry_drop_x.get())
                self.config.autobot.trash_drop_y = int(self.entry_drop_y.get())
            except ValueError:
                pass
            self._on_extras_toggle()  # Tüm toggle'ları config'e yaz
            self._apply_sliders_to_config()  # İnce ayar slider'larını uygula

            # Başlat
            self.btn_start.configure(text="⏹ Durdur", fg_color="red", hover_color="darkred")
            self.btn_calibrate.configure(state="disabled")
            
            self._last_yabbie_count = 0  # Yeni bot başlatıldığında yabbie sayacını sıfırla (ses/mod düzeltmesi)
            self._yabbie_adrenalin_active = False  # Adrenalin mod flag'ini sıfırla
            self.bot_thread = BotRunnerThread(self.config, self.log, self.update_status)
            self.bot_thread.start()

    def run_calibration(self):
        from fishing_bot.main import run_calibration as rc
        self.log("Kalibrasyon baslatildi. Tam ekran goruntusunden oyunu secin.")
        rc(self.config)
        self.config.save_calibration()
        self.log(f"Bolge ayarlandi: {self.config.capture.width}x{self.config.capture.height} (Kaydedildi)")
        
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
        self.config.save_calibration()
        self.log(f"Zirh konumu kaydedildi: X={x}, Y={y}")

    def _update_ignored_fishes(self):
        ignored = []
        for fish, var in self.fish_vars.items():
            if var.get():
                ignored.append(fish)
        self.config.autobot.ignored_fishes = ignored
        self.config.save_calibration()
        
    def start_chat_region_selection(self):
        import threading
        self.btn_set_chat.configure(state="disabled")
        self.log("Sohbet bolgesi secimi baslatildi. Ekranda cizip ENTER'a basin.")
        threading.Thread(target=self._run_chat_calibration, daemon=True).start()

    def _run_chat_calibration(self):
        try:
            import mss
            import numpy as np
            import cv2
            with mss.mss() as sct:
                monitor = sct.monitors[1]
                raw = sct.grab(monitor)
                full_screen = np.array(raw, dtype=np.uint8)[:, :, :3]
            
            h, w = full_screen.shape[:2]
            display_scale = 1.0
            max_display = 1200
            if w > max_display:
                display_scale = max_display / w
                display = cv2.resize(full_screen, (int(w * display_scale), int(h * display_scale)))
            else:
                display = full_screen
                
            # OpenCV penceresini en öne getirme hilesi
            cv2.namedWindow("Sohbet Bolgesini Secin (ENTER=Onayla, C=Iptal)", cv2.WINDOW_NORMAL)
            cv2.setWindowProperty("Sohbet Bolgesini Secin (ENTER=Onayla, C=Iptal)", cv2.WND_PROP_TOPMOST, 1)
            
            roi = cv2.selectROI("Sohbet Bolgesini Secin (ENTER=Onayla, C=Iptal)", display, fromCenter=False, showCrosshair=True)
            cv2.destroyAllWindows()
            
            if roi != (0, 0, 0, 0):
                x, y, rw, rh = roi
                real_x = int(x / display_scale)
                real_y = int(y / display_scale)
                real_w = int(rw / display_scale)
                real_h = int(rh / display_scale)
                
                self.config.autobot.chat_region_x = real_x
                self.config.autobot.chat_region_y = real_y
                self.config.autobot.chat_region_w = real_w
                self.config.autobot.chat_region_h = real_h
                self.config.save_calibration()
                
                self.after(0, lambda: self.lbl_chat_region.configure(text=f"Bölge: X={real_x}, Y={real_y}, W={real_w}, H={real_h}"))
                self.log(f"Chat bolgesi kaydedildi: W={real_w}, H={real_h}")
            else:
                self.log("Chat bolgesi secimi iptal edildi.")
                
        except Exception as e:
            self.log(f"Secim sirasinda hata: {e}")
        finally:
            self.after(0, lambda: self.btn_set_chat.configure(state="normal"))

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
