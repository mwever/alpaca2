# Alpaca

**Academic Administration, knowLedge base, Paper organization And Collaboration Assistant**

Alpaca is a self-hosted web application for academic research groups. It centralises paper tracking, author management, group collaboration, bibliography export, and more in a single lightweight tool.

---

## Features

### Paper Management
- Track submissions across **conferences** and **journals** with full lifecycle status (submitted → under review → accepted → published)
- Attach resources (PDFs, code, slides, posters) and manage a change log per paper
- Milestone tracking and due-date reminders per submission
- Import paper metadata from **DBLP** and **ORCID**

### Author & Affiliation Management
- Maintain an author database with ORCID identifiers and DBLP PIDs
- Profile photos, affiliation history, and author–user account linking
- Author claim system (authors request to be linked to their user account)

### Research Groups
- Create groups with member roles (member / admin)
- Group-level paper collections, shared notebooks, wikis, and BibTeX collections
- Review exchange coordination within groups
- Group logo and branding

### BibTeX Collections
- Personal and group-owned bibliography collections
- Configurable export styles per collection:
  - Author name format (full / abbreviated / last-name only)
  - Maximum authors shown (with "et al.")
  - Toggle DOI, URL, abstract inclusion
  - Auto-clean proceedings names (strips "Proceedings of the …" prefix)
  - Auto-generate `@proceedings` + `crossref=` for conference papers
- Import entries by pasting BibTeX, uploading a `.bib` file, or importing from tracked papers
- Cite-key format: `{lastname}-{venue}{yy}{a…z}` (e.g. `lecun-icml23a`; arXiv papers use `arxiv`)
- One-click "Regenerate Keys" to normalise all cite keys in a collection
- Share personal collections with research groups; revoke per-member write access

### Scholar & Suggestions
- Google Scholar profile monitoring
- Automatic paper suggestions based on tracked authors

### Collaborative Tools
- **Notebook**: shared markdown notes per group
- **Wiki**: group knowledge base
- **Workflows**: multi-step task pipelines with dependencies and subscriptions
- **Calendar**: personal and group events with milestone integration
- **Service records**: track reviewing / programme committee activity

### User Experience
- Responsive Bootstrap 5 UI with HTMX for partial-page updates
- Light / dark / custom theme support
- Session-based authentication (30-day cookie)
- Admin panel for user management

---

## Tech Stack

| Layer | Technology |
|---|---|
| Web framework | [FastAPI](https://fastapi.tiangolo.com/) |
| Templates | Jinja2 + [HTMX](https://htmx.org/) |
| UI | [Bootstrap 5](https://getbootstrap.com/) + Bootstrap Icons |
| Database ORM | SQLAlchemy (async) |
| Migrations | Alembic |
| Database | MySQL 8+ / 9 |
| Package manager | [uv](https://docs.astral.sh/uv/) |
| Deployment | Docker + Traefik (Let's Encrypt) |

---

## Local Development

### Prerequisites
- Python ≥ 3.13
- [uv](https://docs.astral.sh/uv/) installed
- A running MySQL instance

### Setup

```bash
# 1. Clone and enter the project
git clone <repo-url>
cd alpaca

# 2. Install dependencies
uv sync

# 3. Create .env
cp .env.example .env   # then fill in the values
```

`.env` (minimum required):
```env
DATABASE_URL=mysql+aiomysql://alpaca:password@localhost:3306/alpaca
SECRET_KEY=change-me-to-a-long-random-string
```

```bash
# 4. Create the database and run migrations
uv run alembic upgrade head

# 5. Start the development server
uv run fastapi dev app/main.py
```

The app is now available at `http://localhost:8000`.

---

## Production Deployment (Docker + Traefik)

### Prerequisites
- A server with Docker and Docker Compose installed
- A domain name pointing to the server (required for Let's Encrypt)
- Ports 80 and 443 open

### Steps

```bash
# 1. Copy files to the server
scp -r . user@server:/opt/alpaca

# 2. Create .env on the server
cat > /opt/alpaca/.env <<EOF
ACME_EMAIL=admin@example.com
DOMAIN=alpaca.example.com
DB_NAME=alpaca
DB_USER=alpaca
DB_PASSWORD=<strong-password>
DB_ROOT_PASSWORD=<strong-root-password>
SECRET_KEY=<long-random-string>
EOF

# 3. Build and start
cd /opt/alpaca
docker compose up -d --build
```

On first startup, Traefik will automatically obtain a TLS certificate from Let's Encrypt. HTTP traffic is permanently redirected to HTTPS.

### Services

| Service | Description |
|---|---|
| `traefik` | Reverse proxy — TLS termination, HTTP→HTTPS redirect |
| `db` | MySQL 9.2 — data persisted in `db_data` volume |
| `app` | Alpaca — runs `alembic upgrade head` then starts uvicorn |

### Volumes

| Volume | Contents |
|---|---|
| `db_data` | MySQL data directory |
| `uploads` | User-uploaded files (mounted at `/app/static/uploads`) |
| `letsencrypt` | Let's Encrypt certificates (`acme.json`) |

### Environment Variables

| Variable | Default | Description |
|---|---|---|
| `ACME_EMAIL` | — | Email for Let's Encrypt registration |
| `DOMAIN` | — | Public domain name (e.g. `alpaca.example.com`) |
| `DB_NAME` | `alpaca` | MySQL database name |
| `DB_USER` | `alpaca` | MySQL user |
| `DB_PASSWORD` | — | MySQL user password |
| `DB_ROOT_PASSWORD` | — | MySQL root password |
| `SECRET_KEY` | — | Session signing key (keep secret, min. 32 chars) |

---

## Project Structure

```
alpaca/
├── app/
│   ├── main.py              # FastAPI application factory
│   ├── config.py            # Settings (pydantic-settings)
│   ├── database.py          # Async SQLAlchemy engine & session
│   ├── bibtex_utils.py      # BibTeX parsing, formatting, rendering
│   ├── models/              # SQLAlchemy ORM models
│   ├── routers/             # FastAPI routers (one per feature)
│   └── templates/           # Jinja2 HTML templates
├── alembic/                 # Database migrations
├── static/                  # CSS, JS, images
├── Dockerfile
├── docker-compose.yml
└── pyproject.toml
```

---

## License

MIT
