"""Tests for db.py's CRUD layer, against a real Postgres (see conftest.db_ready)."""

import uuid

from hotline_prices.db import (
    config_claim,
    config_create,
    config_delete,
    config_get,
    config_get_owner,
    config_set_alert_state,
    config_update,
    configs_list_for_owner,
    configs_list_with_owner_email,
)


async def test_create_then_get_roundtrip(db_ready):
    data = {"products": [{"url": "https://hotline.ua/x/y/"}]}
    config_id = await config_create(data)
    assert await config_get(config_id) == data


async def test_get_nonexistent_returns_none(db_ready):
    assert await config_get(uuid.uuid4()) is None


async def test_get_owner_variants(db_ready):
    owned = await config_create({"products": []}, owner_discord_user_id="u1")
    unowned = await config_create({"products": []})
    assert await config_get_owner(owned) == (True, "u1")
    assert await config_get_owner(unowned) == (True, None)
    assert await config_get_owner(uuid.uuid4()) == (False, None)


async def test_update_overwrites_data_and_returns_true(db_ready):
    config_id = await config_create({"products": []})
    new_data = {"products": [{"url": "https://hotline.ua/a/b/"}]}
    assert await config_update(config_id, new_data) is True
    assert await config_get(config_id) == new_data


async def test_update_nonexistent_returns_false(db_ready):
    assert await config_update(uuid.uuid4(), {"products": []}) is False


async def test_update_without_email_leaves_existing_email_unchanged(db_ready):
    config_id = await config_create(
        {"products": []}, owner_discord_email="old@example.com"
    )
    await config_update(config_id, {"products": []}, owner_discord_email=None)
    rows = await configs_list_with_owner_email()
    row = next(r for r in rows if r["id"] == config_id)
    assert row["owner_discord_email"] == "old@example.com"


async def test_update_with_email_changes_it(db_ready):
    config_id = await config_create(
        {"products": []}, owner_discord_email="old@example.com"
    )
    await config_update(
        config_id, {"products": []}, owner_discord_email="new@example.com"
    )
    rows = await configs_list_with_owner_email()
    row = next(r for r in rows if r["id"] == config_id)
    assert row["owner_discord_email"] == "new@example.com"


async def test_delete_removes_row_and_returns_true(db_ready):
    config_id = await config_create({"products": []})
    assert await config_delete(config_id) is True
    assert await config_get(config_id) is None


async def test_delete_nonexistent_returns_false(db_ready):
    assert await config_delete(uuid.uuid4()) is False


async def test_claim_succeeds_on_unowned_config(db_ready):
    config_id = await config_create({"products": []})
    assert (
        await config_claim(config_id, "u1", owner_discord_email="u1@example.com")
        is True
    )
    assert await config_get_owner(config_id) == (True, "u1")


async def test_claim_fails_on_already_owned_config(db_ready):
    config_id = await config_create({"products": []}, owner_discord_user_id="u1")
    assert await config_claim(config_id, "u2") is False
    assert await config_get_owner(config_id) == (True, "u1")


async def test_two_sequential_claims_first_wins(db_ready):
    config_id = await config_create({"products": []})
    assert await config_claim(config_id, "first") is True
    assert await config_claim(config_id, "second") is False
    assert await config_get_owner(config_id) == (True, "first")


async def test_list_with_owner_email_filters_and_shapes(db_ready):
    with_email = await config_create(
        {"products": []}, owner_discord_email="a@example.com"
    )
    await config_create({"products": []})  # no email — must not appear
    rows = await configs_list_with_owner_email()
    ids = {r["id"] for r in rows}
    assert ids == {with_email}
    row = rows[0]
    assert set(row) == {"id", "data", "owner_discord_email", "alert_state"}
    assert row["alert_state"] == {}


async def test_set_alert_state_overwrites(db_ready):
    config_id = await config_create(
        {"products": []}, owner_discord_email="a@example.com"
    )
    await config_set_alert_state(config_id, {"https://x/": {"armed": False}})
    rows = await configs_list_with_owner_email()
    row = next(r for r in rows if r["id"] == config_id)
    assert row["alert_state"] == {"https://x/": {"armed": False}}


async def test_list_for_owner_scoped_and_shaped(db_ready):
    mine = await config_create(
        {"products": [{"url": "https://hotline.ua/a/b/"}]}, owner_discord_user_id="me"
    )
    await config_create({"products": []}, owner_discord_user_id="someone-else")
    rows = await configs_list_for_owner("me")
    assert len(rows) == 1
    row = rows[0]
    assert row["id"] == mine
    assert row["product_count"] == 1
    assert set(row) == {"id", "product_count", "updated_at"}


async def test_list_for_owner_orders_newest_first(db_ready):
    older = await config_create({"products": []}, owner_discord_user_id="me")
    newer = await config_create({"products": []}, owner_discord_user_id="me")
    rows = await configs_list_for_owner("me")
    assert [r["id"] for r in rows] == [newer, older]
