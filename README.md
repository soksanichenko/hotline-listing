# hotline-listing

Multi-tenant price-tracking dashboard for hotline.ua. Each user gets a UUID-based URL — no registration required. The UUID is the access token for the read-only dashboard/chart views (deliberately left open behind the Discord gate, so a share link works for anyone).

## Features

- **Dashboard** — price table with current UAH price, sparkline trend (last 60 days), purchase price/total comparison, and value change vs. purchase price
- **Price charts** — per-product price history page with UAH and USD axes (Chart.js), accessible from the dashboard
- **Editor** — add/remove products via a web form with URL, title, count, purchase price, and purchase date; export current list as YAML
- **YAML import** — upload an existing `config.yaml` to populate a new dashboard
- **Caching** — chart data is cached in Redis per product (default 1 hour)
- **i18n** — UI language toggle: Ukrainian / English / Russian (persisted in localStorage)
- **"My tables"** — configs are tied server-side to the creating Discord user (`owner_discord_user_id`, via `X-Discord-User-Id` forwarded by the nginx gate on `/`, `/import`, and the `/{id}/edit|save|delete` locations); the landing page lists them from the DB, so they follow you across browsers/devices instead of a per-browser `localStorage` list. `/{id}/edit` and `/{id}/save` are owner-only (403 otherwise); the ✕ button on the landing page really deletes the config. Configs created before this existed have no recorded owner and remain open to any Discord-authenticated user, same as before.

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

### Product format

```yaml
products:
  - url: https://hotline.ua/ua/<category>/<product-slug>/
    title: "Optional display name"
    count: 1
    purchase_price: 9999
    purchase_date: 2025-01-01
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

The app is deployed to `zelgray.work/hotline-listing/` via Ansible.

```bash
# Install Ansible tooling and Galaxy collections
./install_dependencies.sh

# Run the playbook (requires INFISICAL_API_URL, INFISICAL_CLIENT_ID, INFISICAL_CLIENT_SECRET)
cd ansible
ansible-playbook -i inventories/zelgray.work playbooks/deploy.yml
```

The container is built on the target host from `sources/` synced by the playbook.
`ROOT_PATH=/hotline-listing` is set automatically by the Ansible role. Alembic migrations run automatically on container start via `entrypoint.sh`.

## License

[MIT](https://opensource.org/licenses/MIT)
