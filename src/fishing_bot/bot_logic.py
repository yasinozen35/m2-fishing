"""
bot_logic.py — Tam otonom balık botu durum makinesi (State Machine).

Oyun döngüsünü yönetir:
1. Yem tak (PREPARE)
2. Zırh değiştir (PREPARE - opsiyonel)
3. Olta at (CAST)
4. Balık bekle (WAITING)
5. Mini-oyunu oyna (MINIGAME)
6. Bekle ve başa dön (POST_CATCH)
"""

import random
import time
from enum import Enum, auto

from fishing_bot.config import AutoBotConfig
from fishing_bot.clicker import HumanClicker
from fishing_bot.detector import DetectionResult


class BotState(Enum):
    """Botun mevcut durumu."""
    IDLE = auto()          # Çalışmıyor / duraklatıldı
    PREPARE = auto()       # Yem takma ve zırh değiştirme
    CAST = auto()          # Oltayı suya atma
    WAITING = auto()       # Dairenin belirmesini bekleme
    MINIGAME = auto()      # Balık yakalama mini-oyunu (3 tık)
    POST_CATCH = auto()    # Yakaladıktan sonra bekleme / envanter yönetimi
    FATIGUE_BREAK = auto() # İnsan yorulması, AFK bekleme modu


class BotLogic:
    """Otonom bot döngüsünü yöneten sınıf."""

    def __init__(self, config: AutoBotConfig, clicker: HumanClicker, capture=None):
        self._cfg = config
        self._clicker = clicker
        self._capture = capture
        
        self.state = BotState.IDLE
        self._state_start_time = 0.0
        
        self.successful_catches = 0
        self.total_casts = 0
        self._click_count_in_minigame = 0
        self._prepare_action_done = False
        self._postcatch_action_done = False
        
        self._next_fatigue_time = 0.0
        self._fatigue_duration = 0.0

    def start(self) -> None:
        """Döngüyü başlatır."""
        self.state = BotState.PREPARE
        self._state_start_time = time.time()
        self._click_count_in_minigame = 0
        
        if self._cfg.use_fatigue_system:
            self._next_fatigue_time = time.time() + random.uniform(
                self._cfg.fatigue_interval_min, 
                self._cfg.fatigue_interval_max
            )

    def stop(self) -> None:
        """Döngüyü durdurur."""
        self.state = BotState.IDLE

    def update(self, detection: DetectionResult, frame=None, detector=None) -> tuple[bool, str]:
        """
        Her karede durum makinesini günceller.
        
        Args:
        Args:
            detection: Ekran görüntüsünden tespit sonuçları.
            detector: Detector objesi (opsiyonel, envanter taramak için).
            
        Returns:
            (clicked, status_message): Bu update'te tıklama yapıldı mı, mevcut durum stringi.
        """
        now = time.time()
        elapsed = now - self._state_start_time
        clicked = False
        status_msg = ""

        if self.state == BotState.IDLE:
            status_msg = "Bot Durduruldu"

        elif self.state == BotState.PREPARE:
            # Sadece bu duruma ilk girildiğinde bir kere çalışmalı
            if not getattr(self, "_prepare_action_done", False):
                self._prepare_action_done = True
                
                # 1. Yem tak
                bait_clicked = False
                # Ekranda (envanterde) minik balık var mı kontrol et
                if self._capture is not None and detector is not None:
                    full_frame = self._capture.grab_full_frame()
                    baits = detector.detect_inventory_items(full_frame, item_type="bait")
                    if baits:
                        bx, by = baits[0]
                        self._clicker.right_click_at(bx, by)
                        bait_clicked = True
                        status_msg = "Minik Balik yeme takildi"
                        
                if not bait_clicked:
                    self._clicker.press_key(self._cfg.key_bait)
                    status_msg = "Hazirlik: Normal Yem takildi"
                
            time.sleep(self._cfg.delay_after_bait)
            
            # 2. Zırh değiştir (opsiyonel trick - Animasyon İptali)
            # Metin2'de zırh hızlı slota atanamaz. Envanterde belirlenen (x,y) koordinatına sağ tıklanır.
            # Çıkar ve geri tak yapmak için arka arkaya iki kez sağ tık atılır.
            if self._cfg.use_armor_trick and self._cfg.armor_x > 0 and self._cfg.armor_y > 0:
                # Zırhı çıkar
                self._clicker.right_click_at(self._cfg.armor_x, self._cfg.armor_y)
                time.sleep(0.15)
                # Zırhı giy
                self._clicker.right_click_at(self._cfg.armor_x, self._cfg.armor_y)
                time.sleep(self._cfg.delay_after_armor)
                
            self._transition_to(BotState.CAST)
            if not status_msg:
                status_msg = "Hazirlik: Yem takildi"

        elif self.state == BotState.CAST:
            # Oltayı at
            self._clicker.press_key(self._cfg.key_fish)
            self.total_casts += 1
            
            # Olta atma animasyonu beklemesi
            time.sleep(self._cfg.delay_after_cast)
            
            self._transition_to(BotState.WAITING)
            status_msg = "Olta atildi"

        elif self.state == BotState.WAITING:
            status_msg = f"Balik bekleniyor... ({int(elapsed)}s)"
            
            # Daire (mini-oyun) çıktıysa minigame state'ine geç
            if detection.circle is not None:
                self._transition_to(BotState.MINIGAME)
                
            # Timeout (balık vurmadıysa veya kaçtıysa)
            elif elapsed > self._cfg.timeout_waiting_fish:
                self._transition_to(BotState.POST_CATCH)

        elif self.state == BotState.MINIGAME:
            status_msg = f"MINIGAME: {self._click_count_in_minigame}/3 Tik"
            
            # Daire kaybolduysa oyun bitti
            if detection.circle is None:
                self._transition_to(BotState.POST_CATCH)
            else:
                # Balık içerdeyse tıkla
                if detection.is_fish_inside and detection.fish is not None:
                    if self._clicker.is_ready:
                        # Balığa tıkla
                        if self._clicker.click_at(detection.fish.center_x, detection.fish.center_y):
                            clicked = True
                            self._click_count_in_minigame += 1
                            
                            # 3 tık başarılı olduysa skoru artır
                            if self._click_count_in_minigame == 3:
                                self.successful_catches += 1
                                # 3 tık atıldı, minigame bitti sayılır
                                # Oyun daireyi kapatacaktır, biz POST_CATCH'e geçebiliriz
                                self._transition_to(BotState.POST_CATCH)

        elif self.state == BotState.POST_CATCH:
            status_msg = f"Toparlaniyor... ({int(self._cfg.delay_after_catch - elapsed)}s)"
            
            if not getattr(self, "_postcatch_action_done", False):
                self._postcatch_action_done = True
                
                full_frame = None
                
                # Çöpleri Yere At
                if self._cfg.auto_drop_trash and self._capture is not None and detector is not None:
                    if full_frame is None:
                        full_frame = self._capture.grab_full_frame()
                        
                    trashes = detector.detect_inventory_items(full_frame, item_type="trash")
                    if trashes:
                        status_msg = f"Envanterdeki {len(trashes)} cop atiliyor..."
                        for tx, ty in trashes:
                            # Sürükle bırak (hedef x=50, y=50 oyunun köşesi veya dışı)
                            self._clicker.drag_and_drop(tx, ty, 50, 50)
                            # 'Yere at' onay diyalogu için Enter bas.
                            self._clicker.press_key('enter')
                            time.sleep(0.5)
                
                # Balıkları aç
                if self._cfg.auto_open_fishes and self._capture is not None and detector is not None:
                    if full_frame is None:
                        full_frame = self._capture.grab_full_frame()
                        
                    fishes = detector.detect_inventory_items(full_frame, item_type="fish")
                    if fishes:
                        status_msg = f"Envanterde {len(fishes)} balik aciliyor..."
                        for fx, fy in fishes:
                            self._clicker.right_click_at(fx, fy)
                            time.sleep(0.1)
            
            # Animasyon beklemesi
            if elapsed > self._cfg.delay_after_catch:
                # Yorulma (Fatigue) kontrolü
                if self._cfg.use_fatigue_system and time.time() > self._next_fatigue_time:
                    self._fatigue_duration = random.uniform(
                        self._cfg.fatigue_duration_min, 
                        self._cfg.fatigue_duration_max
                    )
                    self._transition_to(BotState.FATIGUE_BREAK)
                else:
                    # Başa dön
                    self._transition_to(BotState.PREPARE)
                    
        elif self.state == BotState.FATIGUE_BREAK:
            remaining = self._fatigue_duration - elapsed
            status_msg = f"Cay Molasi ☕ (Kalan: {int(remaining)}s)"
            
            if remaining <= 0:
                self._next_fatigue_time = time.time() + random.uniform(
                    self._cfg.fatigue_interval_min, 
                    self._cfg.fatigue_interval_max
                )
                self._transition_to(BotState.PREPARE)

        return clicked, status_msg

    def _transition_to(self, new_state: BotState) -> None:
        """Durum değiştirir ve zamanlayıcıyı sıfırlar."""
        self.state = new_state
        self._state_start_time = time.time()
        
        if new_state == BotState.MINIGAME:
            self._click_count_in_minigame = 0
        elif new_state == BotState.PREPARE:
            self._prepare_action_done = False
        elif new_state == BotState.POST_CATCH:
            self._postcatch_action_done = False
