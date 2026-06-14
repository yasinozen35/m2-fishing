---
🧬 Metin2 Oyun Mimarisi Analizi

Oyun Motoru ve Teknolojileri

┌────────────┬──────────────────────────────────────────────┬────────────────────────────────────────────────────────┐
│   Katman   │                   Bileşen                    │                        Açıklama                        │
├────────────┼──────────────────────────────────────────────┼────────────────────────────────────────────────────────┤
│ Grafik     │ DirectX 9 (d3dx9_43.dll, d3dcompiler_47.dll) │ 2004'ten kalma DX9 motoru                              │
├────────────┼──────────────────────────────────────────────┼────────────────────────────────────────────────────────┤
│ 3D         │ SpeedTreeRT.dll, granny2.dll                 │ Ağaç/bitki ve karakter animasyonları                   │
├────────────┼──────────────────────────────────────────────┼────────────────────────────────────────────────────────┤
│ Ses        │ MSS32.DLL (Miles Sound System)               │ RAD Game Tools ses motoru                              │
├────────────┼──────────────────────────────────────────────┼────────────────────────────────────────────────────────┤
│ UI         │ libcef.dll (167MB!) + chrome_elf.dll         │ Chromium Embedded Framework — oyun içi tarayıcı/mağaza │
├────────────┼──────────────────────────────────────────────┼────────────────────────────────────────────────────────┤
│ Ağ         │ DecryptionModule.dll (3.1MB)                 │ Paket şifreleme/çözme                                  │
├────────────┼──────────────────────────────────────────────┼────────────────────────────────────────────────────────┤
│ Script     │ python27.dll + python22.dll                  │ Oyun Python 2.7 ve 2.2 ile çalışıyor!                  │
├────────────┼──────────────────────────────────────────────┼────────────────────────────────────────────────────────┤
│ Anti-Cheat │ cheat_blocker/CB.exe + 7 guard modülü        │ Çok katmanlı koruma                                    │
└────────────┴──────────────────────────────────────────────┴────────────────────────────────────────────────────────┘

🐍 Python Katmanı (En Kritik Bulgu)

Oyunun lib/ dizininde standart Python 2.7 kütüphanesi var:
lib/
├── os.pyc, re.pyc, string.pyc ... (standart lib)
├── pyexpat.pyd, pyexpat_d.pyd     (native C extension)
├── xml/ (dom, parsers)
└── encodings/ (cp949 vs)

python27.dll oyun tarafından yükleniyor. Bu demek ki Metin2'nin UI, quest sistemi, ve bazı oyun mantığı Python ile yazılmış. Bu inject için en büyük fırsat penceresi.

🛡️ Anti-Cheat Sistemi Detayları

cheat_blocker/ dizininde tam teşekküllü bir anti-cheat var:

┌────────┬────────┬──────────────────────────────────────────────────┐
│ Dosya  │ Boyut  │                  Muhtemel İşlev                  │
├────────┼────────┼──────────────────────────────────────────────────┤
│ CB.exe │ 7.4MB  │ Ana anti-cheat process'i (heartbeat)             │
├────────┼────────┼──────────────────────────────────────────────────┤
│ CB.cbm │ 10.3MB │ Code Block Module — tespit imzaları veritabanı   │
├────────┼────────┼──────────────────────────────────────────────────┤
│ CB.fcg │ 154KB  │ Function Call Guard — hook tespiti               │
├────────┼────────┼──────────────────────────────────────────────────┤
│ CB.itg │ 56KB   │ Integrity Guard — dosya/memory bütünlük kontrolü │
├────────┼────────┼──────────────────────────────────────────────────┤
│ CB.mfg │ 5KB    │ Memory Function Guard — memory tarama            │
├────────┼────────┼──────────────────────────────────────────────────┤
│ CB.dxg │ 16KB   │ DirectX Guard — DX hook tespiti                  │
├────────┼────────┼──────────────────────────────────────────────────┤
│ CB.pmg │ 17B    │ Process Memory Guard                             │
├────────┼────────┼──────────────────────────────────────────────────┤
│ CB.gr  │ 337B   │ Game Resources — oyun dosyaları hash kontrolü    │
└────────┴────────┴──────────────────────────────────────────────────┘

CB, oyun başlarken metin2client.exe ile birlikte yükleniyor ve sürekli tarama yapıyor. Her bir guard modülü ayrı bir vektörü koruyor.

📦 Pack Dosya Sistemi

pack/ dizininde .ecpk (encrypted compound pack) ve .epk dosyaları var. Toplam boyut ~2GB. Index dosyası (1874 byte) pack indeksini tutuyor. Dosyalar şifreli — modifiye etmek için şifrelemeyi kırmak gerek.

👤 Kullanıcı Verileri

UserData/ altında ilginç dizinler var:
- autohunting/ — Oyunun kendi oto-av tespit mekanizması! Her karakter için ayrı dosya
- looting/ — loot tercihleri
- keysave/ — klavye ayarları
- leftseat/ — sandalye/oturma pozisyonu

---
🔫 Inject Tabanlı Bot: Fizibilite Analizi

Olası Enjeksiyon Vektörleri

1. 🥇 Python Interpreter Injection (En Umut Verici)

Avantaj:
+ python27.dll oyun tarafından yükleniyor
+ PyRun_SimpleString() veya PyEval_Code ile kod çalıştırılabilir
+ Oyunun kendi Python state'ine erişim — balık pozisyonu, daire durumu vs.
+ Bellek taraması yoksa tespit edilmesi ZOR

Dezavantaj:
- CB.itg python27.dll bütünlüğünü kontrol ediyor olabilir
- Python GIL ile çalışmak senkronizasyon sorunu çıkarabilir
- Oyunun Python API'sini reverse-engineer etmek gerek

2. 🥈 Klasik DLL Injection

Avantaj:
+ DirectX Present() hook ile render state'e erişim
+ Send/Recv hook ile paket analizi
+ Tam kontrol

Dezavantaj:
- CB.fcg (Function Call Guard) hook'ları tespit eder
- CB.pmg (Process Memory Guard) memory modifikasyonunu yakalar
- CB.dxg (DirectX Guard) DX hook'larını tespit eder
- CB.exe sürekli heartbeat — process kill edilirse oyun kapanır

3. 🥉 External Memory Reading (ReadProcessMemory)

Avantaj:
+ Kendi process'imizden okuma — DLL injection gerekmez
+ Tespit edilmesi daha zor (handle açmak dışında iz bırakmaz)

Dezavantaj:
- Offset'leri her patch'te bulmak gerek
- CB.mfg memory taraması OpenProcess handle'ı yakalayabilir
- Sadece okuma yapılabilir, yazma/tıklama için başka yöntem gerek

4. 🏅 Packet Tabanlı (Man-in-the-Middle)

Avantaj:
+ Oyuna hiç dokunmadan network seviyesinde çalışır
+ Anti-cheat tamamen bypass edilir

Dezavantaj:
- DecryptionModule.dll şifrelemeyi kırmak gerek
- Şifreleme algoritması bilinmiyor
- Paket yapısı reverse-engineer edilmeli

