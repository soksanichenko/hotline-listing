# CLAUDE.md

## Project summary

Multi-tenant FastAPI price-tracking dashboard for hotline.ua. Users get a UUID URL — the UUID itself is the access token for the read-only dashboard/chart views; creating and editing configs is gated behind Discord SSO. Product configs are stored in PostgreSQL as JSONB.

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
│   │   └── deploy.yml
│   └── roles/hotline-listing/      # syncs sources/, builds image, deploys container + nginx
├── config.yaml                     # products list only — infra fields use AppConfig defaults
├── install_dependencies.sh         # pip requirements.txt + ansible-galaxy + infisical CLI
├── pyproject.toml                  # app + dev/test metadata for local dev with uv (Docker uses sources/src/requirements.txt)
├── uv.lock                         # uv lockfile (local dev only)
├── requirements.txt                # Ansible tooling: infisicalsdk, pre-commit, yamllint, ansible-lint
├── requirements.yml                # Galaxy: infisical.vault, community.docker
├── tests/                          # pytest suite — see Testing section below
├── .pre-commit-config.yaml         # ruff + ruff-format over sources/ and tests/
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
    │       │       ├── d413ff1678f4_create_configs_table.py
    │       │       ├── 6bf7338d4492_add_config_owner.py
    │       │       └── 37f30702a8cc_add_price_alerts.py
    │       ├── app.py              # FastAPI routes, lifespan, Jinja2 filters, price-alert scheduler job
    │       ├── cache.py            # async Redis wrapper (JSON, per-key TTL override)
    │       ├── client.py           # hotline.ua GraphQL client (getChart) + offer-page scraping
    │       ├── config.py           # AppConfig + ProductConfig (Pydantic BaseModel)
    │       ├── db.py               # SQLAlchemy async CRUD + create_db_if_not_exists
    │       ├── models.py           # ProductSummary dataclass (computed properties)
    │       ├── models_db.py        # SQLAlchemy ORM: Base, Config
    │       ├── notifications.py    # SMTP price-target alert emails
    │       └── nuxt_parser.py      # parses hotline.ua's window.__NUXT__ SSR payload (per-seller offers)
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
| POST | `/{uuid}/claim` | Bind an unowned (legacy) config to the requesting Discord user → 303 `/{uuid}/edit` |
| POST | `/{uuid}/delete` | Delete a config (owner-only) → 303 `/` |
| POST | `/logout` | Clear the portal-bridged `zw_session` cookie → 303 `/` |

## AppConfig fields

Loaded from `config.yaml` via `AppConfig.from_yaml()`. All have defaults.

| Field | Default | Description |
|-------|---------|-------------|
| `redis_url` | `redis://localhost:6379` | Redis connection string |
| `database_url` | `postgresql://postgres:postgres@localhost:5432/hotline_prices` | PostgreSQL sync URL |
| `cache_ttl` | `3600` | Redis TTL for chart data (seconds) |
| `city_id` | `154` | Kyiv |
| `products` | `[]` | Local dev list; YAML import reads this key |
| `price_check_interval` | `1800` | Seconds between price-target alert checks (APScheduler job) |
| `smtp_host` | `mail.zelgray.work` | SMTP server for price-target alert emails |
| `smtp_port` | `587` | SMTP port (STARTTLS) |
| `smtp_username` | `""` | SMTP auth username (mailbox address) |
| `smtp_password` | `""` | SMTP auth password |
| `smtp_from` | `noreply@zelgray.work` | `From:` address on alert emails |

`async_database_url` property replaces `postgresql://` → `postgresql+psycopg_async://` for SQLAlchemy async engine.

`ProductConfig` also has an optional `target_price` (float) — see **Price-target email alerts** below.

## DB model

Table `configs` (PostgreSQL, managed by Alembic):

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | `gen_random_uuid()` — also the user's URL token |
| `data` | JSONB | `{"products": [{url, title?, count, purchase_price?, purchase_date?, target_price?}], "name"?}` — `name` is the user-set list name (optional, shown on the dashboard/landing page) |
| `owner_discord_user_id` | text, nullable, indexed | Discord user ID that created the config; `NULL` for legacy configs created before ownership tracking |
| `owner_discord_email` | text, nullable | Verified Discord email of the owner, captured from `X-Discord-Email` on create/save/claim; used as the price-alert notification address |
| `alert_state` | JSONB | Per-product price-alert armed/notified state, keyed by product `url`; managed only by the background alert job, never by `/save` — see **Price-target email alerts** |
| `created_at` | timestamptz | `now()` |
| `updated_at` | timestamptz | `now()` |

## Key dependencies (sources/src/requirements.txt)

| Package | Version | Purpose |
|---------|---------|---------|
| `fastapi` | 0.141.1 | Web framework |
| `uvicorn` | 0.53.0 | ASGI server |
| `sqlalchemy` | 2.1.0 | ORM + async engine |
| `psycopg[binary]` | 3.3.6 | PostgreSQL driver — sync and async, single package |
| `alembic` | 1.20.0 | Schema migrations |
| `redis` | 8.1.0 | Async Redis client |
| `httpx` | 0.28.1 | HTTP client for hotline.ua GraphQL |
| `pydantic` | 2.13.5 | Config validation |
| `jinja2` | 3.1.6 | Server-side HTML templates |
| `python-multipart` | 0.0.32 | YAML file upload (`/import`) |
| `pyyaml` | 6.0.3 | Parse uploaded YAML configs |
| `apscheduler` | 3.11.3 | In-process periodic job for price-target alert checks |

## Architecture notes

**No auth on the read-only dashboard** — `/{uuid}` and `/{uuid}/chart/...` have no access control beyond the UUID itself, so a share link works for anyone. List creation/editing (`/`, `/import`, `/{uuid}/edit|save|claim|delete`) is gated behind Discord SSO via the `meow-elite-club-portal` service (nginx `auth_request` + a cross-domain cookie bridge at `/internal/bridge` — see the `hotline-listing` Ansible role's README and `nginx-location.conf.j2`). Configs are further scoped to the Discord user that created them via `owner_discord_user_id`; `_require_owner()` in `app.py` returns 403 for non-owners and allows any Discord-authenticated user to claim legacy (pre-ownership) configs. The portal also emits a verified `X-Discord-Email` header (requires the `email` OAuth scope) — nginx forwards it on the same gated locations as `X-Discord-User-Id`, and `app.py` persists it to `owner_discord_email` on create/save/claim.

**Price-target email alerts** — a product can have an optional `target_price`. An APScheduler job (`_check_price_alerts()` in `app.py`, interval `price_check_interval`) periodically checks every config with a known `owner_discord_email` and emails (`notifications.send_price_alert()`, plain SMTP via Mailcow at `mail.zelgray.work`) once a product's price drops to or below its target. The comparison uses the real per-seller minimum price scraped from the product page (`_get_offer_prices()`, see **Per-seller offer scraping** below) — not `getChart`'s `minPriceUAH` — since that GraphQL aggregate can lag the live lowest seller price by up to a day (see **hotline.ua API**). Per-product armed/notified state lives in the `alert_state` JSONB column — separate from `data` so the user-editable `/save` endpoint never clobbers it. State machine: price above target → armed; price ≤ target while armed → send + disarm; price ≤ target while disarmed → silent (already notified); price rises back above target → re-arm, so a later dip notifies again.

**Per-seller offer scraping** — the per-seller offer list (individual store prices/`firmTitle`) isn't available from the public `getChart` query; hotline.ua only exposes it via an authenticated GraphQL operation, and that login is behind a Cloudflare captcha, which was deliberately not automated (captcha-solving/headless-browser bypass is fragile and circumvents anti-bot protection the site put there on purpose). Instead, the same offer data is already embedded, unauthenticated, in the plain product page's Nuxt SSR hydration payload (`window.__NUXT__=(function(a,b,c,...){...return {...}})(v1,v2,...);` — a dedup-by-reference IIFE, not JSON). `nuxt_parser.py` hand-parses this with a small recursive-descent parser rather than executing it with a JS engine: Node's `vm` module is explicitly documented as not a security boundary, so running hotline.ua's page JS in it would carry a real sandbox-escape/RCE risk class that a text parser structurally can't have. `client.fetch_offer_prices()` fetches the page and calls `nuxt_parser.extract_offer_prices()`; `app._get_offer_prices()` wraps that with its own Redis cache key (`hotline:offers:{path}`) and a shorter TTL (`_OFFER_PRICES_TTL`, 1800s) than the chart cache, since this backs price alerts and should track `price_check_interval` more closely than `cache_ttl`.

**hotline.ua API** — uses the undocumented GraphQL endpoint at `https://hotline.ua/svc/frontend-api/graphql`, operation `getChart`. This requires no authentication. The `byPathQueryProduct` operation does require auth and is not used. `getChart` returns several distinct price series, not one: `priceUAH`/`priceUSD` (used for the dashboard's displayed price, the chart, and totals — appears to be an average/typical price across sellers, not the cheapest) and `minPriceUAH` (the actual lowest current seller offer, used only for price-target alert comparisons — see **Price-target email alerts** above). The two can differ by a meaningful margin and move independently; don't assume a stalled `priceUAH` means stale data before checking whether `minPriceUAH` already moved.

**Stale chart detection** — hotline.ua sometimes keeps `quantity` (seller count) updating daily for a product while its `priceUAH`/`minPriceUAH` series silently stop moving for weeks/months (observed: Samsung 980 PRO SSD frozen at 04.06.2026 with today's `quantity` still fresh). `_get_product()` in `app.py` checks the last `priceUAH` point's date via `_chart_stale_since()`; if it's more than `_STALE_CHART_DAYS` (3) days old, it now falls back to `_get_offer_prices()` (see **Per-seller offer scraping**) — if that returns real offers, the dashboard shows `price_uah = mean(offer_prices)` (matching `priceUAH`'s usual "typical/average price" semantics), `min_price_uah = min(offer_prices)`, and `quantity = len(offer_prices)`, instead of an error badge; only if the scrape also comes back empty does it fall through to the original `error` badge behavior — except `price_uah` still gets the last known (stale) chart price in that case too (everything else stays zeroed), so `ProductSummary.price_diff`/`total_diff` (vs. purchase price) aren't blanked out just because the price itself is too old to trust for display; the dashboard template still hides the price/min-price/total cells for any row with `error` set, showing only the diff. `_check_price_alerts()` doesn't go through `_get_product()`/this fallback at all — it calls `_get_offer_prices()` directly for every priced product regardless of chart staleness, and always compares against `min(offer_prices)` (see **Price-target email alerts**), not the average — a target-price hit should fire on the cheapest available offer, not a blended one.

**DB auto-creation** — `create_db_if_not_exists(sync_url)` (plain `psycopg`, checking `pg_database` and issuing `CREATE DATABASE` against the `postgres` maintenance database — no `sqlalchemy_utils` dependency) is called in the FastAPI lifespan before `init_db`. Tables are managed exclusively by Alembic — run `alembic upgrade head` manually after first deploy.

**SQLAlchemy driver** — `psycopg[binary]==3.3.6` is the only PostgreSQL driver. Async URL uses `postgresql+psycopg_async://`; sync URL (for `create_db_if_not_exists` and Alembic) uses `postgresql+psycopg://` — both derived from the plain `database_url` in config via `sync_database_url` / `async_database_url` properties.

**Migrations on start** — `entrypoint.sh` runs `alembic upgrade head` before starting uvicorn, so the schema is always current after a container restart or redeploy.

**Static versioning** — `STATIC_VERSION` env var (set by Ansible from MD5 of `style.css + i18n.js`) is exposed as Jinja2 global `static_version` and appended as `?v=` to all CSS/JS URLs. Cloudflare cache is purged after each deploy.

**Subpath deployment** — `ROOT_PATH` env var (e.g. `/hotline-listing`, for a subpath deployment) is read at startup and set as a Jinja2 global. All template links and JS fetch URLs use `{{ root_path }}/...` / `${ROOT_PATH}/...`. Production now serves from its own subdomain (`hotline-listing.zelgray.work`), so `ROOT_PATH` is empty there too — this mechanism only matters again if the app is ever put back behind a subpath.

**config.yaml resolution** — `app.py` reads `Path(os.getenv('CONFIG_PATH', 'config.yaml'))`. When unset, this is relative to CWD. Run uvicorn and alembic from the project root so they find `config.yaml` there. In Docker, CWD is `/app` and the Ansible role mounts `config.yaml` at `/app/config.yaml`.

**Sparklines** — SVG polyline generated server-side as a Jinja2 filter (`_sparkline`) over the last 60 price points from the chart API.

**Template rendering** — `fastapi`'s pinned `starlette` transitive dependency requires the new `Jinja2Templates.TemplateResponse(request, name, context)` signature (request first). Calling it the old way (`TemplateResponse(name, context)`) silently misassigns the context dict as `name`, which crashes deep inside Jinja2's template cache lookup (`TypeError: unhashable type: 'dict'`).

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

## Testing

```bash
uv sync --group dev
.venv/bin/python3 -m pytest
```

Requires Docker — `tests/test_db.py` and every test using the `client`/`db_ready` fixtures spin up a real ephemeral PostgreSQL via `testcontainers` (one container per test session). Redis is faked in-process (`fakeredis`, monkeypatched over `aioredis.from_url`), hotline.ua HTTP calls are mocked (`httpx.MockTransport` via the `fake_hotline` fixture), and no local Postgres/Redis setup is needed. `pyproject.toml`'s `[tool.pytest.ini_options]` sets `pythonpath = ["sources/src"]`, so no `PYTHONPATH` env var is needed when running via `pytest`/`uv`.

`tests/conftest.py` writes its own temp `config.yaml` pointing at the ephemeral DB and sets `CONFIG_PATH` before `hotline_prices.app` is first imported — that module reads `config.yaml` at import time with no env-var override (see **config.yaml resolution** below), so test files must never import `hotline_prices.app` at module top level; only through the `app_module`/`client` fixtures (see the module docstring in `conftest.py`).

Test files roughly mirror `sources/src/hotline_prices/*.py` one-to-one (`test_nuxt_parser.py`, `test_client.py`, `test_config.py`, `test_models.py`, `test_cache.py`, `test_db.py`, `test_notifications.py`, `test_app_helpers.py`, `test_app_pricing.py`, `test_app_routes.py`), plus `tests/fixtures/` holding a real captured hotline.ua page for `nuxt_parser` regression testing.

## Deployment (Ansible)

```bash
./install_dependencies.sh
cd ansible
ansible-playbook -i inventories/zelgray.work playbooks/deploy.yml
```

Requires env: `INFISICAL_API_URL`, `INFISICAL_CLIENT_ID`, `INFISICAL_CLIENT_SECRET`.
The role syncs `sources/` from `hotline_listing_local_source_dir` to the target host, builds the Docker image there, templates `config.yaml`, and starts the container.
