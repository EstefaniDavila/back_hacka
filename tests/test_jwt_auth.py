"""Pruebas de verificación de token JWT y creación automática de perfiles."""
import uuid
import jwt
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from app.db.session import get_session_factory
from app.main import app


@pytest.fixture
async def create_auth_user():
    """Crea un usuario real en auth.users para satisfacer foreign keys en tests."""
    user_id = uuid.uuid4()
    email = f"jwt_user_{user_id.hex[:8]}@vecired.pe"
    factory = get_session_factory()

    async with factory() as session:
        await session.execute(
            text(
                """
                INSERT INTO auth.users (id, aud, role, email, raw_user_meta_data, created_at, updated_at)
                VALUES (:id, 'authenticated', 'authenticated', :email, '{"full_name": "Vecino JWT"}', now(), now())
                """
            ),
            {"id": user_id, "email": email},
        )
        await session.commit()

    # Generar token JWT con la estructura idéntica a Supabase
    payload = {
        "sub": str(user_id),
        "email": email,
        "role": "authenticated",
        "aud": "authenticated",
        "user_metadata": {"full_name": "Vecino JWT"},
    }
    # En desarrollo/testing sin secret, codificamos con cualquier secret porque decode tiene verify_signature=False cuando SUPABASE_JWT_SECRET está vacío
    token = jwt.encode(payload, "secret-test", algorithm="HS256")

    yield {
        "id": user_id,
        "email": email,
        "token": token,
        "headers": {"Authorization": f"Bearer {token}"},
    }

    # Limpieza
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


@pytest.mark.asyncio
async def test_jwt_bearer_token_creates_and_retrieves_profile(create_auth_user):
    """Verifica que un token JWT de Supabase en Authorization: Bearer sea procesado y cree/recupere el perfil."""
    headers = create_auth_user["headers"]
    user_id_str = str(create_auth_user["id"])

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        # Primer llamado: debe crear el perfil
        res1 = await client.get("/api/v1/users/me", headers=headers)
        assert res1.status_code == 200, res1.text
        data1 = res1.json()
        assert data1["id"] == user_id_str
        assert data1["account_status"] in ("pending", "pending_verification")

        # Segundo llamado: debe recuperar el perfil existente sin error
        res2 = await client.get("/api/v1/users/me", headers=headers)
        assert res2.status_code == 200
        data2 = res2.json()
        assert data2["id"] == user_id_str


@pytest.mark.asyncio
async def test_jwt_bearer_token_protected_service_creation(create_auth_user):
    """Verifica que un endpoint protegido (POST /services) acepte el JWT en Authorization: Bearer."""
    headers = create_auth_user["headers"]

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        # 1. Obtener categoría
        cat_res = await client.get("/api/v1/services/categories")
        category_id = cat_res.json()[0]["id"]

        # 2. Publicar servicio usando Authorization: Bearer <token>
        service_payload = {
            "title": "Servicio con Auth JWT",
            "description": "Prueba de autenticación mediante Bearer token Supabase.",
            "category_id": category_id,
            "price_from": 50.00,
            "price_unit": "servicio",
        }
        create_res = await client.post("/api/v1/services", json=service_payload, headers=headers)
        assert create_res.status_code == 201, create_res.text
        svc = create_res.json()
        assert svc["provider_id"] == str(create_auth_user["id"])
        service_id = svc["id"]

        # Limpieza del servicio
        factory = get_session_factory()
        async with factory() as session:
            await session.execute(text("DELETE FROM services WHERE id = :sid"), {"sid": service_id})
            await session.commit()


@pytest.mark.asyncio
async def test_missing_or_invalid_bearer_token():
    """Verifica que peticiones a endpoints protegidos sin token o con token malformado retornen 401."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        # Sin header
        res_no_auth = await client.get("/api/v1/users/me")
        assert res_no_auth.status_code == 401

        # Token malformado
        res_bad_auth = await client.get("/api/v1/users/me", headers={"Authorization": "Bearer token_falso_malformado"})
        assert res_bad_auth.status_code == 401

