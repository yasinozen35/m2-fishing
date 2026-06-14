"""
memory_scanner.py — External memory scanner (Cheat Engine alternatifi).

Metin2 32-bit process'inin belleğini ReadProcessMemory ile dışarıdan okur.
CB.exe tarafından tespit EDİLEMEZ çünkü:
- Sadece OKUMA yapar (yazma/modifikasyon yok)
- Kernel driver kullanmaz
- Bilinen hack aracı imzası taşımaz
- Process adı python.exe (meşru)

Yetenekler:
- Process bulma ve handle açma
- Memory bölgelerini tarama (float/int değer ara)
- Iterative filtering (arttı/azaldı/değişti/değişmedi)
- Pointer chain keşfi
- Offset kaydetme/yükleme (JSON)
"""

import ctypes
from ctypes import wintypes
import json
import os
import struct
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# ── Win32 API Sabitleri ──
PROCESS_VM_READ = 0x0010
PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_VM_OPERATION = 0x0008

MEM_COMMIT = 0x1000
MEM_FREE = 0x10000
MEM_RESERVE = 0x2000

PAGE_NOACCESS = 0x01
PAGE_READONLY = 0x02
PAGE_READWRITE = 0x04
PAGE_WRITECOPY = 0x08
PAGE_EXECUTE = 0x10
PAGE_EXECUTE_READ = 0x20
PAGE_EXECUTE_READWRITE = 0x40
PAGE_GUARD = 0x100

# kernel32 fonksiyonları
_kernel32 = ctypes.windll.kernel32
_kernel32.OpenProcess.restype = wintypes.HANDLE
_kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
_kernel32.CloseHandle.restype = wintypes.BOOL
_kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
_kernel32.ReadProcessMemory.restype = wintypes.BOOL
_kernel32.ReadProcessMemory.argtypes = [
    wintypes.HANDLE, wintypes.LPCVOID, wintypes.LPVOID, ctypes.c_size_t,
    ctypes.POINTER(ctypes.c_size_t)
]
_kernel32.VirtualQueryEx.restype = ctypes.c_size_t
# argtypes tanımlanmıyor — 32-bit process için 28 byte'lık
# MEMORY_BASIC_INFORMATION yapısı farklı olabilir.
# Bunun yerine direkt byref() ile yapı pointer'ı geçiyoruz.

# psapi — module bilgisi için
_psapi = ctypes.windll.psapi
_psapi.EnumProcessModules.restype = wintypes.BOOL

# kernel32 — process listesi için
_kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
_kernel32.Process32FirstW.restype = wintypes.BOOL
_kernel32.Process32NextW.restype = wintypes.BOOL
_kernel32.Module32FirstW.restype = wintypes.BOOL
_kernel32.Module32NextW.restype = wintypes.BOOL


# ── Win32 Yapıları ──
class MEMORY_BASIC_INFORMATION_32(ctypes.Structure):
    """64-bit Python'dan 32-bit process için MEMORY_BASIC_INFORMATION.

    Windows, 64-bit çağrıcıdan VirtualQueryEx yapıldığında
    64-bit native yapı (48 byte) bekler. Adresler alt 32-bit'te
    sıfır-genişletilmiş olarak döner.
    """
    _fields_ = [
        ("BaseAddress", ctypes.c_ulonglong),       # PVOID = 8 bytes (64-bit native)
        ("AllocationBase", ctypes.c_ulonglong),     # PVOID = 8 bytes
        ("AllocationProtect", wintypes.DWORD),      # 4 bytes
        ("_align1", wintypes.DWORD),                # padding (4 bytes)
        ("RegionSize", ctypes.c_ulonglong),         # SIZE_T = 8 bytes
        ("State", wintypes.DWORD),                  # 4 bytes
        ("Protect", wintypes.DWORD),                # 4 bytes
        ("Type", wintypes.DWORD),                   # 4 bytes
        ("_align2", wintypes.DWORD),                # padding (4 bytes)
    ]


class PROCESSENTRY32W(ctypes.Structure):
    """Process girişi (native — işletim sistemini sorgular)."""
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", wintypes.WPARAM),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", wintypes.LONG),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", ctypes.c_wchar * 260),
    ]


class MODULEENTRY32W(ctypes.Structure):
    """Module girişi (native — işletim sistemini sorgular)."""
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("th32ModuleID", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("GlblcntUsage", wintypes.DWORD),
        ("ProccntUsage", wintypes.DWORD),
        ("modBaseAddr", ctypes.c_ulonglong),  # BYTE* = pointer boyutlu (8 byte on 64-bit)
        ("modBaseSize", wintypes.DWORD),
        ("hModule", wintypes.HANDLE),
        ("szModule", ctypes.c_wchar * 256),
        ("szExePath", ctypes.c_wchar * 260),
    ]


# ── Data Classes ──
@dataclass
class MemoryRegion:
    """Taranabilir bir bellek bölgesi."""
    base: int       # Başlangıç adresi (DWORD)
    size: int       # Bölge boyutu
    protect: int    # Koruma flag'i

    def __repr__(self):
        return (f"Region(0x{self.base:08X}, "
                f"size={self.size // 1024}KB, "
                f"protect=0x{self.protect:02X})")


@dataclass
class ScanResult:
    """Tek bir tarama sonucu (bir adreste bulunan değer)."""
    address: int
    value: float | int
    value_type: str  # "float" | "int32"

    def __repr__(self):
        if self.value_type == "float":
            return f"0x{self.address:08X} → {self.value:.4f}"
        return f"0x{self.address:08X} → {self.value}"


# ── Scanner Sınıfı ──
class MemoryScanner:
    """External process memory scanner — Cheat Engine benzeri tarama."""

    def __init__(self, process_name: str = "metin2client.exe"):
        self._process_name = process_name
        self._pid: int = 0
        self._handle: int = 0
        self._base_addr: int = 0
        self._module_size: int = 0

        # Son tarama sonuçları (iterative filtering için)
        self._last_results: dict[int, ScanResult] = {}
        self._regions: list[MemoryRegion] = []

        # Keşfedilen offset'ler
        self.discovered_offsets: dict[str, int] = {}

    # ── Process Yönetimi ──

    def find_and_attach(self) -> bool:
        """metin2client.exe process'ini bul ve handle aç."""
        self._pid = self._find_pid(self._process_name)
        if self._pid == 0:
            print(f"HATA: '{self._process_name}' process'i bulunamadı!")
            return False

        self._handle = _kernel32.OpenProcess(
            PROCESS_VM_READ | PROCESS_VM_OPERATION | PROCESS_QUERY_INFORMATION,
            False, self._pid
        )
        if not self._handle:
            print(f"HATA: Process handle açılamadı! PID={self._pid}")
            return False

        self._base_addr = self._get_module_base()
        print(f"✓ {self._process_name} bulundu: PID={self._pid}, "
              f"Base=0x{self._base_addr:08X}")

        return True

    def detach(self) -> None:
        """Process handle'ını kapat."""
        if self._handle:
            _kernel32.CloseHandle(self._handle)
            self._handle = 0

    @property
    def pid(self) -> int:
        return self._pid

    @property
    def base(self) -> int:
        return self._base_addr

    # ── Memory Bölge Taraması ──

    def enumerate_regions(self, readable_only: bool = True) -> list[MemoryRegion]:
        """Process'in tüm commit edilmiş bellek bölgelerini listele."""
        regions = []
        mbi = MEMORY_BASIC_INFORMATION_32()

        if not self._handle:
            print("HATA: Önce find_and_attach() çağırın!")
            return regions

        address = 0x00010000  # Minimum kullanıcı adres alanı (32-bit)
        max_address = 0x7FFEFFFF  # Maksimum kullanıcı adres alanı (32-bit)

        while address < max_address:
            try:
                result = _kernel32.VirtualQueryEx(
                    wintypes.HANDLE(self._handle),
                    wintypes.LPCVOID(address),
                    ctypes.byref(mbi),
                    ctypes.sizeof(mbi)
                )
                if result == 0:
                    break

                if mbi.State == MEM_COMMIT:
                    if readable_only:
                        # Sadece okunabilir bölgeler
                        readable_prots = {
                            PAGE_READONLY, PAGE_READWRITE, PAGE_WRITECOPY,
                            PAGE_EXECUTE_READ, PAGE_EXECUTE_READWRITE,
                        }
                        if mbi.Protect in readable_prots and \
                           mbi.Protect != PAGE_GUARD and \
                           not (mbi.Protect & PAGE_GUARD):
                            regions.append(MemoryRegion(
                                base=mbi.BaseAddress,
                                size=mbi.RegionSize,
                                protect=mbi.Protect,
                            ))
                    else:
                        regions.append(MemoryRegion(
                            base=mbi.BaseAddress,
                            size=mbi.RegionSize,
                            protect=mbi.Protect,
                        ))

                address = mbi.BaseAddress + mbi.RegionSize

            except Exception as e:
                print(f"VirtualQueryEx hatası @ 0x{address:08X}: {e}")
                break

        self._regions = regions
        return regions

    # ── Değer Okuma ──

    def read_bytes(self, address: int, size: int) -> bytes | None:
        """Belirtilen adresten N byte oku."""
        buf = ctypes.create_string_buffer(size)
        bytes_read = ctypes.c_size_t(0)
        success = _kernel32.ReadProcessMemory(
            wintypes.HANDLE(self._handle),
            wintypes.LPCVOID(address),
            buf, size,
            ctypes.byref(bytes_read)
        )
        if success and bytes_read.value == size:
            return buf.raw
        return None

    def read_float(self, address: int) -> float | None:
        """32-bit float oku."""
        data = self.read_bytes(address, 4)
        if data:
            return struct.unpack('<f', data)[0]
        return None

    def read_int32(self, address: int) -> int | None:
        """32-bit signed integer oku."""
        data = self.read_bytes(address, 4)
        if data:
            return struct.unpack('<i', data)[0]
        return None

    def read_ptr(self, address: int) -> int | None:
        """32-bit pointer (unsigned) oku."""
        data = self.read_bytes(address, 4)
        if data:
            return struct.unpack('<I', data)[0]
        return None

    def read_ptr_chain(self, base_address: int, offsets: list[int]) -> int | None:
        """Pointer chain takip et: [base + o0] + o1 + o2 ... → final address."""
        addr = base_address
        for offset in offsets:
            ptr = self.read_ptr(addr)
            if ptr is None or ptr == 0:
                return None
            addr = ptr + offset
        return addr

    # ── Memory Tarama (Cheat Engine benzeri) ──

    def scan_float(self, value: float, tolerance: float = 0.5) -> list[ScanResult]:
        """Tüm okunabilir bölgelerde float değer tara."""
        results = []
        total_size = sum(r.size for r in self._regions)
        scanned = 0

        for region in self._regions:
            # Büyük bölgeleri chunk'lar halinde oku (bellek verimli)
            chunk_size = 65536  # 64KB chunks
            offset = 0
            while offset < region.size:
                remain = region.size - offset
                read_size = min(chunk_size, remain)
                addr = region.base + offset

                data = self.read_bytes(addr, read_size)
                if data:
                    # Her 4 byte'ı float olarak kontrol et
                    for i in range(0, len(data) - 3, 4):
                        try:
                            f = struct.unpack_from('<f', data, i)[0]
                            # NaN ve Inf'i atla
                            if abs(f - value) <= tolerance and f == f and f != float('inf') and f != float('-inf'):
                                results.append(ScanResult(
                                    address=addr + i,
                                    value=f,
                                    value_type="float"
                                ))
                        except Exception:
                            pass

                scanned += read_size
                offset += read_size

            # İlerleme raporu (büyük taramalarda)
            progress = (scanned / total_size) * 100 if total_size > 0 else 0
            if progress % 20 < 0.1:
                print(f"  Tarama: %{progress:.0f} ({scanned // 1024}KB/{total_size // 1024}KB)...")

        return results

    def scan_int32(self, value: int) -> list[ScanResult]:
        """Tüm okunabilir bölgelerde int32 değer tara."""
        results = []
        total_size = sum(r.size for r in self._regions)
        scanned = 0

        for region in self._regions:
            chunk_size = 65536
            offset = 0
            while offset < region.size:
                remain = region.size - offset
                read_size = min(chunk_size, remain)
                addr = region.base + offset

                data = self.read_bytes(addr, read_size)
                if data:
                    for i in range(0, len(data) - 3, 4):
                        try:
                            ival = struct.unpack_from('<i', data, i)[0]
                            if ival == value:
                                results.append(ScanResult(
                                    address=addr + i,
                                    value=ival,
                                    value_type="int32"
                                ))
                        except Exception:
                            pass

                scanned += read_size
                offset += read_size

        return results

    # ── Iterative Filtering (Cheat Engine "Next Scan") ──

    def set_results(self, results: list[ScanResult]) -> None:
        """Sonuçları kaydet (ilk tarama veya filtre sonrası)."""
        self._last_results = {r.address: r for r in results}

    def filter_increased(self, value_type: str = "float") -> list[ScanResult]:
        """Sadece değeri ARTAN adresleri tut."""
        filtered = []
        for addr, old_result in self._last_results.items():
            if value_type == "float":
                new_val = self.read_float(addr)
                if new_val is not None and new_val > old_result.value:
                    filtered.append(ScanResult(addr, new_val, value_type))
            elif value_type == "int32":
                new_val = self.read_int32(addr)
                if new_val is not None and new_val > old_result.value:
                    filtered.append(ScanResult(addr, new_val, value_type))
        self._last_results = {r.address: r for r in filtered}
        return filtered

    def filter_decreased(self, value_type: str = "float") -> list[ScanResult]:
        """Sadece değeri AZALAN adresleri tut."""
        filtered = []
        for addr, old_result in self._last_results.items():
            if value_type == "float":
                new_val = self.read_float(addr)
                if new_val is not None and new_val < old_result.value:
                    filtered.append(ScanResult(addr, new_val, value_type))
            elif value_type == "int32":
                new_val = self.read_int32(addr)
                if new_val is not None and new_val < old_result.value:
                    filtered.append(ScanResult(addr, new_val, value_type))
        self._last_results = {r.address: r for r in filtered}
        return filtered

    def filter_changed(self, value_type: str = "float",
                       tolerance: float = 0.01) -> list[ScanResult]:
        """Değeri DEĞİŞEN (eski değerden farklı) adresleri tut."""
        filtered = []
        for addr, old_result in self._last_results.items():
            if value_type == "float":
                new_val = self.read_float(addr)
                if new_val is not None and abs(new_val - old_result.value) > tolerance:
                    filtered.append(ScanResult(addr, new_val, value_type))
            elif value_type == "int32":
                new_val = self.read_int32(addr)
                if new_val is not None and new_val != old_result.value:
                    filtered.append(ScanResult(addr, new_val, value_type))
        self._last_results = {r.address: r for r in filtered}
        return filtered

    def filter_unchanged(self, value_type: str = "float",
                         tolerance: float = 0.01) -> list[ScanResult]:
        """Değeri DEĞİŞMEYEN adresleri tut."""
        filtered = []
        for addr, old_result in self._last_results.items():
            if value_type == "float":
                new_val = self.read_float(addr)
                if new_val is not None and abs(new_val - old_result.value) < tolerance:
                    filtered.append(ScanResult(addr, new_val, value_type))
            elif value_type == "int32":
                new_val = self.read_int32(addr)
                if new_val is not None and new_val == old_result.value:
                    filtered.append(ScanResult(addr, new_val, value_type))
        self._last_results = {r.address: r for r in filtered}
        return filtered

    def filter_by_value(self, new_value: float | int,
                        value_type: str = "float",
                        tolerance: float = 0.5) -> list[ScanResult]:
        """Yeni bir değerle filtrele (guided scanning)."""
        filtered = []
        for addr, old_result in self._last_results.items():
            if value_type == "float":
                new_val = self.read_float(addr)
                if new_val is not None and abs(new_val - new_value) <= tolerance:
                    filtered.append(ScanResult(addr, new_val, value_type))
            elif value_type == "int32":
                new_val = self.read_int32(addr)
                if new_val is not None and new_val == new_value:
                    filtered.append(ScanResult(addr, new_val, value_type))
        self._last_results = {r.address: r for r in filtered}
        return filtered

    def filter_was_value(self, was_value: float | int,
                         now_is: float | int,
                         value_type: str = "float",
                         tolerance: float = 0.5) -> list[ScanResult]:
        """
        Önceki değeri X olan ve şimdi Y olan adresleri bul.
        "Unknown initial value" taramaları için kullanılır.
        """
        filtered = []
        for addr in list(self._last_results.keys()):
            if value_type == "float":
                prev = self._last_results[addr].value
                new_val = self.read_float(addr)
                if (new_val is not None and
                        abs(prev - was_value) <= tolerance and
                        abs(new_val - now_is) <= tolerance):
                    filtered.append(ScanResult(addr, new_val, value_type))
            elif value_type == "int32":
                prev = self._last_results[addr].value
                new_val = self.read_int32(addr)
                if new_val is not None and prev == was_value and new_val == now_is:
                    filtered.append(ScanResult(addr, new_val, value_type))
        self._last_results = {r.address: r for r in filtered}
        return filtered

    # ── Pointer Chain Keşfi ──

    def find_pointers_to(self, target_addr: int,
                         within_range: int = 1024) -> list[int]:
        """
        Verilen adresi işaret eden tüm pointer'ları bul.
        Pointer [base + offset] formatında döner.
        """
        ptr_value = target_addr
        results = []

        total_size = sum(r.size for r in self._regions)
        scanned = 0

        for region in self._regions:
            chunk_size = 65536
            offset = 0
            while offset < region.size:
                remain = region.size - offset
                read_size = min(chunk_size, remain)
                addr = region.base + offset

                data = self.read_bytes(addr, read_size)
                if data:
                    for i in range(0, len(data) - 3, 4):
                        try:
                            ptr = struct.unpack_from('<I', data, i)[0]
                            diff = abs(int(ptr) - int(target_addr))
                            if diff <= within_range:
                                results.append(addr + i)
                        except Exception:
                            pass

                scanned += read_size
                offset += read_size

        return results

    def resolve_pointer_chain(self, static_base: int,
                              max_depth: int = 5,
                              max_offset: int = 0x2000) -> dict[str, list[int]]:
        """
        Statik adresten hedef adrese giden chain'i bul.
        Bu işlem AĞIRDIR — sadece birkaç aday adres için çalıştırın.

        Dönüş: {"address_hex": [off1, off2, off3], ...}
        Her chain: [base + off1] → [* + off2] → [* + off3] = target
        """
        chains = {}

        for target_str, target_addr in self.discovered_offsets.items():
            if target_addr == 0:
                continue

            # Adım 1: target'i işaret eden pointer'ları bul
            ptrs = self.find_pointers_to(target_addr, within_range=4)
            print(f"  {target_str}: {len(ptrs)} pointer bulundu → 0x{target_addr:08X}")

            if not ptrs:
                continue

            # Adım 2: Her pointer için chain'i geriye doğru takip et
            for ptr_addr in ptrs[:20]:  # İlk 20 yeterli
                chain = []
                current = ptr_addr
                valid = True

                for depth in range(max_depth):
                    # current'ın statik base'den offset'ini hesapla
                    if self._base_addr <= current <= self._base_addr + self._module_size:
                        off = current - self._base_addr
                        chain.append(off)
                        break

                    # current'ı işaret eden pointer ara
                    ptrs_up = self.find_pointers_to(current, within_range=4)
                    if ptrs_up:
                        chain.append(current - ptrs_up[0] if ptrs_up else 0)
                        current = ptrs_up[0]
                    else:
                        valid = False
                        break

                if valid and chain:
                    chain.reverse()
                    key = f"{target_str} (via 0x{ptr_addr:08X})"
                    chains[key] = chain
                    if len(chains) >= 10:
                        break

            if len(chains) >= 10:
                break

        return chains

    # ── Offset Kaydetme / Yükleme ──

    OFFSETS_DIR = Path(__file__).parent / "offsets"

    def save_offsets(self, filename: str = "offsets.json") -> str:
        """Keşfedilen offset'leri JSON'a kaydet."""
        self.OFFSETS_DIR.mkdir(exist_ok=True)
        path = self.OFFSETS_DIR / filename

        data = {
            "_meta": {
                "process": self._process_name,
                "pid": self._pid,
                "base_address": f"0x{self._base_addr:08X}",
                "discovered_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            },
            "offsets": {
                k: f"0x{v:08X}" for k, v in self.discovered_offsets.items()
            }
        }

        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"✓ Offset'ler kaydedildi: {path}")
        return str(path)

    def load_offsets(self, filename: str = "offsets.json") -> bool:
        """Kaydedilmiş offset'leri yükle."""
        path = self.OFFSETS_DIR / filename
        if not path.exists():
            print(f"HATA: Offset dosyası bulunamadı: {path}")
            return False

        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        for k, v in data["offsets"].items():
            self.discovered_offsets[k] = int(v, 16)

        print(f"✓ Offset'ler yüklendi: {path} ({len(self.discovered_offsets)} adet)")
        return True

    # ── Yardımcı Metodlar ──

    def _find_pid(self, process_name: str) -> int:
        """Process adından PID bul."""
        snapshot = _kernel32.CreateToolhelp32Snapshot(0x00000002, 0)  # TH32CS_SNAPPROCESS
        if snapshot == wintypes.HANDLE(-1).value:
            return 0

        entry = PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)

        if _kernel32.Process32FirstW(snapshot, ctypes.byref(entry)):
            while True:
                if entry.szExeFile.lower() == process_name.lower():
                    _kernel32.CloseHandle(snapshot)
                    return entry.th32ProcessID
                if not _kernel32.Process32NextW(snapshot, ctypes.byref(entry)):
                    break

        _kernel32.CloseHandle(snapshot)
        return 0

    def _get_module_base(self) -> int:
        """metin2client.exe'nin yüklendiği base adresi bul."""
        snapshot = _kernel32.CreateToolhelp32Snapshot(0x00000008, self._pid)  # TH32CS_SNAPMODULE
        if snapshot == wintypes.HANDLE(-1).value:
            return 0

        entry = MODULEENTRY32W()
        entry.dwSize = ctypes.sizeof(MODULEENTRY32W)

        base = 0
        if _kernel32.Module32FirstW(snapshot, ctypes.byref(entry)):
            while True:
                if entry.szModule.lower() == self._process_name.lower():
                    base = entry.modBaseAddr
                    self._module_size = entry.modBaseSize
                    break
                if not _kernel32.Module32NextW(snapshot, ctypes.byref(entry)):
                    break

        _kernel32.CloseHandle(snapshot)
        return base

    def print_regions_summary(self) -> None:
        """Bellek bölgelerinin özetini yazdır."""
        if not self._regions:
            self.enumerate_regions()

        total = sum(r.size for r in self._regions)
        print(f"\n{'─'*60}")
        print(f"Memory Bölgeleri ({len(self._regions)} adet, toplam {total // 1048576}MB):")
        print(f"{'─'*60}")

        by_protect = defaultdict(lambda: {"count": 0, "size": 0})
        for r in self._regions:
            prot_names = {
                0x02: "R", 0x04: "RW", 0x08: "WC",
                0x20: "RX", 0x40: "RWX",
            }
            name = prot_names.get(r.protect & 0xFF, f"0x{r.protect:02X}")
            by_protect[name]["count"] += 1
            by_protect[name]["size"] += r.size

        for prot, info in sorted(by_protect.items()):
            print(f"  {prot:>4}: {info['count']:4d} bölge, {info['size'] // 1024:6d} KB")

        print(f"{'─'*60}")

    def print_results(self, results: list[ScanResult], max_show: int = 50) -> None:
        """Tarama sonuçlarını yazdır."""
        print(f"\nSonuç: {len(results)} adres bulundu")
        if results:
            print(f"{'─'*50}")
            # İlk N sonucu göster
            for r in results[:max_show]:
                print(f"  0x{r.address:08X} → {r.value}")
            if len(results) > max_show:
                print(f"  ... ve {len(results) - max_show} adres daha")
            print(f"{'─'*50}")


# ── Kolay Kullanım ──

def create_scanner() -> MemoryScanner | None:
    """Factory: metin2client.exe'ye bağlanan scanner oluştur."""
    scanner = MemoryScanner("metin2client.exe")
    if not scanner.find_and_attach():
        return None
    scanner.enumerate_regions()
    return scanner


if __name__ == "__main__":
    print("Memory Scanner — Test")
    scanner = create_scanner()
    if scanner:
        scanner.print_regions_summary()
        scanner.detach()
