"""Abuse guards on the public API: CORS allow-list, per-client limits, input caps."""
import os

os.environ.pop("GEMINI_API_KEY", None)
os.environ.pop("CORS_ORIGINS", None)

from fastapi.testclient import TestClient  # noqa: E402

from backend import main  # noqa: E402

client = TestClient(main.app)


def test_cors_rejects_unknown_origin():
    r = client.options("/generate-exercise", headers={
        "Origin": "https://evil.example", "Access-Control-Request-Method": "POST"})
    assert "access-control-allow-origin" not in r.headers


def test_cors_allows_site():
    r = client.options("/generate-exercise", headers={
        "Origin": "https://www.role2builder.org", "Access-Control-Request-Method": "POST"})
    assert r.headers.get("access-control-allow-origin") == "https://www.role2builder.org"
    assert "access-control-allow-credentials" not in r.headers


def test_name_requests_are_limited_per_client(monkeypatch):
    monkeypatch.setattr(main, "MAX_NAMES_PER_CLIENT_PER_HOUR", 2)
    main._rate_hits.clear()
    hdr = {"X-Forwarded-For": "203.0.113.7"}
    codes = [client.post("/generate-name", json={}, headers=hdr).status_code for _ in range(3)]
    assert codes[-1] == 429
    # a different client is unaffected
    assert client.post("/generate-name", json={}, headers={"X-Forwarded-For": "203.0.113.8"}).status_code != 429
    main._rate_hits.clear()


def test_oversized_input_rejected():
    r = client.post("/generate-name", json={"region": "x" * 5000})
    assert r.status_code == 422


def test_star_env_falls_back_to_site(monkeypatch):
    import importlib
    monkeypatch.setenv("CORS_ORIGINS", "*")
    m = importlib.reload(main)
    assert "https://www.role2builder.org" in m.CORS_ORIGINS
    monkeypatch.delenv("CORS_ORIGINS")
    importlib.reload(main)


def test_cors_allows_own_vercel_previews_only():
    def acao(origin):
        return client.options("/generate-name", headers={
            "Origin": origin, "Access-Control-Request-Method": "POST"}).headers.get("access-control-allow-origin")
    ok = "https://role2-builder-5kd17xv78-brians-projects-0545fc67.vercel.app"
    assert acao(ok) == ok
    assert acao("https://role2-builder.vercel.app") == "https://role2-builder.vercel.app"
    assert acao("https://role2-builder-evil.vercel.app") is None
    assert acao("https://role2-builder-x-brians-projects-0545fc67.vercel.app.evil.com") is None


def test_frontend_has_no_railway_address():
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[1] / "src"
    hits = [str(p) for p in root.rglob("*.ts*") if "railway" in p.read_text().lower()
            and p.name != "api.ts"]
    assert hits == []
