"""
Turkish NLP Preprocessor, Language Detector, Clause Splitter, and Assisted Pre-Annotator
for Film Reviews on Letterboxd.
"""

import re

ASPECT_DIMENSIONS = [
    {
        "key": "sinematografi",
        "label": "Sinematografi & Görsellik",
        "en_label": "Cinematography & Visuals",
        "keywords": [
            "görüntü yönetimi", "görüntü", "sinematografi", "kamera", "kadraj", "renk",
            "palet", "ışık", "ışıklandırma", "görsel", "çekim", "plan sekans", "sekans",
            "lens", "estetik", "efekt", "mekan", "kostüm", "prodüksiyon", "tasarım", "tablo"
        ],
    },
    {
        "key": "senaryo",
        "label": "Senaryo & Hikaye",
        "en_label": "Screenplay & Story",
        "keywords": [
            "senaryo", "hikaye", "öykü", "diyalog", "konu", "olay örgüsü", "metin",
            "final", "sonu", "twist", "sürpriz", "alt metin", "anlatı", "yazım",
            "dramaturji", "mantık", "boşluk", "klişe", "özgün", "derinlik", "mesaj"
        ],
    },
    {
        "key": "tempo",
        "label": "Kurgu & Tempo",
        "en_label": "Editing & Pacing",
        "keywords": [
            "tempo", "kurgu", "montaj", "akıcı", "akıcılık", "ritim", "süre",
            "yavaş", "sıkıcı", "sıktı", "sarkıyor", "sarktı", "uzun", "kopuk",
            "geçiş", "dinamik", "soluksuz", "su gibi", "yorucu", "ağır"
        ],
    },
    {
        "key": "oyunculuk",
        "label": "Oyunculuk & Karakter",
        "en_label": "Acting & Characters",
        "keywords": [
            "oyunculuk", "oyuncu", "performans", "karakter", "başrol", "kadro",
            "cast", "rol", "kimya", "canlandırma", "jest", "mimik", "empati",
            "yan rol", "oynamış", "döktürmüş"
        ],
    },
    {
        "key": "muzik_atmosfer",
        "label": "Müzik, Ses & Atmosfer",
        "en_label": "Music, Sound & Atmosphere",
        "keywords": [
            "müzik", "soundtrack", "ses", "atmosfer", "ambiyans", "ruh", "his",
            "duygu", "gerilim", "melankoli", "melankolik", "karanlık", "dünya",
            "büyüleyici", "hipnotize", "şarkı", "beste"
        ],
    },
    {
        "key": "yonetmenlik",
        "label": "Yönetmenlik & Reji",
        "en_label": "Direction & Style",
        "keywords": [
            "yönetmen", "reji", "mizansen", "üslup", "vizyon", "anlatım dili",
            "sinema dili", "imza", "tarz", "bakış açısı", "auteur", "çekmiş"
        ],
    },
]

ASPECT_KEYS = [d["key"] for d in ASPECT_DIMENSIONS]

TURKISH_CHARS = set("çğıöşüÇĞİÖŞÜ")

TURKISH_STOP_AND_COMMON = {
    "bir", "ve", "ama", "fakat", "ancak", "çok", "için", "bu", "şu", "o",
    "film", "filmi", "filmin", "filmde", "sahne", "sahneler", "bence", "kadar",
    "gibi", "daha", "olan", "olarak", "değil", "güzel", "iyi", "kötü", "harika",
    "muazzam", "yönetmen", "oyunculuk", "senaryo", "kurgu", "hikaye", "gerçekten",
    "kesinlikle", "biraz", "hiç", "bile", "hem", "ya", "da", "de", "ki", "mi",
    "en", "son", "ilk", "uzun", "kısa", "rağmen", "olsa", "olmuş", "olmamış",
    "izlediğim", "izlerken", "insan", "zaman", "hayat", "dünya", "kendi", "şey"
}

POSITIVE_ROOTS = [
    "iyi", "güzel", "harika", "muazzam", "muhteşem", "kusursuz", "başarılı",
    "etkileyici", "büyüleyici", "şahane", "mükemmel", "enfes", "sağlam",
    "güçlü", "doğal", "akıcı", "özgün", "derin", "sevdim", "bayıldım",
    "hayran", "başyapıt", "lezzetli", "fevkalade", "tutkulu", "inandırıcı",
    "döktürmüş", "kurtarmış", "taşımış", "zirve", "keyifli", "sürükleyici",
    "başarı", "etkiledi", "vurucu", "çarpıcı", "ustaca", "şiir gibi", "su gibi",
    "etkileyiciydi", "harikaydı", "güçlüydü", "iyiydi", "başarılıydı"
]

NEGATIVE_ROOTS = [
    "kötü", "zayıf", "berbat", "sıkıcı", "sıktı", "kopuk", "koptu", "kopmuş",
    "yetersiz", "yapay", "klişe", "boş", "sığ", "yorucu", "olmamış", "başarısız",
    "vasat", "dağılmış", "dağıldı", "sarkıyor", "sarktı", "sarkmış", "gereksiz",
    "uzun", "ağır", "yavaş", "yavaştı", "bayat", "inandırıcı değil", "sevmedim",
    "beğenmedim", "hayal kırıklığı", "yazık", "karton", "tekdüze", "monoton",
    "sorunlu", "eksik", "kusurlu", "zorlama", "saçma", "tutarsız", "havada",
    "baydı", "bunaltıcı", "sarmadı"
]

CONTRAST_SPLIT_REGEX = re.compile(
    r"\b(?:ama|fakat|lakin|ancak|buna rağmen|rağmen|olsa da|haricinde|dışında|ne var ki|öte yandan|diğer yandan)\b|[;.]",
    flags=re.IGNORECASE,
)


def tr_lower(text: str) -> str:
    """Proper Turkish lowercase conversion (I -> ı, İ -> i)."""
    if not text:
        return ""
    return text.replace("İ", "i").replace("I", "ı").lower()


def is_turkish_review(text: str) -> bool:
    """
    Determine whether a Letterboxd review text is genuinely written in Turkish.
    """
    if not text or len(text.strip()) < 18:
        return False

    lowered = tr_lower(text)
    words = re.findall(r"[a-zçğıöşü]+", lowered)
    if len(words) < 3:
        return False

    tr_char_count = sum(1 for ch in text if ch in TURKISH_CHARS)
    tr_word_hits = sum(1 for w in words if w in TURKISH_STOP_AND_COMMON)

    en_stopwords = {"the", "and", "was", "with", "that", "this", "from", "have", "movie", "really", "about", "just"}
    en_hits = sum(1 for w in words if w in en_stopwords)
    if en_hits > tr_word_hits and en_hits >= 2:
        return False

    if tr_char_count >= 2 and tr_word_hits >= 1:
        return True
    if tr_word_hits >= 2:
        return True
    if tr_char_count >= 4:
        return True
    return False


def split_into_clauses(text: str) -> list[str]:
    """
    Split a Turkish review into contrast/sentence clauses so that praise and criticism
    in compound sentences ('görüntü harika ama senaryo zayıf') are isolated accurately.
    """
    if not text:
        return []
    raw_parts = CONTRAST_SPLIT_REGEX.split(text)
    clauses = [p.strip(" ,-\n\t") for p in raw_parts if len(p.strip(" ,-\n\t")) >= 4]
    return clauses if clauses else [text.strip()]


def preprocess_turkish_text(text: str) -> str:
    """
    Normalize Turkish text and bind negation markers ('kötü değil' -> 'kötü_degil')
    for feature extraction and neural tokenization.
    """
    lowered = tr_lower(text)
    lowered = re.sub(r"https?://\S+", " ", lowered)
    tokens = re.findall(r"[a-zçğıöşü0-9]+", lowered)

    processed = []
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if i + 1 < len(tokens) and tokens[i + 1] in {"değil", "degil", "yok"}:
            processed.append(f"{tok}_degil")
            i += 2
        else:
            processed.append(tok)
            i += 1
    return " ".join(processed)


def score_clause_polarity(clause_lower: str, star_rating: float | None = None) -> int:
    """
    Compute sentiment polarity (-1, 0, +1) for a single Turkish clause.
    """
    pos_score = 0
    neg_score = 0

    if re.search(r"\b(kötü|fena|sıkıcı|uzun|yorucu|vasat)\s+değil", clause_lower):
        pos_score += 2
    if re.search(r"\b(iyi|güzel|başarılı|etkileyici|inandırıcı|yeterli)\s+değil", clause_lower):
        neg_score += 2

    if re.search(r"\b(sıkmıyor|sıkmadı|baymıyor|bunaltmıyor)\b", clause_lower):
        pos_score += 2
    if re.search(r"\b(olmamış|kurtarmıyor|yetmemiş|yetmiyor|geçmiyor|sarmadı|etkilemedi)\b", clause_lower):
        neg_score += 2

    for p_root in POSITIVE_ROOTS:
        if p_root in clause_lower and f"{p_root} değil" not in clause_lower:
            pos_score += 1

    for n_root in NEGATIVE_ROOTS:
        if n_root in clause_lower and f"{n_root} değil" not in clause_lower:
            neg_score += 1

    if pos_score > neg_score:
        return 1
    if neg_score > pos_score:
        return -1

    if star_rating is not None:
        if star_rating >= 3.5:
            return 1
        if star_rating <= 2.5:
            return -1
    return 1


def suggest_aspect_labels(review_text: str, star_rating: float | None = None) -> dict:
    """
    Assisted Pre-Annotator:
    Splits a Turkish review into clauses, detects which of the 6 cinematic dimensions
    are discussed in each clause, and assigns suggested (-1, 0, +1) labels + evidence spans.
    """
    clauses = split_into_clauses(review_text)
    labels = {k: 0 for k in ASPECT_KEYS}
    evidence = {k: [] for k in ASPECT_KEYS}

    for clause in clauses:
        c_low = tr_lower(clause)
        clause_pol = score_clause_polarity(c_low, star_rating)

        for dim in ASPECT_DIMENSIONS:
            key = dim["key"]
            matched_kw = [kw for kw in dim["keywords"] if kw in c_low]
            if matched_kw:
                labels[key] = clause_pol
                evidence[key].append(
                    {
                        "clause": clause,
                        "keywords": matched_kw,
                        "polarity": clause_pol,
                    }
                )

    return {
        "clauses": clauses,
        "labels": labels,
        "evidence": evidence,
    }
