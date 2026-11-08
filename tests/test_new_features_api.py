"""Tests integrales para las nuevas APIs de VeciRed:
- Chat comunitario con persistencia de historial
- Alertas y notificaciones a la comunidad
- Cámara frontal y posterior
- Mapa de servicios y emergencias
- Calificaciones y reseñas
- Categorías de productos
- Edición de perfil (avatar, habilidades, teléfono)
"""
import uuid
from unittest.mock import AsyncMock, MagicMock
import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.modules.chat.dependencies import get_chat_service
from app.modules.chat.schemas import (
    ChatMessageResponse,
    ConversationDetailResponse,
    ConversationListItem,
)
from app.modules.chat.service import ChatService
from app.modules.commerce.dependencies import get_commerce_service
from app.modules.commerce.schemas import ProductCategoryResponse
from app.modules.commerce.service import CommerceService
from app.modules.geo.dependencies import get_geo_service
from app.modules.geo.schemas import (
    EmergencyMapMarker,
    MapOverviewResponse,
    ServiceMapMarker,
)
from app.modules.geo.service import GeoService
from app.modules.interactions.dependencies import get_review_service
from app.modules.interactions.schemas import ReviewResponse, UserReputationSummary
from app.modules.interactions.service import ReviewService
from app.modules.notifications.dependencies import get_notification_service
from app.modules.notifications.schemas import NotificationResponse, UnreadCountResponse
from app.modules.notifications.service import NotificationService
from app.modules.users.dependencies import get_user_service
from app.modules.users.schemas import (
    IdentityVerificationResultResponse,
    ProfileResponse,
)
from app.modules.users.service import UserService


# 1. Test Chat Comunitario e Historial
@pytest.mark.asyncio
async def test_chat_list_and_history():
    mock_chat_service = MagicMock(spec=ChatService)
    test_conv_id = uuid.uuid4()
    mock_chat_service.list_conversations = AsyncMock(return_value=[
        ConversationListItem(
            id=test_conv_id,
            title="Chat General - Zona A",
            is_group=True,
            last_message="Hola a todos",
            unread_count=2,
        )
    ])
    msg_item = ChatMessageResponse(
        id=uuid.uuid4(),
        conversation_id=test_conv_id,
        sender_id=uuid.uuid4(),
        sender_name="Vecina María",
        content="Hola a todos los vecinos",
    )
    mock_chat_service.get_conversation_detail = AsyncMock(return_value=ConversationDetailResponse(
        id=test_conv_id,
        title="Chat General - Zona A",
        is_group=True,
        messages=[msg_item],
    ))

    app.dependency_overrides[get_chat_service] = lambda: mock_chat_service

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        # Listar chats
        res = await client.get("/api/v1/chats")
        assert res.status_code == 200
        data = res.json()
        assert len(data) == 1
        assert data[0]["title"] == "Chat General - Zona A"

        # Historial de mensajes
        res_msgs = await client.get(f"/api/v1/chats/{test_conv_id}/messages")
        assert res_msgs.status_code == 200
        msgs = res_msgs.json()
        assert len(msgs) == 1
        assert msgs[0]["content"] == "Hola a todos los vecinos"

    app.dependency_overrides.pop(get_chat_service, None)


# 2. Test Notificaciones y Alertas
@pytest.mark.asyncio
async def test_notifications_flow():
    mock_notif_service = MagicMock(spec=NotificationService)
    test_notif_id = uuid.uuid4()
    mock_notif_service.list_my_notifications = AsyncMock(return_value=[
        NotificationResponse(
            id=test_notif_id,
            user_id=uuid.uuid4(),
            title="🚨 Alerta Vecinal: Aniego en Mz. B",
            message="Se ha reportado ingreso de agua.",
            notification_type="emergency",
            is_read=False,
        )
    ])
    mock_notif_service.get_unread_count = AsyncMock(return_value=UnreadCountResponse(unread_count=1))
    mock_notif_service.mark_as_read = AsyncMock(return_value=NotificationResponse(
        id=test_notif_id,
        user_id=uuid.uuid4(),
        title="🚨 Alerta Vecinal: Aniego en Mz. B",
        message="Se ha reportado ingreso de agua.",
        notification_type="emergency",
        is_read=True,
    ))

    app.dependency_overrides[get_notification_service] = lambda: mock_notif_service

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        res = await client.get("/api/v1/notifications")
        assert res.status_code == 200
        assert len(res.json()) == 1

        res_count = await client.get("/api/v1/notifications/unread-count")
        assert res_count.status_code == 200
        assert res_count.json()["unread_count"] == 1

        res_patch = await client.patch(f"/api/v1/notifications/{test_notif_id}/read")
        assert res_patch.status_code == 200
        assert res_patch.json()["is_read"] is True

    app.dependency_overrides.pop(get_notification_service, None)


# 3. Test Mapa Vecinal (Servicios y Emergencias)
@pytest.mark.asyncio
async def test_map_markers():
    mock_geo_service = MagicMock(spec=GeoService)
    mock_geo_service.get_services_map_markers = AsyncMock(return_value=[
        ServiceMapMarker(
            id=uuid.uuid4(),
            title="Gasfitería Express",
            provider_id=uuid.uuid4(),
            provider_name="Carlos Gasfitero",
            latitude=-12.0463,
            longitude=-77.0427,
            status="active",
        )
    ])
    mock_geo_service.get_emergencies_map_markers = AsyncMock(return_value=[
        EmergencyMapMarker(
            id=uuid.uuid4(),
            title="Incendio controlado en Manzana 4",
            severity="high",
            status="active",
            latitude=-12.0455,
            longitude=-77.0415,
        )
    ])
    mock_geo_service.get_map_overview = AsyncMock(return_value=MapOverviewResponse(
        services=[
            ServiceMapMarker(
                id=uuid.uuid4(),
                title="Gasfitería Express",
                provider_id=uuid.uuid4(),
                provider_name="Carlos Gasfitero",
                latitude=-12.0463,
                longitude=-77.0427,
                status="active",
            )
        ],
        emergencies=[
            EmergencyMapMarker(
                id=uuid.uuid4(),
                title="Incendio controlado en Manzana 4",
                severity="high",
                status="active",
                latitude=-12.0455,
                longitude=-77.0415,
            )
        ]
    ))

    app.dependency_overrides[get_geo_service] = lambda: mock_geo_service

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        res_svc = await client.get("/api/v1/geo/map/services")
        assert res_svc.status_code == 200
        assert len(res_svc.json()) == 1

        res_emg = await client.get("/api/v1/geo/map/emergencies")
        assert res_emg.status_code == 200
        assert len(res_emg.json()) == 1

        res_all = await client.get("/api/v1/geo/map/all")
        assert res_all.status_code == 200
        data = res_all.json()
        assert len(data["services"]) == 1
        assert len(data["emergencies"]) == 1

    app.dependency_overrides.pop(get_geo_service, None)


# 4. Test Calificaciones y Reseñas
@pytest.mark.asyncio
async def test_reviews_api():
    mock_review_service = MagicMock(spec=ReviewService)
    user_id = uuid.uuid4()
    svc_id = uuid.uuid4()
    mock_review_service.create_review = AsyncMock(return_value=ReviewResponse(
        id=uuid.uuid4(),
        reviewer_id=uuid.uuid4(),
        reviewed_user_id=user_id,
        service_id=svc_id,
        rating=5,
        comment="Excelente servicio, muy puntual y confiable.",
    ))
    mock_review_service.list_service_reviews = AsyncMock(return_value=[
        ReviewResponse(
            id=uuid.uuid4(),
            reviewer_id=uuid.uuid4(),
            reviewed_user_id=user_id,
            service_id=svc_id,
            rating=5,
            comment="Muy buen trabajo.",
        )
    ])
    mock_review_service.get_user_reputation = AsyncMock(return_value=UserReputationSummary(
        user_id=user_id,
        average_rating=4.9,
        total_reviews=15,
        reviews=[],
    ))

    app.dependency_overrides[get_review_service] = lambda: mock_review_service

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        # Crear reseña
        res_create = await client.post(
            "/api/v1/reviews",
            json={
                "service_id": str(svc_id),
                "reviewed_user_id": str(user_id),
                "rating": 5,
                "comment": "Excelente servicio, muy puntual y confiable."
            }
        )
        assert res_create.status_code == 201
        assert res_create.json()["rating"] == 5

        # Listar por servicio
        res_svc = await client.get(f"/api/v1/reviews/service/{svc_id}")
        assert res_svc.status_code == 200
        assert len(res_svc.json()) == 1

        # Reputación por usuario
        res_rep = await client.get(f"/api/v1/reviews/user/{user_id}")
        assert res_rep.status_code == 200
        assert res_rep.json()["average_rating"] == 4.9

    app.dependency_overrides.pop(get_review_service, None)


# 5. Test Categorías de Productos
@pytest.mark.asyncio
async def test_product_categories_api():
    mock_commerce_service = MagicMock(spec=CommerceService)
    mock_commerce_service.list_product_categories = AsyncMock(return_value=[
        ProductCategoryResponse(id=uuid.uuid4(), name="Panadería y Pastelería"),
        ProductCategoryResponse(id=uuid.uuid4(), name="Bodega y Abarrotes"),
    ])
    mock_commerce_service.create_product_category = AsyncMock(return_value=ProductCategoryResponse(
        id=uuid.uuid4(),
        name="Comida Casera",
    ))

    app.dependency_overrides[get_commerce_service] = lambda: mock_commerce_service

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        res_get = await client.get("/api/v1/products/categories")
        assert res_get.status_code == 200
        assert len(res_get.json()) == 2

        res_post = await client.post(
            "/api/v1/products/categories",
            json={"name": "Comida Casera"}
        )
        assert res_post.status_code == 201
        assert res_post.json()["name"] == "Comida Casera"

    app.dependency_overrides.pop(get_commerce_service, None)


# 6. Test Edición de Perfil (Avatar, Habilidades, Teléfono) y Cámara
@pytest.mark.asyncio
async def test_profile_update_and_camera_capture():
    mock_user_service = MagicMock(spec=UserService)
    user_id = uuid.UUID("a0000000-0000-0000-0000-000000000001")
    mock_user_service.update_profile = AsyncMock(return_value=ProfileResponse(
        id=user_id,
        full_name="Juan Vecino Pérez",
        phone="987654321",
        avatar_url="data:image/jpeg;base64,mockavatar",
        skill="Electricidad e Iluminación",
        skills=["Electricidad", "Reparaciones"],
    ))
    mock_user_service.verify_identity = AsyncMock(return_value=IdentityVerificationResultResponse(
        success=True,
        identity_status="verified",
        document_type="DNI",
        message="Verificación con cámara frontal y posterior exitosa.",
    ))

    app.dependency_overrides[get_user_service] = lambda: mock_user_service

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        # Actualizar perfil (habilidades, teléfono, etc.)
        res_update = await client.put(
            "/api/v1/users/me",
            json={
                "phone": "987654321",
                "skill": "Electricidad e Iluminación",
                "skills": ["Electricidad", "Reparaciones"]
            }
        )
        assert res_update.status_code == 200
        assert res_update.json()["phone"] == "987654321"
        assert res_update.json()["skill"] == "Electricidad e Iluminación"

        # Subir avatar mediante cámara o archivo
        avatar_bytes = b"\xff\xd8\xff\xe0\x00\x10JFIF" + b"\x00" * 100
        res_avatar = await client.post(
            "/api/v1/users/me/avatar",
            files={"avatar": ("avatar.jpg", avatar_bytes, "image/jpeg")}
        )
        assert res_avatar.status_code == 200
        assert "avatar_url" in res_avatar.json()

        # Captura frontal y posterior con la cámara
        fake_dni_front = b"\xff\xd8\xff\xe0" + b"\x00" * 100
        fake_dni_back = b"\xff\xd8\xff\xe0" + b"\x00" * 100
        res_camera = await client.post(
            "/api/v1/users/camera-capture",
            files={
                "dni_front": ("dni_front.jpg", fake_dni_front, "image/jpeg"),
                "dni_back": ("dni_back.jpg", fake_dni_back, "image/jpeg"),
            },
            data={"full_name": "Juan Vecino Pérez"}
        )
        assert res_camera.status_code == 200
        assert res_camera.json()["success"] is True

    app.dependency_overrides.pop(get_user_service, None)
