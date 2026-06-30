# CLAUDE.md

## Project summary

Multi-tenant FastAPI price-tracking dashboard for hotline.ua. Users get a UUID URL — the UUID itself is the access token, no auth. Product configs are stored in PostgreSQL as JSONB.

## Project structure

```
hotline-listing/
├── ansible/
│   ├── ansible.cfg
│   ├── inventories/zelgray.work/
│   │   ├── hosts.yml
│   │   └── group_vars/all.yml      # minimal: docker_network, nginx paths, postgres_password
│   ├── playbooks/
│   │   ├── pre_tasks/infisical.yml
│   │   └── hotline-listing.yml
│   └── roles/hotline-listing/      # syncs sources/, builds image, deploys container + nginx
├── config.yaml                     # products list only — infra fields use AppConfig defaults
├── install_dependencies.sh         # pip requirements.txt + ansible-galaxy + infisical CLI
├── pyproject.toml                  # app metadata for local dev with uv (Docker uses sources/src/requirements.txt)
├── uv.lock                         # uv lockfile (local dev only)
├── requirements.txt                # Ansible tooling: infisicalsdk, pre-commit, yamllint, ansible-lint
├── requirements.yml                # Galaxy: infisical.vault, community.docker
└── sources/                        # Docker build context; synced as a unit to target host
    ├── Dockerfile                  # Python 3.12-slim, port 8999
    ├── alembic.ini                 # script_location = src/hotline_prices/alembic
    ├── entrypoint.sh               # runs `alembic upgrade head` then exec uvicorn
    ├── src/
    │   ├── requirements.txt        # Python app deps (pinned)
    │   └── hotline_prices/
    │       ├── alembic/
    │       │   ├── env.py          # async env; reads config.yaml from CWD
    │       │   └── versions/
    │       │       └── d413ff1678f4_create_configs_table.py
    │       ├── app.py              # FastAPI routes, lifespan, Jinja2 filters
    │       ├── cache.py            # async Redis wrapper (JSON, TTL)
    │       ├── client.py           # hotline.ua GraphQL client (getChart)
    │       ├── config.py           # AppConfig + ProductConfig (Pydantic BaseModel)
    │       ├── db.py               # SQLAlchemy async CRUD + create_db_if_not_exists
    │       ├── models.py           # ProductSummary dataclass (computed properties)
    │       └── models_db.py        # SQLAlchemy ORM: Base, Config
    ├── static/
    │   ├── i18n.js                 # UK/EN/RU translations, applyLang/setLang/detectLang
    │   └── style.css               # dark theme
    └── templates/
        ├── chart.html              # Chart.js price history (UAH + USD axes)
        ├── dashboard.html          # price table, sparklines, totals, diff, i18n
        ├── edit.html               # product form (JS add/remove rows), YAML export, share URL
        └── landing.html            # new table + YAML import + localStorage recent list
```

## HTTP routes

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Landing page |
| POST | `/` | Create empty config → 303 `/{uuid}/edit` |
| POST | `/import` | Upload YAML file → parse products → 303 `/{uuid}/edit` |
| GET | `/{uuid}` | Dashboard (fetches prices, renders table) |
| GET | `/{uuid}/chart/{slug}` | Price history chart for one product (Chart.js) |
| GET | `/{uuid}/edit` | Product list editor |
| POST | `/{uuid}/save` | JSON body `{products:[…]}` → persist → 303 `/{uuid}` |

## AppConfig fields

Loaded from `config.yaml` via `AppConfig.from_yaml()`. All have defaults.

| Field | Default | Description |
|-------|---------|-------------|
| `redis_url` | `redis://localhost:6379` | Redis connection string |
| `database_url` | `postgresql://postgres:postgres@localhost:5432/hotline_prices` | PostgreSQL sync URL |
| `cache_ttl` | `3600` | Redis TTL for chart data (seconds) |
| `city_id` | `154` | Kyiv |
| `products` | `[]` | Local dev list; YAML import reads this key |

`async_database_url` property replaces `postgresql://` → `postgresql+psycopg_async://` for SQLAlchemy async engine.

## DB model

Table `configs` (PostgreSQL, managed by Alembic):

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | `gen_random_uuid()` — also the user's URL token |
| `data` | JSONB | `{"products": [{url, title?, count, purchase_price?, purchase_date?}]}` |
| `created_at` | timestamptz | `now()` |
| `updated_at` | timestamptz | `now()` |

## Key dependencies (sources/src/requirements.txt)

| Package | Version | Purpose |
|---------|---------|---------|
| `fastapi` | 0.115.12 | Web framework |
| `uvicorn` | 0.34.3 | ASGI server |
| `sqlalchemy` | 2.0.41 | ORM + async engine |
| `psycopg[binary]` | 3.3.4 | PostgreSQL driver — sync and async, single package |
| `alembic` | 1.16.2 | Schema migrations |
| `sqlalchemy-utils` | 0.41.2 | `create_database` / `database_exists` |
| `redis` | 5.2.1 | Async Redis client |
| `httpx` | 0.28.1 | HTTP client for hotline.ua GraphQL |
| `pydantic` | 2.11.5 | Config validation |
| `jinja2` | 3.1.6 | Server-side HTML templates |
| `python-multipart` | 0.0.20 | YAML file upload (`/import`) |
| `pyyaml` | 6.0.2 | Parse uploaded YAML configs |

## Architecture notes

**No auth** — the UUID URL is the only access control. Anyone with the link can view and edit.

**hotline.ua API** — uses the undocumented GraphQL endpoint at `https://hotline.ua/svc/frontend-api/graphql`, operation `getChart`. This requires no authentication. The `byPathQueryProduct` operation does require auth and is not used.

**DB auto-creation** — `create_db_if_not_exists(sync_url)` (via `sqlalchemy_utils`) is called in the FastAPI lifespan before `init_db`. Tables are managed exclusively by Alembic — run `alembic upgrade head` manually after first deploy.

**SQLAlchemy driver** — `psycopg[binary]==3.3.4` is the only PostgreSQL driver. Async URL uses `postgresql+psycopg_async://`; sync URL (for sqlalchemy_utils and Alembic) uses `postgresql+psycopg://` — both derived from the plain `database_url` in config via `sync_database_url` / `async_database_url` properties.

**Migrations on start** — `entrypoint.sh` runs `alembic upgrade head` before starting uvicorn, so the schema is always current after a container restart or redeploy.

**Static versioning** — `STATIC_VERSION` env var (set by Ansible from MD5 of `style.css + i18n.js`) is exposed as Jinja2 global `static_version` and appended as `?v=` to all CSS/JS URLs. Cloudflare cache is purged after each deploy.

**Subpath deployment** — `ROOT_PATH` env var (e.g. `/hotline-listing`) is read at startup and set as a Jinja2 global. All template links and JS fetch URLs use `{{ root_path }}/...` / `${ROOT_PATH}/...`. When empty, the app serves from root (local dev).

**config.yaml resolution** — `app.py` reads `Path(os.getenv('CONFIG_PATH', 'config.yaml'))`. When unset, this is relative to CWD. Run uvicorn and alembic from the project root so they find `config.yaml` there. In Docker, CWD is `/app` and the Ansible role mounts `config.yaml` at `/app/config.yaml`.

**Sparklines** — SVG polyline generated server-side as a Jinja2 filter (`_sparkline`) over the last 60 price points from the chart API.

**Cache key** — `hotline:chart:{product-path-slug}`, TTL from `cache_ttl`.

## Migrations

```bash
# Apply (run from project root)
PYTHONPATH=sources/src alembic -c sources/alembic.ini upgrade head

# New migration (with live DB)
PYTHONPATH=sources/src alembic -c sources/alembic.ini revision --autogenerate -m "description"
```

Alembic `env.py` reads `config.yaml` from CWD (project root).

## Running locally

```bash
pip install -r sources/src/requirements.txt
PYTHONPATH=sources/src alembic -c sources/alembic.ini upgrade head
PYTHONPATH=sources/src uvicorn hotline_prices.app:app --reload
```

All commands run from the **project root**; `config.yaml` is found in CWD.

## Deployment (Ansible)

```bash
./install_dependencies.sh
cd ansible
ansible-playbook -i inventories/zelgray.work playbooks/hotline-listing.yml
```

Requires env: `INFISICAL_API_URL`, `INFISICAL_CLIENT_ID`, `INFISICAL_CLIENT_SECRET`.
The role syncs `sources/` from `hotline_listing_local_source_dir` to the target host, builds the Docker image there, templates `config.yaml`, and starts the container.
