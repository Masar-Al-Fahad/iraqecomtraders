from fastapi.testclient import TestClient

from main import app
from routers import admin_app_settings


FRONTEND_ORIGIN = "https://mfec.iraq-ecom-traders.masaralfahad.com"
BRAND_PATH = "/api/v1/public/app-settings/brand"


async def _fake_db():
    yield object()


async def _noop_schema():
    return None


async def _brand_settings(_db):
    return {"site_name": "test"}


def test_brand_get_and_preflight_allow_custom_frontend(monkeypatch):
    monkeypatch.setattr(admin_app_settings, "ensure_schema", _noop_schema)
    monkeypatch.setattr(admin_app_settings, "get_brand_settings", _brand_settings)
    fastapi_app = app.app
    fastapi_app.dependency_overrides[admin_app_settings.get_db] = _fake_db

    try:
        with TestClient(app) as client:
            response = client.get(BRAND_PATH, headers={"Origin": FRONTEND_ORIGIN})
            assert response.status_code == 200
            assert response.headers["access-control-allow-origin"] == FRONTEND_ORIGIN
            assert response.headers["access-control-allow-credentials"] == "true"

            preflight = client.options(
                BRAND_PATH,
                headers={
                    "Origin": FRONTEND_ORIGIN,
                    "Access-Control-Request-Method": "GET",
                },
            )
            assert preflight.status_code == 200
            assert preflight.headers["access-control-allow-origin"] == FRONTEND_ORIGIN
            assert preflight.headers["access-control-allow-credentials"] == "true"
    finally:
        fastapi_app.dependency_overrides.clear()
