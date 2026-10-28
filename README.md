# The Just

The Just is a social discovery, film taste compatibility, and Turkish Aspect-Based Sentiment Analysis (ABSA) web application built around Letterboxd watch histories and film reviews. Users can create a profile, upload a profile photo, link their Letterboxd username, analyze what cinematic aspects they praise or criticize in reviews, and connect with people who share similar cinematic tastes.

## Overview

The platform is organized into separate, focused screens rather than displaying all information on a single page:

1. **Welcome and Authentication:** Clean entry screen with dedicated views for user login and account registration.
2. **Profile and Photo Setup:** Users provide personal details (name, age, location, bio, connection preference, favorite genres), upload a profile photo, and link their public Letterboxd username.
3. **Member Discovery:** Displays registered members ordered by calculated film taste compatibility percentage.
4. **Compatibility Breakdown:** A dedicated view comparing the logged-in user and a selected member across shared watched films, rating distance, mutual favorites, rating disagreements, and shared watchlist items.
5. **Turkish NLP and Aspect-Based Sentiment Studio:** A three-window studio for harvesting genuine Turkish Letterboxd film reviews, labeling reviews across six cinematic dimensions, training two machine learning / deep learning models, and running live clause-level contrast analysis.
6. **Direct Messaging:** A dedicated chat window with conversation starters generated from shared film history.
7. **Head-to-Head Comparison Tool:** A standalone view for comparing any two public Letterboxd usernames directly.

## Turkish NLP Architecture (Aspect-Based Sentiment Analysis)

The NLP subsystem (`nlp/`) extracts fine-grained sentiment (`-1` negative, `0` neutral/unmentioned, `+1` positive) across six core cinematic dimensions from Turkish film reviews:

- `sinematografi` — Cinematography, lighting, color palette, framing, and visual composition
- `senaryo` — Screenplay, dialogue, plot structure, and character writing
- `tempo` — Editing, pacing, rhythm, and narrative flow
- `oyunculuk` — Acting performances and cast chemistry
- `muzik_atmosfer` — Original score, sound design, and atmosphere
- `yonetmenlik` — Direction and mise-en-scene

### Linguistic Preprocessing and Contrast Splitting

Turkish film reviews frequently express opposing sentiments within a single sentence using contrast conjunctions (such as `ama`, `fakat`, `lakin`, `ancak`, `ragmen`, `olsa da`). `nlp/preprocessor.py` normalizes Turkish casing (`I -> ı`, `İ -> i`), binds negation suffixes (`değil`, `yok`, `olmamış`), and splits compound sentences at contrast boundaries so that each clause is evaluated for the specific cinematic dimension it addresses.

### Two-Stage Model Pipeline

1. **Stage 1 (Classical Machine Learning — Scikit-Learn):** Combines word N-grams `(1, 2)` with character word-boundary N-grams `(3, 5)` via `FeatureUnion` TF-IDF vectorization to handle Turkish agglutinative morphology, feeding six regularized `LogisticRegression` classifiers.
2. **Stage 2 (Deep Learning — PyTorch):** `TurkishBiLSTMAttentionABSA` embeds tokens into a shared Bidirectional LSTM sequence encoder followed by six independent Aspect Self-Attention Heads. Each head computes token-level attention weights and predicts `-1 / 0 / +1` sentiment for its target dimension.

## Project Structure

```text
the-just/
├── app.py                      # Multi-threaded HTTP server, SQLite database layer, and API routes
├── nlp/
│   ├── __init__.py
│   ├── preprocessor.py         # Turkish normalization, contrast clause splitter, and lexicon pre-annotator
│   ├── collector.py            # Live Letterboxd network crawler and Turkish RSS review harvester
│   └── models.py               # Stage 1 (Scikit-Learn TF-IDF + LogReg) and Stage 2 (PyTorch BiLSTM + Attention)
├── data/
│   └── tr_letterboxd_absa.jsonl # Harvested genuine Turkish Letterboxd reviews and aspect annotations
├── static/
│   ├── index.html              # Application shell and navigation header
│   ├── styles.css              # Dark theme stylesheet
│   └── app.js                  # Multi-screen client router and NLP Studio interface
└── README.md
```

## API Endpoints

### Authentication, Discovery, and Compatibility
- `POST /api/auth/register` — Registers a new user account, stores profile metadata and photo, and syncs initial Letterboxd summary statistics.
- `POST /api/auth/login` — Authenticates an existing user and returns a session token.
- `GET /api/auth/me` — Returns the currently authenticated user profile.
- `POST /api/profile/update` — Updates personal information, profile photo, and linked Letterboxd account.
- `GET /api/discover` — Lists community members ranked by taste compatibility with the current user.
- `GET /api/member?id=<id>` — Returns a member's profile alongside a full head-to-head Letterboxd compatibility analysis.
- `GET /api/messages?user_id=<id>` and `POST /api/messages` — Retrieves and sends direct messages between matched users.
- `GET /api/compatibility?user1=<u1>&user2=<u2>` — Computes taste compatibility between any two Letterboxd usernames.

### Turkish NLP and ABSA Studio
- `GET /api/nlp/status` — Returns dataset statistics and training metrics for both Stage 1 and Stage 2 models.
- `GET /api/nlp/reviews?filter=all|unverified|verified&limit=40&offset=0` — Lists harvested Turkish Letterboxd reviews for the labeling studio.
- `POST /api/nlp/harvest` — Expands seed Letterboxd usernames and harvests genuine Turkish film reviews from RSS feeds.
- `POST /api/nlp/label` — Saves verified six-dimension sentiment labels (`-1, 0, +1`) for a review or bulk-approves pre-annotations.
- `POST /api/nlp/train` — Trains Stage 1 (`scikit-learn`) and Stage 2 (`PyTorch BiLSTM + Attention`) models on the current dataset.
- `POST /api/nlp/analyze` — Runs clause-level and full-review inference using both models and returns per-aspect scores and attention weights.

## Getting Started

### Prerequisites

- Python 3.10 or newer
- `numpy`, `scikit-learn`, and `torch`

### Running Locally

```bash
git clone https://github.com/mustafa-akkus/the-just.git
cd the-just
pip install numpy scikit-learn torch
python app.py
```

Open `http://localhost:8000` in your browser.

## License

MIT License
