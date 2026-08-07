# hotline-listing

Deploys the hotline-listing FastAPI service as a Docker container on the target host and wires it into the nginx reverse proxy at `/hotline-listing/`.

## What it does

1. Creates the data directory at `{{ hotline_listing_data_dir }}`
2. Syncs `sources/` from the Ansible controller to `{{ hotline_listing_data_dir }}/` (Docker build context)
3. Builds the Docker image locally on the target host from the synced source
4. Templates `config.yaml` (Redis URL, database URL, cache TTL) into the data directory
5. Starts the container with `config.yaml` mounted read-only and `ROOT_PATH` + `STATIC_VERSION` env vars set
6. Deploys the nginx upstream config to `custom-upstream/` and the location config at `/hotline-listing/` (when `hotline_listing_nginx_proxy: true`)
7. Purges the Cloudflare cache (when `cf_purge_cache: true`)

## Variables

| Variable | Default | Description |
|---|---|---|
| `hotline_listing_container_name` | `hotline-listing` | Docker container name |
| `hotline_listing_image` | `hotline-listing:local` | Image name:tag (built on host) |
| `hotline_listing_http_port` | `8999` | Port the container listens on |
| `hotline_listing_data_dir` | `{{ docker_volumes_directory }}/hotline-listing` | Data and build directory on target |
| `hotline_listing_nginx_proxy` | `false` | Set to `true` to deploy the nginx upstream + location config |
| `hotline_listing_upstream_name` | `hotline_listing_upstream` | Nginx upstream block name; referenced by the location config's `proxy_pass` |
| `hotline_listing_root_path` | `/hotline-listing` | URL prefix passed to the app as `ROOT_PATH` |
| `hotline_listing_local_source_dir` | `{{ playbook_dir }}/../..` | Project root on the Ansible controller (resolved relative to the playbook) |
| `hotline_listing_database_url` | `postgresql://postgres:{{ postgres_password }}@{{ postgresql_container_name }}:5432/hotline_prices` | PostgreSQL URL written into config.yaml |
| `hotline_listing_redis_url` | `redis://{{ redis_container_name }}:6379` | Redis URL written into config.yaml |
| `hotline_listing_cache_ttl` | `3600` | Chart cache TTL in seconds |
| `hotline_listing_city_id` | `154` | City ID (Kyiv) |
| `meow_elite_club_portal_upstream_name` | `meow_elite_club_portal_upstream` | Nginx upstream name for the Discord SSO gate's `/auth` and `/bridge/consume` endpoints |
| `hotline_listing_service_slug` | `hotline-listing` | `X-Service-Slug` sent to `/auth`; also the `slug` this role self-registers as its `GatedService` row |
| `meow_elite_club_portal_service_registration_token` | *(from Infisical `/hosts/shared` `meow-elite-club-portal-service-registration-token`)* | Bearer token for `POST /api/services/register` |

## Tags

| Tag | Effect |
|---|---|
| `hotline-listing` | Run all tasks |
| `hotline-listing-nginx` | Nginx config only |
| `cf-purge` | Cloudflare cache purge only |

## Usage

```bash
cd ansible
ansible-playbook -i inventories/zelgray.work playbooks/deploy.yml
```

Force image rebuild regardless of source changes:

```bash
ansible-playbook -i inventories/zelgray.work playbooks/deploy.yml \
  -e docker_force_recreate=true
```

## Notes

- The PostgreSQL database (`hotline_prices`) is created automatically at container startup via `sqlalchemy_utils`. Alembic migrations also run automatically on every container start via `entrypoint.sh` — no manual step needed.
- The image is built on the **target host** from `sources/` synced by this role. It is not pulled from a registry.
- `hotline_listing_nginx_proxy` is `false` by default — set it in `group_vars/all.yml` to enable nginx integration.
- List creation/editing (`/hotline-listing/`, `/hotline-listing/import`, `/hotline-listing/{id}/edit`, `/hotline-listing/{id}/save`) is gated behind the Discord SSO gate (`meow-elite-club-portal`, `auth_request` + `/internal/bridge`, see `docs/portal-architecture.md` in `infra`). The read-only per-config dashboard (`/hotline-listing/{id}`, `/hotline-listing/{id}/chart/...`) is intentionally left open — the UUID is the share link's access token, and gating it would break sharing a dashboard with someone outside the allow-list.
- The gate enforces per-service access, not just "any valid Discord session": a `GatedService(slug="hotline-listing")` row and at least one `ServiceAccess` grant (individual Discord user or guild) must exist. The `GatedService` row is created/updated automatically on every deploy (`POST /api/services/register`, Bearer-token auth — see `meow-elite-club-portal`'s own role README); `ServiceAccess` grants remain entirely manual, through `/admin/services`.
- The landing and editor pages show a top-right "logged in as" menu (Discord avatar, or a plain placeholder if the visitor has no custom one, plus a Log out button) — the two gated locations now also capture and forward `X-Discord-Avatar-Url`. This app has no login of its own, so `POST /logout` only clears the `zw_session` cookie the portal set on `zelgray.work` — a purely local action, not a real Discord sign-out: `portal_session` on meow-elite.club stays valid, so the very next Discord-gated page load just re-bridges a fresh `zw_session` automatically. That's the point (force-refreshing a stale one), not a bug. `zw_session` is root-domain-scoped, so this also affects any other `zelgray.work`-rooted gated service open in the same browser (e.g. `vless-config-generator`) — not new coupling, just how the shared bridge cookie already worked.
