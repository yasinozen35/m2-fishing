"""
multi_client.py — Çoklu Metin2 client yönetimi.

Aynı anda birden fazla Metin2 client'ını yönetmek için:
- Her client için ayrı MemoryReader (RPM)
- Her client için ayrı BotLogic instance'ı
- Her client kendi thread'inde çalışır
- Client'lar arası rastgele gecikme (anti-cheat pattern çeşitliliği)

Gereksinimler:
- Sandboxie ile çoklu Metin2 client'ı açılmış olmalı
- VEYA sanal monitör ile farklı ekranlarda client'lar
- VEYA pencere modunda yan yana dizilmiş client'lar

Kullanım:
    manager = MultiClientManager([
        ClientConfig(pid=1234, region=(0, 0, 1366, 768), profile="normal"),
        ClientConfig(pid=5678, region=(1920, 0, 1366, 768), profile="aggressive"),
    ])
    manager.start_all()
    manager.monitor()  # Blocking — tüm client'ları izler
"""

import random
import sys
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

# Bot import'ları — çalışma zamanında import et (circular önleme)
_BOT_LOGIC = None
_MEMORY_READER = None
_DETECTOR = None
_CLICKER = None
_CONFIG = None
_SCREEN_CAPTURE = None


def _lazy_import():
    """Circular import'ları önlemek için lazy import."""
    global _BOT_LOGIC, _MEMORY_READER, _DETECTOR, _CLICKER, _CONFIG, _SCREEN_CAPTURE
    if _BOT_LOGIC is None:
        from fishing_bot.bot_logic import BotLogic as _BOT_LOGIC
        from fishing_bot.memory_reader import MemoryReader as _MEMORY_READER
        from fishing_bot.memory_reader import MemoryDetector
        from fishing_bot.detector import Detector as _DETECTOR
        from fishing_bot.clicker import HumanClicker as _CLICKER
        from fishing_bot.config import AutoBotConfig as _CONFIG
        from fishing_bot.screen_capture import ScreenCapture as _SCREEN_CAPTURE
    return _BOT_LOGIC, _MEMORY_READER, MemoryDetector, _DETECTOR, _CLICKER, _CONFIG, _SCREEN_CAPTURE


class PlayerProfile(Enum):
    """Oyuncu profili — her client farklı davranır."""
    NOVICE = "acemi"        # Yavaş reaksiyon, çok hata
    NORMAL = "normal"       # Orta seviye
    PRO = "profesyonel"     # Hızlı ve isabetli
    TIRED = "yorgun"        # Dalgalı performans, sık mola


@dataclass
class ClientConfig:
    """Bir Metin2 client'ının yapılandırması."""

    # Process
    pid: int = 0                    # 0 = otomatik bul (ilk client)
    process_name: str = "metin2client.exe"

    # Ekran bölgesi (piksel bot için)
    region: tuple[int, int, int, int] = (0, 0, 1366, 768)

    # Oyuncu profili
    profile: PlayerProfile = PlayerProfile.NORMAL

    # Karakter adı (log için)
    char_name: str = ""

    # Bellek okuma kullan (True = RPM, False = OpenCV)
    use_memory: bool = True

    # Offset dosyası (None = varsayılan offsets.json)
    offset_file: str | None = None


@dataclass
class ClientState:
    """Bir client'ın canlı durumu."""
    config: ClientConfig
    bot: object = None          # BotLogic instance
    reader: object = None       # MemoryReader (RPM modunda)
    detector: object = None     # MemoryDetector veya Detector
    clicker: object = None      # HumanClicker
    capturer: object = None     # ScreenCapture
    thread: threading.Thread | None = None
    running: bool = False
    catches: int = 0
    casts: int = 0
    errors: int = 0
    last_error: str = ""


class MultiClientManager:
    """Çoklu Metin2 client yöneticisi."""

    def __init__(self, clients: list[ClientConfig]):
        if len(clients) < 1:
            raise ValueError("En az 1 client gerekli")
        self._clients = clients
        self._states: dict[int, ClientState] = {}
        self._stop_event = threading.Event()

    @property
    def client_count(self) -> int:
        return len(self._clients)

    def start_all(self) -> None:
        """Tüm client'ları başlat (her biri ayrı thread'de)."""
        BotLogic, MemoryReader, MemoryDetector, Detector, HumanClicker, AutoBotConfig, ScreenCapture = _lazy_import()

        # Client'ları sıralı başlat (aynı anda değil — anti-cheat için)
        for i, cfg in enumerate(self._clients):
            # Client'lar arası 2-8sn rastgele başlatma gecikmesi
            if i > 0:
                delay = random.uniform(2.0, 8.0)
                print(f"  → Client {i+1} için {delay:.1f}s bekleniyor...")
                time.sleep(delay)

            print(f"\n{'='*55}")
            print(f"  Client {i+1}/{len(self._clients)} başlatılıyor...")
            print(f"  Profil: {cfg.profile.value}, PID: {cfg.pid or 'auto'}")
            print(f"{'='*55}")

            state = ClientState(config=cfg)
            self._states[i] = state

            try:
                # ── Profil bazlı config oluştur ──
                human_cfg, auto_cfg, capture_cfg = self._build_configs(cfg)

                # ── Clicker ──
                clicker = HumanClicker(human_cfg, capture_cfg)

                # ── Detector (Memory veya OpenCV) ──
                if cfg.use_memory:
                    reader = MemoryReader(
                        cfg.process_name,
                        offset_file=cfg.offset_file
                    )
                    # OpenCV fallback detector (envanter için)
                    circle_cfg = auto_cfg  # FIXME
                    fish_cfg = auto_cfg    # FIXME
                    try:
                        fallback = Detector(circle_cfg=None, fish_cfg=None)  # FIXME
                    except Exception:
                        fallback = None
                    detector = MemoryDetector(reader, fallback_detector=fallback)
                    state.reader = reader
                else:
                    # TODO: OpenCV detector oluştur
                    detector = None

                # ── Capturer (OpenCV fallback için) ──
                capturer = None
                if not cfg.use_memory:
                    capturer = ScreenCapture(capture_cfg)

                # ── Bot ──
                from fishing_bot.bot_logic import BotLogic
                bot = BotLogic(auto_cfg, clicker, capturer)

                state.bot = bot
                state.detector = detector
                state.clicker = clicker
                state.capturer = capturer

                # ── Thread başlat ──
                thread = threading.Thread(
                    target=self._run_client,
                    args=(i, state),
                    daemon=True,
                    name=f"BotClient-{i+1}"
                )
                state.thread = thread
                state.running = True
                thread.start()

                print(f"  ✓ Client {i+1} başlatıldı: {cfg.char_name or 'isimsiz'}")

            except Exception as e:
                print(f"  ❌ Client {i+1} başlatılamadı: {e}")
                state.running = False
                state.last_error = str(e)
                state.errors += 1

    def stop_all(self) -> None:
        """Tüm client'ları durdur."""
        print("\n⏹ Tüm client'lar durduruluyor...")
        self._stop_event.set()

        for i, state in self._states.items():
            state.running = False
            if state.bot:
                try:
                    state.bot.stop()
                except Exception:
                    pass
            if state.reader:
                try:
                    state.reader.close()
                except Exception:
                    pass

        # Thread'lerin bitmesini bekle
        for i, state in self._states.items():
            if state.thread and state.thread.is_alive():
                state.thread.join(timeout=5.0)

        print("✓ Tüm client'lar durdu.")

    def monitor(self) -> None:
        """
        Tüm client'ları izle (blocking).
        Ctrl+C ile çıkılır.
        """
        print(f"\n🔍 {len(self._states)} client izleniyor... (Ctrl+C: durdur)")
        try:
            while not self._stop_event.is_set():
                self._print_status()
                time.sleep(5.0)
        except KeyboardInterrupt:
            print("\n\n⏹ Durduruluyor...")
        finally:
            self.stop_all()

    def get_stats(self) -> dict:
        """Tüm client'ların toplam istatistikleri."""
        total_catches = sum(s.catches for s in self._states.values())
        total_casts = sum(s.casts for s in self._states.values())
        total_errors = sum(s.errors for s in self._states.values())
        alive = sum(1 for s in self._states.values() if s.running)
        return {
            "clients": len(self._states),
            "alive": alive,
            "total_catches": total_catches,
            "total_casts": total_casts,
            "total_errors": total_errors,
        }

    # ── Private ──

    def _build_configs(self, cfg: ClientConfig) -> tuple:
        """Profil bazlı config üret."""
        from fishing_bot.config import HumanConfig, AutoBotConfig, CaptureConfig

        profile = cfg.profile

        # Profil bazlı parametreler
        profiles = {
            PlayerProfile.NOVICE: {
                "reaction_min": 0.25, "reaction_max": 0.45,
                "click_cooldown": 0.70, "aim_offset": 8,
                "intentional_miss_rate": 0.12,
            },
            PlayerProfile.NORMAL: {
                "reaction_min": 0.12, "reaction_max": 0.28,
                "click_cooldown": 0.35, "aim_offset": 4,
                "intentional_miss_rate": 0.04,
            },
            PlayerProfile.PRO: {
                "reaction_min": 0.06, "reaction_max": 0.15,
                "click_cooldown": 0.28, "aim_offset": 2,
                "intentional_miss_rate": 0.01,
            },
            PlayerProfile.TIRED: {
                "reaction_min": 0.20, "reaction_max": 0.50,
                "click_cooldown": 0.55, "aim_offset": 6,
                "intentional_miss_rate": 0.08,
            },
        }
        p = profiles[profile]

        human = HumanConfig(
            reaction_min=p["reaction_min"],
            reaction_max=p["reaction_max"],
            click_cooldown=p["click_cooldown"],
            aim_offset_px=p["aim_offset"],
            intentional_miss_rate=p["intentional_miss_rate"],
        )

        auto = AutoBotConfig(
            use_memory_reader=cfg.use_memory,
        )

        capture = CaptureConfig(
            left=cfg.region[0],
            top=cfg.region[1],
            width=cfg.region[2],
            height=cfg.region[3],
        )

        return human, auto, capture

    def _run_client(self, idx: int, state: ClientState) -> None:
        """Bir client'ın ana döngüsü (thread)."""
        bot_logic = state.bot
        detector = state.detector
        bot_logic.start()

        frame_count = 0
        while state.running and not self._stop_event.is_set():
            try:
                # Frame al (memory modunda None, OpenCV modunda gerçek frame)
                frame = None
                if state.capturer:
                    frame = state.capturer.grab_region()

                # Detection (memory veya OpenCV)
                result = detector.detect(frame)

                # Bot update
                clicked, status = bot_logic.update(result, frame=frame, detector=detector)
                frame_count += 1

                # İstatistik güncelle
                state.catches = bot_logic.successful_catches
                state.casts = bot_logic.total_casts

                # Ufak bir uyku (CPU'yu rahatlat)
                if not clicked:
                    time.sleep(0.001)

            except Exception as e:
                state.errors += 1
                state.last_error = str(e)
                time.sleep(0.5)

    def _print_status(self) -> None:
        """Canlı durum özeti."""
        stats = self.get_stats()
        print(f"\r⚡ {stats['alive']}/{stats['clients']} aktif | "
              f"Toplam: {stats['total_catches']} balık, "
              f"{stats['total_casts']} olta | "
              f"Hata: {stats['total_errors']}", end='')


# ── Kolay Kullanım ──

def quick_start(num_clients: int = 2,
                pids: list[int] | None = None,
                regions: list[tuple] | None = None,
                profiles: list[PlayerProfile] | None = None) -> MultiClientManager:
    """
    Hızlı başlatma.

    Args:
        num_clients: Client sayısı
        pids: PID listesi (None = otomatik)
        regions: Ekran bölgeleri (None = varsayılan)
        profiles: Profil listesi (None = hepsi NORMAL)

    Returns:
        MultiClientManager instance
    """
    default_region = (0, 0, 1366, 768)
    clients = []

    for i in range(num_clients):
        pid = pids[i] if pids and i < len(pids) else 0
        region = regions[i] if regions and i < len(regions) else default_region
        profile = profiles[i] if profiles and i < len(profiles) else PlayerProfile.NORMAL

        clients.append(ClientConfig(
            pid=pid,
            region=region,
            profile=profile,
            char_name=f"Client-{i+1}",
            use_memory=True,
        ))

    manager = MultiClientManager(clients)
    manager.start_all()
    return manager


if __name__ == "__main__":
    print("MultiClientManager Test")
    print("=" * 50)

    # Tek client test
    manager = quick_start(num_clients=1)
    manager.monitor()
