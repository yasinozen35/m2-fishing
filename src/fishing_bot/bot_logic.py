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

import difflib
import math
import random
import time
from collections import deque
from enum import Enum, auto

from fishing_bot.config import AutoBotConfig
from fishing_bot.clicker import HumanClicker
from fishing_bot.detector import DetectionResult

RARE_FISHES = frozenset({
    "Yabbie Yengeci", "Kral Yengeci", "Altın Sudak", "Kadife Balığı",
    "Altın Yüzük", "Görünmezlik Pelerini", "Bilge Kralın Eldiveni",
    "Hırsızın Eldiveni", "Kaçak Pelerin", "Lucy'nin Yüzüğü", "Denizkızı Anahtarı",
})


class BotState(Enum):
    """Botun mevcut durumu."""
    IDLE = auto()          # Çalışmıyor / duraklatıldı
    PREPARE = auto()       # Yem takma ve zırh değiştirme
    CAST = auto()          # Oltayı suya atma
    WAITING = auto()       # Dairenin belirmesini bekleme
    MINIGAME = auto()      # Balık yakalama mini-oyunu (3 tık)
    POST_CATCH = auto()    # Yakaladıktan sonra bekleme / envanter yönetimi
    FATIGUE_BREAK = auto() # İnsan yorulması, AFK bekleme modu
    MICRO_BREAK = auto()   # Kısa telefona bakma molası


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
        self._inventory_checked = False
        self._inventory_open_retries = 0

        self._next_fatigue_time = 0.0
        self._next_micro_break_time = 0.0
        self._break_duration = 0.0
        self._break_is_micro = False

        # Frame-timer: time.sleep() yerine non-blocking bekleme
        self._block_until: float = 0.0
        # WAITING state: ardışık circle tespit sayacı (false positive önleme)
        self._consecutive_circle_count: int = 0
        # MINIGAME: balık pozisyon geçmişi (son 5 frame) — adaptif prediction için
        self._fish_pos_history: deque = deque(maxlen=5)
        # MINIGAME: tıklama ritim pattern'i (insansı çeşitlilik)
        self._click_rhythm: list[float] = []
        self._click_rhythm_idx: int = 0
        # MINIGAME: bilerek ıskalama sayacı
        self._catch_streak: int = 0
        # WAITING: idle mouse hareket zamanlayıcısı
        self._last_idle_move: float = 0.0
        # WAITING: state geçiş tereddütü
        self._hesitation_start: float = 0.0
        self._hesitation_duration: float = 0.0
        # Watchdog: minigame bitişini takip et
        self._last_minigame_end_time: float = 0.0
        # MINIGAME: İnsansı reaksiyon gecikmesi sistemi
        self._reaction_delay: float = 0.0       # Bu tıklama için random reaksiyon süresi
        self._fish_entered_safe_at: float = 0.0  # Balık safe zone'a ilk girdiği an
        self._fish_was_inside: bool = False      # Önceki frame'de balık içerde miydi?
        
        # Dinamik yem tuşu kaydırması
        self._bait_slot_offset: int = 0
        self._last_bait_switch_time: float = 0.0
        # Yem tuşu sırası: 1,2,3,4 → F1,F2,F3,F4 → tekrar 1
        self._bait_keys: list[str] = ["1", "2", "3", "4", "f1", "f2", "f3", "f4"]
        
        # Karşılaşılan balıkların sayacı (GUI için)
        self.encountered_fishes: dict[str, int] = {}

        # Oturum istatistikleri (GUI için)
        self._session_start_time = 0.0
        self._last_yabbie_time: float | None = None
        self._yabbie_timestamps: list[float] = []
        self._rare_fish_counts: dict[str, int] = {}
        self._cycle_start_time: float | None = None
        self._cycle_durations: deque = deque(maxlen=500)

    def start(self) -> None:
        """Döngüyü başlatır."""
        self.state = BotState.PREPARE
        self._state_start_time = time.time()
        self._click_count_in_minigame = 0
        self._bait_slot_offset = 0  # Her yeni başlatmada yem döngüsünü başa al (1'den başla)
        self._last_bait_switch_time = 0.0
        
        self._session_start_time = time.time()
        self._last_yabbie_time = None
        self._yabbie_timestamps.clear()
        self._rare_fish_counts.clear()
        self._cycle_durations.clear()
        self._cycle_start_time = None
        self._schedule_fatigue()
        self._schedule_micro_break()

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

        # ── WATCHDOG: Minigame sonrası 10sn içinde yeni minigame başlamazsa ──
        # CAST state'ine zorla (space'e tekrar bas)
        if (self.state not in (BotState.IDLE, BotState.MINIGAME, BotState.FATIGUE_BREAK, BotState.MICRO_BREAK)
                and self._last_minigame_end_time > 0
                and now - self._last_minigame_end_time > self._cfg.retry_cast_timeout):
            status_msg = f"Watchdog: {int(now - self._last_minigame_end_time)}s oldu, tekrar olta atiliyor..."
            self._last_minigame_end_time = 0.0  # Tek seferlik tetikle
            self._transition_to(BotState.CAST)
            return False, status_msg

        if self.state == BotState.IDLE:
            status_msg = "Bot Durduruldu"

        elif self.state == BotState.PREPARE:
            # Bekleme süresi doldu mu?
            if now < self._block_until:
                status_msg = f"Hazirlik: Bekleniyor... ({self._block_until - now:.1f}s)"
                return False, status_msg

            # Envanter açma kontrolü
            if self._cfg.use_inventory_check and self._cfg.inventory_region_w > 0 and self._cfg.inventory_region_h > 0:
                if not getattr(self, "_inventory_checked", False):
                    inv_region = {
                        'top': self._cfg.inventory_region_y,
                        'left': self._cfg.inventory_region_x,
                        'width': self._cfg.inventory_region_w,
                        'height': self._cfg.inventory_region_h
                    }
                    inv_text = self._read_ocr_region(inv_region)
                    inv_text_norm = self._normalize_tr(inv_text)
                    
                    if "envanter" not in inv_text_norm and "inventory" not in inv_text_norm:
                        retries = getattr(self, "_inventory_open_retries", 0)
                        if retries < 3:
                            self._inventory_open_retries = retries + 1
                            self._clicker.press_key('i')
                            self._block_until = now + 0.5
                            status_msg = f"Envanter kapali, aciliyor (Deneme {self._inventory_open_retries}/3)..."
                            return False, status_msg
                        else:
                            # 3 deneme de başarısız oldu, kilitlenmeyi önlemek için geçiyoruz.
                            self._inventory_checked = True
                            self._inventory_open_retries = 0
                    else:
                        self._inventory_checked = True
                        self._inventory_open_retries = 0

            # Non-blocking: sadece bu state'e ilk girildiğinde aksiyonu yap
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
                    # Yem sırasından tuşu al: 1→2→3→4→f1→f2→f3→f4→1...
                    idx = self._bait_slot_offset % len(self._bait_keys)
                    current_bait_key = self._bait_keys[idx]
                    self._clicker.press_key(current_bait_key)
                    status_msg = f"Hazirlik: Normal Yem takildi (Tus: {current_bait_key})"

                # Yem sonrası bekleme — olta atmak için (config'den ayarlanabilir)
                self._block_until = now + self._randomize_delay(self._cfg.delay_after_bait)
                return False, status_msg

            # Zırh trick POST_CATCH'e taşındı — minigame biter bitmez yapılıyor
            self._transition_to(BotState.CAST)
            if not status_msg:
                status_msg = "Hazirlik: Yem takildi"

        elif self.state == BotState.CAST:
            # Non-blocking: oltayı sadece bir kez at
            if not getattr(self, "_cast_done", False):
                self._cast_done = True
                # Oltayı at - oyunun yemi algılaması için mini gecikme
                self._block_until = now + 0.05
                status_msg = "CAST: Hazirlaniyor..."
                return False, status_msg

            if now < self._block_until:
                status_msg = "CAST: Hazirlaniyor..."
                return False, status_msg

            if not getattr(self, "_cast_pressed", False):
                self._cast_pressed = True
                # Space tuşuna bas
                self._clicker.press_key(self._cfg.key_fish, hold_min=0.12, hold_max=0.25)
                self.total_casts += 1
                # Cast sonrası animasyon beklemesi başlat (bu sürede tespit yapma)
                self._block_until = now + self._randomize_delay(self._cfg.delay_after_cast)
                status_msg = "CAST: Olta atildi, animasyon bekleniyor..."
                return False, status_msg

            # Animasyon süresi doldu mu?
            if now < self._block_until:
                status_msg = f"CAST: Animasyon... ({self._block_until - now:.1f}s)"
                return False, status_msg

            self._transition_to(BotState.WAITING)
            status_msg = "Olta atildi, balik bekleniyor"

        elif self.state == BotState.WAITING:
            status_msg = f"Balik bekleniyor... ({int(elapsed)}s)"
            
            # Chat okuyucuyu başlat/güncelle (İptal sistemi ve Yem kontrolü için gerekli)
            if not hasattr(self, '_chat_reader') or self._chat_reader is None:
                from fishing_bot.chat_reader import ChatReader
                self._chat_reader = ChatReader({
                    'top': self._cfg.chat_region_y,
                    'left': self._cfg.chat_region_x,
                    'width': self._cfg.chat_region_w,
                    'height': self._cfg.chat_region_h
                })
            else:
                self._chat_reader.update_region(
                    self._cfg.chat_region_x, self._cfg.chat_region_y,
                    self._cfg.chat_region_w, self._cfg.chat_region_h
                )
                
            # ── YEM BİTTİ KONTROLÜ (Oltayı attıktan ~1.2 sn sonra SADECE 1 KERE chat'e bak ve son yem değişiminden sonra 10 sn geçmiş olmalı) ──
            if elapsed > 1.2 and not getattr(self, "_checked_bait_error", False) and (now - self._last_bait_switch_time > 10.0):
                self._checked_bait_error = True
                if self._cfg.chat_region_w > 0 and self._cfg.chat_region_h > 0:
                    raw_chat = self._chat_reader.get_raw_chat()
                    if raw_chat:
                        chat_norm = raw_chat.lower().replace('ü', 'u').replace('ö', 'o').replace('ı', 'i').replace('ş', 's').replace('ğ', 'g').replace('ç', 'c').replace('i̇', 'i')
                        # Oyun "Önce yemi çengele geçir." uyarısı verdiyse yem bitmiştir!
                        if "once yemi" in chat_norm or "cengele gecir" in chat_norm:
                            self._bait_slot_offset = (self._bait_slot_offset + 1) % len(self._bait_keys)
                            self._last_bait_switch_time = now
                            idx = self._bait_slot_offset % len(self._bait_keys)
                            next_key = self._bait_keys[idx]
                            self._transition_to(BotState.PREPARE)
                            status_msg = f"Yem bitti! Sonraki yem: {next_key}"
                            return False, status_msg

            # ── Idle Mouse Hareketi (İnsan sıkılmış gibi) ──
            # Her 3-7 saniyede bir fareyi hafifçe oynat
            if now - self._last_idle_move > random.uniform(3.0, 7.0):
                self._last_idle_move = now
                try:
                    import pyautogui
                    cur_x, cur_y = pyautogui.position()
                    jitter_x = cur_x + random.randint(-25, 25)
                    jitter_y = cur_y + random.randint(-25, 25)
                    # Küçük, yavaş hareket (oyuncu etrafa bakıyor gibi)
                    import ctypes
                    ctypes.windll.user32.SetCursorPos(jitter_x, jitter_y)
                except Exception:
                    pass  # Mouse hareketi başarısız olursa sessizce devam et

            # Daire tespit edilirse MINIGAME'e geç
            if detection.circle is not None:
                # ── Tespit Kör Noktası (Anti-Cheat) ──
                # %2-3 ihtimalle circle'ı "görme" (insan bazen kaçırır)
                blind_spot = self._clicker._human.detection_blind_spot_rate
                if blind_spot > 0 and random.random() < blind_spot:
                    status_msg = "Balik bekleniyor... (gozden kacti)"
                    return False, status_msg

                # ── State Geçiş Tereddütü (Anti-Cheat) ──
                # Circle görüldü ama hemen tepki verme — 30-120ms "düşün"
                if self._hesitation_start == 0.0:
                    self._hesitation_start = now
                    self._hesitation_duration = random.uniform(
                        self._clicker._human.transition_hesitation_min,
                        self._clicker._human.transition_hesitation_max
                    )
                    return False, status_msg
                if now - self._hesitation_start < self._hesitation_duration:
                    return False, status_msg
                self._hesitation_start = 0.0
                
                # ── İPTAL SİSTEMİ (Chat OCR) ──
                if self._cfg.use_fish_ocr and self._cfg.chat_region_w > 0 and self._cfg.chat_region_h > 0:
                    hooked_fish = None
                    
                    KNOWN_FISHES = [
                        "Büyük Sudak Balığı", "Yılan Başı Balığı", "Görünmezlik Pelerini", "Bilge Kralın Eldiveni",
                        "Hırsızın Eldiveni", "Denizkızı Anahtarı", "Lucy'nin Yüzüğü", "Kurbağa Balığı",
                        "Dere Alabalığı", "Kadife Balığı", "Kral Yengeci", "Altın Yüzük", "Kaçak Pelerin", 
                        "Ringa Balığı", "Gümüş Balığı", "Şiraz Balığı", "Sudak Balığı", "Altın Sudak", "Altın Sudak Balığı",
                        "Ot Sazanı", "Som Balığı", "Minik Balık", "Saç Boyası", "Alabalık", "Uskumru", 
                        "Palamut", "Zargana", "Yabbie Yengeci", "Levrek", "Yayın Balığı", "Çopra", "Sazan", "Lüfer Balığı"
                    ]
                    
                    # Kullanıcının eklediği özel balıkları ve iptal listesindekileri tanınan kelimelere dahil et
                    if hasattr(self._cfg, 'custom_fishes') and self._cfg.custom_fishes:
                        KNOWN_FISHES.extend(self._cfg.custom_fishes)
                    if hasattr(self._cfg, 'ignored_fishes') and self._cfg.ignored_fishes:
                        KNOWN_FISHES.extend(self._cfg.ignored_fishes)
                        
                    # Tekrarlayan isimleri çıkar
                    KNOWN_FISHES = list(set(KNOWN_FISHES))

                    # Dinamik olarak en uzun isme göre sırala ki alt dize çakışmaları kesin olarak önlensin
                    KNOWN_FISHES.sort(key=len, reverse=True)

                    def normalize_tr(text):
                        replacements = {'ü': 'u', 'ö': 'o', 'ı': 'i', 'ş': 's', 'ğ': 'g', 'ç': 'c', 'i̇': 'i'}
                        text = text.lower()
                        for k, v in replacements.items():
                            text = text.replace(k, v)
                        return text
                    
                    # Chat yazısının ekrana düşmesi oyun motorunda gecikebilir
                    for _ in range(5):
                        raw_chat = self._chat_reader.get_raw_chat()
                        fish_detected_in_chat = False
                        
                        if raw_chat:
                            lines = raw_chat.split('\n')
                            # En son (en alttaki) mesajlara öncelik ver
                            for line in reversed(lines):
                                # Oyuncu mesajlarını (içinde ':' olan) atla, sadece sistem mesajlarına bak
                                if ":" in line:
                                    continue
                                
                                line_norm = normalize_tr(line)
                                detected_known_fish = None
                                
                                # Hangi balığın tutulduğunu tam olarak tespit et (Fuzzy OCR eşleştirme)
                                best_fish = None
                                best_score = 0.0
                                
                                for known in KNOWN_FISHES:
                                    known_norm = normalize_tr(known)
                                    len_k = len(known_norm)
                                    
                                    if len(line_norm) < len_k:
                                        # Metin balık adından kısaysa tamamına bak
                                        ratio = difflib.SequenceMatcher(None, known_norm, line_norm).ratio()
                                        m = ratio * (len_k + len(line_norm)) / 2.0
                                        score = m * ratio
                                        if score > best_score and ratio > 0.65:
                                            best_score = score
                                            best_fish = known
                                    else:
                                        # Karakter bazlı sliding window (OCR hatalarını kompanse eder)
                                        # score = (Eşleşen Karakter Sayısı) * (Benzerlik Oranı)
                                        # Bu formül sayesinde "Büyük Sudak Balığı" hatalı okunsa bile,
                                        # "Sudak Balığı"nın 100% eşleşmesini yenecektir.
                                        for i in range(len(line_norm) - len_k + 1):
                                            window = line_norm[i:i+len_k]
                                            ratio = difflib.SequenceMatcher(None, known_norm, window).ratio()
                                            m = ratio * (len_k + len(window)) / 2.0
                                            score = m * ratio
                                            
                                            if score > best_score and ratio > 0.65:
                                                best_score = score
                                                best_fish = known
                                
                                detected_known_fish = best_fish
                                
                                # Tespit edilen balık bizim iptal listemizde var mı kontrol et
                                if detected_known_fish:
                                    fish_detected_in_chat = True
                                    self._current_hooked_fish = detected_known_fish
                                    self.encountered_fishes[detected_known_fish] = self.encountered_fishes.get(detected_known_fish, 0) + 1
                                    self._record_fish_encounter(detected_known_fish, now)
                                    
                                    for ignored_fish in self._cfg.ignored_fishes:
                                        # İptal listesindeki balıklarla tam eşleşme arıyoruz
                                        if normalize_tr(ignored_fish) == normalize_tr(detected_known_fish):
                                            hooked_fish = detected_known_fish
                                            break
                                    # Herhangi bir balık tespit edildiği an (iptal edilsin veya edilmesin) 
                                    # chat'in güncellendiğinden eminiz. Diğer satırlara bakmaya gerek yok.
                                    break 
                        
                        if fish_detected_in_chat:
                            # Balık bulundu! Gereksiz yere 5 kere bekleyip botu dondurma.
                            break
                        time.sleep(0.06)  # 60ms bekle ve tekrar oku
                        
                    if hooked_fish:
                        # İnsan okuma ve tepki verme süresi (Kullanıcı isteğiyle 1 sn yapıldı)
                        time.sleep(random.uniform(0.9, 1.2))
                        
                        # ── ESC basmadan önce minigame'in hala aktif olduğunu doğrula! ──
                        # Aksi halde minigame kapandıysa ESC tuşu oyun menüsünü açar.
                        minigame_still_active = False
                        if self._capture is not None and detector is not None:
                            verify_frame = self._capture.grab_frame()
                            cached_circle = detector._cached_circle
                            if cached_circle is not None:
                                # Hızlı ve yüksek güvenilirlikli çember doğrulaması kullan (HoughCircles'ın tek karede ıskalama ihtimaline karşı)
                                minigame_still_active = detector._verify_cached_circle(verify_frame, cached_circle)
                            else:
                                verify_det = detector.detect(verify_frame)
                                if verify_det.circle is not None:
                                    minigame_still_active = True
                                
                        if minigame_still_active:
                            # İptal et (ESC tuşu) insani basma süresiyle
                            self._clicker.press_key('esc', hold_min=0.10, hold_max=0.22)
                            status_msg = f"İptal Edildi: {hooked_fish}"
                        else:
                            status_msg = f"İptal İptal Edildi (Minigame zaten kapanmış): {hooked_fish}"
                            
                        self._transition_to(BotState.POST_CATCH)
                        return False, status_msg

                self._transition_to(BotState.MINIGAME)
            else:
                # Circle yok → sayacı sıfırla, tereddütü de sıfırla
                self._consecutive_circle_count = 0
                self._hesitation_start = 0.0

            # Timeout (balık vurmadıysa veya kaçtıysa)
            if elapsed > self._cfg.timeout_waiting_fish:
                self._transition_to(BotState.POST_CATCH)

        elif self.state == BotState.MINIGAME:
            if getattr(self, "_current_hooked_fish", None) == "Yabbie Yengeci" and getattr(self._cfg, "leave_to_me_yabbie", False):
                status_msg = "Bana Birak: Yabbie Yengeci Bekleniyor..."
                if detection.circle is None:
                    missing_count = getattr(self, "_circle_missing_count", 0) + 1
                    self._circle_missing_count = missing_count
                    if missing_count >= 5:
                        if detector is not None:
                            detector.invalidate_circle_cache()
                        self._circle_missing_count = 0
                        self._transition_to(BotState.POST_CATCH)
                else:
                    self._circle_missing_count = 0
                return False, status_msg

            status_msg = f"MINIGAME: {self._click_count_in_minigame}/3 Tik"

            # Daire kaybolduysa hemen çıkma — 5 frame üst üste yoksa gerçekten bitti
            if detection.circle is None:
                missing_count = getattr(self, "_circle_missing_count", 0) + 1
                self._circle_missing_count = missing_count
                if missing_count >= 5:
                    if self._click_count_in_minigame >= 3:
                        self.successful_catches += 1
                    if detector is not None:
                        detector.invalidate_circle_cache()
                    self._circle_missing_count = 0
                    self._transition_to(BotState.POST_CATCH)
                else:
                    status_msg = f"MINIGAME: Circle yok ({missing_count}/5)..."
                    return False, status_msg  # Tıklama yapma, bekle
            else:
                self._circle_missing_count = 0
                # Maksimum 8 tık — 15sn minigame'de ~0.5sn aralıklarla doğal ritim
                if self._click_count_in_minigame >= self._cfg.max_clicks_per_minigame:
                    status_msg = f"MINIGAME: {self._click_count_in_minigame} tik tamam, circle kapaniyor..."
                    return False, status_msg
                # Balık içerdeyse işle
                if detection.is_fish_inside and detection.fish is not None:

                    # ── ADAPTİF HIZ VE TAHMİN (PREDICTION) ALGORİTMASI ──
                    current_x = detection.fish.center_x
                    current_y = detection.fish.center_y
                    now = time.time()

                    # Pozisyon geçmişine ekle (son 5 frame)
                    self._fish_pos_history.append((current_x, current_y, now))

                    # Hız hesapla (son 5 frame moving average)
                    speed = 0.0
                    vx, vy = 0.0, 0.0
                    if len(self._fish_pos_history) >= 2:
                        velocities = []
                        history_list = list(self._fish_pos_history)
                        for i in range(1, len(history_list)):
                            px, py, pt = history_list[i]
                            ppx, ppy, ppt = history_list[i - 1]
                            dt_i = pt - ppt
                            if 0 < dt_i < 0.2:
                                vx_i = (px - ppx) / dt_i
                                vy_i = (py - ppy) / dt_i
                                velocities.append((vx_i, vy_i))
                        if velocities:
                            vx = sum(v[0] for v in velocities) / len(velocities)
                            vy = sum(v[1] for v in velocities) / len(velocities)
                            speed = math.hypot(vx, vy)

                    # Hıza göre DİNAMİK safe_radius
                    base_radius = detection.circle.radius
                    if speed > 250:       # Efsanevi/ultra hızlı balık
                        safe_radius = base_radius * 0.65
                    elif speed > 150:     # Nadir/çok hızlı balık
                        safe_radius = base_radius * 0.72
                    elif speed > 80:      # Orta-hızlı balık
                        safe_radius = base_radius * 0.78
                    else:                 # Normal/yavaş balık
                        safe_radius = base_radius * 0.85

                    dist_to_center = math.hypot(
                        current_x - detection.circle.center_x,
                        current_y - detection.circle.center_y
                    )

                    if dist_to_center > safe_radius:
                        # Balık safe zone dışında → reaksiyon sıfırla
                        self._fish_was_inside = False
                        self._fish_entered_safe_at = 0.0
                        self._reaction_delay = 0.0
                        return False, status_msg

                    # Cooldown aktifken reaksiyon süresini başlatma (anlık tıklama yarış durumunu önle)
                    if not self._clicker.is_ready:
                        self._fish_was_inside = False
                        self._fish_entered_safe_at = 0.0
                        self._reaction_delay = 0.0
                        return False, "MINIGAME: Tıklama cooldown'u bekleniyor..."

                    # ── İNSANSI REAKSİYON GECİKMESİ SİSTEMİ (ANTI-CHEAT) ──
                    # Balık safe zone'a İLK girdiğinde zamanı kaydet.
                    # Her tıklama için yeni bir reaksiyon süresi belirle.
                    if not self._fish_was_inside:
                        self._fish_was_inside = True
                        self._fish_entered_safe_at = now
                        self._reaction_delay = random.uniform(
                            self._clicker._human.reaction_min,
                            self._clicker._human.reaction_max
                        )

                    # Reaksiyon süresi dolmadıysa tıklama YAPMA
                    reaction_elapsed = now - self._fish_entered_safe_at
                    if reaction_elapsed < self._reaction_delay:
                        status_msg = (
                            f"MINIGAME: {self._click_count_in_minigame}/3 Tik "
                            f"(reaksiyon: {reaction_elapsed*1000:.0f}/{self._reaction_delay*1000:.0f}ms)"
                        )
                        return False, status_msg

                    # ── PREDICTION: TÜM BALIKLARA UYGULA (hız > eşik ise) ──
                    target_x = current_x
                    target_y = current_y

                    pred_threshold = self._clicker._human.prediction_speed_threshold
                    move_duration = 0.0
                    
                    if self._clicker._human.targeting_mode == "organic":
                        move_duration = self._clicker._human.prediction_look_ahead_base

                    if speed > pred_threshold:
                        # ── HEDEFLEME MODU SEÇİMİ ──
                        if self._clicker._human.targeting_mode == "terminator":
                            look_ahead_base = 0.02
                            look_ahead_max = 0.04
                            move_duration = 0.0
                        else:
                            look_ahead_base = self._clicker._human.prediction_look_ahead_base
                            look_ahead_max = self._clicker._human.prediction_look_ahead_max

                        # Dinamik look_ahead: hıza göre ölçeklenir
                        speed_factor = min(1.0, speed / 300.0)  # 0-1 arası normalleştir
                        look_ahead = look_ahead_base + speed_factor * (look_ahead_max - look_ahead_base)

                        if self._clicker._human.targeting_mode == "organic":
                            move_duration = look_ahead

                        # Velocity bazlı pozisyon tahmini
                        target_x = int(current_x + vx * look_ahead)
                        target_y = int(current_y + vy * look_ahead)

                        # Ek lead: balık yönüne doğru ekstra offset
                        # lead_factor ayarlanabilir: 0.3=az lead, 1.2=çok lead
                        if speed > 0:
                            lead_px = min(
                                self._clicker._human.prediction_max_lead_px,
                                int(speed * look_ahead * self._clicker._human.prediction_lead_factor)
                            )
                            # ── Prediction Gürültüsü (Anti-Cheat) ──
                            # İnsan her zaman optimal lead yapamaz — over/under-shoot
                            noise_sigma = self._clicker._human.prediction_noise_sigma
                            if noise_sigma > 0:
                                lead_px = int(lead_px * random.gauss(1.0, noise_sigma))
                                lead_px = max(0, lead_px)  # Negatif olmasın
                            target_x = int(target_x + (vx / speed) * lead_px)
                            target_y = int(target_y + (vy / speed) * lead_px)

                    # ── ÇEMBER SINIRI KORUMASI ──
                    # Prediction hedefi çember dışına taşıyabilir.
                    # Tıklama HER ZAMAN çemberin İÇİNDE kalmalı.
                    circle_cx = detection.circle.center_x
                    circle_cy = detection.circle.center_y
                    target_dist = math.hypot(target_x - circle_cx, target_y - circle_cy)

                    # Maksimum izin verilen mesafe: config'den ayarlanabilir
                    # Varsayılan %90, GUI'den 0.75-0.95 arası ayarlanabilir
                    max_click_radius = int(detection.circle.radius * self._clicker._human.click_inner_margin)

                    if target_dist > max_click_radius and target_dist > 0:
                        # Hedefi çember sınırına geri çek (yönde clamp)
                        scale = max_click_radius / target_dist
                        target_x = int(circle_cx + (target_x - circle_cx) * scale)
                        target_y = int(circle_cy + (target_y - circle_cy) * scale)

                    # ── YATAY JITTER: Balığın sağına/soluna rastgele tıkla ──
                    h_jitter = self._clicker._human.horizontal_jitter_px
                    if h_jitter > 0:
                        target_x += random.randint(-h_jitter, h_jitter)

                    # ── TIKLAMA KARARI ──
                    if self._clicker.is_ready:
                        # ── Bilerek Iskalama (hız-bazlı) ──
                        # Hızlı balıkta kaçırma oranı daha yüksek
                        _miss_rate = self._clicker._human.intentional_miss_rate
                        if speed > 100:
                            _miss_rate = self._clicker._human.fast_fish_miss_rate
                        _should_miss = random.random() < _miss_rate
                        if _should_miss and self._click_count_in_minigame >= 1:
                            # Tıklamayı ATLA (bilerek kaçır)
                            self._clicker._last_click_time = time.time()
                            self._fish_was_inside = False
                            self._fish_entered_safe_at = 0.0
                            self._reaction_delay = 0.0
                            self._click_count_in_minigame += 1  # Tık sayılır ama aslında kaçırdık
                            return False, status_msg

                        # Tahmin edilen noktaya HIZLI tıkla (bezier'siz, insansı)
                        if self._clicker.fast_click_at(target_x, target_y, duration=move_duration):
                            clicked = True
                            self._click_count_in_minigame += 1

                            # ── Tıklama sonrası: reaksiyonu sıfırla ──
                            # Her tıklama yeni bir "görsel karar" gerektirir
                            self._fish_was_inside = False
                            self._fish_entered_safe_at = 0.0
                            self._reaction_delay = 0.0
                            self._fish_pos_history.clear()

                            # ── İnsansı Ritim: tıklamadan SONRA cooldown'u ayarla ──
                            if self._click_rhythm and self._click_rhythm_idx < len(self._click_rhythm):
                                self._clicker._human.click_cooldown = self._click_rhythm[self._click_rhythm_idx]
                                self._click_rhythm_idx += 1

        elif self.state == BotState.POST_CATCH:
            status_msg = f"Toparlaniyor... ({int(self._cfg.delay_after_catch - elapsed)}s)"
            
            if not getattr(self, "_postcatch_action_done", False):
                self._postcatch_action_done = True
                self._armor_trick_used = False

                # ── ZIRH TRICK: Minigame bittiği ANDA zırh çıkar-tak ──
                if self._cfg.use_armor_trick and self._cfg.armor_x > 0 and self._cfg.armor_y > 0:
                    self._clicker.right_click_at(self._cfg.armor_x, self._cfg.armor_y)
                    status_msg = "Zirh trick: Animasyon iptal edildi"
                    self._armor_trick_used = True

                full_frame = None

                # Envanter işlemleri (sadece zırh trick KAPALIYSA yap)
                if not self._armor_trick_used:
                    # Çöpleri Yere At
                    if self._cfg.auto_drop_trash and self._capture is not None and detector is not None:
                        if full_frame is None:
                            full_frame = self._capture.grab_full_frame()

                        trashes = detector.detect_inventory_items(full_frame, item_type="trash", threshold=0.60)
                        if trashes:
                            status_msg = f"Envanterde {len(trashes)} cop bulundu, atiliyor..."
                            drop_x = self._cfg.trash_drop_x
                            drop_y = self._cfg.trash_drop_y
                            for tx, ty in trashes:
                                self._clicker.drag_and_drop(tx, ty, drop_x, drop_y)
                                # "Evet" butonunu bul ve tıkla (Enter yerine)
                                time.sleep(0.3)  # Dialog'un açılmasını bekle
                                confirm_frame = self._capture.grab_full_frame()
                                yes_btn = detector.detect_yes_button(confirm_frame, threshold=0.60)
                                if yes_btn:
                                    self._clicker.left_click_screen(yes_btn[0], yes_btn[1])
                                    status_msg = f"Cop atildi (Yes butonuna tiklandi)"
                                else:
                                    # Fallback: Enter dene
                                    self._clicker.press_key('enter')
                                    status_msg = f"Cop atildi (Enter ile onaylandi)"
                                time.sleep(random.uniform(0.35, 0.55))
                        else:
                            status_msg = "Cop bulunamadi (template eslesmedi)"

                    # Balıkları aç
                    if self._cfg.auto_open_fishes and self._capture is not None and detector is not None:
                        if full_frame is None:
                            full_frame = self._capture.grab_full_frame()

                        fishes = detector.detect_inventory_items(full_frame, item_type="fish", threshold=0.60)
                        if fishes:
                            status_msg = f"Envanterde {len(fishes)} balik bulundu, aciliyor..."
                            for fx, fy in fishes:
                                self._clicker.right_click_at(fx, fy)
                                time.sleep(random.uniform(0.08, 0.15))

            # ── Zırh trick kullanıldıysa HEMEN PREPARE'e geç (bekleme YOK) ──
            if getattr(self, "_armor_trick_used", False):
                if not self._maybe_take_break():
                    self._transition_to(BotState.PREPARE)
            else:
                # Animasyon beklemesi (rastgeleleştirilmiş) — normal akış
                _postcatch_delay = getattr(self, "_postcatch_target_delay", 0.0)
                if _postcatch_delay == 0.0:
                    self._postcatch_target_delay = self._randomize_delay(self._cfg.delay_after_catch)
                    _postcatch_delay = self._postcatch_target_delay
                if elapsed > _postcatch_delay:
                    if not self._maybe_take_break():
                        self._transition_to(BotState.PREPARE)
                    
        elif self.state in (BotState.FATIGUE_BREAK, BotState.MICRO_BREAK):
            remaining = self._break_duration - elapsed
            if self._break_is_micro:
                status_msg = f"Telefona Bakiyor (Kalan: {int(remaining)}s)"
            else:
                status_msg = f"Cay Molasi (Kalan: {int(remaining)}s)"
            
            # ── Moladayken Rastgele Fare Hareketleri (Bilgisayar başında vakit geçiriyor gibi) ──
            if now - getattr(self, "_last_idle_move", 0.0) > random.uniform(2.0, 5.0):
                self._last_idle_move = now
                try:
                    import pyautogui
                    cur_x, cur_y = pyautogui.position()
                    jitter_x = cur_x + random.randint(-60, 60)
                    jitter_y = cur_y + random.randint(-60, 60)
                    import ctypes
                    ctypes.windll.user32.SetCursorPos(jitter_x, jitter_y)
                except Exception:
                    pass
            
            if remaining <= 0:
                if self._break_is_micro:
                    self._schedule_micro_break()
                else:
                    self._schedule_fatigue()
                self._transition_to(BotState.PREPARE)

        return clicked, status_msg

    def _record_fish_encounter(self, fish_name: str, now: float) -> None:
        if fish_name == "Yabbie Yengeci":
            self._last_yabbie_time = now
            self._yabbie_timestamps.append(now)
        if fish_name in RARE_FISHES:
            self._rare_fish_counts[fish_name] = self._rare_fish_counts.get(fish_name, 0) + 1

    def get_session_stats(self) -> dict:
        now = time.time()
        session_elapsed = now - self._session_start_time if self._session_start_time else 0.0

        if self._last_yabbie_time is None:
            last_yabbie = "Henüz yok"
        else:
            ago = now - self._last_yabbie_time
            if ago < 60:
                last_yabbie = f"{int(ago)} sn önce"
            elif ago < 3600:
                last_yabbie = f"{int(ago // 60)} dk önce"
            else:
                last_yabbie = time.strftime("%H:%M", time.localtime(self._last_yabbie_time))

        hours = max(session_elapsed / 3600.0, 1.0 / 3600.0)
        yabbie_count = len(self._yabbie_timestamps)
        yabbie_per_hour = yabbie_count / hours if session_elapsed > 0 else 0.0

        avg_cycle = 0.0
        if self._cycle_durations:
            avg_cycle = sum(self._cycle_durations) / len(self._cycle_durations)

        return {
            "last_yabbie": last_yabbie,
            "yabbie_per_hour": yabbie_per_hour,
            "yabbie_count": yabbie_count,
            "avg_cycle_sec": avg_cycle,
            "cycle_count": len(self._cycle_durations),
            "rare_total": sum(self._rare_fish_counts.values()),
            "session_minutes": session_elapsed / 60.0,
        }

    def _schedule_fatigue(self) -> None:
        if self._cfg.use_fatigue_system:
            self._next_fatigue_time = time.time() + random.uniform(
                self._cfg.fatigue_interval_min,
                self._cfg.fatigue_interval_max,
            )

    def _schedule_micro_break(self) -> None:
        if self._cfg.use_fatigue_system and self._cfg.use_micro_breaks:
            self._next_micro_break_time = time.time() + random.uniform(
                self._cfg.micro_break_interval_min,
                self._cfg.micro_break_interval_max,
            )

    def _maybe_take_break(self) -> bool:
        if not self._cfg.use_fatigue_system:
            return False

        now = time.time()
        fatigue_due = now >= self._next_fatigue_time
        micro_due = self._cfg.use_micro_breaks and now >= self._next_micro_break_time

        if fatigue_due:
            self._break_duration = random.uniform(
                self._cfg.fatigue_duration_min,
                self._cfg.fatigue_duration_max,
            )
            self._break_is_micro = False
            self._transition_to(BotState.FATIGUE_BREAK)
            return True

        if micro_due:
            self._break_duration = random.uniform(
                self._cfg.micro_break_duration_min,
                self._cfg.micro_break_duration_max,
            )
            self._break_is_micro = True
            self._transition_to(BotState.MICRO_BREAK)
            return True

        return False

    def _randomize_delay(self, base_delay: float) -> float:
        """Sabit delay'e ±% insansı gürültü ekler (Anti-Cheat)."""
        r = self._cfg.timing_randomization
        return base_delay * random.uniform(1.0 - r, 1.0 + r)

    def _transition_to(self, new_state: BotState) -> None:
        """Durum değiştirir ve zamanlayıcıyı sıfırlar."""
        old_state = self.state
        self.state = new_state
        self._state_start_time = time.time()

        if old_state == BotState.POST_CATCH and new_state in (
            BotState.PREPARE, BotState.FATIGUE_BREAK, BotState.MICRO_BREAK
        ):
            if self._cycle_start_time is not None:
                self._cycle_durations.append(time.time() - self._cycle_start_time)
                self._cycle_start_time = None
        
        if new_state in (BotState.IDLE, BotState.WAITING):
            self._current_hooked_fish = None

        if new_state == BotState.MINIGAME:
            self._last_minigame_end_time = 0.0  # Watchdog sıfırla
            self._click_count_in_minigame = 0
            self._fish_clicked_this_pass = False
            self._fish_pos_history.clear()  # Yeni minigame → temiz pozisyon geçmişi
            self._circle_missing_count = 0  # Circle dalgalanma sayacı
            # Reaksiyon gecikmesi sıfırla
            self._reaction_delay = 0.0
            self._fish_entered_safe_at = 0.0
            self._fish_was_inside = False

            # ── DİNAMİK Tıklama Ritmi (Anti-Cheat) ──
            # Sabit 5 pattern YERİNE: prosedürel Gauss gürültüsü ile canlı üretim
            base_cooldown = self._clicker._human.click_cooldown
            if self._clicker._human.use_dynamic_rhythm:
                sigma = self._clicker._human.rhythm_noise_sigma
                self._click_rhythm = [
                    base_cooldown * random.gauss(1.0, sigma),
                    base_cooldown * random.gauss(1.0, sigma),
                    base_cooldown * random.gauss(1.0, sigma),
                    base_cooldown * random.gauss(1.0, sigma),
                    base_cooldown * random.gauss(1.0, sigma),
                ]
            else:
                patterns = [
                    [base_cooldown, base_cooldown * 1.1, base_cooldown * 0.9],
                    [base_cooldown * 0.85, base_cooldown * 0.9, base_cooldown * 1.2],
                    [base_cooldown * 1.15, base_cooldown * 0.85, base_cooldown * 0.9],
                    [base_cooldown * 0.95, base_cooldown * 1.1, base_cooldown * 0.95],
                    [base_cooldown * 1.05, base_cooldown * 0.8, base_cooldown * 1.1],
                ]
                self._click_rhythm = random.choice(patterns)
            self._click_rhythm_idx = 0

            # ── Bilerek Iskalama: her minigame'de sayaç artar ──
            self._catch_streak += 1
        elif new_state == BotState.PREPARE:
            self._prepare_action_done = False
            self._inventory_checked = False
            self._inventory_open_retries = 0
        elif new_state == BotState.POST_CATCH:
            self._postcatch_action_done = False
            self._postcatch_target_delay = 0.0  # Her seferinde yeni rastgele değer
            self._last_minigame_end_time = time.time()  # Watchdog için
        elif new_state == BotState.CAST:
            self._cast_done = False
            self._cast_pressed = False
            self._cycle_start_time = time.time()
        elif new_state == BotState.WAITING:
            self._consecutive_circle_count = 0
            self._checked_bait_error = False

    def _read_ocr_region(self, region: dict) -> str:
        """Belirli bir ekran bölgesini yakalar ve OCR ile okur."""
        import mss
        import cv2
        import numpy as np
        import pytesseract
        import os

        # Windows Tesseract path check
        default_path = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
        if os.path.exists(default_path):
            pytesseract.pytesseract.tesseract_cmd = default_path
            
        project_dir = os.path.dirname(os.path.abspath(__file__))
        tessdata_dir = os.path.join(project_dir, 'tessdata')
        if os.path.exists(os.path.join(tessdata_dir, 'tur.traineddata')):
            os.environ['TESSDATA_PREFIX'] = tessdata_dir

        try:
            with mss.mss() as sct:
                screenshot = sct.grab(region)
                img = np.array(screenshot)
                
            if img.size == 0:
                return ""
                
            # Scale image x2
            img_scaled = cv2.resize(img, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
            gray = cv2.cvtColor(img_scaled, cv2.COLOR_BGRA2GRAY)
            _, thresh = cv2.threshold(gray, 120, 255, cv2.THRESH_BINARY)
            
            config_to_use = '--psm 6'
            text = pytesseract.image_to_string(thresh, lang='tur+eng', config=config_to_use)
            return text.strip()
        except Exception:
            try:
                text = pytesseract.image_to_string(thresh, lang='eng', config=config_to_use)
                return text.strip()
            except Exception:
                return ""

    def _normalize_tr(self, text: str) -> str:
        replacements = {'ü': 'u', 'ö': 'o', 'ı': 'i', 'ş': 's', 'ğ': 'g', 'ç': 'c', 'i̇': 'i'}
        text = text.lower()
        for k, v in replacements.items():
            text = text.replace(k, v)
        return text
