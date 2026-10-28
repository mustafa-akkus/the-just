/**
 * FourFrames — Letterboxd Taste Compatibility Frontend Engine
 * Works both with the local Python API (/api/compatibility) and static hosting (GitHub Pages fallback).
 */

const STORAGE_KEY_USER1 = "fourframes:user1";

let appState = {
  data: null,
  activeTab: "agreements", // 'agreements' | 'disagreements' | 'watchlist' | 'discovery' | 'recent' | 'receipt'
  discoveryMode: "u1_unseen", // 'u1_unseen' | 'u2_unseen' | 'recommendations'
  agreementFilter: "",
  clashSort: "diff", // 'diff' | 'u1' | 'u2'
  pickedMovie: null,
};

function cleanUsername(raw) {
  if (!raw) return "";
  let s = raw.trim();
  const m = s.match(/letterboxd\.com\/([a-zA-Z0-9_-]+)/i);
  if (m) return m[1].toLowerCase();
  return s.replace(/^@+/, "").replace(/\/+$/, "").toLowerCase().replace(/[^a-z0-9_-]/g, "");
}

function escapeHtml(str) {
  if (str === null || str === undefined) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function defaultAvatarSvg(username) {
  const initial = (username || "?").charAt(0).toUpperCase();
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="80" height="80" viewBox="0 0 80 80">
    <rect width="80" height="80" rx="40" fill="#1c2632"/>
    <text x="50%" y="54%" dominant-baseline="middle" text-anchor="middle" fill="#00e054" font-family="Inter, sans-serif" font-weight="700" font-size="32">${initial}</text>
  </svg>`;
  return `data:image/svg+xml;utf8,${encodeURIComponent(svg)}`;
}

// ============================================================================
// BROWSER-SIDE FALLBACK PARSER (For Static Hosting / GitHub Pages)
// ============================================================================
async function fetchViaCorsProxy(targetUrl) {
  const proxies = [
    (u) => `https://api.allorigins.win/raw?url=${encodeURIComponent(u)}`,
    (u) => `https://api.codetabs.com/v1/proxy?quest=${encodeURIComponent(u)}`,
  ];
  for (const buildProxy of proxies) {
    try {
      const resp = await fetch(buildProxy(targetUrl));
      if (resp.ok) {
        return await resp.text();
      }
    } catch (_) {
      // try next proxy
    }
  }
  throw new Error("CORS proxy üzerinden veri alınamadı.");
}

function parsePosterGridDom(containerEl) {
  if (!containerEl) return [];
  const items = [];
  containerEl.querySelectorAll(".poster-cell").forEach((cell) => {
    const a = cell.querySelector("a.poster");
    const img = cell.querySelector("img");
    const cap = cell.querySelector(".poster-caption");
    if (!a || !img) return;
    const caption = cap ? cap.textContent.trim() : "";
    const numMatch = caption.match(/(\d+(?:\.\d+)?)/);
    items.push({
      title: img.getAttribute("alt") || "",
      filmUrl: a.getAttribute("href") || "",
      posterUrl: img.getAttribute("src") || "",
      caption,
      rating: numMatch ? parseFloat(numMatch[1]) : null,
    });
  });
  return items;
}

async function fetchClientSideCompatibility(user1, user2) {
  const compatUrl = `https://letterboxd.tools/tools/compatibility?user1=${encodeURIComponent(user1)}&user2=${encodeURIComponent(user2)}`;
  const htmlText = await fetchViaCorsProxy(compatUrl);
  const parser = new DOMParser();
  const doc = parser.parseFromString(htmlText, "text/html");

  const scoreEl = doc.querySelector(".score-num");
  if (!scoreEl) {
    throw new Error("Kullanıcı verileri bulunamadı veya henüz senkronize edilmedi.");
  }
  const score = parseInt(scoreEl.textContent.trim(), 10) || 50;
  const scoreLabel = doc.querySelector(".score-copy strong")?.textContent.trim() || "Taste Match";
  const scoreSummary = doc.querySelector(".score-copy .muted")?.textContent.trim() || "";

  const users = [];
  doc.querySelectorAll("a.compat-user").forEach((el) => {
    const uname = el.querySelector("strong")?.textContent.trim() || "";
    const statsText = el.querySelector(".muted")?.textContent.trim() || "";
    const watches = parseInt((statsText.match(/(\d+)\s*watches/) || [])[1] || "0", 10);
    const ratings = parseInt((statsText.match(/(\d+)\s*ratings/) || [])[1] || "0", 10);
    const avgRating = parseFloat((statsText.match(/(\d+(?:\.\d+)?)★?\s*avg/) || [])[1] || "0");
    users.push({
      username: uname,
      displayName: uname,
      profileUrl: el.getAttribute("href") || `https://letterboxd.com/${uname}/`,
      avatarUrl: el.querySelector("img")?.getAttribute("src") || "",
      watches,
      ratings,
      avgRating,
      statsText,
      recentStats: {},
      recentFilms: [],
      recentReviews: [],
    });
  });

  const overlapEls = doc.querySelectorAll(".compat-overlap");
  let watchOverlap = { onlyUser1: 0, bothSeen: 0, onlyUser2: 0 };
  let ratingOverlap = { bothRatedCount: 0, user1Higher: 0, agreedExactly: 0, user2Higher: 0, avgDistance: 0.8 };

  if (overlapEls[0]) {
    const bigs = overlapEls[0].querySelectorAll(".big");
    if (bigs.length >= 3) {
      watchOverlap = {
        onlyUser1: parseInt(bigs[0].textContent, 10) || 0,
        bothSeen: parseInt(bigs[1].textContent, 10) || 0,
        onlyUser2: parseInt(bigs[2].textContent, 10) || 0,
      };
    }
  }
  if (overlapEls[1]) {
    const bigs = overlapEls[1].querySelectorAll(".big");
    if (bigs.length >= 3) {
      ratingOverlap.user1Higher = parseInt(bigs[0].textContent, 10) || 0;
      ratingOverlap.agreedExactly = parseInt(bigs[1].textContent, 10) || 0;
      ratingOverlap.user2Higher = parseInt(bigs[2].textContent, 10) || 0;
      ratingOverlap.bothRatedCount =
        ratingOverlap.user1Higher + ratingOverlap.agreedExactly + ratingOverlap.user2Higher;
    }
  }

  let agreements = [];
  let disagreements = [];
  let user1FavouritesUnseen = [];
  let user2FavouritesUnseen = [];
  let sharedWatchlist = [];
  let recommendations = [];

  doc.querySelectorAll("h3").forEach((h3) => {
    const heading = h3.textContent.trim().toLowerCase();
    const nextEl = h3.nextElementSibling;
    if (!nextEl) return;

    if (heading.includes("favourites") && heading.includes("hasn't seen")) {
      if (heading.startsWith(user1.toLowerCase())) {
        user1FavouritesUnseen = parsePosterGridDom(nextEl);
      } else {
        user2FavouritesUnseen = parsePosterGridDom(nextEl);
      }
    } else if (heading.includes("films you agree on")) {
      agreements = parsePosterGridDom(nextEl);
    } else if (heading.includes("disagree most on")) {
      nextEl.querySelectorAll("tbody tr").forEach((tr) => {
        const tds = tr.querySelectorAll("td");
        if (tds.length < 3) return;
        const rawFilm = tds[0].textContent.trim();
        const ym = rawFilm.match(/^(.*?)\s*\((\d{4})\)$/);
        const r1 = parseFloat(tds[1].textContent) || 0;
        const r2 = parseFloat(tds[2].textContent) || 0;
        disagreements.push({
          title: ym ? ym[1].trim() : rawFilm,
          year: ym ? ym[2] : "",
          user1Rating: r1,
          user2Rating: r2,
          diff: Math.round(Math.abs(r1 - r2) * 10) / 10,
        });
      });
    } else if (heading.includes("watchlists")) {
      sharedWatchlist = parsePosterGridDom(nextEl);
    } else if (heading.includes("model thinks you'll both like")) {
      recommendations = parsePosterGridDom(nextEl);
    }
  });

  const avgDist = ratingOverlap.avgDistance || 0.8;
  const ratingHarmony = Math.max(10, Math.min(100, Math.round((1 - avgDist / 3.0) * 100)));
  const exactAgreementRate = Math.max(
    5,
    Math.min(100, Math.round((ratingOverlap.agreedExactly / Math.max(1, ratingOverlap.bothRatedCount)) * 100))
  );

  const icebreakers = [];
  if (agreements.length > 0) {
    icebreakers.push({
      category: "Ortak Favori • Shared Obsession",
      badgeColor: "green",
      title: agreements[0].title,
      prompt: `İkimiz de ${agreements[0].title} (${agreements[0].caption}) konusunda hemfikiriz! Bu filmi senin için özel kılan en unutulmaz sahne hangisiydi?`,
    });
  }
  if (disagreements.length > 0) {
    const c = disagreements[0];
    icebreakers.push({
      category: "Zıt Görüş • Hot Take Münazarası",
      badgeColor: "orange",
      title: `${c.title} (Δ ${c.diff}★)`,
      prompt: `${c.title} filmine @${user1} ${c.user1Rating}★ verirken @${user2} ${c.user2Rating}★ vermiş! Karşı tarafı kendi puanına ikna etmek için tek bir argüman hakkın var.`,
    });
  }
  if (sharedWatchlist.length > 0) {
    icebreakers.push({
      category: "Ortak Watchlist • Movie Night",
      badgeColor: "blue",
      title: sharedWatchlist[0].title,
      prompt: `İkinizin de izleme listesinde ${sharedWatchlist[0].title} dahil ${sharedWatchlist.length} ortak film bekliyor! Bu hafta sonu beraber izleyelim mi?`,
    });
  }

  return {
    source: "client_cors",
    score,
    scoreLabel,
    scoreSummary,
    users,
    watchOverlap,
    ratingOverlap,
    agreements,
    disagreements,
    user1FavouritesUnseen,
    user2FavouritesUnseen,
    sharedWatchlist,
    recommendations,
    subMetrics: {
      ratingHarmony,
      catalogOverlap: 65,
      exactAgreementRate,
    },
    icebreakers,
  };
}

// ============================================================================
// MAIN COMPARE CONTROLLER
// ============================================================================
async function compareUsers(user1Raw, user2Raw, refresh = false) {
  const user1 = cleanUsername(user1Raw);
  const user2 = cleanUsername(user2Raw);

  const statusBox = document.getElementById("statusContainer");
  const resultsBox = document.getElementById("resultsContainer");
  const submitBtn = document.getElementById("submitBtn");
  const shareUrlBtn = document.getElementById("shareUrlBtn");

  if (!user1 || !user2) {
    statusBox.innerHTML = `<div class="status-box error">Lütfen geçerli iki Letterboxd kullanıcı adı girin.</div>`;
    return;
  }
  if (user1 === user2) {
    statusBox.innerHTML = `<div class="status-box error">Karşılaştırma yapmak için iki farklı Letterboxd kullanıcı adı girin.</div>`;
    return;
  }

  document.getElementById("user1Input").value = user1;
  document.getElementById("user2Input").value = user2;
  try {
    localStorage.setItem(STORAGE_KEY_USER1, user1);
  } catch (_) {}

  // Update browser URL without reloading
  const newUrl = `${window.location.pathname}?user1=${encodeURIComponent(user1)}&user2=${encodeURIComponent(user2)}`;
  window.history.replaceState({ user1, user2 }, "", newUrl);

  submitBtn.disabled = true;
  resultsBox.style.display = "none";
  statusBox.innerHTML = `
    <div class="status-box">
      <div class="spinner"></div>
      <p style="font-weight: 600; margin-bottom: 0.25rem;">
        @${escapeHtml(user1)} ve @${escapeHtml(user2)} izleme geçmişleri karşılaştırılıyor...
      </p>
      <p style="font-size: 0.8rem; color: var(--text-muted);">
        Ortak filmler, yıldız puanları, Watchlist kesişimleri ve güncel RSS günlükleri analiz ediliyor.
      </p>
    </div>
  `;

  try {
    let payloadData = null;

    // 1. Try local/backend Python API first
    try {
      const apiUrl = `./api/compatibility?user1=${encodeURIComponent(user1)}&user2=${encodeURIComponent(user2)}&refresh=${refresh ? "1" : "0"}`;
      const resp = await fetch(apiUrl);
      const contentType = resp.headers.get("content-type") || "";
      if (contentType.includes("application/json")) {
        const json = await resp.json();
        if (!resp.ok || !json.ok) {
          throw new Error(json.error || "API hatası");
        }
        payloadData = json.data;
      }
    } catch (apiErr) {
      if (apiErr.message && (apiErr.message.includes("bulunamadı") || apiErr.message.includes("farklı"))) {
        throw apiErr;
      }
      // Fallback to browser-side CORS fetch if static hosting (GitHub Pages)
      payloadData = await fetchClientSideCompatibility(user1, user2);
    }

    appState.data = payloadData;
    appState.pickedMovie = null;
    statusBox.innerHTML = "";
    resultsBox.style.display = "block";
    if (shareUrlBtn) shareUrlBtn.style.display = "inline-flex";
    renderResults();
  } catch (err) {
    statusBox.innerHTML = `
      <div class="status-box error">
        <p style="font-weight: 700; margin-bottom: 0.3rem;">Karşılaştırma Yapılamadı</p>
        <p style="font-size: 0.86rem;">${escapeHtml(err.message || "Beklenmeyen bir hata oluştu.")}</p>
      </div>
    `;
  } finally {
    submitBtn.disabled = false;
  }
}

function handleCompareSubmit(event) {
  event.preventDefault();
  const u1 = document.getElementById("user1Input").value;
  const u2 = document.getElementById("user2Input").value;
  compareUsers(u1, u2, false);
}

function swapUsers() {
  const in1 = document.getElementById("user1Input");
  const in2 = document.getElementById("user2Input");
  const tmp = in1.value;
  in1.value = in2.value;
  in2.value = tmp;
  if (in1.value && in2.value) {
    compareUsers(in1.value, in2.value, false);
  }
}

function runPreset(u1, u2) {
  document.getElementById("user1Input").value = u1;
  document.getElementById("user2Input").value = u2;
  compareUsers(u1, u2, false);
}

// ============================================================================
// RENDER DASHBOARD & TABS
// ============================================================================
function getScoreAccent(score) {
  if (score >= 70) return { color: "#00e054", trTitle: "Ruh İkizi Sinefiller" };
  if (score >= 50) return { color: "#40bcf4", trTitle: "Güçlü Ortak Zemin" };
  return { color: "#ff8000", trTitle: "Zıt Kutuplar & Tartışma" };
}

function renderResults() {
  const d = appState.data;
  if (!d) return;

  const container = document.getElementById("resultsContainer");
  const u1 = d.users[0] || { username: "user1", displayName: "User 1", watches: 0, ratings: 0, avgRating: 0 };
  const u2 = d.users[1] || { username: "user2", displayName: "User 2", watches: 0, ratings: 0, avgRating: 0 };

  const accent = getScoreAccent(d.score);
  const radius = 39;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (Math.max(0, Math.min(100, d.score)) / 100) * circumference;

  // Overlap percentages
  const wo = d.watchOverlap || { onlyUser1: 0, bothSeen: 0, onlyUser2: 0 };
  const totalWatchUnion = Math.max(1, wo.onlyUser1 + wo.bothSeen + wo.onlyUser2);
  const pctOnly1 = Math.max(6, Math.round((wo.onlyUser1 / totalWatchUnion) * 100));
  const pctBoth = Math.max(8, Math.round((wo.bothSeen / totalWatchUnion) * 100));
  const pctOnly2 = Math.max(6, 100 - pctOnly1 - pctBoth);

  // Rating harmony percentages
  const ro = d.ratingOverlap || { bothRatedCount: 0, user1Higher: 0, agreedExactly: 0, user2Higher: 0, avgDistance: 0 };
  const totalRatedUnion = Math.max(1, ro.user1Higher + ro.agreedExactly + ro.user2Higher);
  const rPct1 = Math.max(6, Math.round((ro.user1Higher / totalRatedUnion) * 100));
  const rPctEq = Math.max(8, Math.round((ro.agreedExactly / totalRatedUnion) * 100));
  const rPct2 = Math.max(6, 100 - rPct1 - rPctEq);

  const sub = d.subMetrics || { ratingHarmony: 70, catalogOverlap: 50, exactAgreementRate: 25 };

  container.innerHTML = `
    <!-- Üst Yenileme & Durum Çubuğu -->
    <div class="section-header-inline" style="margin-bottom: 0.85rem;">
      <span class="section-eyebrow">
        ✅ Letterboxd Verileri Senkronize Edildi (${escapeHtml(u1.username)} ⇄ ${escapeHtml(u2.username)})
      </span>
      <button
        type="button"
        class="copy-btn"
        onclick="compareUsers('${escapeHtml(u1.username)}', '${escapeHtml(u2.username)}', true)"
      >
        ↻ Verileri Yeniden Çek
      </button>
    </div>

    <!-- 1. BENTO ÖZET PANOSU -->
    <div class="bento-summary">
      <!-- KART A: Uyum Yüzdesi Halkası -->
      <div class="bento-card col-score">
        <div class="score-card-inner">
          <div class="score-top">
            <div class="score-ring-wrap">
              <svg class="score-ring-svg" viewBox="0 0 96 96">
                <circle class="score-ring-bg" cx="48" cy="48" r="${radius}"></circle>
                <circle
                  class="score-ring-fg"
                  cx="48"
                  cy="48"
                  r="${radius}"
                  style="stroke: ${accent.color}; stroke-dasharray: ${circumference}; stroke-dashoffset: ${offset};"
                ></circle>
              </svg>
              <div class="score-ring-text">
                ${d.score}<small>%</small>
              </div>
            </div>
            <div>
              <span class="score-label-badge" style="color: ${accent.color}">
                ${escapeHtml(d.scoreLabel || accent.trTitle)}
              </span>
              <h2 class="score-headline">${escapeHtml(accent.trTitle)}</h2>
              <p class="score-desc">
                İkiniz de ortak <strong>${wo.bothSeen} film</strong> izlediniz ve ortak puanladığınız filmlerde ortalama sadece <strong>${ro.avgDistance || 0.8}★</strong> fark var.
              </p>
            </div>
          </div>

          <div class="submetrics-list">
            <div class="submetric-row">
              <div class="submetric-head">
                <span>Puanlama Yakınlığı (Rating Harmony)</span>
                <strong>%${sub.ratingHarmony}</strong>
              </div>
              <div class="progress-track">
                <div class="progress-fill" style="width: ${sub.ratingHarmony}%; background: var(--lb-green);"></div>
              </div>
            </div>

            <div class="submetric-row">
              <div class="submetric-head">
                <span>Katalog Kesişim Oranı</span>
                <strong>%${sub.catalogOverlap}</strong>
              </div>
              <div class="progress-track">
                <div class="progress-fill" style="width: ${sub.catalogOverlap}%; background: var(--lb-blue);"></div>
              </div>
            </div>

            <div class="submetric-row">
              <div class="submetric-head">
                <span>Birebir Aynı Puan İsabeti (${ro.agreedExactly} Film)</span>
                <strong>%${sub.exactAgreementRate}</strong>
              </div>
              <div class="progress-track">
                <div class="progress-fill" style="width: ${sub.exactAgreementRate}%; background: var(--lb-orange);"></div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- KART B: Karşılaştırılan Kullanıcı Profilleri -->
      <div class="bento-card col-users">
        <span class="section-eyebrow">Kullanıcı Profilleri</span>
        <div class="users-pair-list">
          ${[u1, u2]
            .map((u, idx) => {
              const avatar = u.avatarUrl || defaultAvatarSvg(u.username);
              const likeRatio = u.recentStats && u.recentStats.likeRatio !== undefined ? u.recentStats.likeRatio : null;
              return `
                <a href="${escapeHtml(u.profileUrl)}" target="_blank" rel="noopener" class="user-mini-card">
                  <img
                    src="${escapeHtml(avatar)}"
                    alt="${escapeHtml(u.username)}"
                    class="user-avatar"
                    onerror="this.src='${defaultAvatarSvg(u.username)}'"
                  />
                  <div class="user-meta">
                    <div class="user-name-row">
                      <strong>${escapeHtml(u.displayName || u.username)}</strong>
                      <span class="user-handle">@${escapeHtml(u.username)}</span>
                    </div>
                    <div class="user-stats-pills">
                      <span class="stat-chip">🎬 ${u.watches} izleme</span>
                      <span class="stat-chip">★ ${u.avgRating.toFixed(2)} ort.</span>
                      <span class="stat-chip">${u.ratings} puan</span>
                      ${likeRatio !== null ? `<span class="stat-chip">❤️ %${likeRatio} beğeni</span>` : ""}
                    </div>
                  </div>
                </a>
              `;
            })
            .join("")}
        </div>
      </div>

      <!-- KART C: İzleme Kesişimi & Puanlama Dengesi -->
      <div class="bento-card col-bars" style="display:flex; flex-direction:column; justify-content:space-between; gap:1rem;">
        <div>
          <div class="submetric-head">
            <span class="section-eyebrow">İzlenen Filmler Kesişimi</span>
            <strong style="font-size:0.78rem;">${wo.bothSeen} Ortak</strong>
          </div>
          <div class="segmented-bar">
            <div class="seg-u1" style="width: ${pctOnly1}%" title="Sadece @${escapeHtml(u1.username)}: ${wo.onlyUser1}"></div>
            <div class="seg-both" style="width: ${pctBoth}%" title="Ortak İzlenen: ${wo.bothSeen}"></div>
            <div class="seg-u2" style="width: ${pctOnly2}%" title="Sadece @${escapeHtml(u2.username)}: ${wo.onlyUser2}"></div>
          </div>
          <div class="overlap-legend">
            <div class="legend-box">
              <span class="big-num" style="color: var(--lb-orange)">${wo.onlyUser1}</span>
              <span class="small-lbl">Sadece @${escapeHtml(u1.username)}</span>
            </div>
            <div class="legend-box">
              <span class="big-num" style="color: var(--lb-green)">${wo.bothSeen}</span>
              <span class="small-lbl">Ortak İzlenen</span>
            </div>
            <div class="legend-box">
              <span class="big-num" style="color: var(--lb-blue)">${wo.onlyUser2}</span>
              <span class="small-lbl">Sadece @${escapeHtml(u2.username)}</span>
            </div>
          </div>
        </div>

        <div>
          <div class="submetric-head">
            <span class="section-eyebrow">Puanlama Dengesi (${ro.bothRatedCount} Ortak Puan)</span>
            <strong style="font-size:0.78rem;">Δ ${ro.avgDistance || 0.8}★</strong>
          </div>
          <div class="segmented-bar">
            <div class="seg-u1" style="width: ${rPct1}%"></div>
            <div class="seg-both" style="width: ${rPctEq}%"></div>
            <div class="seg-u2" style="width: ${rPct2}%"></div>
          </div>
          <div class="overlap-legend">
            <div class="legend-box">
              <span class="big-num">${ro.user1Higher}</span>
              <span class="small-lbl">@${escapeHtml(u1.username)} yüksek</span>
            </div>
            <div class="legend-box">
              <span class="big-num" style="color: var(--lb-green)">${ro.agreedExactly}</span>
              <span class="small-lbl">Tam Aynı Puan</span>
            </div>
            <div class="legend-box">
              <span class="big-num">${ro.user2Higher}</span>
              <span class="small-lbl">@${escapeHtml(u2.username)} yüksek</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 2. BUZ KIRICI SOHBET BAŞLATICILAR (ICEBREAKERS) -->
    ${
      d.icebreakers && d.icebreakers.length > 0
        ? `
      <div class="icebreakers-section">
        <div class="section-header-inline">
          <span class="section-eyebrow">💬 Otomatik Buz Kırıcı Sohbet Başlatıcılar (Ortak Filmlerinizden Üretildi)</span>
        </div>
        <div class="icebreakers-grid">
          ${d.icebreakers
            .map(
              (ib, idx) => `
              <div class="icebreaker-card">
                <div>
                  <span class="ib-badge ${escapeHtml(ib.badgeColor)}">${escapeHtml(ib.category)}</span>
                  <p class="ib-prompt">“${escapeHtml(ib.prompt)}”</p>
                </div>
                <button type="button" class="copy-btn" onclick="copyText(${idx}, this)">
                  📋 Soruyu Kopyala
                </button>
              </div>
            `
            )
            .join("")}
        </div>
      </div>
    `
        : ""
    }

    <!-- 3. DETAY SEKMELERİ (SADE VE DÜZENLİ NAVİGASYON) -->
    <div class="tabs-nav" role="tablist">
      <button
        type="button"
        class="tab-btn ${appState.activeTab === "agreements" ? "active" : ""}"
        onclick="setActiveTab('agreements')"
      >
        <span>🤝 Ortak Sevilenler</span>
        <span class="tab-count">${(d.agreements || []).length}</span>
      </button>

      <button
        type="button"
        class="tab-btn ${appState.activeTab === "disagreements" ? "active" : ""}"
        onclick="setActiveTab('disagreements')"
      >
        <span>⚡ Zıt Görüşler</span>
        <span class="tab-count">${(d.disagreements || []).length}</span>
      </button>

      <button
        type="button"
        class="tab-btn ${appState.activeTab === "watchlist" ? "active" : ""}"
        onclick="setActiveTab('watchlist')"
      >
        <span>🍿 Ortak Watchlist & Seçici</span>
        <span class="tab-count">${(d.sharedWatchlist || []).length}</span>
      </button>

      <button
        type="button"
        class="tab-btn ${appState.activeTab === "discovery" ? "active" : ""}"
        onclick="setActiveTab('discovery')"
      >
        <span>🔭 Kör Noktalar & Öneriler</span>
        <span class="tab-count">${
          (d.user1FavouritesUnseen || []).length +
          (d.user2FavouritesUnseen || []).length +
          (d.recommendations || []).length
        }</span>
      </button>

      <button
        type="button"
        class="tab-btn ${appState.activeTab === "recent" ? "active" : ""}"
        onclick="setActiveTab('recent')"
      >
        <span>🕒 Son İzlenenler (RSS)</span>
      </button>

      <button
        type="button"
        class="tab-btn ${appState.activeTab === "receipt" ? "active" : ""}"
        onclick="setActiveTab('receipt')"
      >
        <span>🧾 Özet Uyum Kartı</span>
      </button>
    </div>

    <!-- AKTİF SEKME İÇERİĞİ -->
    <div id="tabPanelContent"></div>
  `;

  renderActiveTabPanel();
}

function setActiveTab(tabName) {
  appState.activeTab = tabName;
  renderResults();
}

function renderPosterGridHtml(items, emptyMessage) {
  if (!items || items.length === 0) {
    return `<div class="status-box"><p style="color:var(--text-muted);">${escapeHtml(emptyMessage)}</p></div>`;
  }
  return `
    <div class="posters-grid">
      ${items
        .map(
          (item) => `
          <a href="${escapeHtml(item.filmUrl)}" target="_blank" rel="noopener" class="poster-item">
            <div class="poster-img-wrap">
              ${
                item.posterUrl
                  ? `<img loading="lazy" src="${escapeHtml(item.posterUrl)}" alt="${escapeHtml(item.title)}" />`
                  : `<div style="padding:1rem; font-size:0.8rem; color:var(--text-muted);">${escapeHtml(item.title)}</div>`
              }
              ${
                item.caption
                  ? `<span class="poster-rating-pill">${escapeHtml(item.caption)}</span>`
                  : ""
              }
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

function renderActiveTabPanel() {
  const d = appState.data;
  const panel = document.getElementById("tabPanelContent");
  if (!d || !panel) return;

  const u1 = d.users[0] || { username: "user1" };
  const u2 = d.users[1] || { username: "user2" };

  // TAB 1: AGREEMENTS
  if (appState.activeTab === "agreements") {
    const allAgreements = d.agreements || [];
    const q = appState.agreementFilter.trim().toLowerCase();
    const filtered = q
      ? allAgreements.filter((m) => m.title.toLowerCase().includes(q))
      : allAgreements;

    panel.innerHTML = `
      <div class="section-header-inline" style="margin-bottom: 1rem;">
        <div>
          <h3 style="font-size: 1.05rem; font-weight: 700;">İkinizin de Yüksek Puan Verdiği Ortak Favoriler</h3>
          <p style="font-size: 0.82rem; color: var(--text-muted);">
            Hem @${escapeHtml(u1.username)} hem de @${escapeHtml(u2.username)} tarafından sevilen ve tam uzlaşı sağlanan filmler.
          </p>
        </div>
        <input
          type="text"
          placeholder="Film ara..."
          value="${escapeHtml(appState.agreementFilter)}"
          oninput="filterAgreements(this.value)"
          style="background:var(--bg-elevated); border:1px solid var(--border); color:var(--text); padding:0.45rem 0.8rem; border-radius:8px; font-size:0.84rem; outline:none;"
        />
      </div>
      <div id="agreementsGridWrap">
        ${renderPosterGridHtml(filtered, "Bu kriterde ortak favori film bulunamadı.")}
      </div>
    `;
    return;
  }

  // TAB 2: DISAGREEMENTS / CLASHES
  if (appState.activeTab === "disagreements") {
    const list = [...(d.disagreements || [])];
    if (appState.clashSort === "u1") {
      list.sort((a, b) => b.user1Rating - a.user1Rating);
    } else if (appState.clashSort === "u2") {
      list.sort((a, b) => b.user2Rating - a.user2Rating);
    } else {
      list.sort((a, b) => b.diff - a.diff);
    }

    panel.innerHTML = `
      <div class="section-header-inline" style="margin-bottom: 1rem;">
        <div>
          <h3 style="font-size: 1.05rem; font-weight: 700;">En Keskin Puan Ayrılıkları (Hot Takes)</h3>
          <p style="font-size: 0.82rem; color: var(--text-muted);">
            İkinizin de izleyip en farklı yıldızları verdiği, tartışmaya en açık filmler.
          </p>
        </div>
        <div style="display:flex; gap:0.4rem;">
          <button type="button" class="copy-btn" onclick="setClashSort('diff')">Farka Göre Sırala (Δ)</button>
          <button type="button" class="copy-btn" onclick="setClashSort('u1')">@${escapeHtml(u1.username)} Puanı</button>
          <button type="button" class="copy-btn" onclick="setClashSort('u2')">@${escapeHtml(u2.username)} Puanı</button>
        </div>
      </div>

      ${
        list.length === 0
          ? `<div class="status-box"><p style="color:var(--text-muted);">Keskin puan ayrılığı yaşanan film bulunamadı.</p></div>`
          : `
          <div class="clashes-grid">
            ${list
              .map((c) => {
                const w1 = Math.round((c.user1Rating / 5) * 100);
                const w2 = Math.round((c.user2Rating / 5) * 100);
                return `
                  <div class="clash-card">
                    <div class="clash-head">
                      <div>
                        <div class="clash-title">
                          ${escapeHtml(c.title)}
                          ${c.year ? `<span style="color:var(--text-muted); font-weight:500;">(${escapeHtml(c.year)})</span>` : ""}
                        </div>
                      </div>
                      <span class="clash-delta">Δ ${c.diff}★ Fark</span>
                    </div>

                    <div class="clash-bars">
                      <div class="clash-user-row">
                        <span class="clash-user-name">@${escapeHtml(u1.username)}</span>
                        <div class="progress-track">
                          <div class="progress-fill" style="width:${w1}%; background:var(--lb-orange);"></div>
                        </div>
                        <strong style="text-align:right; color:var(--lb-orange);">${c.user1Rating}★</strong>
                      </div>

                      <div class="clash-user-row">
                        <span class="clash-user-name">@${escapeHtml(u2.username)}</span>
                        <div class="progress-track">
                          <div class="progress-fill" style="width:${w2}%; background:var(--lb-blue);"></div>
                        </div>
                        <strong style="text-align:right; color:var(--lb-blue);">${c.user2Rating}★</strong>
                      </div>
                    </div>
                  </div>
                `;
              })
              .join("")}
          </div>
        `
      }
    `;
    return;
  }

  // TAB 3: SHARED WATCHLIST & RANDOM MOVIE NIGHT PICKER
  if (appState.activeTab === "watchlist") {
    const wl = d.sharedWatchlist || [];
    const pool = wl.length > 0 ? wl : d.recommendations || [];
    const picked = appState.pickedMovie;

    panel.innerHTML = `
      <div class="picker-banner">
        <div>
          <span class="ib-badge green">🎲 RASTGELE FİLM GECESİ SEÇİCİ (RANDOM MOVIE PICKER)</span>
          <h3 style="font-size: 1.05rem; font-weight: 800;">Karar Veremiyor Musunuz? Zar Atın!</h3>
          <p style="font-size: 0.83rem; color: var(--text-muted);">
            ${
              wl.length > 0
                ? `İkinizin de Watchlist'inde bulunan ${wl.length} ortak film arasından bu akşam izleyeceğiniz filmi rastgele seçin.`
                : `Ortak Watchlist kesişimi bulunamadı, ancak modelin ikinize önerdiği ${pool.length} film arasından rastgele seçebilirsiniz.`
            }
          </p>
        </div>
        <button type="button" class="submit-btn" onclick="rollRandomMovie()">
          🎲 Rastgele Film Seç
        </button>
      </div>

      ${
        picked
          ? `
          <div class="bento-card" style="margin-bottom: 1.25rem; border-color: var(--lb-green); display:flex; align-items:center; justify-content:space-between; gap:1rem; flex-wrap:wrap;">
            <div style="display:flex; align-items:center; gap:1rem;">
              ${
                picked.posterUrl
                  ? `<img src="${escapeHtml(picked.posterUrl)}" alt="${escapeHtml(picked.title)}" style="width:64px; height:96px; object-fit:cover; border-radius:8px;" />`
                  : ""
              }
              <div>
                <span class="ib-badge green">✨ BU AKŞAMIN SEÇİMİ</span>
                <h4 style="font-size: 1.2rem; font-weight: 800;">${escapeHtml(picked.title)}</h4>
                <p style="font-size: 0.82rem; color: var(--text-muted);">İkinizin ortak listesinden rastgele seçildi.</p>
              </div>
            </div>
            <a href="${escapeHtml(picked.filmUrl)}" target="_blank" rel="noopener" class="ghost-link">
              Letterboxd'da Aç ↗
            </a>
          </div>
        `
          : ""
      }

      <div class="section-header-inline">
        <h4 style="font-size: 0.95rem; font-weight: 700;">
          Ortak İzleme Listesi (${wl.length} Film)
        </h4>
      </div>
      ${renderPosterGridHtml(
        wl,
        "İki kullanıcının Watchlist'inde henüz ortak bir film bulunmuyor. 'Kör Noktalar & Öneriler' sekmesindeki ortak önerilere göz atabilirsiniz!"
      )}
    `;
    return;
  }

  // TAB 4: BLIND SPOTS & JOINT RECOMMENDATIONS
  if (appState.activeTab === "discovery") {
    const mode = appState.discoveryMode;
    let currentItems = [];
    let desc = "";

    if (mode === "u1_unseen") {
      currentItems = d.user1FavouritesUnseen || [];
      desc = `@${u1.username} tarafından çok yüksek puanlanan ama @${u2.username} tarafından henüz izlenmemiş filmler.`;
    } else if (mode === "u2_unseen") {
      currentItems = d.user2FavouritesUnseen || [];
      desc = `@${u2.username} tarafından çok yüksek puanlanan ama @${u1.username} tarafından henüz izlenmemiş filmler.`;
    } else {
      currentItems = d.recommendations || [];
      desc = `İkinizin puanlama profiline göre her ikinizin de seveceği tahmin edilen ortak film önerileri.`;
    }

    panel.innerHTML = `
      <div class="section-header-inline" style="margin-bottom: 1rem;">
        <div style="display:flex; gap:0.5rem; flex-wrap:wrap;">
          <button
            type="button"
            class="tab-btn ${mode === "u1_unseen" ? "active" : ""}"
            onclick="setDiscoveryMode('u1_unseen')"
          >
            🌟 @${escapeHtml(u1.username)} Favorileri (@${escapeHtml(u2.username)} İzlemedi)
          </button>
          <button
            type="button"
            class="tab-btn ${mode === "u2_unseen" ? "active" : ""}"
            onclick="setDiscoveryMode('u2_unseen')"
          >
            🌟 @${escapeHtml(u2.username)} Favorileri (@${escapeHtml(u1.username)} İzlemedi)
          </button>
          <button
            type="button"
            class="tab-btn ${mode === "recommendations" ? "active" : ""}"
            onclick="setDiscoveryMode('recommendations')"
          >
            🤖 İkinizin de Seveceği Öneriler
          </button>
        </div>
      </div>
      <p style="font-size: 0.84rem; color: var(--text-muted); margin-bottom: 1rem;">${escapeHtml(desc)}</p>
      ${renderPosterGridHtml(currentItems, "Bu kategoride film bulunamadı.")}
    `;
    return;
  }

  // TAB 5: LIVE RSS DIARY & REVIEWS
  if (appState.activeTab === "recent") {
    panel.innerHTML = `
      <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 1.25rem;">
        ${[u1, u2]
          .map(
            (u) => `
            <div class="bento-card">
              <div class="section-header-inline" style="margin-bottom: 0.85rem;">
                <div>
                  <h4 style="font-size: 1rem; font-weight: 800;">@${escapeHtml(u.username)} • Son Günlük (RSS)</h4>
                  <p style="font-size: 0.78rem; color: var(--text-muted);">
                    Letterboxd RSS akışından çekilen son izlenen filmler ve incelemeler
                  </p>
                </div>
              </div>

              ${
                !u.recentFilms || u.recentFilms.length === 0
                  ? `<p style="font-size: 0.84rem; color: var(--text-muted);">Güncel RSS kaydı bulunamadı.</p>`
                  : `
                  <div style="display:flex; flex-direction:column; gap:0.65rem;">
                    ${u.recentFilms
                      .slice(0, 8)
                      .map(
                        (f) => `
                        <a
                          href="${escapeHtml(f.logUrl || f.filmUrl)}"
                          target="_blank"
                          rel="noopener"
                          style="display:flex; gap:0.75rem; padding:0.6rem; border-radius:10px; background:var(--bg); border:1px solid var(--border-subtle); text-decoration:none; color:var(--text);"
                        >
                          ${
                            f.posterUrl
                              ? `<img src="${escapeHtml(f.posterUrl)}" alt="${escapeHtml(f.title)}" style="width:44px; height:66px; object-fit:cover; border-radius:6px; flex-shrink:0;" />`
                              : ""
                          }
                          <div style="min-width:0; flex:1;">
                            <div style="display:flex; justify-content:space-between; gap:0.5rem;">
                              <strong style="font-size:0.86rem; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">
                                ${escapeHtml(f.title)} ${f.year ? `(${escapeHtml(f.year)})` : ""}
                              </strong>
                              <span style="font-size:0.8rem; font-weight:700; color:var(--lb-green); flex-shrink:0;">
                                ${f.rating ? `★${f.rating}` : ""} ${f.liked ? "❤️" : ""}
                              </span>
                            </div>
                            <span style="font-size:0.75rem; color:var(--text-dim); display:block; margin-top:2px;">
                              📅 ${escapeHtml(f.watchedDate || "Yakın zamanda")}
                            </span>
                            ${
                              f.review
                                ? `<p style="font-size:0.78rem; color:var(--text-muted); margin-top:4px; display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden;">“${escapeHtml(f.review)}”</p>`
                                : ""
                            }
                          </div>
                        </a>
                      `
                      )
                      .join("")}
                  </div>
                `
              }
            </div>
          `
          )
          .join("")}
      </div>
    `;
    return;
  }

  // TAB 6: SHAREABLE RECEIPT CARD
  if (appState.activeTab === "receipt") {
    const topAgreements = (d.agreements || []).slice(0, 4);
    const topClash = (d.disagreements || [])[0];
    const movieNight = (d.sharedWatchlist || [])[0] || (d.recommendations || [])[0];

    panel.innerHTML = `
      <div style="max-width: 520px; margin: 0 auto;">
        <div class="bento-card" style="padding: 1.75rem; border-width: 2px;">
          <div class="top-accent-bar" style="border-radius:999px; margin-bottom:1.25rem;"></div>
          <div style="display:flex; justify-content:space-between; align-items:flex-start; border-bottom:1px dashed var(--border); padding-bottom:1rem; margin-bottom:1rem;">
            <div>
              <span style="font-family:monospace; font-size:0.75rem; color:var(--text-muted);">FOURFRAMES TASTE RECEIPT</span>
              <h3 style="font-size:1.25rem; font-weight:800; margin-top:2px;">
                @${escapeHtml(u1.username)} ⇄ @${escapeHtml(u2.username)}
              </h3>
              <span style="font-size:0.8rem; color:var(--text-muted);">${escapeHtml(d.scoreLabel || "Taste Compatibility")}</span>
            </div>
            <div style="text-align:right;">
              <span style="font-size:2rem; font-weight:900; color:var(--lb-green); line-height:1;">%${d.score}</span>
              <span style="display:block; font-family:monospace; font-size:0.75rem; color:var(--text-muted);">UYUM SKORU</span>
            </div>
          </div>

          <div style="display:grid; grid-template-columns:repeat(4, 1fr); gap:0.5rem; margin-bottom:1.1rem;">
            ${topAgreements
              .map(
                (m) => `
                <div style="aspect-ratio:2/3; border-radius:8px; overflow:hidden; background:var(--bg); border:1px solid var(--border);">
                  ${
                    m.posterUrl
                      ? `<img src="${escapeHtml(m.posterUrl)}" alt="${escapeHtml(m.title)}" style="width:100%; height:100%; object-fit:cover;" />`
                      : `<div style="padding:6px; font-size:0.75rem;">${escapeHtml(m.title)}</div>`
                  }
                </div>
              `
              )
              .join("")}
          </div>

          <div style="font-family:monospace; font-size:0.8rem; display:flex; flex-direction:column; gap:0.45rem; border-top:1px dashed var(--border); border-bottom:1px dashed var(--border); padding:0.9rem 0; margin-bottom:1rem;">
            <div style="display:flex; justify-content:space-between;">
              <span style="color:var(--text-muted);">ORTAK İZLENEN FİLM:</span>
              <strong>${d.watchOverlap?.bothSeen || 0} Film</strong>
            </div>
            <div style="display:flex; justify-content:space-between;">
              <span style="color:var(--text-muted);">ORTALAMA PUAN FARKI:</span>
              <strong style="color:var(--lb-green);">${d.ratingOverlap?.avgDistance || 0.8}★</strong>
            </div>
            ${
              topClash
                ? `
              <div style="display:flex; justify-content:space-between;">
                <span style="color:var(--text-muted);">EN BÜYÜK AYRILIK:</span>
                <strong style="color:var(--lb-orange);">${escapeHtml(topClash.title)} (${topClash.user1Rating}★ vs ${topClash.user2Rating}★)</strong>
              </div>
            `
                : ""
            }
            ${
              movieNight
                ? `
              <div style="display:flex; justify-content:space-between;">
                <span style="color:var(--text-muted);">SIRADAKİ FİLM GECESİ:</span>
                <strong style="color:var(--lb-blue);">${escapeHtml(movieNight.title)}</strong>
              </div>
            `
                : ""
            }
          </div>

          <div style="display:flex; gap:0.6rem; justify-content:space-between; flex-wrap:wrap;">
            <button type="button" class="submit-btn" style="flex:1;" onclick="copySummaryReceipt(this)">
              📋 Özeti Metin Olarak Kopyala
            </button>
            <button type="button" class="copy-btn" style="padding:0.6rem 1rem;" onclick="copyShareUrl(this)">
              🔗 Linki Kopyala
            </button>
          </div>
        </div>
      </div>
    `;
  }
}

// ============================================================================
// UI HELPERS & INTERACTIONS
// ============================================================================
function filterAgreements(val) {
  appState.agreementFilter = val;
  const d = appState.data;
  if (!d) return;
  const q = val.trim().toLowerCase();
  const filtered = q
    ? (d.agreements || []).filter((m) => m.title.toLowerCase().includes(q))
    : d.agreements || [];
  const wrap = document.getElementById("agreementsGridWrap");
  if (wrap) {
    wrap.innerHTML = renderPosterGridHtml(filtered, "Bu kriterde ortak favori film bulunamadı.");
  }
}

function setClashSort(sortKey) {
  appState.clashSort = sortKey;
  renderActiveTabPanel();
}

function setDiscoveryMode(mode) {
  appState.discoveryMode = mode;
  renderActiveTabPanel();
}

function rollRandomMovie() {
  const d = appState.data;
  if (!d) return;
  const wl = d.sharedWatchlist || [];
  const pool = wl.length > 0 ? wl : d.recommendations || [];
  if (pool.length === 0) return;
  const idx = Math.floor(Math.random() * pool.length);
  appState.pickedMovie = pool[idx];
  renderActiveTabPanel();
}

function copyText(ibIdx, btnEl) {
  const d = appState.data;
  if (!d || !d.icebreakers || !d.icebreakers[ibIdx]) return;
  const text = d.icebreakers[ibIdx].prompt;
  navigator.clipboard.writeText(text).then(() => {
    const old = btnEl.textContent;
    btnEl.textContent = "✅ Kopyalandı!";
    setTimeout(() => {
      btnEl.textContent = old;
    }, 1800);
  });
}

function copyShareUrl(btnEl) {
  navigator.clipboard.writeText(window.location.href).then(() => {
    const target = btnEl || document.getElementById("shareUrlBtn");
    if (target) {
      const old = target.textContent;
      target.textContent = "✅ Link Kopyalandı!";
      setTimeout(() => {
        target.textContent = old;
      }, 1800);
    }
  });
}

function copySummaryReceipt(btnEl) {
  const d = appState.data;
  if (!d) return;
  const u1 = d.users[0]?.username || "user1";
  const u2 = d.users[1]?.username || "user2";
  const topAgree = (d.agreements || []).slice(0, 3).map((m) => m.title).join(", ");
  const topClash = (d.disagreements || [])[0];
  const text = [
    `🎬 FourFrames — Letterboxd Zevk Uyumu`,
    `@${u1} ⇄ @${u2} • %${d.score} Uyum`,
    `• Ortak İzlenen: ${d.watchOverlap?.bothSeen || 0} film (Ort. fark: ${d.ratingOverlap?.avgDistance || 0.8}★)`,
    topAgree ? `• Ortak Favoriler: ${topAgree}` : "",
    topClash ? `• En Büyük Ayrılık: ${topClash.title} (${topClash.user1Rating}★ vs ${topClash.user2Rating}★)` : "",
  ]
    .filter(Boolean)
    .join("\n");

  navigator.clipboard.writeText(text).then(() => {
    const old = btnEl.textContent;
    btnEl.textContent = "✅ Özet Panoya Kopyalandı!";
    setTimeout(() => {
      btnEl.textContent = old;
    }, 1800);
  });
}

// ============================================================================
// INITIALIZE ON PAGE LOAD
// ============================================================================
window.addEventListener("DOMContentLoaded", () => {
  const params = new URLSearchParams(window.location.search);
  const qUser1 = params.get("user1");
  const qUser2 = params.get("user2");

  try {
    const savedUser1 = localStorage.getItem(STORAGE_KEY_USER1);
    if (savedUser1 && !qUser1) {
      document.getElementById("user1Input").value = savedUser1;
    }
  } catch (_) {}

  if (qUser1 && qUser2) {
    compareUsers(qUser1, qUser2, false);
  } else {
    // Load a live comparison by default so the user sees real Letterboxd data immediately!
    runPreset("dtquandt", "karsten");
  }
});
