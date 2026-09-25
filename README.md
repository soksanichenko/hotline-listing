# hotline-listing

Multi-tenant price-tracking dashboard for hotline.ua. Each user gets a UUID-based URL — no registration required. The UUID is the access token for the read-only dashboard/chart views (deliberately left open behind the Discord gate, so a share link works for anyone).

## Features

- **Dashboard** — price table with current UAH price, current minimum seller price, sparkline trend (last 60 days), purchase price/total comparison, and value change vs. purchase price
- **Price charts** — per-product price history page with UAH and USD axes (Chart.js), accessible from the dashboard
- **Editor** — add/remove products via a web form with URL, title, count, purchase price, and purchase date; export current list as YAML
- **YAML import** — upload an existing `config.yaml` to populate a new dashboard
- **Caching** — chart data is cached in Redis per product (default 1 hour)
- **i18n** — UI language toggle: Ukrainian / English / Russian (persisted in localStorage)
- **"My tables"** — configs are tied server-side to the creating Discord user (`owner_discord_user_id`, via `X-Discord-User-Id` forwarded by the nginx gate on `/`, `/import`, and the `/{id}/edit|save|delete|claim` locations); the landing page lists them from the DB, so they follow you across browsers/devices instead of a per-browser `localStorage` list. `/{id}/edit` and `/{id}/save` are owner-only (403 otherwise); the ✕ button on the landing page really deletes the config. Configs created before this existed have no recorded owner and remain open to any Discord-authenticated user, same as before — the edit page shows a "claim as mine" button for these, which binds the config to whoever clicks it first (`POST /{id}/claim`, a no-op if already claimed by you, 403 if claimed by someone else in the meantime).
- **Price-target email alerts** — set a target price on any product in the editor and you'll get an email at your Discord account's (verified) email address once the current minimum seller price drops to it or below. A checker runs periodically in the background; once notified, it stays quiet until the price rises back above the target and dips again, so you're not emailed on every check while it's still low.

## Requirements

- Python 3.12+
- PostgreSQL 15+
- Redis 7+

## Configuration

`config.yaml` is loaded at startup. All fields are optional — defaults are shown below.

| Field | Default | Description |
|---|---|---|
| `redis_url` | `redis://localhost:6379` | Redis connection string |
| `database_url` | `postgresql://postgres:postgres@localhost:5432/hotline_prices` | PostgreSQL connection string |
| `cache_ttl` | `3600` | Chart data cache TTL in seconds |
| `city_id` | `154` | City ID (154 = Kyiv) |
| `products` | `[]` | Product list — used for local dev and YAML import format |
| `price_check_interval` | `1800` | Seconds between price-target alert checks |
| `smtp_host` | `mail.zelgray.work` | SMTP server used to send price-target alert emails |
| `smtp_port` | `587` | SMTP port (STARTTLS) |
| `smtp_username` | `""` | SMTP auth username |
| `smtp_password` | `""` | SMTP auth password |
| `smtp_from` | `noreply@zelgray.work` | `From:` address on alert emails |

### Product format

```yaml
products:
  - url: https://hotline.ua/ua/<category>/<product-slug>/
    title: "Optional display name"
    count: 1
    purchase_price: 9999
    purchase_date: 2025-01-01
    target_price: 8999
```

`url` is the only required field. A bare URL string is also accepted.

## Running locally

```bash
# Install app dependencies
pip install -r sources/src/requirements.txt

# Start Redis and PostgreSQL (e.g. via Docker)
docker run -d --name redis -p 6379:6379 redis:7-alpine
docker run -d --name postgres -e POSTGRES_PASSWORD=postgres -p 5432:5432 postgres:16

# Apply database migrations
PYTHONPATH=sources/src alembic -c sources/alembic.ini upgrade head

# Start the app (run from project root so config.yaml is found in CWD)
PYTHONPATH=sources/src uvicorn hotline_prices.app:app --reload
```

Open `http://localhost:8000`.

## Deployment

The app is deployed to `hotline-listing.zelgray.work` via Ansible.

```bash
# Install Ansible tooling and Galaxy collections
./install_dependencies.sh

# Run the playbook (requires INFISICAL_API_URL, INFISICAL_CLIENT_ID, INFISICAL_CLIENT_SECRET)
cd ansible
ansible-playbook -i inventories/zelgray.work playbooks/deploy.yml
```

The container is built on the target host from `sources/` synced by the playbook.
Alembic migrations run automatically on container start via `entrypoint.sh`.

## License

[MIT](https://opensource.org/licenses/MIT)
