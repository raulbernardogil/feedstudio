"""Scheduling, pipeline runs and Google Drive delivery."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from zoneinfo import ZoneInfo

import httpx
import pytest
from cryptography.fernet import Fernet
from pydantic import ValidationError

from feedstudio.scheduling import ScheduleConfig, next_run
from tests.factories import rss_feed, rss_item

UTC = timezone.utc


# --- schedule computation -----------------------------------------------------------------


def test_interval_schedule():
    cfg = ScheduleConfig(mode="interval", every_hours=2)
    assert next_run(cfg, datetime(2026, 10, 19, 10, 0, tzinfo=UTC)) == datetime(2026, 10, 19, 12, 0, tzinfo=UTC)
    assert next_run(ScheduleConfig(), datetime.now(UTC)) is None


def test_daily_schedule_in_local_time():
    cfg = ScheduleConfig(mode="daily", times=["20:00", "08:00"], timezone="Europe/Madrid")
    assert cfg.times == ["08:00", "20:00"]
    madrid = ZoneInfo("Europe/Madrid")
    after = datetime(2026, 10, 19, 9, 0, tzinfo=madrid)
    assert next_run(cfg, after) == datetime(2026, 10, 19, 20, 0, tzinfo=madrid).astimezone(UTC)
    late = datetime(2026, 10, 19, 21, 0, tzinfo=madrid)
    assert next_run(cfg, late) == datetime(2026, 10, 20, 8, 0, tzinfo=madrid).astimezone(UTC)


def test_daily_schedule_across_dst_gap():
    # 2026-03-29 02:30 does not exist in Madrid (02:00 -> 03:00): it runs at 03:30 CEST.
    cfg = ScheduleConfig(mode="daily", times=["02:30"], timezone="Europe/Madrid")
    result = next_run(cfg, datetime(2026, 3, 29, 0, 0, tzinfo=UTC))
    assert result == datetime(2026, 3, 29, 1, 30, tzinfo=UTC)
    assert result.astimezone(ZoneInfo("Europe/Madrid")).hour == 3


@pytest.mark.parametrize("data", [
    {"mode": "interval", "every_hours": 5},
    {"mode": "daily", "times": []},
    {"mode": "daily", "times": ["25:00"]},
    {"mode": "daily", "times": ["08:00"], "timezone": "Mars/Base"},
    {"mode": "manual", "extra": 1},
])
def test_invalid_schedules(data):
    with pytest.raises(ValidationError):
        ScheduleConfig.model_validate(data)


# --- fixtures ---------------------------------------------------------------------------------


FEED = rss_feed([rss_item(i, **{"g:price": f"{(i + 1) * 1000}.990,00 CLP"}) for i in range(6)])


@pytest.fixture()
def google_env(app_client, monkeypatch):
    """Enable Google Drive with a mocked Google API."""
    from feedstudio import config
    from feedstudio.integrations import google

    monkeypatch.setenv("FEEDSTUDIO_SECRET_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("FEEDSTUDIO_GOOGLE_CLIENT_ID", "client-id.apps.googleusercontent.com")
    monkeypatch.setenv("FEEDSTUDIO_GOOGLE_CLIENT_SECRET", "test-secret")
    monkeypatch.setenv("FEEDSTUDIO_APP_BASE_URL", "http://app.test")
    config.get_settings.cache_clear()
    fake = FakeGoogle()
    google.set_transport(httpx.MockTransport(fake))
    yield fake
    google.set_transport(None)
    config.get_settings.cache_clear()


class FakeGoogle:
    def __init__(self):
        self.calls: list[tuple[str, str]] = []
        self.uploads: list[bytes] = []
        self.fail_refresh = False
        self.next_id = 1

    def __call__(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        self.calls.append((request.method, url.split("?")[0]))
        if url.startswith("https://oauth2.googleapis.com/token"):
            form = parse_qs(request.content.decode())
            if form["grant_type"] == ["refresh_token"] and self.fail_refresh:
                return httpx.Response(400, json={"error": "invalid_grant", "error_description": "Token has been expired or revoked."})
            return httpx.Response(200, json={"access_token": "access-1", "refresh_token": "refresh-1",
                                             "scope": "openid email https://www.googleapis.com/auth/drive.file"})
        if url.startswith("https://openidconnect.googleapis.com/v1/userinfo"):
            return httpx.Response(200, json={"email": "demo@example.com"})
        if url.startswith("https://oauth2.googleapis.com/revoke"):
            return httpx.Response(200)
        if url.startswith("https://www.googleapis.com/upload/drive/v3/files"):
            assert request.headers["authorization"] == "Bearer access-1"
            assert parse_qs(urlsplit(url).query)["uploadType"] == ["resumable"]
            path = urlsplit(url).path
            file_id = path.rsplit("/", 1)[-1] if path.count("/") > 4 else f"FILE{self.next_id}"
            if request.method == "POST":
                self.next_id += 1
            return httpx.Response(200, headers={"location": f"https://upload.test/session/{file_id}"})
        if url.startswith("https://upload.test/session/"):
            self.uploads.append(request.read())
            file_id = url.rsplit("/", 1)[-1]
            return httpx.Response(200, json={"id": file_id, "webViewLink": f"https://drive.google.com/file/d/{file_id}/view"})
        return httpx.Response(404)


def upload(c, content=FEED):
    res = c.post("/api/sources/upload", data={"name": "Demo"}, files={"file": ("feed.xml", content.encode(), "application/xml")})
    assert res.status_code == 202, res.text
    return res.json()["source"]["id"]


def connect_google(c) -> int:
    url = c.post("/api/integrations/google/authorize").json()["url"]
    query = parse_qs(urlsplit(url).query)
    assert query["scope"] == ["openid email https://www.googleapis.com/auth/drive.file"]
    assert query["access_type"] == ["offline"]
    res = c.get("/api/integrations/google/callback", params={"code": "abc", "state": query["state"][0]}, follow_redirects=False)
    assert res.status_code == 303 and res.headers["location"] == "http://app.test/channels?google=connected"
    [account] = c.get("/api/integrations/google").json()["accounts"]
    return account["id"]


# --- Google OAuth ---------------------------------------------------------------------------------


def test_oauth_callback_stores_encrypted_token_and_rejects_bad_state(app_client, google_env):
    from feedstudio.db import session_scope
    from feedstudio.models import GoogleAccount

    c = app_client
    account_id = connect_google(c)
    with session_scope() as s:
        account = s.get(GoogleAccount, account_id)
        assert account.email == "demo@example.com"
        assert "refresh-1" not in account.encrypted_refresh_token
    bad = c.get("/api/integrations/google/callback", params={"code": "abc", "state": "forged.state"}, follow_redirects=False)
    assert bad.headers["location"].endswith("google=error")
    assert len(c.get("/api/integrations/google").json()["accounts"]) == 1  # same email -> same account
    assert c.delete(f"/api/integrations/google/{account_id}").status_code == 204


def test_google_not_configured_gives_clear_error(app_client):
    res = app_client.post("/api/integrations/google/authorize")
    assert res.status_code == 409 and res.json()["error"]["code"] == "google_not_configured"


# --- pipeline + delivery ------------------------------------------------------------------------


def test_pipeline_publishes_and_updates_the_same_drive_file(app_client, google_env):
    c = app_client
    sid = upload(c)
    cid = c.post("/api/channels", json={"source_id": sid, "name": "Google", "auto_publish": True}).json()["id"]
    c.post("/api/rules", json={"source_id": sid, "channel_id": None, "definition": {
        "name": "precio", "target": "price", "actions": [{"type": "normalize_price"}]}})
    account_id = connect_google(c)
    dest = c.post(f"/api/channels/{cid}/destinations", json={
        "google_account_id": account_id, "file_name": "google-demo.xml",
        "folder": "https://drive.google.com/drive/folders/1AbCdEfGhIjKlMnOp"}).json()
    assert dest["folder_id"] == "1AbCdEfGhIjKlMnOp"

    job = c.post(f"/api/sources/{sid}/run").json()["job"]
    result = c.get(f"/api/jobs/{job['id']}").json()
    assert result["status"] == "succeeded", result
    [entry] = result["result"]["channels"]
    assert entry["result"] == "published" and entry["deliveries"][0]["status"] == "succeeded"
    first = c.get(f"/api/channels/{cid}/destinations").json()["items"][0]
    assert first["remote_file_id"] == "FILE1" and first["last_status"] == "succeeded"
    assert b"<g:price>1000990.00 CLP</g:price>" in google_env.uploads[-1]

    c.post(f"/api/sources/{sid}/run")
    second = c.get(f"/api/channels/{cid}/destinations").json()["items"][0]
    assert second["remote_file_id"] == "FILE1"  # same file, stable link
    assert ("PATCH", "https://www.googleapis.com/upload/drive/v3/files/FILE1") in google_env.calls


def test_manual_publish_delivers_and_candidate_only_without_auto_publish(app_client, google_env):
    c = app_client
    sid = upload(c)
    cid = c.post("/api/channels", json={"source_id": sid, "name": "Google"}).json()["id"]
    account_id = connect_google(c)
    c.post(f"/api/channels/{cid}/destinations", json={"google_account_id": account_id, "file_name": "feed.xml"})

    job = c.post(f"/api/sources/{sid}/run").json()["job"]
    entry = c.get(f"/api/jobs/{job['id']}").json()["result"]["channels"][0]
    assert entry["result"] == "candidate" and c.get(f"/api/channels/{cid}").json()["published_version_id"] is None

    c.post(f"/api/feed-versions/{entry['version_id']}/publish")
    deliveries = c.get("/api/jobs", params={"kind": "deliver"}).json()["items"]
    assert deliveries[0]["status"] == "succeeded"


def test_revoked_google_access_marks_destination_and_account(app_client, google_env):
    c = app_client
    sid = upload(c)
    cid = c.post("/api/channels", json={"source_id": sid, "name": "Google", "auto_publish": True}).json()["id"]
    account_id = connect_google(c)
    c.post(f"/api/channels/{cid}/destinations", json={"google_account_id": account_id, "file_name": "feed.xml"})
    google_env.fail_refresh = True
    c.post(f"/api/sources/{sid}/run")
    dest = c.get(f"/api/channels/{cid}/destinations").json()["items"][0]
    assert dest["last_status"] == "failed" and "vuelve a conectar" in dest["last_error"]
    assert c.get("/api/integrations/google").json()["accounts"][0]["status"] == "invalid"


def test_publish_blocked_in_pipeline_does_not_deliver(app_client, google_env):
    c = app_client
    sid = upload(c)
    cid = c.post("/api/channels", json={"source_id": sid, "name": "Google", "auto_publish": True}).json()["id"]
    account_id = connect_google(c)
    c.post(f"/api/channels/{cid}/destinations", json={"google_account_id": account_id, "file_name": "feed.xml"})
    c.post(f"/api/sources/{sid}/run")
    uploads_before = len(google_env.uploads)
    c.post("/api/rules", json={"source_id": sid, "channel_id": cid, "definition": {
        "name": "excluir casi todo", "condition": {"conditions": [{"field": "id", "operator": "not_equals", "value": "SKU-00000"}]},
        "actions": [{"type": "exclude"}]}})
    job = c.post(f"/api/sources/{sid}/run").json()["job"]
    entry = c.get(f"/api/jobs/{job['id']}").json()["result"]["channels"][0]
    assert entry["result"] == "publish_blocked"
    assert len(google_env.uploads) == uploads_before


# --- scheduler ------------------------------------------------------------------------------------


def _url_source(feed_path: Path, schedule: dict) -> int:
    from feedstudio.db import session_scope
    from feedstudio.models import Source

    with session_scope() as s:
        src = Source(organization_id=1, name="URL demo", kind="url", url="https://feeds.example.com/demo.xml",
                     schedule=schedule["mode"], schedule_config=schedule,
                     next_run_at=datetime.now(UTC) - timedelta(minutes=1))
        s.add(src)
        s.flush()
        return src.id


def test_scheduler_tick_runs_due_sources_once(app_client, tmp_path, monkeypatch):
    from feedstudio import scheduler
    from feedstudio.ingestion.fetcher import FetchResult
    from feedstudio.services import importing

    feed = tmp_path / "remote.xml"
    feed.write_text(FEED, encoding="utf-8")

    def fake_fetch(url, dest, policy, *a, **kw):
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(feed.read_bytes())
        return FetchResult(dest, dest.stat().st_size, "x" * 64, "application/xml", url)

    monkeypatch.setattr(importing, "fetch_to_file", fake_fetch)
    sid = _url_source(feed, {"mode": "interval", "every_hours": 2, "times": [], "timezone": "UTC"})
    c = app_client
    cid = c.post("/api/channels", json={"source_id": sid, "name": "Google", "auto_publish": True}).json()["id"]

    started = scheduler.tick()
    assert len(started) == 1
    job = c.get(f"/api/jobs/{started[0]}").json()
    assert job["status"] == "succeeded" and job["params"]["trigger"] == "schedule"
    assert c.get(f"/api/channels/{cid}").json()["published_version_id"] is not None
    source = c.get(f"/api/sources/{sid}").json()
    assert source["active_snapshot"]["product_count"] == 6
    next_at = datetime.fromisoformat(source["next_run_at"])
    assert timedelta(hours=1, minutes=59) < next_at - datetime.now(UTC) <= timedelta(hours=2)
    assert scheduler.tick() == []  # not due again yet


def test_scheduler_skips_when_previous_run_still_active(app_client):
    from feedstudio import scheduler
    from feedstudio.db import session_scope
    from feedstudio.models import ProcessingJob, Source

    sid = _url_source(Path("unused"), {"mode": "daily", "times": ["08:00"], "timezone": "Europe/Madrid"})
    with session_scope() as s:
        s.add(ProcessingJob(organization_id=1, kind="pipeline", status="running", source_id=sid, params={}, events=[]))
    assert scheduler.tick() == []
    with session_scope() as s:
        assert s.get(Source, sid).next_run_at is not None  # advanced to the next 08:00


def test_schedule_endpoint_rules(app_client):
    c = app_client
    sid = upload(c)
    res = c.put(f"/api/sources/{sid}/schedule", json={"mode": "interval", "every_hours": 1})
    assert res.status_code == 422 and res.json()["error"]["code"] == "schedule_requires_url"
    url_sid = _url_source(Path("unused"), {"mode": "manual", "times": [], "timezone": "UTC"})
    res = c.put(f"/api/sources/{url_sid}/schedule", json={"mode": "daily", "times": ["08:00", "20:00"], "timezone": "America/Santiago"})
    assert res.status_code == 200
    body = res.json()
    assert body["schedule_label"] == "Diario a las 08:00, 20:00 (America/Santiago)" and body["next_run_at"]
    assert c.put(f"/api/sources/{url_sid}/schedule", json={"mode": "interval", "every_hours": 7}).status_code == 422
    manual = c.put(f"/api/sources/{url_sid}/schedule", json={"mode": "manual"}).json()
    assert manual["next_run_at"] is None
    assert c.get("/api/dashboard").json()["next_sync"] is None
