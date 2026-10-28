# The Just

The Just is a social discovery and film taste compatibility web application built around Letterboxd watch histories. Users can create a profile, upload a profile photo, link their Letterboxd username, and connect with people who share similar cinematic tastes.

## Overview

The platform is organized into separate, focused screens rather than displaying all information on a single page:

1. **Welcome and Authentication:** Clean entry screen with dedicated views for user login and account registration.
2. **Profile and Photo Setup:** Users provide personal details (name, age, location, bio, connection preference, favorite genres), upload a profile photo, and link their public Letterboxd username.
3. **Member Discovery:** Displays registered members ordered by calculated film taste compatibility percentage.
4. **Compatibility Breakdown:** A dedicated view comparing the logged-in user and a selected member across shared watched films, rating distance, mutual favorites, rating disagreements, and shared watchlist items.
5. **Direct Messaging:** A dedicated chat window with conversation starters generated from shared film history.
6. **Head-to-Head Comparison Tool:** A standalone view for comparing any two public Letterboxd usernames directly.

## Technical Architecture

The project runs on the Python 3 standard library (`http.server`, `sqlite3`, `urllib.request`, `xml.etree.ElementTree`, `concurrent.futures`) with no external package dependencies required.

```text
the-just/
├── app.py              # Multi-threaded HTTP server, SQLite database layer, and Letterboxd parser
├── static/
│   ├── index.html      # Application shell and navigation header
│   ├── styles.css      # Dark theme stylesheet
│   └── app.js          # Multi-screen client router and API integration
└── README.md
```

### API Endpoints

- `POST /api/auth/register` — Registers a new user account, stores profile metadata and photo, and syncs initial Letterboxd summary statistics.
- `POST /api/auth/login` — Authenticates an existing user and returns a session token.
- `GET /api/auth/me` — Returns the currently authenticated user profile.
- `POST /api/profile/update` — Updates personal information, profile photo, and linked Letterboxd account.
- `GET /api/discover` — Lists community members ranked by taste compatibility with the current user.
- `GET /api/member?id=<id>` — Returns a member's profile alongside a full head-to-head Letterboxd compatibility analysis.
- `GET /api/messages?user_id=<id>` & `POST /api/messages` — Retrieves and sends direct messages between matched users.
- `GET /api/compatibility?user1=<u1>&user2=<u2>` — Computes taste compatibility between any two Letterboxd usernames.

## Getting Started

### Prerequisites

- Python 3.10 or newer

### Running Locally

```bash
git clone https://github.com/mustafa-akkus/the-just.git
cd the-just
python app.py
```

Open `http://localhost:8000` in your browser.

## License

MIT License
