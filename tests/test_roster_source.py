"""ROSTER_SOURCE switch (sv-registry roster cutover). Synthetic data only:
fake names, test-* slugs, fake channel ids. No network: every request goes
through a stub opener or a patched urllib.request.urlopen."""

import importlib
import io
import json
import os
import sys
import urllib.error
import urllib.request

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import roster_source as rs  # noqa: E402


def _row(slug, name, dc=2026, ch=True, **kw):
    r = {"slug": slug, "name": name, "draft_class": dc, "is_client": True,
         "is_coach": False, "career_status": "active", "nicknames": []}
    if ch:
        r["slack_channel_name"] = slug.replace("test-", "")
        r["slack_channel_id"] = "CTEST" + slug.upper().replace("-", "")[:6]
    r.update(kw)
    return r


def _projection(rows, meta_extra=None):
    meta = {"generated_at": "2026-09-28T00:00:00Z", "contains_no_contact_data": True}
    meta.update(meta_extra or {})
    return {"_meta": meta, "rows": rows}


def _filler(n):
    return [_row(f"test-filler-{i}", f"Filler Person{i}", dc=2030 + (i % 3), ch=False)
            for i in range(n)]


class _Resp(io.BytesIO):
    headers = {}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _opener_for(body=None, status=200, calls=None):
    def opener(req, timeout=None):
        if calls is not None:
            calls.append(req)
        if status != 200:
            raise urllib.error.HTTPError(req.full_url, status, "err", {}, None)
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        return _Resp(data)
    return opener


# --- the switch -------------------------------------------------------------

def test_default_is_hardcoded(monkeypatch):
    monkeypatch.delenv("ROSTER_SOURCE", raising=False)
    assert rs.roster_source() == "hardcoded"


@pytest.mark.parametrize("val,want", [("sheet", "hardcoded"), ("HARDCODED", "hardcoded"),
                                      (" registry ", "registry"), ("", "hardcoded")])
def test_switch_values(monkeypatch, val, want):
    monkeypatch.setenv("ROSTER_SOURCE", val)
    assert rs.roster_source() == want


def test_unknown_switch_value_refused(monkeypatch):
    monkeypatch.setenv("ROSTER_SOURCE", "regsitry")
    with pytest.raises(rs.RosterProjectionError):
        rs.roster_source()


# --- fail closed ------------------------------------------------------------

def test_missing_token_fails_before_any_request():
    calls = []
    with pytest.raises(rs.RosterProjectionError, match="SV_REGISTRY_ROSTER_TOKEN"):
        rs.fetch_projection(token="", opener=_opener_for({}, calls=calls))
    assert calls == []


@pytest.mark.parametrize("status,msg", [(401, "re-mint"), (403, "not scoped"), (500, "HTTP 500")])
def test_http_failures_fail_closed(status, msg):
    with pytest.raises(rs.RosterProjectionError, match=msg):
        rs.fetch_projection(token="svt_x", opener=_opener_for(status=status))


def test_sends_bearer_token():
    calls = []
    rs.fetch_projection(token="svt_abc", min_rows=1,
                        opener=_opener_for(_projection([_row("test-a", "Al Alpha")]), calls=calls))
    assert calls[0].get_header("Authorization") == "Bearer svt_abc"


@pytest.mark.parametrize("body,msg", [
    (b"<html>", "not JSON"),
    ({"rows": []}, "missing _meta"),
    (_projection([_row("test-a", "Al Alpha")], {"contains_no_contact_data": False}), "contains_no_contact_data"),
    (_projection([_row("test-a", "Al Alpha"), {"name": "No Slug"}]), "without a slug"),
    (_projection([_row("test-a", "Al Alpha"), _row("test-a", "Al Again")]), "duplicate slugs"),
])
def test_untrustworthy_bodies_refused(body, msg):
    with pytest.raises(rs.RosterProjectionError, match=msg):
        rs.fetch_projection(token="svt_x", min_rows=1, opener=_opener_for(body))


def test_too_few_rows_fails_closed():
    with pytest.raises(rs.RosterProjectionError, match="fail-closed floor"):
        rs.fetch_projection(token="svt_x", min_rows=50, opener=_opener_for(_projection(_filler(3))))


# --- mapping ----------------------------------------------------------------

def test_build_roster_membership_and_shapes():
    rows = [
        _row("test-al-alpha", "Al Alpha", nicknames=["Big Al", "Al Alpha"]),
        _row("test-bo-beta-jr", "Bo Beta Jr."),
        _row("test-cy-gamma", "Cy Gamma", ch=False),
        _row("test-coach", "Coach Delta", is_coach=True),
        _row("test-former", "Ex Client", is_client=False),
        _row("test-next-year", "Ed Epsilon", dc=2027),
        _row("test-str-year", "Fi Zeta", dc="2026"),
    ]
    r = rs.build_roster(rows, 2026)
    assert r["slugs"] == ["test-al-alpha", "test-bo-beta-jr", "test-cy-gamma", "test-str-year"]
    assert r["players"] == {"alpha": "Al Alpha", "beta": "Bo Beta Jr.", "gamma": "Cy Gamma",
                            "zeta": "Fi Zeta"}
    assert r["channel_to_player"]["al-alpha"] == "Al Alpha"
    assert "cy-gamma" not in r["channel_to_player"]  # no channel in canon -> no channel entry
    assert ("al-alpha", r["channels"][0][1]) == r["channels"][0]
    assert "nicknames" not in r  # never taken: the alias map lands in the public page


def test_empty_draft_class_refused():
    with pytest.raises(rs.RosterProjectionError, match="no clients with draft_class=2026"):
        rs.build_roster([_row("test-a", "Al Alpha", dc=2027)], 2026)


def test_last_name_collision_refused():
    with pytest.raises(rs.RosterProjectionError, match="last-name key 'same'"):
        rs.build_roster([_row("test-a", "Al Same"), _row("test-b", "Bo Same")], 2026)


def test_dual_run_line():
    reg = rs.build_roster([_row("test-al-alpha", "Al Alpha"), _row("test-bo-beta", "Bo Beta")], 2026)
    line = rs.dual_run_line({"alpha": "Al Alpha", "omega": "Om Omega"},
                            {"al-alpha": "Al Alpha", "om-omega": "Om Omega"}, reg)
    assert line.startswith("[dual-run] roster hardcoded=2 registry=2 ")
    assert "only_hardcoded=['om-omega']" in line
    assert "only_registry=['test-bo-beta']" in line
    assert "channel_mismatch=['om-omega']" in line


# --- fetch_and_build.py integration -----------------------------------------

def _load_fab(monkeypatch, env, urlopen):
    pytest.importorskip("slack_sdk")
    for k in ("ROSTER_SOURCE", "SV_REGISTRY_ROSTER_TOKEN", "ROSTER_PROJECTION_URL", "ROSTER_MIN_ROWS"):
        monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    sys.modules.pop("fetch_and_build", None)
    return importlib.import_module("fetch_and_build")


def _no_network(*a, **k):
    raise AssertionError("network touched")


def test_default_import_is_the_hardcoded_roster_and_offline(monkeypatch):
    fab = _load_fab(monkeypatch, {}, _no_network)
    assert fab.ROSTER_SOURCE == "hardcoded"
    assert len(fab.PLAYERS_2026) == 20 and len(fab.CHANNEL_TO_PLAYER) == 20
    assert len(fab.CHANNELS) == 24
    assert fab.PLAYER_ALIASES["Cameron Flukey"] >= {"cam", "flukey", "cameron"}
    # dual run is off without a token, so no request is made
    assert fab.log_roster_dual_run() is None


def test_dual_run_never_breaks_the_build(monkeypatch):
    fab = _load_fab(monkeypatch, {"SV_REGISTRY_ROSTER_TOKEN": "svt_x"}, _no_network)
    before = dict(fab.PLAYERS_2026)
    line = fab.log_roster_dual_run()
    assert line.startswith("[dual-run] WARN")
    assert fab.PLAYERS_2026 == before


def test_dual_run_logs_comparison(monkeypatch):
    rows = [_row("aiden-robbins", "Aiden Robbins", slack_channel_name="aiden-robbins",
                 slack_channel_id="C08DQTL4TGE"), _row("test-new", "New Client")] + _filler(60)
    fab = _load_fab(monkeypatch, {"SV_REGISTRY_ROSTER_TOKEN": "svt_x"},
                    _opener_for(_projection(rows)))
    line = fab.log_roster_dual_run()
    assert "hardcoded=20 registry=2" in line and "only_registry=['test-new']" in line


def test_registry_mode_replaces_player_entries_keeps_group_channels(monkeypatch):
    rows = [_row("test-tess-loy", "Tess Loy", nicknames=["T-Lo"]),
            _row("test-uma-vance", "Uma Vance")] + _filler(60)
    fab = _load_fab(monkeypatch, {"ROSTER_SOURCE": "registry", "SV_REGISTRY_ROSTER_TOKEN": "svt_x"},
                    _opener_for(_projection(rows)))
    assert fab.ALL_2026_PLAYERS == ["Tess Loy", "Uma Vance"]
    names = [n for n, _ in fab.CHANNELS]
    assert "2026-draft-general" in names and "2026-mlb-combine" in names
    assert "aiden-robbins" not in names and "tess-loy" in names
    assert fab.PLAYER_ALIASES["Tess Loy"] == {"loy", "tess"}  # registry nicknames stay out
    # whole-word last-name match: "employ" is not Tess Loy
    assert fab.find_players_in_text("they want to employ him") == set()
    assert fab.find_players_in_text("KC loves Loy") == {"Tess Loy"}
    # first-name shortcuts never invent a non-member ("Cam" -> Cameron Flukey)
    assert fab.find_players_in_text("Cam looked great") == set()


def test_registry_mode_fails_closed_at_import(monkeypatch):
    with pytest.raises(rs.RosterProjectionError):
        _load_fab(monkeypatch, {"ROSTER_SOURCE": "registry"}, _no_network)
