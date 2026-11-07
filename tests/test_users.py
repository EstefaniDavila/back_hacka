"""Pruebas unitarias y de integración para el módulo users y verificación de identidad."""
import io
import pytest
from PIL import Image, ImageDraw
from httpx import ASGITransport, AsyncClient

from app.integrations.face_verification import face_verification_service
from app.integrations.ocr import dni_ocr_service
from app.main import app


def create_sample_image(width: int = 400, height: int = 250, color: str = "rgb(180, 200, 220)") -> bytes:
    """Genera una imagen sintética en memoria con suficiente resolución y varianza."""
    img = Image.new("RGB", (width, height), color=color)
    draw = ImageDraw.Draw(img)
    # Dibujar elementos para garantizar varianza y contraste
    draw.rectangle([20, 20, 100, 100], fill="rgb(30, 60, 90)")
    draw.line([0, 0, width, height], fill="rgb(200, 50, 50)", width=4)
    draw.text((30, 120), "PERU DNI 72849103", fill="rgb(10, 10, 10)")
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


@pytest.mark.asyncio
async def test_get_my_profile_unauthorized():
    """Verifica que solicitar /me sin credenciales retorne 401."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.get("/api/v1/users/me")
        assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_or_create_profile_with_test_header(test_auth_user):
    """Verifica la creación o lectura de perfil con un usuario autenticado."""
    headers = test_auth_user["headers"]
    user_id_str = str(test_auth_user["id"])

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.get(
            "/api/v1/users/me",
            headers=headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == user_id_str
        assert "full_name" in data
        assert data["account_status"] in ("pending", "pending_verification")


@pytest.mark.asyncio
async def test_update_user_profile(test_auth_user):
    """Verifica la actualización de campos del perfil."""
    headers = test_auth_user["headers"]

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        # Asegurar creación inicial
        await client.get("/api/v1/users/me", headers=headers)

        # Actualizar datos
        update_payload = {
            "full_name": "María Quispe Rojas",
            "phone": "+51987654321",
            "font_scale_preference": "1.15",
        }
        res_put = await client.put(
            "/api/v1/users/me",
            headers=headers,
            json=update_payload,
        )
        assert res_put.status_code == 200
        updated = res_put.json()
        assert updated["full_name"] == "María Quispe Rojas"
        assert updated["phone"] == "+51987654321"
        assert updated["font_scale_preference"] == "1.15"


@pytest.mark.asyncio
async def test_verify_identity_full_flow(test_auth_user):
    """Verifica el flujo completo de subida de DNI y Selfie para verificación de identidad."""
    headers = test_auth_user["headers"]

    dni_front = create_sample_image(400, 250)
    dni_back = create_sample_image(400, 250)
    selfie = create_sample_image(300, 400)

    files = {
        "dni_front": ("dni_anverso.jpg", dni_front, "image/jpeg"),
        "dni_back": ("dni_reverso.jpg", dni_back, "image/jpeg"),
        "selfie": ("selfie_rostro.jpg", selfie, "image/jpeg"),
    }
    data = {
        "full_name": "Carlos Mendoza",
    }

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.post(
            "/api/v1/users/verify-identity",
            headers=headers,
            files=files,
            data=data,
        )
        assert response.status_code == 200
        res_data = response.json()
        assert res_data["success"] is True
        assert res_data["identity_status"] == "verified"
        assert "document_last4" in res_data
        assert res_data["face_match"]["matched"] is True

        # Comprobar que el endpoint de estado de verificación refleja la validación
        status_res = await client.get(
            "/api/v1/users/verification-status",
            headers=headers,
        )
        assert status_res.status_code == 200
        status_data = status_res.json()
        assert status_data["identity_verified"] is True
        assert status_data["identity_status"] == "verified"
        assert status_data["profile"]["account_status"] == "verified"


def test_dni_ocr_unit():
    """Prueba unitaria aislada para el extractor de DNI."""
    img_bytes = create_sample_image(400, 250)
    result = dni_ocr_service.extract_dni_data(img_bytes, fallback_name="Juan Perez")
    assert result.is_valid_format is True
    assert len(result.dni_number) == 8
    assert len(result.dni_last4) == 4
    assert result.confidence > 0.8


def test_face_verification_unit():
    """Prueba unitaria aislada para comparación de rostro y prueba de vida."""
    selfie_bytes = create_sample_image(300, 400)
    dni_bytes = create_sample_image(400, 250)
    result = face_verification_service.verify_face_match(selfie_bytes, dni_bytes)
    assert result.is_match is True
    assert result.liveness_passed is True
    assert result.confidence_score >= 0.8
