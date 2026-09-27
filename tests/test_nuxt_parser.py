"""Tests for the hand-written NUXT SSR payload parser."""

from pathlib import Path

import pytest
from hotline_prices.nuxt_parser import extract_offer_prices, parse_nuxt_payload

_FIXTURES = Path(__file__).parent / "fixtures"


def _payload_html(src: str) -> str:
    return f"<html><body><script>window.__NUXT__={src}</script></body></html>"


def test_basic_substitution():
    html = _payload_html('(function(a,b,c){return {n:a,s:b,f:c}})(1,"x",true);')
    assert parse_nuxt_payload(html) == {"n": 1, "s": "x", "f": True}


def test_nested_objects_and_arrays_with_substitution():
    html = _payload_html(
        '(function(a,b){return {outer:{inner:[a,b,{deep:a}]}}})(1,"y");'
    )
    assert parse_nuxt_payload(html) == {"outer": {"inner": [1, "y", {"deep": 1}]}}


def test_string_escapes():
    html = _payload_html(
        r'(function(a){return {s:a}})("line1\nline2 \"quoted\" / end é");'
    )
    result = parse_nuxt_payload(html)
    assert result == {"s": 'line1\nline2 "quoted" / end é'}


@pytest.mark.parametrize("literal", ["null", "undefined", "void 0"])
def test_null_like_literals_parse_to_none(literal):
    html = _payload_html(f"(function(){{return {{v:{literal}}}}})();")
    assert parse_nuxt_payload(html) == {"v": None}


def test_pre_return_array_index_assignment():
    html = _payload_html('(function(a){a[0]="x";a[1]="y";return {p:a}})([]);')
    assert parse_nuxt_payload(html) == {"p": ["x", "y"]}


def test_array_call_produces_none_filled_list():
    html = _payload_html("(function(){return {arr:Array(3)}})();")
    assert parse_nuxt_payload(html) == {"arr": [None, None, None]}


def test_object_assign_call_merges_dicts():
    html = _payload_html("(function(){return {m:Object.assign({a:1},{b:2})}})();")
    assert parse_nuxt_payload(html) == {"m": {"a": 1, "b": 2}}


def test_missing_nuxt_marker_raises():
    with pytest.raises(ValueError):
        parse_nuxt_payload("<html><body>no payload here</body></html>")


def test_unbalanced_brackets_raise():
    html = _payload_html("(function(a){return {v:a}})(1;")
    with pytest.raises(ValueError):
        parse_nuxt_payload(html)


def test_unresolved_identifier_raises():
    html = _payload_html("(function(a){return {v:someUnknownIdent}})(1);")
    with pytest.raises(ValueError):
        parse_nuxt_payload(html)


def test_extract_offer_prices_finds_deeply_nested_edges():
    html = _payload_html(
        "(function(a,b,c){return {state:{wrapper:{product:{offers:{edges:["
        "{node:{price:a,other:1}},{node:{price:b,other:2}}"
        "]}}}},unrelated:c}})(100,200.5,null);"
    )
    assert extract_offer_prices(html) == [100.0, 200.5]


def test_extract_offer_prices_no_offers_shape_returns_empty_list():
    html = _payload_html('(function(a){return {state:{product:{name:a}}}})("x");')
    assert extract_offer_prices(html) == []


def test_extract_offer_prices_real_page_fixture():
    fixture = _FIXTURES / "alienware_aw3426dwm_page.html"
    if not fixture.exists():
        pytest.skip("real-page fixture not present")
    html = fixture.read_text(encoding="utf-8")
    assert sorted(extract_offer_prices(html)) == sorted(
        [19000.0, 19061.0, 19239.0, 19243.0, 19399.0, 19399.0, 20369.0]
    )
