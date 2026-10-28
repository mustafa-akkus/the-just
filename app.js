/**
 * The Just — Multi-Screen Social Film Taste & Compatibility Platform
 * Separates authentication, personal profile & photo upload, member discovery,
 * detailed taste compatibility, messaging, and head-to-head comparison into distinct views.
 */

const TOKEN_KEY = "thejust:token";
const USER_KEY = "thejust:user";
const LOCAL_USERS_KEY = "thejust:local_users";
const LOCAL_MSGS_KEY = "thejust:local_msgs";

let state = {
  currentScreen: "welcome", // 'welcome' | 'login' | 'register' | 'discover' | 'member-detail' | 'chat' | 'profile' | 'compare'
  token: localStorage.getItem(TOKEN_KEY) || "",
  currentUser: null,
  tempPhotoData: "",
  members: [],
  discoverFilter: "All", // 'All' | 'Friendship' | 'Dating'
  selectedMember: null,
  selectedCompatibility: null,
  detailTab: "overview", // 'overview' | 'agreements' | 'disagreements' | 'watchlist'
  chatMessages: [],
  compareData: null,
  compareTab: "overview",
  flashMessage: null,
};

function escapeHtml(str) {
  if (str === null || str === undefined) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function makeAvatarSvg(name, bg = "#1c2632", fg = "#00e054") {
  const initials = (name || "U")
    .split(" ")
    .map((w) => w[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="160" height="160" viewBox="0 0 160 160">
    <rect width="160" height="160" rx="80" fill="${bg}"/>
    <text x="50%" y="53%" dominant-baseline="middle" text-anchor="middle" fill="${fg}" font-family="Inter, sans-serif" font-weight="700" font-size="54">${initials}</text>
  </svg>`;
  return `data:image/svg+xml;utf8,${encodeURIComponent(svg)}`;
}

const DEFAULT_SEED_MEMBERS = [
  {
    id: 1,
    name: "Defne Yılmaz",
    age: 26,
    city: "İstanbul • Kadıköy",
    bio: "Kurgu asistanı. Wong Kar-wai neonları, 90'lar bağımsız sineması ve festival seçkileri üzerine konuşmayı severim.",
    intent: "Both",
    favoriteGenres: "Arthouse, Drama, Thriller",
    letterboxdUsername: "karsten",
    photoData: makeAvatarSvg("Defne Yılmaz", "#1e293b", "#00e054"),
    lbSummary: {
      watches: 2410,
      ratings: 2190,
      avgRating: 3.42,
      topFilms: ["Mulholland Drive", "Aftersun", "Close-Up", "Parasite"],
    },
    compatibility: {
      score: 88,
      bothSeen: 112,
      sharedHighlights: ["Mulholland Drive", "Parasite", "After Hours"],
    },
  },
  {
    id: 2,
    name: "Kaan Demir",
    age: 28,
    city: "İstanbul • Beyoğlu",
    bio: "Sinema yazarı ve yazılım geliştirici. Atlas Sineması çıkışında film tartışacak yeni insanlar arıyorum.",
    intent: "Friendship",
    favoriteGenres: "Sci-Fi, Neo-Noir, Mystery",
    letterboxdUsername: "davidehrlich",
    photoData: makeAvatarSvg("Kaan Demir", "#172554", "#40bcf4"),
    lbSummary: {
      watches: 3480,
      ratings: 3373,
      avgRating: 3.04,
      topFilms: ["The Red Shoes", "Children of Men", "Yi Yi", "In the Mood for Love"],
    },
    compatibility: {
      score: 79,
      bothSeen: 183,
      sharedHighlights: ["The Wolf of Wall Street", "No Country for Old Men", "Uncut Gems"],
    },
  },
  {
    id: 3,
    name: "Zeynep Kaya",
    age: 25,
    city: "Ankara • Çankaya",
    bio: "Mimarlık yüksek lisans öğrencisi. A24 filmleri, MUBI klasikleri ve psikolojik gerilim tutkunu.",
    intent: "Dating",
    favoriteGenres: "Indie, Romance, Psychological",
    letterboxdUsername: "dtquandt",
    photoData: makeAvatarSvg("Zeynep Kaya", "#3b0764", "#ff8000"),
    lbSummary: {
      watches: 337,
      ratings: 297,
      avgRating: 3.88,
      topFilms: ["Mulholland Drive", "After Hours", "Poor Things", "The Holdovers"],
    },
    compatibility: {
      score: 91,
      bothSeen: 94,
      sharedHighlights: ["Poor Things", "The Holdovers", "After Hours"],
    },
  },
  {
    id: 4,
    name: "Emre Aydın",
    age: 29,
    city: "İzmir • Alsancak",
    bio: "Görüntü yönetmeni. Filmleri senaryodan önce ışık ve renk paletine göre değerlendiririm.",
    intent: "Both",
    favoriteGenres: "Crime, Classic, World Cinema",
    letterboxdUsername: "schaffrillas",
    photoData: makeAvatarSvg("Emre Aydın", "#14532d", "#00e054"),
    lbSummary: {
      watches: 1120,
      ratings: 1050,
      avgRating: 3.56,
      topFilms: ["Whiplash", "La Haine", "The Tale of the Princess Kaguya", "Parasite"],
    },
    compatibility: {
      score: 74,
      bothSeen: 68,
      sharedHighlights: ["Whiplash", "La Haine", "Parasite"],
    },
  },
];

// ============================================================================
// PHOTO UPLOAD COMPRESSION HELPER (Reads file & resizes to clean Data URL)
// ============================================================================
function handlePhotoFileSelect(inputEl, previewImgId) {
  const file = inputEl.files && inputEl.files[0];
  if (!file) return;

  const reader = new FileReader();
  reader.onload = function (ev) {
    const img = new Image();
    img.onload = function () {
      const canvas = document.createElement("canvas");
      const size = 240;
      canvas.width = size;
      canvas.height = size;
      const ctx = canvas.getContext("2d");

      const minDim = Math.min(img.width, img.height);
      const sx = (img.width - minDim) / 2;
      const sy = (img.height - minDim) / 2;

      ctx.drawImage(img, sx, sy, minDim, minDim, 0, 0, size, size);
      const compressedDataUrl = canvas.toDataURL("image/jpeg", 0.85);
      state.tempPhotoData = compressedDataUrl;

      const previewEl = document.getElementById(previewImgId);
      if (previewEl) {
        previewEl.src = compressedDataUrl;
      }
    };
    img.src = ev.target.result;
  };
  reader.readAsDataURL(file);
}

// ============================================================================
// API HELPER WITH AUTOMATIC STATIC FALLBACK
// ============================================================================
async function apiRequest(path, options = {}) {
  const headers = {
    "Content-Type": "application/json",
    ...(options.headers || {}),
  };
  if (state.token) {
    headers["Authorization"] = `Bearer ${state.token}`;
  }
  const resp = await fetch(path, {
    ...options,
    headers,
  });
  const ct = resp.headers.get("content-type") || "";
  if (!ct.includes("application/json")) {
    throw new Error("STATIC_MODE");
  }
  const json = await resp.json();
  if (!resp.ok || !json.ok) {
    throw new Error(json.error || "İşlem başarısız oldu.");
  }
  return json;
}

// ============================================================================
// NAVIGATION & HEADER RENDERING
// ============================================================================
function navigateTo(screen, params = {}) {
  state.currentScreen = screen;
  state.flashMessage = params.flash || null;

  if (screen === "home") {
    state.currentScreen = state.currentUser ? "discover" : "welcome";
  }

  renderHeader();
  renderCurrentScreen(params);
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function renderHeader() {
  const nav = document.getElementById("headerNav");
  if (!nav) return;

  if (!state.currentUser) {
    nav.innerHTML = `
      <button type="button" class="nav-btn ${state.currentScreen === "welcome" ? "active" : ""}" onclick="navigateTo('welcome')">
        Ana Sayfa
      </button>
      <button type="button" class="nav-btn ${state.currentScreen === "compare" ? "active" : ""}" onclick="navigateTo('compare')">
        Hızlı Uyum Testi
      </button>
      <button type="button" class="nav-btn ${state.currentScreen === "login" ? "active" : ""}" onclick="navigateTo('login')">
        Giriş Yap
      </button>
      <button type="button" class="btn-primary btn-sm" onclick="navigateTo('register')">
        Kayıt Ol
      </button>
    `;
  } else {
    const u = state.currentUser;
    const avatar = u.photoData || makeAvatarSvg(u.name);
    nav.innerHTML = `
      <button type="button" class="nav-btn ${state.currentScreen === "discover" ? "active" : ""}" onclick="navigateTo('discover')">
        İnsanlarla Tanış
      </button>
      <button type="button" class="nav-btn ${state.currentScreen === "compare" ? "active" : ""}" onclick="navigateTo('compare')">
        İkili Uyum Aracı
      </button>
      <button type="button" class="nav-btn ${state.currentScreen === "profile" ? "active" : ""}" onclick="navigateTo('profile')">
        Profilim & Fotoğrafım
      </button>
      <div class="nav-user-pill" onclick="navigateTo('profile')" title="Profili Düzenle">
        <img src="${escapeHtml(avatar)}" alt="${escapeHtml(u.name)}" />
        <span>${escapeHtml(u.name.split(" ")[0])}</span>
      </div>
      <button type="button" class="nav-btn" onclick="handleLogout()">
        Çıkış
      </button>
    `;
  }
}

// ============================================================================
// SCREEN ROUTER
// ============================================================================
function renderCurrentScreen(params = {}) {
  const root = document.getElementById("screenRoot");
  if (!root) return;

  switch (state.currentScreen) {
    case "welcome":
      renderWelcomeScreen(root);
      break;
    case "login":
      renderLoginScreen(root);
      break;
    case "register":
      renderRegisterScreen(root);
      break;
    case "discover":
      renderDiscoverScreen(root);
      break;
    case "member-detail":
      renderMemberDetailScreen(root);
      break;
    case "chat":
      renderChatScreen(root);
      break;
    case "profile":
      renderProfileScreen(root);
      break;
    case "compare":
      renderCompareScreen(root);
      break;
    default:
      renderWelcomeScreen(root);
  }
}

// ============================================================================
// SCREEN 1: CLEAN WELCOME SCREEN
// ============================================================================
function renderWelcomeScreen(root) {
  root.innerHTML = `
    <section class="screen-view welcome-hero">
      <span class="welcome-eyebrow">The Just • Sinema Odaklı Tanışma Platformu</span>
      <h1 class="welcome-title">Aynı Filmleri Seven İnsanlarla Tanışın</h1>
      <p class="welcome-desc">
        Profilinizi oluşturun, fotoğrafınızı yükleyin ve Letterboxd kullanıcı adınızı bağlayın.
        Sizinle aynı filmlere yüksek puan veren, aynı yönetmenleri seven insanlarla eşleşin ve sohbet edin.
      </p>

      <div class="welcome-actions">
        <button type="button" class="btn-primary" onclick="navigateTo('register')">
          Hesap Oluştur ve Başla
        </button>
        <button type="button" class="btn-secondary" onclick="navigateTo('login')">
          Giriş Yap
        </button>
        <button type="button" class="btn-secondary" onclick="navigateTo('compare')">
          Üyeliksiz Hızlı Uyum Testi
        </button>
      </div>

      <div class="welcome-steps">
        <div class="step-card">
          <span class="step-num">1. Adım</span>
          <h3>Profilini Oluştur</h3>
          <p>Kişisel bilgilerini gir, profil fotoğrafını yükle ve Letterboxd kullanıcı adını ekle.</p>
        </div>
        <div class="step-card">
          <span class="step-num">2. Adım</span>
          <h3>Zevk Uyumunu Gör</h3>
          <p>Ortak izlediğiniz filmler, verdiğiniz yıldızlar ve ortak Watchlist kesişimleriniz otomatik hesaplansın.</p>
        </div>
        <div class="step-card">
          <span class="step-num">3. Adım</span>
          <h3>Tanış ve Sohbet Et</h3>
          <p>Sinema zevki sana en yakın kişilerin profillerini incele ve ortak filmleriniz üzerinden sohbete başla.</p>
        </div>
      </div>
    </section>
  `;
}

// ============================================================================
// SCREEN 2: LOGIN SCREEN
// ============================================================================
function renderLoginScreen(root) {
  root.innerHTML = `
    <section class="screen-view">
      <div class="auth-card">
        <div class="auth-header">
          <h2>The Just'a Giriş Yap</h2>
          <p>Film zevki eşleşmelerinizi görmek için hesabınıza giriş yapın.</p>
        </div>

        <div id="loginAlert"></div>

        <form onsubmit="submitLogin(event)">
          <div class="form-field">
            <label for="loginEmail">E-posta Adresi</label>
            <input id="loginEmail" type="email" placeholder="ornek@eposta.com" required />
          </div>

          <div class="form-field">
            <label for="loginPass">Şifre</label>
            <input id="loginPass" type="password" placeholder="••••••••" required />
          </div>

          <button type="submit" class="btn-primary" style="width: 100%; margin-top: 0.5rem;">
            Giriş Yap
          </button>
        </form>

        <div style="margin-top: 1.25rem; padding-top: 1.15rem; border-top: 1px solid var(--border-subtle); text-align: center; display: flex; flex-direction: column; gap: 0.65rem;">
          <button type="button" class="btn-secondary" style="width: 100%;" onclick="quickDemoLogin()">
            Örnek Kullanıcı Hesabıyla Hızlı Giriş Yap
          </button>
          <p style="font-size: 0.84rem; color: var(--text-muted);">
            Henüz hesabınız yok mu?
            <a href="#" onclick="event.preventDefault(); navigateTo('register');" style="color: var(--lb-green); font-weight: 600; text-decoration: none;">
              Yeni Hesap Oluştur
            </a>
          </p>
        </div>
      </div>
    </section>
  `;
}

async function submitLogin(e) {
  e.preventDefault();
  const email = document.getElementById("loginEmail").value.trim();
  const password = document.getElementById("loginPass").value;
  const alertBox = document.getElementById("loginAlert");

  try {
    const res = await apiRequest("./api/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
    state.token = res.token;
    state.currentUser = res.user;
    localStorage.setItem(TOKEN_KEY, res.token);
    localStorage.setItem(USER_KEY, JSON.stringify(res.user));
    navigateTo("discover");
  } catch (err) {
    if (err.message === "STATIC_MODE") {
      // Check local storage users
      const localUsers = JSON.parse(localStorage.getItem(LOCAL_USERS_KEY) || "[]");
      const found = localUsers.find((u) => u.email.toLowerCase() === email.toLowerCase());
      if (found) {
        state.currentUser = found;
        localStorage.setItem(USER_KEY, JSON.stringify(found));
        navigateTo("discover");
        return;
      }
      quickDemoLogin();
      return;
    }
    alertBox.innerHTML = `<div class="alert-box alert-error">${escapeHtml(err.message)}</div>`;
  }
}

async function quickDemoLogin() {
  try {
    const res = await apiRequest("./api/auth/login", {
      method: "POST",
      body: JSON.stringify({ email: "zeynep@thejust.app", password: "demo123" }),
    });
    state.token = res.token;
    state.currentUser = res.user;
    localStorage.setItem(TOKEN_KEY, res.token);
    localStorage.setItem(USER_KEY, JSON.stringify(res.user));
    navigateTo("discover");
  } catch (_) {
    const demoUser = {
      id: 99,
      name: "Zeynep Kaya",
      email: "zeynep@thejust.app",
      age: 25,
      city: "Ankara • Çankaya",
      bio: "Mimarlık yüksek lisans öğrencisi. A24 filmleri, MUBI klasikleri ve psikolojik gerilim tutkunu.",
      intent: "Both",
      favoriteGenres: "Indie, Drama, Mystery",
      letterboxdUsername: "dtquandt",
      photoData: makeAvatarSvg("Zeynep Kaya", "#3b0764", "#ff8000"),
    };
    state.currentUser = demoUser;
    localStorage.setItem(USER_KEY, JSON.stringify(demoUser));
    navigateTo("discover");
  }
}

// ============================================================================
// SCREEN 3: REGISTER & PERSONAL PROFILE + PHOTO UPLOAD
// ============================================================================
function renderRegisterScreen(root) {
  state.tempPhotoData = makeAvatarSvg("Yeni Üye", "#1e293b", "#00e054");

  root.innerHTML = `
    <section class="screen-view">
      <div class="auth-card wide">
        <div class="auth-header">
          <h2>Hesap Oluştur ve Profilini Tamamla</h2>
          <p>Fotoğrafınızı yükleyin, kişisel bilgilerinizi ve Letterboxd kullanıcı adınızı girin.</p>
        </div>

        <div id="registerAlert"></div>

        <form onsubmit="submitRegister(event)">
          <!-- Fotoğraf Yükleme Alanı -->
          <div class="photo-upload-box">
            <img id="regPhotoPreview" src="${state.tempPhotoData}" alt="Profil Önizleme" class="photo-preview" />
            <div style="flex: 1;">
              <label style="display:block; font-size:0.86rem; font-weight:700; margin-bottom:0.25rem;">
                Profil Fotoğrafı Yükle
              </label>
              <p style="font-size:0.78rem; color:var(--text-muted); margin-bottom:0.6rem;">
                Bilgisayarınızdan veya telefonunuzdan bir fotoğraf seçin (JPG veya PNG).
              </p>
              <input
                type="file"
                accept="image/*"
                onchange="handlePhotoFileSelect(this, 'regPhotoPreview')"
                style="font-size:0.8rem; color:var(--text-muted);"
              />
            </div>
          </div>

          <div class="form-grid">
            <div class="form-field">
              <label for="regName">Ad Soyad *</label>
              <input id="regName" type="text" placeholder="Örn: Mustafa Can" required />
            </div>

            <div class="form-field">
              <label for="regLetterboxd">Letterboxd Kullanıcı Adı *</label>
              <input id="regLetterboxd" type="text" placeholder="Örn: dtquandt veya karsten" required />
            </div>
          </div>

          <div class="form-grid">
            <div class="form-field">
              <label for="regEmail">E-posta Adresi *</label>
              <input id="regEmail" type="email" placeholder="ornek@eposta.com" required />
            </div>

            <div class="form-field">
              <label for="regPass">Şifre *</label>
              <input id="regPass" type="password" placeholder="En az 6 karakter" required />
            </div>
          </div>

          <div class="form-grid">
            <div class="form-field">
              <label for="regAge">Yaş</label>
              <input id="regAge" type="number" min="18" max="99" value="24" required />
            </div>

            <div class="form-field">
              <label for="regCity">Şehir / Konum</label>
              <input id="regCity" type="text" placeholder="Örn: İstanbul • Kadıköy" required />
            </div>
          </div>

          <div class="form-grid">
            <div class="form-field">
              <label for="regIntent">Tanışma Amacı</label>
              <select id="regIntent">
                <option value="Both">Hem Arkadaşlık Hem Romantik Tanışma</option>
                <option value="Friendship">Sinema & Festival Arkadaşlığı</option>
                <option value="Dating">Romantik Tanışma (Date)</option>
              </select>
            </div>

            <div class="form-field">
              <label for="regGenres">Favori Film Türleri</label>
              <input id="regGenres" type="text" placeholder="Örn: Bilim Kurgu, Bağımsız, Gerilim" />
            </div>
          </div>

          <div class="form-field">
            <label for="regBio">Hakkında & Sinema Zevkin</label>
            <textarea id="regBio" rows="3" placeholder="Kendinden, en sevdiğin yönetmenlerden veya film izleme alışkanlığından bahset..."></textarea>
          </div>

          <button type="submit" id="regSubmitBtn" class="btn-primary" style="width: 100%; margin-top: 0.5rem;">
            Profilimi Oluştur ve Eşleşmeleri Gör
          </button>
        </form>
      </div>
    </section>
  `;
}

async function submitRegister(e) {
  e.preventDefault();
  const btn = document.getElementById("regSubmitBtn");
  const alertBox = document.getElementById("registerAlert");

  const payload = {
    name: document.getElementById("regName").value.trim(),
    letterboxdUsername: document.getElementById("regLetterboxd").value.trim(),
    email: document.getElementById("regEmail").value.trim(),
    password: document.getElementById("regPass").value,
    age: parseInt(document.getElementById("regAge").value, 10) || 24,
    city: document.getElementById("regCity").value.trim(),
    intent: document.getElementById("regIntent").value,
    favoriteGenres: document.getElementById("regGenres").value.trim(),
    bio: document.getElementById("regBio").value.trim(),
    photoData: state.tempPhotoData || makeAvatarSvg(document.getElementById("regName").value),
  };

  btn.disabled = true;
  btn.textContent = "Letterboxd Verilerin Senkronize Ediliyor...";

  try {
    const res = await apiRequest("./api/auth/register", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    state.token = res.token;
    state.currentUser = res.user;
    localStorage.setItem(TOKEN_KEY, res.token);
    localStorage.setItem(USER_KEY, JSON.stringify(res.user));
    navigateTo("discover");
  } catch (err) {
    if (err.message === "STATIC_MODE") {
      const newUser = { id: Date.now(), ...payload };
      const localUsers = JSON.parse(localStorage.getItem(LOCAL_USERS_KEY) || "[]");
      localUsers.push(newUser);
      localStorage.setItem(LOCAL_USERS_KEY, JSON.stringify(localUsers));
      state.currentUser = newUser;
      localStorage.setItem(USER_KEY, JSON.stringify(newUser));
      navigateTo("discover");
      return;
    }
    alertBox.innerHTML = `<div class="alert-box alert-error">${escapeHtml(err.message)}</div>`;
    btn.disabled = false;
    btn.textContent = "Profilimi Oluştur ve Eşleşmeleri Gör";
  }
}

// ============================================================================
// SCREEN 4: DISCOVER PEOPLE SCREEN (SEPARATE WINDOW)
// ============================================================================
async function renderDiscoverScreen(root) {
  if (!state.currentUser) {
    navigateTo("login");
    return;
  }

  root.innerHTML = `
    <section class="screen-view">
      <div class="screen-header">
        <div>
          <h1>Seninle Aynı Film Zevkine Sahip İnsanlar</h1>
          <p>
            Letterboxd hesabın (<strong>@${escapeHtml(state.currentUser.letterboxdUsername || "belirtilmedi")}</strong>) baz alınarak film uyumuna göre sıralandı.
          </p>
        </div>

        <div style="display:flex; gap:0.45rem; flex-wrap:wrap;">
          <button type="button" class="nav-btn ${state.discoverFilter === "All" ? "active" : ""}" onclick="setDiscoverFilter('All')">
            Tümü
          </button>
          <button type="button" class="nav-btn ${state.discoverFilter === "Friendship" ? "active" : ""}" onclick="setDiscoverFilter('Friendship')">
            Sinema Arkadaşlığı
          </button>
          <button type="button" class="nav-btn ${state.discoverFilter === "Dating" ? "active" : ""}" onclick="setDiscoverFilter('Dating')">
            Romantik Tanışma
          </button>
        </div>
      </div>

      <div id="discoverGridContainer">
        <div style="text-align:center; padding: 3rem;">
          <div class="spinner"></div>
          <p style="color:var(--text-muted); font-size:0.9rem;">Eşleşmeler yükleniyor...</p>
        </div>
      </div>
    </section>
  `;

  try {
    const res = await apiRequest("./api/discover");
    state.members = res.members || [];
  } catch (_) {
    state.members = DEFAULT_SEED_MEMBERS;
  }

  renderDiscoverCards();
}

function setDiscoverFilter(filterVal) {
  state.discoverFilter = filterVal;
  renderDiscoverScreen(document.getElementById("screenRoot"));
}

function getIntentLabel(intent) {
  if (intent === "Friendship") return "Sinema Arkadaşı Arıyor";
  if (intent === "Dating") return "Tanışma (Date)";
  return "Arkadaşlık & Tanışma";
}

function renderDiscoverCards() {
  const box = document.getElementById("discoverGridContainer");
  if (!box) return;

  let list = state.members.filter((m) => m.id !== state.currentUser?.id);
  if (state.discoverFilter !== "All") {
    list = list.filter((m) => m.intent === state.discoverFilter || m.intent === "Both");
  }

  if (list.length === 0) {
    box.innerHTML = `<div class="auth-card" style="text-align:center;"><p style="color:var(--text-muted);">Bu filtrede henüz üye bulunamadı.</p></div>`;
    return;
  }

  box.innerHTML = `
    <div class="members-grid">
      ${list
        .map((m) => {
          const compat = m.compatibility || { score: 75, bothSeen: 40, sharedHighlights: [] };
          const topFilms =
            compat.sharedHighlights && compat.sharedHighlights.length > 0
              ? compat.sharedHighlights
              : (m.lbSummary && m.lbSummary.topFilms) || [];

          return `
            <article class="member-card">
              <div style="display:flex; flex-direction:column; gap:0.9rem;">
                <div class="member-top">
                  <img src="${escapeHtml(m.photoData)}" alt="${escapeHtml(m.name)}" class="member-photo" />
                  <div class="member-info">
                    <div class="member-name-row">
                      <span class="member-name">${escapeHtml(m.name)}, ${m.age}</span>
                      <span class="match-pill">%${compat.score} Uyum</span>
                    </div>
                    <div class="member-sub">${escapeHtml(m.city || "Türkiye")} • ${escapeHtml(getIntentLabel(m.intent))}</div>
                    <span class="member-lb-tag">Letterboxd: @${escapeHtml(m.letterboxdUsername)}</span>
                  </div>
                </div>

                <p class="member-bio">${escapeHtml(m.bio || "Sinema tutkunu.")}</p>

                ${
                  topFilms.length > 0
                    ? `
                  <div>
                    <span style="font-size:0.74rem; font-weight:700; color:var(--text-dim); display:block; margin-bottom:0.35rem; text-transform:uppercase;">
                      Öne Çıkan Filmleri
                    </span>
                    <div class="member-films-tags">
                      ${topFilms.map((f) => `<span class="film-tag">${escapeHtml(f)}</span>`).join("")}
                    </div>
                  </div>
                `
                    : ""
                }
              </div>

              <div class="member-actions">
                <button type="button" class="btn-secondary btn-sm" onclick="openMemberDetail(${m.id})">
                  Uyum Detayını Aç
                </button>
                <button type="button" class="btn-primary btn-sm" onclick="openChatScreen(${m.id})">
                  Tanış & Mesajlaş
                </button>
              </div>
            </article>
          `;
        })
        .join("")}
    </div>
  `;
}

// ============================================================================
// SCREEN 5: DEDICATED MEMBER & TASTE COMPATIBILITY DETAIL WINDOW
// ============================================================================
async function openMemberDetail(memberId) {
  const found = state.members.find((m) => m.id === memberId) || DEFAULT_SEED_MEMBERS[0];
  state.selectedMember = found;
  state.selectedCompatibility = null;
  state.detailTab = "overview";
  navigateTo("member-detail");

  try {
    const myLb = state.currentUser?.letterboxdUsername || "dtquandt";
    const res = await apiRequest(`./api/member?id=${memberId}&my_lb=${encodeURIComponent(myLb)}`);
    state.selectedMember = res.member;
    state.selectedCompatibility = res.compatibility;
    if (state.currentScreen === "member-detail") {
      renderMemberDetailScreen(document.getElementById("screenRoot"));
    }
  } catch (_) {
    // Fallback compatibility call if static mode
    const myLb = state.currentUser?.letterboxdUsername || "dtquandt";
    const targetLb = found.letterboxdUsername || "karsten";
    try {
      const res2 = await apiRequest(`./api/compatibility?user1=${encodeURIComponent(myLb)}&user2=${encodeURIComponent(targetLb)}`);
      state.selectedCompatibility = res2.data;
      if (state.currentScreen === "member-detail") {
        renderMemberDetailScreen(document.getElementById("screenRoot"));
      }
    } catch (_e) {}
  }
}

function setDetailTab(tabName) {
  state.detailTab = tabName;
  renderMemberDetailScreen(document.getElementById("screenRoot"));
}

function renderMemberDetailScreen(root) {
  const m = state.selectedMember;
  if (!m) {
    navigateTo("discover");
    return;
  }

  const c = state.selectedCompatibility;
  const myName = state.currentUser?.name || "Sen";
  const myLb = state.currentUser?.letterboxdUsername || "dtquandt";

  let subViewHtml = "";

  if (!c) {
    subViewHtml = `
      <div style="text-align:center; padding: 3rem; background:var(--bg-elevated); border:1px solid var(--border); border-radius:var(--radius-lg);">
        <div class="spinner"></div>
        <p style="font-weight:600; margin-bottom:0.25rem;">
          @${escapeHtml(myLb)} ve @${escapeHtml(m.letterboxdUsername)} Letterboxd verileri karşılaştırılıyor...
        </p>
        <p style="font-size:0.82rem; color:var(--text-muted);">
          İzleme geçmişleri, ortak filmler ve puan uyumları analiz ediliyor.
        </p>
      </div>
    `;
  } else if (state.detailTab === "overview") {
    const wo = c.watchOverlap || { onlyUser1: 0, bothSeen: 0, onlyUser2: 0 };
    const ro = c.ratingOverlap || { bothRatedCount: 0, user1Higher: 0, agreedExactly: 0, user2Higher: 0, avgDistance: 0.8 };

    subViewHtml = `
      <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 1.25rem;">
        <div class="step-card">
          <span class="step-num">Genel Zevk Uyumu</span>
          <div style="font-size:2.4rem; font-weight:800; color:var(--lb-green); margin: 0.25rem 0;">
            %${c.score}
          </div>
          <p style="margin-bottom:0.85rem;">
            İkiniz de ortak <strong>${wo.bothSeen} film</strong> izlediniz. Ortak puanladığınız filmlerde aranızdaki ortalama fark yalnızca <strong>${ro.avgDistance || 0.8}★</strong>.
          </p>
        </div>

        <div class="step-card">
          <span class="step-num">İzleme Kesişimi (Venn)</span>
          <div style="display:grid; grid-template-columns:repeat(3,1fr); gap:0.5rem; text-align:center; margin-top:0.75rem;">
            <div style="background:var(--bg); padding:0.65rem; border-radius:8px;">
              <strong style="font-size:1.15rem; color:var(--lb-orange); display:block;">${wo.onlyUser1}</strong>
              <span style="font-size:0.75rem; color:var(--text-muted);">Sadece Sen</span>
            </div>
            <div style="background:var(--bg); padding:0.65rem; border-radius:8px;">
              <strong style="font-size:1.15rem; color:var(--lb-green); display:block;">${wo.bothSeen}</strong>
              <span style="font-size:0.75rem; color:var(--text-muted);">İkiniz de İzlediniz</span>
            </div>
            <div style="background:var(--bg); padding:0.65rem; border-radius:8px;">
              <strong style="font-size:1.15rem; color:var(--lb-blue); display:block;">${wo.onlyUser2}</strong>
              <span style="font-size:0.75rem; color:var(--text-muted);">Sadece ${escapeHtml(m.name.split(" ")[0])}</span>
            </div>
          </div>
        </div>

        <div class="step-card">
          <span class="step-num">Sohbet Başlatıcı Konular</span>
          <div style="display:flex; flex-direction:column; gap:0.6rem; margin-top:0.5rem;">
            ${(c.icebreakers || [])
              .map(
                (ib) => `
                <div style="background:var(--bg); padding:0.65rem 0.8rem; border-radius:8px; font-size:0.82rem;">
                  <strong style="color:var(--lb-green); display:block; margin-bottom:2px;">${escapeHtml(ib.category)}</strong>
                  <span>“${escapeHtml(ib.prompt)}”</span>
                </div>
              `
              )
              .join("")}
          </div>
        </div>
      </div>
    `;
  } else if (state.detailTab === "agreements") {
    const items = c.agreements || [];
    subViewHtml = `
      <div class="posters-grid">
        ${items
          .map(
            (item) => `
            <a href="${escapeHtml(item.filmUrl)}" target="_blank" rel="noopener" class="poster-item">
              <div class="poster-img-wrap">
                <img loading="lazy" src="${escapeHtml(item.posterUrl)}" alt="${escapeHtml(item.title)}" />
                ${item.caption ? `<span class="poster-rating-pill">${escapeHtml(item.caption)}</span>` : ""}
              </div>
              <div class="poster-info">
                <div class="poster-title">${escapeHtml(item.title)}</div>
              </div>
            </a>
          `
          )
          .join("")}
      </div>
    `;
  } else if (state.detailTab === "disagreements") {
    const list = c.disagreements || [];
    subViewHtml = `
      <div style="display:grid; grid-template-columns:repeat(auto-fill, minmax(300px, 1fr)); gap:1rem;">
        ${list
          .map(
            (dItem) => `
            <div class="step-card">
              <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:0.6rem;">
                <strong>${escapeHtml(dItem.title)} ${dItem.year ? `(${escapeHtml(dItem.year)})` : ""}</strong>
                <span class="match-pill" style="color:var(--lb-orange); border-color:rgba(255,128,0,0.4); background:rgba(255,128,0,0.12);">
                  Δ ${dItem.diff}★ Fark
                </span>
              </div>
              <div style="font-size:0.84rem; display:flex; justify-content:space-between; color:var(--text-muted);">
                <span>Senin Puanın: <strong style="color:var(--lb-orange);">${dItem.user1Rating}★</strong></span>
                <span>${escapeHtml(m.name.split(" ")[0])}: <strong style="color:var(--lb-blue);">${dItem.user2Rating}★</strong></span>
              </div>
            </div>
          `
          )
          .join("")}
      </div>
    `;
  } else if (state.detailTab === "watchlist") {
    const wl = (c.sharedWatchlist && c.sharedWatchlist.length > 0 ? c.sharedWatchlist : c.recommendations) || [];
    subViewHtml = `
      <p style="font-size:0.88rem; color:var(--text-muted); margin-bottom:1rem;">
        İkinizin beraber izleyebileceği ortak Watchlist ve zevk önerisi filmleri:
      </p>
      <div class="posters-grid">
        ${wl
          .map(
            (item) => `
            <a href="${escapeHtml(item.filmUrl)}" target="_blank" rel="noopener" class="poster-item">
              <div class="poster-img-wrap">
                <img loading="lazy" src="${escapeHtml(item.posterUrl)}" alt="${escapeHtml(item.title)}" />
              </div>
              <div class="poster-info">
                <div class="poster-title">${escapeHtml(item.title)}</div>
              </div>
            </a>
          `
          )
          .join("")}
      </div>
    `;
  }

  root.innerHTML = `
    <section class="screen-view">
      <div style="margin-bottom: 1.25rem;">
        <button type="button" class="btn-secondary btn-sm" onclick="navigateTo('discover')">
          ← İnsanlarla Tanış Ekranına Dön
        </button>
      </div>

      <!-- Kişi Başlık Kartı -->
      <div class="member-card" style="margin-bottom: 1.5rem;">
        <div style="display:flex; align-items:center; justify-content:space-between; gap:1.25rem; flex-wrap:wrap;">
          <div style="display:flex; align-items:center; gap:1.15rem;">
            <img src="${escapeHtml(m.photoData)}" alt="${escapeHtml(m.name)}" class="member-photo" style="width:82px; height:82px;" />
            <div>
              <div style="display:flex; align-items:center; gap:0.65rem; flex-wrap:wrap;">
                <h1 style="font-size:1.45rem; font-weight:800;">${escapeHtml(m.name)}, ${m.age}</h1>
                ${c ? `<span class="match-pill">%${c.score} Film Zevki Uyumu</span>` : ""}
              </div>
              <p class="member-sub">${escapeHtml(m.city)} • Letterboxd: <strong>@${escapeHtml(m.letterboxdUsername)}</strong></p>
              <p style="font-size:0.88rem; margin-top:0.45rem; max-width:620px;">${escapeHtml(m.bio)}</p>
            </div>
          </div>

          <button type="button" class="btn-primary" onclick="openChatScreen(${m.id})">
            ${escapeHtml(m.name.split(" ")[0])} İle Sohbet Başlat
          </button>
        </div>
      </div>

      <!-- Alt Pencereler Sekmesi -->
      <div class="subnav-bar">
        <button type="button" class="nav-btn ${state.detailTab === "overview" ? "active" : ""}" onclick="setDetailTab('overview')">
          Genel Uyum Özeti
        </button>
        <button type="button" class="nav-btn ${state.detailTab === "agreements" ? "active" : ""}" onclick="setDetailTab('agreements')">
          Ortak Sevilen Filmler ${c ? `(${(c.agreements || []).length})` : ""}
        </button>
        <button type="button" class="nav-btn ${state.detailTab === "disagreements" ? "active" : ""}" onclick="setDetailTab('disagreements')">
          Puan Ayrılıkları ${c ? `(${(c.disagreements || []).length})` : ""}
        </button>
        <button type="button" class="nav-btn ${state.detailTab === "watchlist" ? "active" : ""}" onclick="setDetailTab('watchlist')">
          Beraber İzlenecekler
        </button>
      </div>

      <div>${subViewHtml}</div>
    </section>
  `;
}

// ============================================================================
// SCREEN 6: DEDICATED CHAT WINDOW
// ============================================================================
async function openChatScreen(memberId) {
  const found = state.members.find((m) => m.id === memberId) || DEFAULT_SEED_MEMBERS[0];
  state.selectedMember = found;
  state.chatMessages = [];
  navigateTo("chat");

  try {
    const res = await apiRequest(`./api/messages?user_id=${memberId}`);
    state.chatMessages = res.messages || [];
  } catch (_) {
    const allLocal = JSON.parse(localStorage.getItem(LOCAL_MSGS_KEY) || "{}");
    state.chatMessages = allLocal[memberId] || [];
  }

  if (state.chatMessages.length === 0) {
    state.chatMessages = [
      {
        isMine: false,
        content: `Selam! Letterboxd listelerimizdeki ortak filmleri gördüm, sinema zevkimiz bayağı uyuşuyor.`,
      },
    ];
  }

  if (state.currentScreen === "chat") {
    renderChatScreen(document.getElementById("screenRoot"));
  }
}

function renderChatScreen(root) {
  const m = state.selectedMember;
  if (!m) {
    navigateTo("discover");
    return;
  }

  const sampleFilms = (m.lbSummary && m.lbSummary.topFilms) || ["Mulholland Drive", "Aftersun"];
  const icebreakers = [
    `İkimiz de ${sampleFilms[0] || "aynı"} filmini çok sevmişiz! En sevdiğin sahnesi hangisiydi?`,
    `Bu hafta sonu ortak Watchlist'imizden bir film seçip izleyelim mi?`,
    `Son zamanlarda Letterboxd'da 5 yıldız verdiğin en iyi film hangisiydi?`,
  ];

  root.innerHTML = `
    <section class="screen-view">
      <div style="max-width:780px; margin: 0 auto 1rem; display:flex; justify-content:space-between; align-items:center;">
        <button type="button" class="btn-secondary btn-sm" onclick="navigateTo('discover')">
          ← Eşleşmelere Dön
        </button>
        <button type="button" class="btn-secondary btn-sm" onclick="openMemberDetail(${m.id})">
          Zevk Uyumu Detayını Gör
        </button>
      </div>

      <div class="chat-layout">
        <div class="chat-header">
          <div style="display:flex; align-items:center; gap:0.85rem;">
            <img src="${escapeHtml(m.photoData)}" alt="${escapeHtml(m.name)}" style="width:44px; height:44px; border-radius:50%; object-fit:cover;" />
            <div>
              <strong style="font-size:1rem; display:block;">${escapeHtml(m.name)}, ${m.age}</strong>
              <span style="font-size:0.78rem; color:var(--text-muted);">
                ${escapeHtml(m.city)} • Letterboxd: @${escapeHtml(m.letterboxdUsername)}
              </span>
            </div>
          </div>
          <span class="match-pill">Sinema Eşleşmesi</span>
        </div>

        <div id="chatMessagesBox" class="chat-messages">
          ${state.chatMessages
            .map(
              (msg) => `
              <div class="msg-bubble ${msg.isMine ? "msg-mine" : "msg-theirs"}">
                ${escapeHtml(msg.content)}
              </div>
            `
            )
            .join("")}
        </div>

        <div class="chat-icebreakers">
          ${icebreakers
            .map(
              (ib) => `
              <button type="button" class="icebreaker-chip" onclick="sendQuickMessage('${escapeHtml(ib)}')">
                ✨ ${escapeHtml(ib)}
              </button>
            `
            )
            .join("")}
        </div>

        <form class="chat-input-bar" onsubmit="handleSendMessage(event)">
          <input id="chatTextInput" type="text" placeholder="${escapeHtml(m.name.split(" ")[0])} ile mesajlaş..." required />
          <button type="submit" class="btn-primary">Gönder</button>
        </form>
      </div>
    </section>
  `;

  const box = document.getElementById("chatMessagesBox");
  if (box) box.scrollTop = box.scrollHeight;
}

async function sendQuickMessage(text) {
  const input = document.getElementById("chatTextInput");
  if (input) {
    input.value = text;
    await handleSendMessage(new Event("submit"));
  }
}

async function handleSendMessage(e) {
  if (e && e.preventDefault) e.preventDefault();
  const input = document.getElementById("chatTextInput");
  if (!input) return;
  const content = input.value.trim();
  if (!content || !state.selectedMember) return;

  input.value = "";
  state.chatMessages.push({ isMine: true, content });
  renderChatScreen(document.getElementById("screenRoot"));

  try {
    await apiRequest("./api/messages", {
      method: "POST",
      body: JSON.stringify({ receiverId: state.selectedMember.id, content }),
    });
  } catch (_) {
    const allLocal = JSON.parse(localStorage.getItem(LOCAL_MSGS_KEY) || "{}");
    allLocal[state.selectedMember.id] = state.chatMessages;
    localStorage.setItem(LOCAL_MSGS_KEY, JSON.stringify(allLocal));
  }
}

// ============================================================================
// SCREEN 7: MY PROFILE & PHOTO EDIT SCREEN
// ============================================================================
function renderProfileScreen(root) {
  const u = state.currentUser;
  if (!u) {
    navigateTo("login");
    return;
  }

  state.tempPhotoData = u.photoData || makeAvatarSvg(u.name);

  root.innerHTML = `
    <section class="screen-view">
      <div class="auth-card wide">
        <div class="auth-header">
          <h2>Profilim ve Fotoğrafım</h2>
          <p>Kişisel bilgilerinizi, fotoğrafınızı ve bağlı Letterboxd kullanıcı adınızı güncelleyin.</p>
        </div>

        <div id="profileAlert"></div>

        <form onsubmit="submitProfileUpdate(event)">
          <div class="photo-upload-box">
            <img id="profPhotoPreview" src="${escapeHtml(state.tempPhotoData)}" alt="Profil Fotoğrafı" class="photo-preview" />
            <div style="flex:1;">
              <label style="display:block; font-size:0.86rem; font-weight:700; margin-bottom:0.25rem;">
                Profil Fotoğrafını Değiştir
              </label>
              <p style="font-size:0.78rem; color:var(--text-muted); margin-bottom:0.6rem;">
                Yeni bir fotoğraf yüklemek için dosya seçin.
              </p>
              <input
                type="file"
                accept="image/*"
                onchange="handlePhotoFileSelect(this, 'profPhotoPreview')"
                style="font-size:0.8rem; color:var(--text-muted);"
              />
            </div>
          </div>

          <div class="form-grid">
            <div class="form-field">
              <label for="profName">Ad Soyad</label>
              <input id="profName" type="text" value="${escapeHtml(u.name)}" required />
            </div>

            <div class="form-field">
              <label for="profLetterboxd">Letterboxd Kullanıcı Adı</label>
              <input id="profLetterboxd" type="text" value="${escapeHtml(u.letterboxdUsername || "")}" required />
            </div>
          </div>

          <div class="form-grid">
            <div class="form-field">
              <label for="profAge">Yaş</label>
              <input id="profAge" type="number" min="18" max="99" value="${u.age || 24}" required />
            </div>

            <div class="form-field">
              <label for="profCity">Şehir / Konum</label>
              <input id="profCity" type="text" value="${escapeHtml(u.city || "")}" required />
            </div>
          </div>

          <div class="form-grid">
            <div class="form-field">
              <label for="profIntent">Tanışma Amacı</label>
              <select id="profIntent">
                <option value="Both" ${u.intent === "Both" ? "selected" : ""}>Hem Arkadaşlık Hem Romantik Tanışma</option>
                <option value="Friendship" ${u.intent === "Friendship" ? "selected" : ""}>Sinema & Festival Arkadaşlığı</option>
                <option value="Dating" ${u.intent === "Dating" ? "selected" : ""}>Romantik Tanışma (Date)</option>
              </select>
            </div>

            <div class="form-field">
              <label for="profGenres">Favori Film Türleri</label>
              <input id="profGenres" type="text" value="${escapeHtml(u.favoriteGenres || "")}" />
            </div>
          </div>

          <div class="form-field">
            <label for="profBio">Hakkında & Sinema Zevkin</label>
            <textarea id="profBio" rows="3">${escapeHtml(u.bio || "")}</textarea>
          </div>

          <div style="display:flex; gap:0.75rem; justify-content:flex-end;">
            <button type="button" class="btn-secondary" onclick="navigateTo('discover')">
              İptal
            </button>
            <button type="submit" id="profSaveBtn" class="btn-primary">
              Değişiklikleri Kaydet
            </button>
          </div>
        </form>
      </div>
    </section>
  `;
}

async function submitProfileUpdate(e) {
  e.preventDefault();
  const btn = document.getElementById("profSaveBtn");
  const alertBox = document.getElementById("profileAlert");

  const payload = {
    name: document.getElementById("profName").value.trim(),
    letterboxdUsername: document.getElementById("profLetterboxd").value.trim(),
    age: parseInt(document.getElementById("profAge").value, 10) || 24,
    city: document.getElementById("profCity").value.trim(),
    intent: document.getElementById("profIntent").value,
    favoriteGenres: document.getElementById("profGenres").value.trim(),
    bio: document.getElementById("profBio").value.trim(),
    photoData: state.tempPhotoData || state.currentUser.photoData,
  };

  btn.disabled = true;
  btn.textContent = "Kaydediliyor...";

  try {
    const res = await apiRequest("./api/profile/update", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    state.currentUser = res.user;
    localStorage.setItem(USER_KEY, JSON.stringify(res.user));
    renderHeader();
    alertBox.innerHTML = `<div class="alert-box alert-success">Profiliniz ve Letterboxd verileriniz başarıyla güncellendi.</div>`;
  } catch (err) {
    state.currentUser = { ...state.currentUser, ...payload };
    localStorage.setItem(USER_KEY, JSON.stringify(state.currentUser));
    renderHeader();
    alertBox.innerHTML = `<div class="alert-box alert-success">Profiliniz güncellendi.</div>`;
  } finally {
    btn.disabled = false;
    btn.textContent = "Değişiklikleri Kaydet";
  }
}

function handleLogout() {
  state.token = "";
  state.currentUser = null;
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
  navigateTo("welcome");
}

// ============================================================================
// SCREEN 8: STANDALONE TWO-USER COMPARE TOOL
// ============================================================================
function renderCompareScreen(root) {
  const defaultU1 = state.currentUser?.letterboxdUsername || "dtquandt";
  const c = state.compareData;

  root.innerHTML = `
    <section class="screen-view">
      <div class="screen-header">
        <div>
          <h1>İkili Letterboxd Zevk Uyumu Testi</h1>
          <p>Herhangi iki Letterboxd kullanıcı adını girerek aralarındaki film uyumunu ayrı pencerelerde inceleyin.</p>
        </div>
      </div>

      <form onsubmit="submitStandaloneCompare(event)" class="member-card" style="margin-bottom: 1.5rem;">
        <div style="display:grid; grid-template-columns: 1fr 1fr auto; gap: 0.85rem; align-items: end;">
          <div class="form-field" style="margin-bottom:0;">
            <label>1. Letterboxd Kullanıcısı</label>
            <input id="cmpU1" type="text" value="${escapeHtml(defaultU1)}" placeholder="kullanici_1" required />
          </div>
          <div class="form-field" style="margin-bottom:0;">
            <label>2. Letterboxd Kullanıcısı</label>
            <input id="cmpU2" type="text" value="karsten" placeholder="kullanici_2" required />
          </div>
          <button type="submit" id="cmpBtn" class="btn-primary" style="height:42px;">
            Uyumu Analiz Et
          </button>
        </div>
      </form>

      <div id="compareResultBox">
        ${c ? renderStandaloneCompareResult(c) : ""}
      </div>
    </section>
  `;
}

async function submitStandaloneCompare(e) {
  e.preventDefault();
  const u1 = document.getElementById("cmpU1").value.trim();
  const u2 = document.getElementById("cmpU2").value.trim();
  const box = document.getElementById("compareResultBox");

  box.innerHTML = `
    <div style="text-align:center; padding:2.5rem;">
      <div class="spinner"></div>
      <p style="color:var(--text-muted);">@${escapeHtml(u1)} ve @${escapeHtml(u2)} karşılaştırılıyor...</p>
    </div>
  `;

  try {
    const res = await apiRequest(`./api/compatibility?user1=${encodeURIComponent(u1)}&user2=${encodeURIComponent(u2)}`);
    state.compareData = res.data;
    state.compareTab = "overview";
    box.innerHTML = renderStandaloneCompareResult(state.compareData);
  } catch (err) {
    box.innerHTML = `<div class="alert-box alert-error">${escapeHtml(err.message || "Karşılaştırma yapılamadı.")}</div>`;
  }
}

function setCompareTab(t) {
  state.compareTab = t;
  const box = document.getElementById("compareResultBox");
  if (box && state.compareData) {
    box.innerHTML = renderStandaloneCompareResult(state.compareData);
  }
}

function renderStandaloneCompareResult(c) {
  const wo = c.watchOverlap || { onlyUser1: 0, bothSeen: 0, onlyUser2: 0 };
  const ro = c.ratingOverlap || { avgDistance: 0.8, agreedExactly: 0 };

  let body = "";
  if (state.compareTab === "overview") {
    body = `
      <div class="welcome-steps" style="margin-top:0;">
        <div class="step-card">
          <span class="step-num">Uyum Skoru</span>
          <div style="font-size:2.2rem; font-weight:800; color:var(--lb-green);">%${c.score}</div>
          <p>${escapeHtml(c.scoreLabel || "Taste Match")} • Ortak ${wo.bothSeen} film izlendi.</p>
        </div>
        <div class="step-card">
          <span class="step-num">Puanlama Yakınlığı</span>
          <div style="font-size:2.2rem; font-weight:800; color:var(--lb-blue);">${ro.avgDistance}★</div>
          <p>Ortak puanlanan filmlerde ortalama yıldız farkı (${ro.agreedExactly} filmde birebir aynı puan).</p>
        </div>
        <div class="step-card">
          <span class="step-num">Ortak Watchlist</span>
          <div style="font-size:2.2rem; font-weight:800; color:var(--lb-orange);">${(c.sharedWatchlist || []).length}</div>
          <p>İki kullanıcının da izleme listesinde bekleyen ortak film sayısı.</p>
        </div>
      </div>
    `;
  } else if (state.compareTab === "agreements") {
    body = `
      <div class="posters-grid">
        ${(c.agreements || [])
          .map(
            (m) => `
            <a href="${escapeHtml(m.filmUrl)}" target="_blank" rel="noopener" class="poster-item">
              <div class="poster-img-wrap">
                <img loading="lazy" src="${escapeHtml(m.posterUrl)}" alt="${escapeHtml(m.title)}" />
                ${m.caption ? `<span class="poster-rating-pill">${escapeHtml(m.caption)}</span>` : ""}
              </div>
              <div class="poster-info"><div class="poster-title">${escapeHtml(m.title)}</div></div>
            </a>
          `
          )
          .join("")}
      </div>
    `;
  } else if (state.compareTab === "disagreements") {
    body = `
      <div class="members-grid">
        ${(c.disagreements || [])
          .map(
            (d) => `
            <div class="step-card">
              <div style="display:flex; justify-content:space-between; margin-bottom:0.4rem;">
                <strong>${escapeHtml(d.title)}</strong>
                <span class="match-pill">Δ ${d.diff}★</span>
              </div>
              <p>${d.user1Rating}★ vs ${d.user2Rating}★</p>
            </div>
          `
          )
          .join("")}
      </div>
    `;
  }

  return `
    <div class="subnav-bar">
      <button type="button" class="nav-btn ${state.compareTab === "overview" ? "active" : ""}" onclick="setCompareTab('overview')">
        Özet
      </button>
      <button type="button" class="nav-btn ${state.compareTab === "agreements" ? "active" : ""}" onclick="setCompareTab('agreements')">
        Ortak Sevilenler (${(c.agreements || []).length})
      </button>
      <button type="button" class="nav-btn ${state.compareTab === "disagreements" ? "active" : ""}" onclick="setCompareTab('disagreements')">
        Zıt Görüşler (${(c.disagreements || []).length})
      </button>
    </div>
    ${body}
  `;
}

// ============================================================================
// INITIALIZE SESSION ON BOOT
// ============================================================================
window.addEventListener("DOMContentLoaded", async () => {
  try {
    const savedUser = localStorage.getItem(USER_KEY);
    if (savedUser) {
      state.currentUser = JSON.parse(savedUser);
    }
    if (state.token) {
      const res = await apiRequest("./api/auth/me");
      state.currentUser = res.user;
      localStorage.setItem(USER_KEY, JSON.stringify(res.user));
    }
  } catch (_) {}

  navigateTo(state.currentUser ? "discover" : "welcome");
});
