import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from nexus.app import create_app
from nexus.config import Settings


@pytest_asyncio.fixture
async def client(tmp_path):
    settings = Settings(data_dir=tmp_path / "data")
    app = create_app(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield http


@pytest.mark.asyncio
async def test_textwall_relay_is_opt_in_and_safe_when_unconfigured(client):
    status = await client.get("/api/v1/apps/textwall")
    assert status.status_code == 200
    assert status.json() == {"configured": False, "mode": "direct-only"}

    result = await client.post("/api/v1/apps/textwall/commands", json={
        "action": "apply_cue", "payload": {"text": "HELLO"}})
    assert result.status_code == 409
    assert "NEXUS_TEXTWALL_URL" in result.json()["detail"]
