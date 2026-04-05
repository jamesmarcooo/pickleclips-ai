import pytest


@pytest.mark.asyncio
async def test_protected_route_requires_auth(client):
    response = await client.get("/api/v1/videos")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_protected_route_accepts_valid_token(client, test_token):
    response = await client.get(
        "/api/v1/videos",
        headers={"Authorization": f"Bearer {test_token}"},
    )
    # 200 or empty list — just not 401
    assert response.status_code != 401


@pytest.mark.asyncio
async def test_invalid_token_rejected(client):
    response = await client.get(
        "/api/v1/videos",
        headers={"Authorization": "Bearer not.a.valid.token"},
    )
    assert response.status_code == 401
