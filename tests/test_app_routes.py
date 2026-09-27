"""HTTP route tests via FastAPI TestClient."""

import sqlalchemy


def _create_config(client, owner=None, email=None):
    headers = {}
    if owner:
        headers["X-Discord-User-Id"] = owner
    if email:
        headers["X-Discord-Email"] = email
    resp = client.post("/", headers=headers, follow_redirects=False)
    return resp.headers["location"].split("/")[1]


# ── landing / create / import / logout ──────────────────────────────────────


def test_landing_page_anonymous(client):
    resp = client.get("/")
    assert resp.status_code == 200


def test_landing_lists_only_own_configs(client):
    config_id = _create_config(client, owner="owner-1")

    resp_owner = client.get("/", headers={"X-Discord-User-Id": "owner-1"})
    assert config_id in resp_owner.text

    resp_anon = client.get("/")
    assert config_id not in resp_anon.text


def test_create_config_redirects_to_edit(client):
    resp = client.post("/", headers={"X-Discord-User-Id": "u1"}, follow_redirects=False)
    assert resp.status_code == 303
    location = resp.headers["location"]
    assert location.endswith("/edit")
    config_id = location.split("/")[1]

    edit_resp = client.get(f"/{config_id}/edit", headers={"X-Discord-User-Id": "u1"})
    assert edit_resp.status_code == 200


def test_import_yaml_happy_path(client):
    yaml_body = b"products:\n  - url: https://hotline.ua/ua/cat/some-item/\n"
    resp = client.post(
        "/import",
        files={"file": ("cfg.yaml", yaml_body, "text/yaml")},
        headers={"X-Discord-User-Id": "u1"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    config_id = resp.headers["location"].split("/")[1]

    edit_resp = client.get(f"/{config_id}/edit", headers={"X-Discord-User-Id": "u1"})
    assert "some-item" in edit_resp.text


def test_import_yaml_with_name(client):
    yaml_body = (
        b"name: Laptops\nproducts:\n  - url: https://hotline.ua/ua/cat/some-item/\n"
    )
    resp = client.post(
        "/import",
        files={"file": ("cfg.yaml", yaml_body, "text/yaml")},
        headers={"X-Discord-User-Id": "u1"},
        follow_redirects=False,
    )
    config_id = resp.headers["location"].split("/")[1]
    edit_resp = client.get(f"/{config_id}/edit", headers={"X-Discord-User-Id": "u1"})
    assert "Laptops" in edit_resp.text


def test_import_invalid_yaml_returns_400(client):
    resp = client.post(
        "/import",
        files={"file": ("cfg.yaml", b"not: valid: yaml: at: all: ][", "text/yaml")},
    )
    assert resp.status_code == 400


def test_import_missing_required_field_returns_400(client):
    resp = client.post(
        "/import",
        files={
            "file": ("cfg.yaml", b"products:\n  - title: no url here\n", "text/yaml")
        },
    )
    assert resp.status_code == 400


def test_logout_clears_cookie(client):
    resp = client.post("/logout", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"].endswith("/")
    set_cookie = resp.headers.get("set-cookie", "")
    assert "zw_session=" in set_cookie
    assert "Max-Age=0" in set_cookie or "max-age=0" in set_cookie.lower()


# ── dashboard ────────────────────────────────────────────────────────────────


def test_dashboard_404_for_unknown_config(client):
    resp = client.get("/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404


def test_dashboard_empty_products_200(client):
    config_id = _create_config(client)
    resp = client.get(f"/{config_id}")
    assert resp.status_code == 200


def test_dashboard_renders_chart_price(client, fake_hotline):
    fake_hotline.set_chart(
        "some-item",
        {
            "priceUAH": [["27.09.2026", 999]],
            "minPriceUAH": [["27.09.2026", 900]],
            "priceUSD": [["27.09.2026", 25]],
            "quantity": [["27.09.2026", 3]],
        },
    )
    config_id = _create_config(client, owner="u1")
    client.post(
        f"/{config_id}/save",
        headers={"X-Discord-User-Id": "u1"},
        json={"products": [{"url": "https://hotline.ua/ua/cat/some-item/"}]},
    )
    resp = client.get(f"/{config_id}")
    assert resp.status_code == 200
    assert "999" in resp.text


# ── chart ────────────────────────────────────────────────────────────────────


def test_chart_404_for_unknown_config(client):
    resp = client.get("/00000000-0000-0000-0000-000000000000/chart/some-slug")
    assert resp.status_code == 404


def test_chart_matched_product_uses_its_title(client, fake_hotline):
    fake_hotline.set_chart(
        "some-item", {"priceUAH": [], "priceUSD": [], "quantity": []}
    )
    config_id = _create_config(client, owner="u1")
    client.post(
        f"/{config_id}/save",
        headers={"X-Discord-User-Id": "u1"},
        json={
            "products": [
                {"url": "https://hotline.ua/ua/cat/some-item/", "title": "My Title"}
            ]
        },
    )
    resp = client.get(f"/{config_id}/chart/some-item")
    assert resp.status_code == 200
    assert "My Title" in resp.text


def test_chart_unmatched_slug_still_renders(client, fake_hotline):
    config_id = _create_config(client)
    resp = client.get(f"/{config_id}/chart/no-such-product")
    assert resp.status_code == 200


# ── edit / ownership ─────────────────────────────────────────────────────────


def test_edit_404_for_unknown_config(client):
    resp = client.get("/00000000-0000-0000-0000-000000000000/edit")
    assert resp.status_code == 404


def test_edit_403_for_non_owner(client):
    config_id = _create_config(client, owner="owner-1")
    resp = client.get(f"/{config_id}/edit", headers={"X-Discord-User-Id": "other-user"})
    assert resp.status_code == 403


def test_edit_403_for_owned_config_without_header(client):
    config_id = _create_config(client, owner="owner-1")
    resp = client.get(f"/{config_id}/edit")
    assert resp.status_code == 403


def test_edit_200_for_owner(client):
    config_id = _create_config(client, owner="owner-1")
    resp = client.get(f"/{config_id}/edit", headers={"X-Discord-User-Id": "owner-1"})
    assert resp.status_code == 200


def test_edit_200_and_unclaimed_for_legacy_config(client, database_url):
    config_id = _create_config(client)  # no owner header -> unowned/legacy
    resp = client.get(f"/{config_id}/edit", headers={"X-Discord-User-Id": "anyone"})
    assert resp.status_code == 200


# ── claim ────────────────────────────────────────────────────────────────────


def test_claim_binds_unowned_config(client, database_url):
    config_id = _create_config(client)  # legacy/unowned

    resp = client.post(
        f"/{config_id}/claim",
        headers={"X-Discord-User-Id": "claimer"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"].endswith("/edit")

    sync_url = database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    engine = sqlalchemy.create_engine(sync_url)
    with engine.connect() as conn:
        owner = conn.execute(
            sqlalchemy.text("SELECT owner_discord_user_id FROM configs WHERE id = :id"),
            {"id": config_id},
        ).scalar_one()
    engine.dispose()
    assert owner == "claimer"


def test_claim_by_different_user_after_claim_is_403(client):
    config_id = _create_config(client)  # legacy/unowned
    client.post(f"/{config_id}/claim", headers={"X-Discord-User-Id": "first"})

    resp = client.post(f"/{config_id}/claim", headers={"X-Discord-User-Id": "second"})
    assert resp.status_code == 403


def test_claim_already_owned_by_same_user_is_noop(client):
    config_id = _create_config(client, owner="owner-1")
    resp = client.post(
        f"/{config_id}/claim",
        headers={"X-Discord-User-Id": "owner-1"},
        follow_redirects=False,
    )
    assert resp.status_code == 303


# ── save ─────────────────────────────────────────────────────────────────────


def test_save_happy_path_persists_and_redirects(client):
    config_id = _create_config(client, owner="owner-1")
    resp = client.post(
        f"/{config_id}/save",
        headers={"X-Discord-User-Id": "owner-1"},
        json={"products": [{"url": "https://hotline.ua/ua/cat/some-item/"}]},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == f"/{config_id}"

    edit_resp = client.get(
        f"/{config_id}/edit", headers={"X-Discord-User-Id": "owner-1"}
    )
    assert "some-item" in edit_resp.text


def test_save_name_persists_and_shows_up_everywhere(client):
    config_id = _create_config(client, owner="owner-1")
    client.post(
        f"/{config_id}/save",
        headers={"X-Discord-User-Id": "owner-1"},
        json={"products": [], "name": "Laptops"},
    )

    edit_resp = client.get(
        f"/{config_id}/edit", headers={"X-Discord-User-Id": "owner-1"}
    )
    assert "Laptops" in edit_resp.text

    dashboard_resp = client.get(f"/{config_id}")
    assert "Laptops" in dashboard_resp.text

    landing_resp = client.get("/", headers={"X-Discord-User-Id": "owner-1"})
    assert "Laptops" in landing_resp.text


def test_save_empty_name_clears_it(client):
    config_id = _create_config(client, owner="owner-1")
    client.post(
        f"/{config_id}/save",
        headers={"X-Discord-User-Id": "owner-1"},
        json={"products": [], "name": "Laptops"},
    )
    client.post(
        f"/{config_id}/save",
        headers={"X-Discord-User-Id": "owner-1"},
        json={"products": [], "name": ""},
    )
    edit_resp = client.get(
        f"/{config_id}/edit", headers={"X-Discord-User-Id": "owner-1"}
    )
    assert "Laptops" not in edit_resp.text


def test_save_invalid_product_returns_422(client):
    config_id = _create_config(client, owner="owner-1")
    resp = client.post(
        f"/{config_id}/save",
        headers={"X-Discord-User-Id": "owner-1"},
        json={"products": [{"title": "missing url"}]},
    )
    assert resp.status_code == 422


def test_save_404_for_unknown_config(client):
    resp = client.post(
        "/00000000-0000-0000-0000-000000000000/save", json={"products": []}
    )
    assert resp.status_code == 404


def test_save_403_for_non_owner(client):
    config_id = _create_config(client, owner="owner-1")
    resp = client.post(
        f"/{config_id}/save",
        headers={"X-Discord-User-Id": "other"},
        json={"products": []},
    )
    assert resp.status_code == 403


def test_save_refreshes_owner_email(client, database_url):
    config_id = _create_config(client, owner="owner-1")
    client.post(
        f"/{config_id}/save",
        headers={
            "X-Discord-User-Id": "owner-1",
            "X-Discord-Email": "owner@example.com",
        },
        json={"products": []},
    )
    sync_url = database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    engine = sqlalchemy.create_engine(sync_url)
    with engine.connect() as conn:
        email = conn.execute(
            sqlalchemy.text("SELECT owner_discord_email FROM configs WHERE id = :id"),
            {"id": config_id},
        ).scalar_one()
    engine.dispose()
    assert email == "owner@example.com"


# ── delete ───────────────────────────────────────────────────────────────────


def test_delete_403_for_non_owner(client):
    config_id = _create_config(client, owner="owner-1")
    resp = client.post(f"/{config_id}/delete", headers={"X-Discord-User-Id": "other"})
    assert resp.status_code == 403


def test_delete_happy_path(client):
    config_id = _create_config(client, owner="owner-1")
    resp = client.post(
        f"/{config_id}/delete",
        headers={"X-Discord-User-Id": "owner-1"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"].endswith("/")

    resp = client.get(f"/{config_id}")
    assert resp.status_code == 404
