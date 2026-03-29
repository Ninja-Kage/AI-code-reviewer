# AI Code Reviewer

A self-hosted code review system that hooks into your GitHub repos and automatically reviews pull requests using Groq's LLM API. It stores review history in PostgreSQL and serves everything through a React frontend.

I built this because I was tired of waiting on teammates to review small PRs, and I wanted something that actually understands context — not just a linter.

---

## What it does

- Listens for GitHub webhook events (pull requests, pushes)
- Sends the diff to Groq and gets back a structured code review
- Stores the review history in a PostgreSQL database
- Displays reviews in a clean React UI
- Runs entirely in Docker, so setup is straightforward

---

## Stack

- **Backend** — Python (FastAPI), runs on port 8000
- **Frontend** — React
- **Database** — PostgreSQL
- **LLM** — Groq (`llama-3.3-70b-versatile` by default, configurable)
- **Infrastructure** — Docker Compose

---

## Prerequisites

Before anything else, make sure you have:

- Docker + Docker Compose installed
- A [Groq API key](https://console.groq.com)
- A GitHub repo you want to connect (you'll need to set up a webhook)

---

## Getting started

### 1. Clone the repo

```bash
git clone https://github.com/yourusername/ai-code-reviewer.git
cd ai-code-reviewer
```

### 2. Set up environment variables

Copy the example env file and fill in your values:

```bash
cp .env.example .env
```

Your `.env` should look like this:

```env
GITHUB_TOKEN=your_github_token_here
GITHUB_WEBHOOK_SECRET=your_webhook_secret_here
GROQ_API_KEY=your_groq_api_key_here
GROQ_MODEL=llama-3.3-70b-versatile
POSTGRES_PASSWORD=your_db_password_here
```

> **Note:** Never commit your `.env` file. It's already in `.gitignore` but worth double-checking.

### 3. Start everything

```bash
docker compose up --build
```

The first run will take a minute while it pulls images and builds the backend. After that, subsequent starts are fast.

- Backend: `http://localhost:8000`
- Frontend: `http://localhost:3000` (or wherever your React dev server is configured)

---

## GitHub Webhook Setup

For the reviewer to actually receive events from GitHub, you need to configure a webhook on your repo:

1. Go to your GitHub repo → **Settings** → **Webhooks** → **Add webhook**
2. Set the **Payload URL** to your backend's `/webhook` endpoint:
   ```
   http://your-server-ip:8000/webhook
   ```
   If you're running locally, use something like [ngrok](https://ngrok.com) to expose your local server.
3. Set **Content type** to `application/json`
4. Set the **Secret** to whatever you put in `GITHUB_WEBHOOK_SECRET`
5. Choose **Pull requests** (and optionally **Pushes**) as the events to send
6. Hit **Add webhook**

GitHub will send a ping event — if you see a green checkmark, you're good.

---

## Project Structure

```
ai-code-reviewer/
├── backend/
│   ├── Dockerfile
│   ├── main.py
│   ├── reviewer.py        # Groq API integration
│   ├── webhook.py         # GitHub webhook handler
│   ├── database.py        # PostgreSQL models / queries
│   └── requirements.txt
├── frontend/
│   ├── src/
│   └── ...
├── docker-compose.yml
├── .env.example
└── README.md
```

---

## Configuration

| Variable | Description | Default |
|---|---|---|
| `GITHUB_TOKEN` | GitHub personal access token | required |
| `GITHUB_WEBHOOK_SECRET` | Secret for validating webhook payloads | required |
| `GROQ_API_KEY` | Your Groq API key | required |
| `GROQ_MODEL` | Groq model to use for reviews | `llama-3.3-70b-versatile` |
| `POSTGRES_PASSWORD` | Database password | required |

If you want to swap the model, just update `GROQ_MODEL` in your `.env`. Groq's available models are listed [here](https://console.groq.com/docs/models).

---

## Common issues

**`invalid interpolation format` error on startup**
Check your `docker-compose.yml` for any `${VAR:-default}` entries missing the closing `}`. Docker Compose is strict about this.

**Webhook events not being received**
- Make sure your server is publicly accessible (use ngrok locally)
- Double-check that `GITHUB_WEBHOOK_SECRET` matches exactly what you entered in GitHub
- Look at the webhook delivery logs in GitHub (Settings → Webhooks → Recent Deliveries)

**DB connection errors on startup**
The backend depends on the database being healthy before it starts. If you're seeing connection errors, the `healthcheck` on the `db` service might not be passing. Give it 30 seconds and try again, or check `docker compose logs db`.

---

## Development

To run with hot reload (volume is already mounted in `docker-compose.yml`):

```bash
docker compose up
```

Any changes to `./backend` will reflect immediately without rebuilding.

For the frontend, you'll likely want to run it outside Docker during development:

```bash
cd frontend
npm install
npm run dev
```

---

## Roadmap

Things I'm planning to add:

- [ ] PR comment posting directly to GitHub (right now reviews only show in the UI)
- [ ] Severity levels for review feedback (critical / warning / suggestion)
- [ ] Support for multiple repos from a single dashboard
- [ ] Review history filtering and search
- [ ] Slack notifications when a review is ready

---

## License

MIT
