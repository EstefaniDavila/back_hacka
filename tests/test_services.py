"""Pruebas de integración para el módulo de comercio y servicios de VeciRed IA."""
import uuid
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from app.db.session import get_session_factory
from app.main import app


@pytest.fixture
async def second_auth_user():
    """Crea un segundo usuario de prueba para probar reseñas y permisos."""
    user_id = uuid.uuid4()
    email = f"reviewer_{user_id.hex[:8]}@vecired.pe"
    factory = get_session_factory()

    async with factory() as session:
        await session.execute(
            text(
                """
                INSERT INTO auth.users (id, aud, role, email, raw_user_meta_data, created_at, updated_at)
                VALUES (:id, 'authenticated', 'authenticated', :email, '{"full_name": "Vecino Revisor"}', now(), now())
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

    async with factory() as session:
        await session.execute(
            text("DELETE FROM reviews WHERE reviewer_id = :uid"),
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


@pytest.fixture
async def ensure_active_community():
    """Asegura que exista al menos una comunidad activa en la base de datos."""
    factory = get_session_factory()
    comm_id = uuid.uuid4()
    async with factory() as session:
        res = await session.execute(text("SELECT id FROM communities WHERE status = 'active' LIMIT 1"))
        existing = res.scalar()
        if existing:
            return existing

        d_res = await session.execute(text("SELECT id FROM districts LIMIT 1"))
        district_id = d_res.scalar()
        if not district_id:
            await session.execute(
                text("INSERT INTO departments (id, name, ubigeo) VALUES (15, 'Lima', '15') ON CONFLICT DO NOTHING")
            )
            await session.execute(
                text("INSERT INTO provinces (id, department_id, name, ubigeo) VALUES (1501, 15, 'Lima', '1501') ON CONFLICT DO NOTHING")
            )
            await session.execute(
                text("INSERT INTO districts (id, province_id, name, ubigeo) VALUES (150101, 1501, 'Lima Cercado', '150101') ON CONFLICT DO NOTHING")
            )
            district_id = 150101

        await session.execute(
            text(
                """
                INSERT INTO communities (id, district_id, name, description, status, created_at)
                VALUES (:id, :did, 'Comunidad Test VeciRed', 'Comunidad para pruebas automatizadas', 'active', now())
                """
            ),
            {"id": comm_id, "did": district_id},
        )
        await session.commit()

    return comm_id


@pytest.mark.asyncio
async def test_list_service_categories():
    """Verifica que se listen las categorías de servicios (autoseed si está vacía)."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.get("/api/v1/services/categories")
        assert response.status_code == 200
        categories = response.json()
        assert isinstance(categories, list)
        assert len(categories) > 0
        assert "id" in categories[0]
        assert "name" in categories[0]


@pytest.mark.asyncio
async def test_service_crud_lifecycle(
    test_auth_user,
    second_auth_user,
    ensure_active_community,
):
    """Prueba el ciclo completo de vida de un servicio: Crear, Leer, Editar, Pausar, Reseñar y Desactivar."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        # 1. Asegurar que los perfiles existan vía /users/me
        await client.get("/api/v1/users/me", headers=test_auth_user["headers"])
        await client.get("/api/v1/users/me", headers=second_auth_user["headers"])

        # 2. Obtener una categoría válida
        cat_res = await client.get("/api/v1/services/categories")
        categories = cat_res.json()
        category_id = categories[0]["id"]

        # 3. CREAR un servicio
        create_payload = {
            "title": "Reparación de Fugas y Griferías Test",
            "description": "Servicio rápido de gasfitería para emergencias del barrio.",
            "category_id": category_id,
            "community_id": str(ensure_active_community),
            "price_from": 35.50,
            "price_unit": "visita",
            "availability": "Lunes a Viernes 8am - 6pm",
        }
        create_res = await client.post(
            "/api/v1/services",
            json=create_payload,
            headers=test_auth_user["headers"],
        )
        assert create_res.status_code == 201, create_res.text
        created_service = create_res.json()
        service_id = created_service["id"]
        assert created_service["title"] == create_payload["title"]
        assert float(created_service["price_from"]) == 35.50
        assert created_service["provider_id"] == str(test_auth_user["id"])

        # 4. CONSULTAR DETALLE
        detail_res = await client.get(f"/api/v1/services/{service_id}")
        assert detail_res.status_code == 200
        detail = detail_res.json()
        assert detail["id"] == service_id
        assert "provider" in detail
        assert detail["provider"]["id"] == str(test_auth_user["id"])

        # 5. LISTAR CON FILTROS Y BÚSQUEDA
        list_res = await client.get(f"/api/v1/services?q=Fugas&category_id={category_id}")
        assert list_res.status_code == 200
        list_data = list_res.json()
        assert list_data["meta"]["total"] >= 1
        found_ids = [s["id"] for s in list_data["items"]]
        assert service_id in found_ids

        # 6. CONSULTAR MIS SERVICIOS
        my_res = await client.get("/api/v1/services/my", headers=test_auth_user["headers"])
        assert my_res.status_code == 200
        my_services = my_res.json()
        assert any(s["id"] == service_id for s in my_services["items"])

        # 7. EDITAR SERVICIO
        update_res = await client.put(
            f"/api/v1/services/{service_id}",
            json={"title": "Reparación de Fugas Actualizada", "price_from": 40.00},
            headers=test_auth_user["headers"],
        )
        assert update_res.status_code == 200
        assert update_res.json()["title"] == "Reparación de Fugas Actualizada"
        assert float(update_res.json()["price_from"]) == 40.00

        # 8. INTENTO DE EDICIÓN NO AUTORIZADO (segundo usuario debe recibir 403)
        unauth_edit = await client.put(
            f"/api/v1/services/{service_id}",
            json={"title": "Hackeado"},
            headers=second_auth_user["headers"],
        )
        assert unauth_edit.status_code == 403

        # 9. PAUSAR SERVICIO
        pause_res = await client.patch(
            f"/api/v1/services/{service_id}/status",
            json={"status": "paused"},
            headers=test_auth_user["headers"],
        )
        assert pause_res.status_code == 200
        assert pause_res.json()["status"] == "paused"

        # En listado público de activos no debe aparecer
        public_res = await client.get("/api/v1/services?q=Actualizada")
        assert not any(s["id"] == service_id for s in public_res.json()["items"])

        # Reactivar
        await client.patch(
            f"/api/v1/services/{service_id}/status",
            json={"status": "active"},
            headers=test_auth_user["headers"],
        )

        # 10. VALORACIÓN / RESEÑA (Review)
        # Dueño no puede autocalificarse
        self_rev = await client.post(
            f"/api/v1/services/{service_id}/reviews",
            json={"rating": 5, "comment": "Soy el mejor"},
            headers=test_auth_user["headers"],
        )
        assert self_rev.status_code == 400

        # Vecino diferente califica con 5 estrellas
        rev_res = await client.post(
            f"/api/v1/services/{service_id}/reviews",
            json={"rating": 5, "comment": "Excelente atención y puntualidad."},
            headers=second_auth_user["headers"],
        )
        assert rev_res.status_code == 201
        rev_data = rev_res.json()
        assert rev_data["rating"] == 5
        assert rev_data["comment"] == "Excelente atención y puntualidad."

        # Consultar detalle con la nueva valoración reflejada
        detail_after_rev = await client.get(f"/api/v1/services/{service_id}")
        assert detail_after_rev.status_code == 200
        assert detail_after_rev.json()["rating_avg"] == 5.0
        assert detail_after_rev.json()["reviews_count"] == 1

        # 11. DESACTIVAR / ELIMINAR SERVICIO
        del_res = await client.delete(
            f"/api/v1/services/{service_id}",
            headers=test_auth_user["headers"],
        )
        assert del_res.status_code == 204

        # Limpieza en base de datos para no dejar rastro
        factory = get_session_factory()
        async with factory() as session:
            await session.execute(text("DELETE FROM reviews WHERE service_id = :sid"), {"sid": service_id})
            await session.execute(text("DELETE FROM services WHERE id = :sid"), {"sid": service_id})
            await session.commit()
