# 🎬 FourFrames — Letterboxd Taste Compatibility & Discovery

<p align="center">
  <strong>İki Letterboxd kullanıcısının sinema zevki uyumunu, ortak favorilerini, en keskin puan ayrılıklarını, ortak Watchlist'ini ve güncel RSS günlüklerini analiz eden %100 ücretsiz ve açık kaynaklı web uygulaması.</strong>
</p>

---

## ✨ Temel Özellikler (Features)

- **🎯 %100 Ücretsiz & Şifresiz (Zero-Login):** Herhangi bir üyelik, şifre veya Pro paket kısıtlaması olmadan sadece iki Letterboxd kullanıcı adı (`@user1` ⇄ `@user2`) girerek anında analiz yapar.
- **📊 Çok Boyutlu Zevk Uyumu (Taste Compatibility):**
  - Genel uyum yüzdesi (`%`), puanlama yakınlığı (*Rating Harmony*), katalog kesişim oranı ve birebir aynı puan isabet oranı.
  - **İzleme Kesişimi (Venn Breakdown):** Sadece 1. kullanıcının izledikleri, ikisinin de ortak izlediği filmler ve sadece 2. kullanıcının izledikleri.
  - **Puanlama Dengesi:** Kimin daha bonkör/sert puan verdiği ve ortalama yıldız farkı (`Δ ★`).
- **🤝 Ortak Sevilenler (Agreements):** İki kullanıcının da yüksek puan verip uzlaştığı favori filmler ve anlık arama filtresi.
- **⚡ En Keskin Puan Ayrılıkları (Disagreements / Hot Takes):** İki kullanıcının en farklı puanları verdiği filmlerin görsel karşılaştırma kartları.
- **🍿 Ortak Watchlist & 🎲 Rastgele Film Gecesi Seçici (Random Movie Picker):** İki kullanıcının da izleme listesinde bekleyen ortak filmler ve *"Bu akşam ne izleyelim?"* sorusunu tek tıkla çözen zar atma aracı.
- **🔭 Kör Noktalar & Model Önerileri (Blind Spots & Joint Picks):**
  - 1. kullanıcının favorisi olup 2. kullanıcının henüz izlemediği filmler,
  - 2. kullanıcının favorisi olup 1. kullanıcının henüz izlemediği filmler,
  - Algoritmanın her iki kullanıcıya ortak önerdiği filmler.
- **🕒 Canlı RSS Günlüğü & İncelemeler:** Doğrudan `letterboxd.com/<username>/rss/` üzerinden iki kullanıcının son izlediği filmler, beğeni (`❤️`) oranları ve yazdıkları incelemeler.
- **💬 Otomatik Buz Kırıcı Sorular (Icebreakers) & 🧾 Paylaşılabilir Uyum Fişi:** Gerçek film kesişimlerinden otomatik üretilen sohbet başlatıcı sorular ve tek tıkla kopyalanabilir özet fişi.

---

## 🚀 Hızlı Başlangıç (Quick Start)

Proje **sıfır harici paket bağımlılığı (Zero-Dependency Python 3 Standard Library)** ile çalışacak şekilde tasarlanmıştır.

```bash
# 1. Depoyu klonlayın
git clone https://github.com/mustafa-akkus/fourframes.git
cd fourframes

# 2. Sunucuyu başlatın (Python 3.10+)
py app.py
# veya: python3 app.py
```

Tarayıcınızda **`http://localhost:8000`** adresini açın.

---

## 🏗️ Mimari (Architecture)

```text
fourframes/
├── app.py              # Çok iş parçacıklı (ThreadPoolExecutor) Python HTTP & API Sunucusu
├── static/
│   ├── index.html      # Sade, sekmeli ve duyarlı (responsive) Web Arayüzü
│   ├── styles.css      # Letterboxd renk paletiyle uyumlu modern karanlık tema
│   └── app.js          # İstemci motoru (Yerel API + GitHub Pages CORS Fallback)
└── README.md
```

### API Uç Noktaları (Endpoints)
- `GET /api/compatibility?user1=<u1>&user2=<u2>&refresh=<0|1>` — İki kullanıcının derin izleme geçmişi uyumunu ve canlı RSS verilerini paralel olarak birleştirip JSON döndürür.
- `GET /api/user?username=<u1>` — Tek bir Letterboxd kullanıcısının canlı RSS günlüklerini, puan ortalamasını ve incelemelerini döndürür.

---

## 📄 Lisans
MIT License — [@mustafa-akkus](https://github.com/mustafa-akkus)
