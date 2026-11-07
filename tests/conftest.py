import uuid
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from app.db.session import get_session_factory
from app.main import app


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def async_client():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        yield client


@pytest.fixture
async def test_auth_user():
    """Crea un usuario real en auth.users para satisfacer foreign keys en tests."""
    user_id = uuid.uuid4()
    email = f"test_{user_id.hex[:8]}@vecired.pe"
    factory = get_session_factory()

    async with factory() as session:
        await session.execute(
            text(
                """
                INSERT INTO auth.users (id, aud, role, email, raw_user_meta_data, created_at, updated_at)
                VALUES (:id, 'authenticated', 'authenticated', :email, '{"full_name": "Vecino Tester"}', now(), now())
                """
            ),
            {"id": user_id, "email": email},
        )
        await session.commit()

    yield {
        "id": user_id,
        "email": email,
        "headers": {"X-Test-User-Id": str(user_id)},
    }

    # Limpieza posterior
    async with factory() as session:
        await session.execute(
            text("DELETE FROM identity_verifications WHERE user_id = :uid"),
            {"uid": user_id},
        )
        await session.execute(
            text("DELETE FROM profiles WHERE id = :uid"),
            {"uid": user_id},
        )
        await session.execute(
            text("DELETE FROM auth.users WHERE id = :uid"),
            {"uid": user_id},
        )
        await session.commit()
