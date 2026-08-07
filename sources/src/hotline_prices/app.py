"""FastAPI application: multi-tenant Hotline price dashboard."""

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import httpx
import yaml
from fastapi import FastAPI, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .cache import Cache
from .client import extract_path, fetch_chart
from .config import AppConfig, ProductConfig
from .db import (
    config_create,
    config_delete,
    config_get,
    config_get_owner,
    config_update,
    configs_list_for_owner,
    create_db_if_not_exists,
    init_db,
)
from .models import ProductSummary

logger = logging.getLogger(__name__)

_ROOT = Path(__file__).parent.parent.parent
_ROOT_PATH = os.getenv("ROOT_PATH", "")
config = AppConfig.from_yaml(Path(os.getenv("CONFIG_PATH", "config.yaml")))

templates = Jinja2Templates(directory=_ROOT / "templates")
_cache: Cache | None = None
_http: httpx.AsyncClient | None = None


# ── Jinja2 filters ────────────────────────────────────────────────────────────


def _fmt_uah(value: float) -> str:
    return f"{value:,.0f} ₴".replace(",", " ")


def _fmt_usd(value: float) -> str:
    return f"${value:,.2f}"


def _sparkline(prices: list[float]) -> str:
    if len(prices) < 2:
        return ""
    mn, mx = min(prices), max(prices)
    rng = mx - mn or 1
    w, h = 90, 28
    pts = [
        f"{i / (len(prices) - 1) * w:.1f},{h - (p - mn) / rng * (h - 4) - 2:.1f}"
        for i, p in enumerate(prices)
    ]
    return " ".join(pts)


templates.env.filters["uah"] = _fmt_uah
templates.env.filters["usd"] = _fmt_usd
templates.env.filters["sparkline"] = _sparkline
# ROOT_PATH is set by the reverse proxy deployment (e.g., '/hotline-listing').
# Empty string means the app is served at the root.
templates.env.globals["root_path"] = os.getenv("ROOT_PATH", "")
templates.env.globals["static_version"] = os.getenv("STATIC_VERSION", "")


# ── Lifespan ──────────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(_: FastAPI):
    global _cache, _http
    create_db_if_not_exists(config.sync_database_url)
    init_db(config.async_database_url)
    _cache = Cache(config.redis_url, config.cache_ttl)
    _http = httpx.AsyncClient(timeout=15.0)
    yield
    await _cache.close()
    await _http.aclose()


app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory=_ROOT / "static"), name="static")


# ── Shared helpers ────────────────────────────────────────────────────────────


def _parse_hotline_date(ts: str) -> str:
    """Convert DD.MM.YYYY to ISO 8601 (YYYY-MM-DD) for JS Date parsing."""
    try:
        return datetime.strptime(ts, "%d.%m.%Y").replace(tzinfo=UTC).date().isoformat()
    except (ValueError, TypeError):
        return ts


def _normalize_series(series: list) -> list:
    return [[_parse_hotline_date(ts), price] for ts, price in series]


def _slug_to_title(path: str) -> str:
    return path.replace("-", " ").title()


async def _get_product(product: ProductConfig) -> ProductSummary:
    path = extract_path(product.url)
    chart_key = f"hotline:chart:{path}"

    try:
        chart = await _cache.get(chart_key)
        if chart is None:
            chart = await fetch_chart(_http, path)
            await _cache.set(chart_key, chart)
    except Exception as exc:
        logger.exception("Failed to fetch chart for %s", path)
        return ProductSummary(
            path=path,
            title=product.title or _slug_to_title(path),
            hotline_url=product.url,
            price_uah=0,
            price_usd=0,
            quantity=0,
            count=product.count,
            purchase_price=product.purchase_price,
            purchase_date=product.purchase_date,
            error=str(exc),
        )

    uah_series = chart["priceUAH"]
    usd_series = chart["priceUSD"]
    qty_series = chart["quantity"]

    return ProductSummary(
        path=path,
        title=product.title or _slug_to_title(path),
        hotline_url=product.url,
        price_uah=uah_series[-1][1] if uah_series else 0,
        price_usd=usd_series[-1][1] if usd_series else 0,
        quantity=qty_series[-1][1] if qty_series else 0,
        count=product.count,
        purchase_price=product.purchase_price,
        purchase_date=product.purchase_date,
        price_history_uah=[p for _, p in uah_series[-60:]],
    )


def _render_ctx(products: list[ProductSummary], request: Request, **extra) -> dict:
    ok = [p for p in products if not p.error]
    diffs = [p.total_diff for p in ok if p.total_diff is not None]
    purchases = [p.purchase_price * p.count for p in ok if p.purchase_price is not None]
    return {
        "request": request,
        "products": products,
        "total_uah": sum(p.total_uah for p in ok),
        "total_usd": sum(p.total_usd for p in ok),
        "total_purchase": sum(purchases) if purchases else None,
        "total_diff": sum(diffs) if diffs else None,
        "updated_at": datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"),
        "cache_ttl_min": config.cache_ttl // 60,
        **extra,
    }


def _db_to_products(data: dict) -> list[ProductConfig]:
    return [ProductConfig(**p) for p in data.get("products", [])]


async def _require_owner(config_id: UUID, request: Request) -> None:
    """Raise 404 if the config doesn't exist, 403 if it's owned by someone
    else. Legacy configs created before ownership tracking existed have no
    owner recorded and remain open to any Discord-authenticated user.
    """
    exists, owner = await config_get_owner(config_id)
    if not exists:
        raise HTTPException(status_code=404, detail="Config not found")
    if owner is not None and owner != request.headers.get("X-Discord-User-Id"):
        raise HTTPException(status_code=403, detail="Not the owner of this config")


def _products_to_db(products: list[ProductConfig]) -> dict:
    return {
        "products": [
            {
                k: v
                for k, v in p.model_dump(mode="json").items()
                if v is not None or k in ("url", "count")
            }
            for p in products
        ]
    }


# ── Routes: landing ───────────────────────────────────────────────────────────


@app.get("/", response_class=HTMLResponse)
async def landing(request: Request) -> HTMLResponse:
    discord_user_id = request.headers.get("X-Discord-User-Id")
    my_configs = (
        await configs_list_for_owner(discord_user_id) if discord_user_id else []
    )
    return templates.TemplateResponse(
        request,
        "landing.html",
        {
            "request": request,
            "avatar_url": request.headers.get("X-Discord-Avatar-Url"),
            "my_configs": my_configs,
        },
    )


@app.post("/")
async def create_config(request: Request) -> RedirectResponse:
    """Create an empty config, owned by the requesting Discord user, and
    redirect to its editor."""
    config_id = await config_create(
        {"products": []}, owner_discord_user_id=request.headers.get("X-Discord-User-Id")
    )
    return RedirectResponse(f"{_ROOT_PATH}/{config_id}/edit", status_code=303)


@app.post("/import")
async def import_yaml(file: UploadFile, request: Request) -> RedirectResponse:
    """Parse an uploaded YAML config and store it as a new config, owned by
    the requesting Discord user."""
    raw = await file.read()
    try:
        data = yaml.safe_load(raw)
        products = [
            ProductConfig(**p) if isinstance(p, dict) else ProductConfig(url=p)
            for p in data.get("products", [])
            if p
        ]
    except Exception as exc:
        logger.exception("Failed to parse uploaded YAML config")
        raise HTTPException(status_code=400, detail=f"Invalid YAML: {exc}")
    config_id = await config_create(
        _products_to_db(products),
        owner_discord_user_id=request.headers.get("X-Discord-User-Id"),
    )
    return RedirectResponse(f"{_ROOT_PATH}/{config_id}/edit", status_code=303)


@app.post("/logout")
async def logout() -> RedirectResponse:
    """Clears the Discord-bridged `zw_session` cookie the portal set on
    zelgray.work — a purely local action, not a real Discord logout: this
    app has no session of its own to clear (no local login exists here at
    all), and as long as `portal_session` is still valid on
    meow-elite.club, the very next Discord-gated page load re-bridges a
    fresh `zw_session` automatically. Same cookie every zelgray.work-rooted
    gated service shares, so this also affects any of them open in the
    same browser — not a bug, that's the point of a root-domain-scoped
    session.
    """
    response = RedirectResponse(f"{_ROOT_PATH}/", status_code=303)
    response.delete_cookie("zw_session", domain="zelgray.work", path="/")
    return response


# ── Routes: dashboard ─────────────────────────────────────────────────────────


@app.get("/{config_id}", response_class=HTMLResponse)
async def dashboard(config_id: UUID, request: Request) -> HTMLResponse:
    data = await config_get(config_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Config not found")

    product_cfgs = _db_to_products(data)
    products = list(await asyncio.gather(*[_get_product(p) for p in product_cfgs]))
    ctx = _render_ctx(products, request, config_id=config_id)
    return templates.TemplateResponse(request, "dashboard.html", ctx)


# ── Routes: chart ─────────────────────────────────────────────────────────────


@app.get("/{config_id}/chart/{product_slug}", response_class=HTMLResponse)
async def product_chart(
    config_id: UUID, product_slug: str, request: Request
) -> HTMLResponse:
    data = await config_get(config_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Config not found")

    product_cfgs = _db_to_products(data)
    matched = next(
        (p for p in product_cfgs if extract_path(p.url) == product_slug), None
    )
    title = matched.title if matched and matched.title else _slug_to_title(product_slug)
    hotline_url = matched.url if matched else None

    chart_key = f"hotline:chart:{product_slug}"
    try:
        chart = await _cache.get(chart_key)
        if chart is None:
            chart = await fetch_chart(_http, product_slug)
            await _cache.set(chart_key, chart)
    except Exception as exc:
        logger.exception("Failed to fetch chart data for %s", product_slug)
        raise HTTPException(
            status_code=502, detail=f"Failed to fetch chart data: {exc}"
        )

    return templates.TemplateResponse(
        request,
        "chart.html",
        {
            "request": request,
            "config_id": config_id,
            "title": title,
            "hotline_url": hotline_url,
            "uah_series": _normalize_series(chart.get("priceUAH", [])),
            "usd_series": _normalize_series(chart.get("priceUSD", [])),
            "qty_series": chart.get("quantity", []),
        },
    )


# ── Routes: editor ────────────────────────────────────────────────────────────


@app.get("/{config_id}/edit", response_class=HTMLResponse)
async def edit_form(config_id: UUID, request: Request) -> HTMLResponse:
    await _require_owner(config_id, request)
    data = await config_get(config_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Config not found")
    products = _db_to_products(data)
    return templates.TemplateResponse(
        request,
        "edit.html",
        {
            "request": request,
            "config_id": config_id,
            "products": products,
            "avatar_url": request.headers.get("X-Discord-Avatar-Url"),
        },
    )


@app.post("/{config_id}/save")
async def save_config(config_id: UUID, request: Request) -> RedirectResponse:
    """Accept JSON body {products: [...]} and persist to DB."""
    await _require_owner(config_id, request)
    body = await request.json()
    try:
        products = [ProductConfig(**p) for p in body.get("products", [])]
    except Exception as exc:
        logger.exception("Invalid product data for config %s", config_id)
        raise HTTPException(status_code=422, detail=str(exc))
    updated = await config_update(config_id, _products_to_db(products))
    if not updated:
        raise HTTPException(status_code=404, detail="Config not found")
    return RedirectResponse(f"{_ROOT_PATH}/{config_id}", status_code=303)


@app.post("/{config_id}/delete")
async def delete_config(config_id: UUID, request: Request) -> RedirectResponse:
    """Delete a config. Owner-only (unowned legacy configs are open to any
    Discord-authenticated user, same rule as edit/save)."""
    await _require_owner(config_id, request)
    await config_delete(config_id)
    return RedirectResponse(f"{_ROOT_PATH}/", status_code=303)
