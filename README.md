# AI Code Reviewer 🤖

An automated, AI-powered GitHub pull request reviewer that acts like a senior engineer — catching bugs, security issues, and bad patterns before they hit main.

Built with **FastAPI + GPT-4 + PyGithub + React**.

---

## How it works

1. Developer opens a Pull Request on GitHub
2. GitHub fires a webhook to your server
3. Your server fetches the code diff via GitHub API
4. The diff is parsed into clean, per-file chunks
5. **GPT-4** reviews the chunks for bugs, security issues, and style
6. **Pylint / ESLint** runs static analysis in parallel
7. Both outputs are merged, scored, and deduplicated
8. Inline comments + a summary are posted back to the PR automatically

---

## Project structure

```
ai-code-reviewer/
├── backend/
│   ├── main.py            # FastAPI app + webhook endpoint + REST API
│   ├── github_client.py   # GitHub API — fetch diffs, post comments
│   ├── diff_parser.py     # Parse unified diffs into clean chunks
│   ├── llm_engine.py      # GPT-4 review logic with structured JSON output
│   ├── rule_checker.py    # Pylint (Python) + pattern checks (JS/TS)
│   ├── aggregator.py      # Merge, deduplicate, score all feedback
│   ├── models.py          # SQLAlchemy DB models
│   ├── database.py        # DB connection + session management
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── App.js
│   │   ├── App.css
│   │   ├── index.js
│   │   └── pages/
│   │       ├── Dashboard.js     # Stats + reviews table + score chart
│   │       └── ReviewDetail.js  # Full review with inline comments
│   ├── public/index.html
│   ├── package.json
│   └── Dockerfile
├── docker-compose.yml
├── .env.example
├── .gitignore
└── README.md
```

---

## Quick start

### 1. Clone and configure

```bash
git clone https://github.com/YOUR_USERNAME/ai-code-reviewer
cd ai-code-reviewer
cp .env.example .env
```

Edit `.env` and fill in your keys:

```env
GITHUB_TOKEN=ghp_...
GITHUB_WEBHOOK_SECRET=any_random_string_you_choose
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o
```

### 2. Run with Docker (recommended)

```bash
docker-compose up --build
```

- Backend API:  http://localhost:8000
- Frontend:     http://localhost:3000
- API docs:     http://localhost:8000/docs

### 3. Run locally (without Docker)

**Backend:**
```bash
cd backend
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

**Frontend:**
```bash
cd frontend
npm install
npm start
```

---

## Setting up the GitHub Webhook

1. Go to your GitHub repo → **Settings → Webhooks → Add webhook**
2. **Payload URL:** `https://YOUR_SERVER_URL/webhook`
   - For local development, use [ngrok](https://ngrok.com): `ngrok http 8000`
   - Copy the HTTPS URL ngrok gives you
3. **Content type:** `application/json`
4. **Secret:** The same value as `GITHUB_WEBHOOK_SECRET` in your `.env`
5. **Events:** Select **"Pull requests"** only
6. Click **Add webhook**

Now open a PR on that repo — the bot will review it within ~30 seconds.

---

## Getting API keys

### GitHub Token
1. Go to https://github.com/settings/tokens
2. Click **Generate new token (classic)**
3. Scopes needed: `repo` (full), `pull_requests`
4. Copy the token → paste into `.env` as `GITHUB_TOKEN`

### OpenAI API Key
1. Go to https://platform.openai.com/api-keys
2. Click **Create new secret key**
3. Copy it → paste into `.env` as `OPENAI_API_KEY`
4. Make sure you have billing set up (GPT-4o costs ~$0.01–0.05 per PR review)

---

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/webhook` | GitHub webhook receiver |
| GET | `/api/reviews` | List all reviews (dashboard) |
| GET | `/api/reviews/{id}` | Single review with all comments |
| GET | `/api/stats` | Aggregate stats for overview cards |
| GET | `/api/health` | Health check |
| GET | `/docs` | Interactive Swagger API docs |

---

## What the bot reviews

**GPT-4 catches:**
- Logic bugs and null pointer risks
- Security vulnerabilities (SQL injection, XSS, hardcoded secrets)
- Performance problems (N+1 queries, memory leaks)
- Missing error handling
- Unclear variable names and dead code

**Pylint catches (Python):**
- Syntax errors and import failures
- Unused variables and imports
- Dangerous default arguments
- Broad except clauses
- Missing docstrings

**Pattern checks (JS/TS):**
- `eval()` usage
- `var` instead of `const`/`let`
- `==` instead of `===`
- Hardcoded credentials
- Empty catch blocks
- Unresolved TODOs

---

## Scoring system

Each review gets a 0–100 quality score:

| Score | Meaning |
|-------|---------|
| 80–100 | ✅ Good to merge |
| 60–79 | ⚠️ Address warnings first |
| 0–59 | ❌ Do not merge — critical issues found |

Score = blend of the LLM's holistic assessment (60%) + rule-based deductions (40%)

---

## Resume bullet

> *"Built an end-to-end AI code review bot using FastAPI, GPT-4, PyGithub, and React. The system receives GitHub webhooks, parses PR diffs, runs parallel LLM + static analysis (Pylint/ESLint), and posts inline review comments with severity scores. Features a React dashboard with score trends and review history. Deployed with Docker + PostgreSQL."*

---

## Tech stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.11, FastAPI, Uvicorn |
| AI review | OpenAI GPT-4o (JSON mode) |
| GitHub integration | PyGithub, GitHub REST API v3 |
| Static analysis | Pylint, custom regex rules |
| Database | PostgreSQL + SQLAlchemy ORM |
| Frontend | React 18, Recharts, React Router |
| Deployment | Docker, docker-compose |

---

## License

MIT — free to use, fork, and put on your resume.
