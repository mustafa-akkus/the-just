"""
Two-Stage Turkish Aspect-Based Sentiment Analysis (ABSA) Models:
- Stage 1: Scikit-Learn Word + Character N-Gram TF-IDF + Multi-Aspect Classifiers
- Stage 2: PyTorch Bidirectional LSTM + Multi-Aspect Attention Network
"""

import json
import pickle
import sqlite3
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score
from sklearn.pipeline import FeatureUnion

from nlp.preprocessor import (
    ASPECT_DIMENSIONS,
    ASPECT_KEYS,
    NEGATIVE_ROOTS,
    POSITIVE_ROOTS,
    preprocess_turkish_text,
    split_into_clauses,
    suggest_aspect_labels,
)

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "the_just.db"
MODELS_DIR = BASE_DIR / "models"
SKLEARN_MODEL_PATH = MODELS_DIR / "sklearn_tr_absa.pkl"
PYTORCH_MODEL_PATH = MODELS_DIR / "pytorch_tr_absa.pt"

CLASS_TO_IDX = {-1: 0, 0: 1, 1: 2}
IDX_TO_CLASS = {0: -1, 1: 0, 2: 1}


def refresh_unverified_suggestions_in_db():
    """Re-run clause pre-annotator on unverified reviews so any lexicon improvements apply."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT id, review_text, rating FROM turkish_reviews WHERE is_verified = 0")
    rows = cur.fetchall()
    for r in rows:
        sugg = suggest_aspect_labels(r["review_text"], r["rating"])
        cur.execute(
            "UPDATE turkish_reviews SET clauses_json = ?, labels_json = ?, evidence_json = ? WHERE id = ?",
            (
                json.dumps(sugg["clauses"], ensure_ascii=False),
                json.dumps(sugg["labels"], ensure_ascii=False),
                json.dumps(sugg["evidence"], ensure_ascii=False),
                r["id"],
            ),
        )
    conn.commit()
    conn.close()


def load_training_samples_from_db() -> tuple[list[str], dict[str, list[int]], int, int]:
    """
    Load all Turkish reviews and their 6-dimension labels from SQLite.
    Extracts both full reviews and localized clause instances for multi-aspect training.
    """
    refresh_unverified_suggestions_in_db()
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM turkish_reviews ORDER BY is_verified DESC, id ASC")
    rows = cur.fetchall()
    conn.close()

    texts = []
    y_dict = {k: [] for k in ASPECT_KEYS}
    verified_count = 0
    total_reviews = len(rows)

    for r in rows:
        if r["is_verified"]:
            verified_count += 1
        rev_text = r["review_text"]
        labels = json.loads(r["labels_json"] or "{}")
        evidence = json.loads(r["evidence_json"] or "{}")

        texts.append(preprocess_turkish_text(rev_text))
        for k in ASPECT_KEYS:
            val = max(-1, min(1, int(labels.get(k, 0))))
            y_dict[k].append(val)

        # Include clause-level instances
        for k in ASPECT_KEYS:
            ev_list = evidence.get(k) or []
            for ev in ev_list:
                clause_txt = ev.get("clause", "")
                pol = int(ev.get("polarity", labels.get(k, 0)))
                if len(clause_txt) >= 5 and pol in (-1, 1):
                    texts.append(preprocess_turkish_text(clause_txt))
                    for other_k in ASPECT_KEYS:
                        y_dict[other_k].append(pol if other_k == k else 0)

    # Include targeted Turkish domain contrast clauses per aspect so every dimension has balanced +/- anchors
    for dim in ASPECT_DIMENSIONS:
        k = dim["key"]
        kws = dim["keywords"]
        for idx_p, pos_adj in enumerate(POSITIVE_ROOTS):
            kw = kws[idx_p % len(kws)]
            texts.append(preprocess_turkish_text(f"{kw} çok {pos_adj}"))
            for other_k in ASPECT_KEYS:
                y_dict[other_k].append(1 if other_k == k else 0)
        for idx_n, neg_adj in enumerate(NEGATIVE_ROOTS):
            kw = kws[idx_n % len(kws)]
            texts.append(preprocess_turkish_text(f"{kw} çok {neg_adj}"))
            for other_k in ASPECT_KEYS:
                y_dict[other_k].append(-1 if other_k == k else 0)

    return texts, y_dict, total_reviews, verified_count


# ============================================================================
# STAGE 1: SCIKIT-LEARN WORD + CHAR N-GRAM TF-IDF MODEL
# ============================================================================
def train_sklearn_model() -> dict:
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    texts, y_dict, total_reviews, verified_count = load_training_samples_from_db()

    if total_reviews == 0:
        raise ValueError("Modeli eğitmek için önce Letterboxd üzerinden Türkçe yorum toplayın.")

    vectorizer = FeatureUnion(
        [
            (
                "word_tfidf",
                TfidfVectorizer(
                    analyzer="word",
                    ngram_range=(1, 2),
                    max_features=5000,
                    sublinear_tf=True,
                ),
            ),
            (
                "char_tfidf",
                TfidfVectorizer(
                    analyzer="char_wb",
                    ngram_range=(3, 5),
                    max_features=7000,
                    sublinear_tf=True,
                ),
            ),
        ]
    )

    X = vectorizer.fit_transform(texts)
    classifiers = {}
    metrics = {}

    for k in ASPECT_KEYS:
        y = np.array(y_dict[k], dtype=int)
        clf = LogisticRegression(C=3.0, class_weight="balanced", max_iter=600)
        clf.fit(X, y)
        classifiers[k] = clf

        preds = clf.predict(X)
        acc = float(accuracy_score(y, preds))
        f1 = float(f1_score(y, preds, average="macro", zero_division=0))
        metrics[k] = {
            "accuracy": round(acc * 100, 1),
            "macroF1": round(f1 * 100, 1),
            "positiveSamples": int(np.sum(y == 1)),
            "negativeSamples": int(np.sum(y == -1)),
        }

    bundle = {
        "vectorizer": vectorizer,
        "classifiers": classifiers,
        "metrics": metrics,
        "totalReviews": total_reviews,
        "sampleCount": len(texts),
        "verifiedCount": verified_count,
    }

    with open(SKLEARN_MODEL_PATH, "wb") as f:
        pickle.dump(bundle, f)

    return {
        "stage": "Stage 1: Scikit-Learn (Word + Char N-Gram TF-IDF)",
        "totalReviews": total_reviews,
        "sampleCount": len(texts),
        "verifiedCount": verified_count,
        "metrics": metrics,
    }


def predict_sklearn(review_text: str) -> dict | None:
    if not SKLEARN_MODEL_PATH.exists():
        return None

    with open(SKLEARN_MODEL_PATH, "rb") as f:
        bundle = pickle.load(f)

    vectorizer = bundle["vectorizer"]
    classifiers = bundle["classifiers"]

    clauses = split_into_clauses(review_text) or [review_text]
    clause_clean = [preprocess_turkish_text(c) for c in clauses]
    X_clauses = vectorizer.transform(clause_clean)

    results = {}
    for dim in ASPECT_DIMENSIONS:
        k = dim["key"]
        clf = classifiers[k]
        classes = list(clf.classes_)

        clause_probs = clf.predict_proba(X_clauses)
        clause_preds = clf.predict(X_clauses)

        chosen_label = 0
        chosen_conf = 0.0
        best_clause = ""

        for idx, pred_cls in enumerate(clause_preds):
            cls_idx = classes.index(pred_cls)
            prob = float(clause_probs[idx][cls_idx])
            if int(pred_cls) != 0 and prob > chosen_conf:
                chosen_label = int(pred_cls)
                chosen_conf = prob
                best_clause = clauses[idx]

        if chosen_label == 0:
            # Take average neutral confidence across clauses
            zero_idx = classes.index(0) if 0 in classes else 0
            chosen_conf = float(np.mean(clause_probs[:, zero_idx]))

        results[k] = {
            "label": chosen_label,
            "confidence": round(chosen_conf * 100, 1),
            "score": round(chosen_label * chosen_conf, 2),
            "matchedClause": best_clause,
        }

    return results


# ============================================================================
# STAGE 2: PYTORCH BILSTM + MULTI-ASPECT ATTENTION NETWORK
# ============================================================================
class TurkishBiLSTMAttentionABSA(nn.Module):
    def __init__(self, vocab_size: int, embed_dim: int = 64, hidden_dim: int = 64, num_aspects: int = 6):
        super().__init__()
        self.embedding = nn.Embedding(vocab_size, embed_dim, padding_idx=0)
        self.dropout = nn.Dropout(0.15)
        self.lstm = nn.LSTM(
            embed_dim,
            hidden_dim,
            num_layers=1,
            batch_first=True,
            bidirectional=True,
        )
        self.aspect_queries = nn.Parameter(torch.randn(num_aspects, hidden_dim * 2) * 0.1)
        self.classifiers = nn.ModuleList(
            [nn.Linear(hidden_dim * 2, 3) for _ in range(num_aspects)]
        )

    def forward(self, input_ids: torch.Tensor, mask: torch.Tensor):
        emb = self.dropout(self.embedding(input_ids))
        lstm_out, _ = self.lstm(emb)

        logits_list = []
        attn_weights_list = []

        for a_idx in range(len(self.classifiers)):
            query = self.aspect_queries[a_idx]
            scores = torch.matmul(lstm_out, query)
            scores = scores.masked_fill(mask == 0, -1e9)
            attn_weights = torch.softmax(scores, dim=-1)
            context = torch.bmm(attn_weights.unsqueeze(1), lstm_out).squeeze(1)
            logits = self.classifiers[a_idx](self.dropout(context))

            logits_list.append(logits)
            attn_weights_list.append(attn_weights)

        return logits_list, attn_weights_list


def tokenize_with_stems(text: str) -> list[str]:
    norm = preprocess_turkish_text(text)
    words = norm.split()
    tokens = []
    for w in words:
        tokens.append(w)
        if len(w) >= 5:
            tokens.append(f"#{w[:5]}")
    return tokens


def build_vocab(texts: list[str], max_vocab: int = 4500) -> dict[str, int]:
    freq = {}
    for t in texts:
        for tok in tokenize_with_stems(t):
            freq[tok] = freq.get(tok, 0) + 1
    sorted_toks = sorted(freq.items(), key=lambda x: x[1], reverse=True)[: max_vocab - 2]
    vocab = {"<PAD>": 0, "<UNK>": 1}
    for tok, _ in sorted_toks:
        vocab[tok] = len(vocab)
    return vocab


def encode_tokens(tokens: list[str], vocab: dict[str, int], max_len: int = 48) -> tuple[list[int], list[int]]:
    ids = [vocab.get(t, 1) for t in tokens[:max_len]]
    mask = [1] * len(ids)
    while len(ids) < max_len:
        ids.append(0)
        mask.append(0)
    return ids, mask


def train_pytorch_model(epochs: int = 32, lr: float = 0.01) -> dict:
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    texts, y_dict, total_reviews, verified_count = load_training_samples_from_db()

    if total_reviews == 0:
        raise ValueError("PyTorch modelini eğitmek için önce Türkçe yorum toplayın.")

    vocab = build_vocab(texts)
    max_len = 48

    X_ids = []
    X_masks = []
    for t in texts:
        ids, mask = encode_tokens(tokenize_with_stems(t), vocab, max_len)
        X_ids.append(ids)
        X_masks.append(mask)

    input_tensor = torch.tensor(X_ids, dtype=torch.long)
    mask_tensor = torch.tensor(X_masks, dtype=torch.float32)

    Y_tensors = []
    for k in ASPECT_KEYS:
        mapped = [CLASS_TO_IDX[val] for val in y_dict[k]]
        Y_tensors.append(torch.tensor(mapped, dtype=torch.long))

    torch.manual_seed(42)
    model = TurkishBiLSTMAttentionABSA(
        vocab_size=len(vocab),
        embed_dim=64,
        hidden_dim=64,
        num_aspects=len(ASPECT_KEYS),
    )

    criterion = nn.CrossEntropyLoss(weight=torch.tensor([2.5, 0.5, 2.5]))
    optimizer = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)

    model.train()
    loss_history = []
    for _ in range(epochs):
        optimizer.zero_grad()
        logits_list, _ = model(input_tensor, mask_tensor)
        total_loss = 0.0
        for a_idx in range(len(ASPECT_KEYS)):
            total_loss = total_loss + criterion(logits_list[a_idx], Y_tensors[a_idx])
        total_loss.backward()
        optimizer.step()
        loss_history.append(round(float(total_loss.item()), 4))

    model.eval()
    metrics = {}
    with torch.no_grad():
        logits_list, _ = model(input_tensor, mask_tensor)
        for a_idx, k in enumerate(ASPECT_KEYS):
            preds = torch.argmax(logits_list[a_idx], dim=-1).numpy()
            trues = Y_tensors[a_idx].numpy()
            acc = float(accuracy_score(trues, preds))
            f1 = float(f1_score(trues, preds, average="macro", zero_division=0))
            metrics[k] = {
                "accuracy": round(acc * 100, 1),
                "macroF1": round(f1 * 100, 1),
            }

    torch.save(
        {
            "state_dict": model.state_dict(),
            "vocab": vocab,
            "max_len": max_len,
            "metrics": metrics,
            "loss_history": loss_history,
            "total_reviews": total_reviews,
            "sample_count": len(texts),
        },
        PYTORCH_MODEL_PATH,
    )

    return {
        "stage": "Stage 2: PyTorch BiLSTM + Multi-Aspect Attention",
        "totalReviews": total_reviews,
        "sampleCount": len(texts),
        "vocabSize": len(vocab),
        "epochs": epochs,
        "initialLoss": loss_history[0] if loss_history else 0.0,
        "finalLoss": loss_history[-1] if loss_history else 0.0,
        "metrics": metrics,
    }


def predict_pytorch(review_text: str) -> dict | None:
    if not PYTORCH_MODEL_PATH.exists():
        return None

    ckpt = torch.load(PYTORCH_MODEL_PATH, map_location="cpu", weights_only=False)
    vocab = ckpt["vocab"]
    max_len = ckpt["max_len"]

    model = TurkishBiLSTMAttentionABSA(
        vocab_size=len(vocab),
        embed_dim=64,
        hidden_dim=64,
        num_aspects=len(ASPECT_KEYS),
    )
    model.load_state_dict(ckpt["state_dict"])
    model.eval()

    clauses = split_into_clauses(review_text) or [review_text]
    results = {
        k: {"label": 0, "confidence": 0.0, "score": 0.0, "topAttendedWords": []}
        for k in ASPECT_KEYS
    }

    with torch.no_grad():
        for clause in clauses:
            toks = tokenize_with_stems(clause)[:max_len]
            if not toks:
                continue
            ids, mask = encode_tokens(toks, vocab, max_len)
            input_tensor = torch.tensor([ids], dtype=torch.long)
            mask_tensor = torch.tensor([mask], dtype=torch.float32)

            logits_list, attn_list = model(input_tensor, mask_tensor)
            for a_idx, k in enumerate(ASPECT_KEYS):
                probs = torch.softmax(logits_list[a_idx][0], dim=-1).numpy()
                pred_idx = int(np.argmax(probs))
                pred_label = IDX_TO_CLASS[pred_idx]
                conf = round(float(probs[pred_idx]) * 100, 1)

                attn = attn_list[a_idx][0][: len(toks)].numpy()
                word_indices = [i for i, t in enumerate(toks) if not t.startswith("#")]
                word_indices.sort(key=lambda idx: attn[idx], reverse=True)
                top_words = [
                    {"word": toks[i], "weight": round(float(attn[i]), 3)}
                    for i in word_indices[:3]
                ]

                if pred_label != 0 and conf > results[k]["confidence"]:
                    results[k] = {
                        "label": pred_label,
                        "confidence": conf,
                        "score": round(float(probs[2] - probs[0]), 2),
                        "topAttendedWords": top_words,
                    }
                elif results[k]["label"] == 0 and conf > results[k]["confidence"]:
                    results[k] = {
                        "label": 0,
                        "confidence": conf,
                        "score": round(float(probs[2] - probs[0]), 2),
                        "topAttendedWords": top_words,
                    }

    return results


def analyze_turkish_review_full(review_text: str, star_rating: float | None = None) -> dict:
    lex = suggest_aspect_labels(review_text, star_rating)
    sk_pred = predict_sklearn(review_text)
    pt_pred = predict_pytorch(review_text)

    combined_dimensions = []
    for dim in ASPECT_DIMENSIONS:
        k = dim["key"]
        lex_label = lex["labels"].get(k, 0)
        sk_item = sk_pred.get(k) if sk_pred else None
        pt_item = pt_pred.get(k) if pt_pred else None

        final_label = lex_label
        if final_label == 0 and sk_item and sk_item["label"] != 0 and sk_item["confidence"] >= 60:
            final_label = sk_item["label"]
        if final_label == 0 and pt_item and pt_item["label"] != 0 and pt_item["confidence"] >= 65:
            final_label = pt_item["label"]

        combined_dimensions.append(
            {
                "key": k,
                "label": dim["label"],
                "sentiment": final_label,
                "evidence": lex["evidence"].get(k, []),
                "sklearn": sk_item,
                "pytorch": pt_item,
            }
        )

    return {
        "clauses": lex["clauses"],
        "dimensions": combined_dimensions,
        "modelsReady": {
            "sklearn": sk_pred is not None,
            "pytorch": pt_pred is not None,
        },
    }


def get_nlp_dashboard_status() -> dict:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) AS cnt FROM turkish_reviews")
    total_cnt = cur.fetchone()["cnt"]
    cur.execute("SELECT COUNT(*) AS cnt FROM turkish_reviews WHERE is_verified = 1")
    ver_cnt = cur.fetchone()["cnt"]
    cur.execute("SELECT labels_json FROM turkish_reviews")
    rows = cur.fetchall()
    conn.close()

    aspect_stats = {k: {"pos": 0, "neg": 0} for k in ASPECT_KEYS}
    for r in rows:
        lbls = json.loads(r["labels_json"] or "{}")
        for k in ASPECT_KEYS:
            v = int(lbls.get(k, 0))
            if v == 1:
                aspect_stats[k]["pos"] += 1
            elif v == -1:
                aspect_stats[k]["neg"] += 1

    sk_metrics = None
    if SKLEARN_MODEL_PATH.exists():
        try:
            with open(SKLEARN_MODEL_PATH, "rb") as f:
                b = pickle.load(f)
                sk_metrics = b.get("metrics")
        except Exception:
            pass

    pt_metrics = None
    if PYTORCH_MODEL_PATH.exists():
        try:
            ckpt = torch.load(PYTORCH_MODEL_PATH, map_location="cpu", weights_only=False)
            pt_metrics = ckpt.get("metrics")
        except Exception:
            pass

    return {
        "totalReviews": total_cnt,
        "verifiedReviews": ver_cnt,
        "aspectStats": aspect_stats,
        "dimensions": [{"key": d["key"], "label": d["label"]} for d in ASPECT_DIMENSIONS],
        "sklearnTrained": sk_metrics is not None,
        "sklearnMetrics": sk_metrics,
        "pytorchTrained": pt_metrics is not None,
        "pytorchMetrics": pt_metrics,
    }


def compute_user_aspect_profile(reviews_list: list[str]) -> dict[str, float]:
    """
    Aggregate a user's Turkish reviews into a 6-dimensional Cinematic Sensitivity Vector
    showing how strongly they care about and praise each film dimension.
    """
    counts = {k: 0 for k in ASPECT_KEYS}
    positive_hits = {k: 0 for k in ASPECT_KEYS}

    for rev in reviews_list:
        sugg = suggest_aspect_labels(rev)
        for k in ASPECT_KEYS:
            lbl = sugg["labels"].get(k, 0)
            if lbl != 0:
                counts[k] += 1
                if lbl > 0:
                    positive_hits[k] += 1

    total_mentions = max(1, sum(counts.values()))
    profile = {}
    for k in ASPECT_KEYS:
        weight = round((counts[k] / total_mentions) * 100, 1)
        profile[k] = weight
    return profile

