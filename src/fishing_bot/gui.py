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
            
            self.log_callback("Bot calisiyor! (Otonom Mod)")
            
            frame_interval = 1.0 / self.config.target_fps
            
            while self.running:
                loop_start = time.time()

                frame = self.capture.grab_frame()
                result = self.detector.detect(frame)

                clicked, status_msg = self.bot_logic.update(result, detector=self.detector)

                # UI'ı güncelle
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
        
        # ── Sağ İçerik (Sekmeler) ──
        self.tabview = ctk.CTkTabview(self, width=500)
        self.tabview.grid(row=0, column=1, padx=20, pady=20, sticky="nsew")
        
        self.tabview.add("Ana Ekran")
        self.tabview.add("Ayarlar")
        self.tabview.add("Zırh & Ekstralar")
        
        self._build_dashboard_tab()
        self._build_settings_tab()
        self._build_extras_tab()

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

        # Tüm toggle'ları varsayılana döndür
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

        # Çöp atma hedef koordinatları
        self.entry_drop_x.delete(0, "end")
        self.entry_drop_x.insert(0, str(c.autobot.trash_drop_x))
        self.entry_drop_y.delete(0, "end")
        self.entry_drop_y.insert(0, str(c.autobot.trash_drop_y))

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
        tab = self.tabview.tab("Zırh & Ekstralar")
        
        # Zırh Çıkar Tak
        ctk.CTkLabel(tab, text="Zırh Animasyon İptali (Çıkar/Tak)", font=ctk.CTkFont(weight="bold")).pack(pady=(10, 5))
        
        self.switch_armor = ctk.CTkSwitch(tab, text="Zırh Tricki Aktif",
                                           command=self._on_extras_toggle)
        self.switch_armor.pack(pady=10)

        self.lbl_armor_pos = ctk.CTkLabel(tab, text="Zırh Konumu: Ayarlanmadı")
        self.lbl_armor_pos.pack(pady=5)

        self.btn_set_armor = ctk.CTkButton(tab, text="📍 Zırh Konumunu Seç", command=self.start_armor_pos_selection)
        self.btn_set_armor.pack(pady=5)

        ctk.CTkLabel(tab, text="Not: Butona basınca 3 saniye içinde mouse'u\nenvanterdeki zırhın üstüne götürün.", text_color="gray").pack(pady=5)

        # Otonom İnsanlaştırma ve Envanter
        ctk.CTkLabel(tab, text="Yapay Zeka & Organik Davranış", font=ctk.CTkFont(weight="bold")).pack(pady=(15, 5))

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

    def _on_extras_toggle(self):
        """TÜM Zırh & Ekstralar toggle'larını CANLI olarak config'e yazar ve kaydeder."""
        c = self.config
        c.autobot.use_armor_trick = self.switch_armor.get() == 1
        c.autobot.use_fatigue_system = self.switch_fatigue.get() == 1
        c.autobot.auto_drop_trash = self.switch_trash.get() == 1
        c.autobot.auto_open_fishes = self.switch_open_fish.get() == 1
        c.human.use_gaussian_jitter = self.switch_gauss.get() == 1
        c.human.use_micro_movement = self.switch_micro.get() == 1
        c.human.use_dynamic_rhythm = self.switch_dynrhythm.get() == 1
        c.human.use_fps_jitter = self.switch_fpsjitter.get() == 1
        try:
            c.autobot.trash_drop_x = int(self.entry_drop_x.get())
            c.autobot.trash_drop_y = int(self.entry_drop_y.get())
        except ValueError:
            pass
        c.save_calibration()

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
        # Tüm toggle'ları da uygula (güvenlik: bot başlarken)
        self._on_extras_toggle()
        
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
