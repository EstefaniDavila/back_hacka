"""Pruebas unitarias y de integración para el módulo users y verificación de identidad."""
import io
import pytest
from PIL import Image, ImageDraw
from httpx import ASGITransport, AsyncClient

from datetime import date
from unittest.mock import AsyncMock, patch

from app.integrations.face_verification import face_verification_service
from app.integrations.ocr import (
    OCRExtractionResult,
    calculate_age,
    dni_ocr_service,
    parse_birth_date,
)
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

    mock_ocr = OCRExtractionResult(
        dni_number="72849103",
        dni_last4="9103",
        document_hash="mock_hash_12345678",
        full_name="Carlos Mendoza",
        first_name="Carlos",
        last_name="Mendoza",
        birth_date=date(1992, 4, 10),
        age=32,
        is_adult=True,
        underage_blocked=False,
        gender="M",
        ubigeo="150101",
        confidence=0.96,
        is_valid_format=True,
        api_key_configured=True,
    )

    with patch.object(dni_ocr_service, "extract_dni_data", new=AsyncMock(return_value=mock_ocr)):
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
            assert res_data["document_last4"] == "9103"
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


def test_age_calculation_and_underage_check():
    """Valida el cálculo de edad y bloqueo estricto a menores de 18 años."""
    today = date(2026, 11, 8)
    
    # Mayor de edad (30 años)
    adult_birth = date(1996, 5, 20)
    assert calculate_age(adult_birth, today) == 30

    # Exactamente 18 años
    exactly_18 = date(2008, 11, 8)
    assert calculate_age(exactly_18, today) == 18

    # Menor de edad (17 años - cumple mañana)
    almost_18 = date(2008, 11, 9)
    assert calculate_age(almost_18, today) == 17

    # Menor de edad (15 años)
    minor_birth = date(2011, 3, 15)
    minor_age = calculate_age(minor_birth, today)
    assert minor_age == 15
    assert minor_age < 18


def test_claude_vision_json_parser_adult_and_underage():
    """Prueba unitaria aislada para el parser de Claude Vision con casos adulto, menor y campos no legibles."""
    img = Image.new("RGB", (400, 250))

    # 1. Caso DNI válido con titular mayor de edad
    valid_json = """{
        "dni_number": "72849103",
        "nombres": "JUAN ALBERTO",
        "primer_apellido": "PEREZ",
        "segundo_apellido": "GOMEZ",
        "fecha_nacimiento": "1994-08-15",
        "sexo": "M",
        "ubigeo": "150101",
        "campos_no_legibles": [],
        "confianza": 0.95,
        "observaciones": "DNI azul nítido"
    }"""
    result = dni_ocr_service._parse_claude_response(valid_json, "dummy_hash", img, None)
    assert result.is_valid_format is True
    assert result.dni_number == "72849103"
    assert result.dni_last4 == "9103"
    assert result.full_name == "JUAN ALBERTO PEREZ GOMEZ"
    assert result.is_adult is True
    assert result.underage_blocked is False
    assert result.age > 18
    assert result.gender == "M"
    assert result.ubigeo == "150101"
    assert len(result.unreadable_fields) == 0

    # 2. Caso DNI con menor de edad (bloqueo automático)
    minor_json = """{
        "dni_number": "79812345",
        "nombres": "LUCIA",
        "primer_apellido": "TORRES",
        "segundo_apellido": "CASTRO",
        "fecha_nacimiento": "2010-06-12",
        "sexo": "F",
        "ubigeo": "150101",
        "campos_no_legibles": [],
        "confianza": 0.92
    }"""
    minor_result = dni_ocr_service._parse_claude_response(minor_json, "dummy_hash", img, None)
    assert minor_result.is_adult is False
    assert minor_result.underage_blocked is True
    assert minor_result.is_valid_format is False
    assert "menor de edad" in minor_result.error_message.lower()

    # 3. Caso con campos borrosos o no legibles
    unreadable_json = """{
        "dni_number": null,
        "nombres": "CARLOS",
        "primer_apellido": null,
        "segundo_apellido": null,
        "fecha_nacimiento": null,
        "sexo": null,
        "ubigeo": null,
        "campos_no_legibles": ["dni_number", "primer_apellido", "segundo_apellido", "fecha_nacimiento", "ubigeo"],
        "confianza": 0.35,
        "observaciones": "Imagen borrosa y con reflejos"
    }"""
    unreadable_result = dni_ocr_service._parse_claude_response(unreadable_json, "dummy_hash", img, None)
    assert unreadable_result.is_valid_format is False
    assert "dni_number" in unreadable_result.unreadable_fields
    assert "primer_apellido" in unreadable_result.unreadable_fields


@pytest.mark.asyncio
async def test_extract_dni_endpoint_flow():
    """Verifica el endpoint POST /api/v1/users/extract-dni para extracción de datos."""
    dni_front = create_sample_image(400, 250)
    dni_back = create_sample_image(400, 250)

    mock_ocr = OCRExtractionResult(
        dni_number="45892014",
        dni_last4="2014",
        document_hash="hash_extract_test",
        full_name="MARIA ELENA QUISPE MAMANI",
        first_name="MARIA ELENA",
        last_name="QUISPE MAMANI",
        birth_date=date(1991, 7, 23),
        age=33,
        is_adult=True,
        underage_blocked=False,
        gender="F",
        ubigeo="150114",
        confidence=0.95,
        is_valid_format=True,
        api_key_configured=True,
    )

    with patch.object(dni_ocr_service, "extract_dni_data", new=AsyncMock(return_value=mock_ocr)):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            response = await client.post(
                "/api/v1/users/extract-dni",
                files={
                    "dni_front": ("dni_f.jpg", dni_front, "image/jpeg"),
                    "dni_back": ("dni_b.jpg", dni_back, "image/jpeg"),
                },
            )
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert data["dni_number"] == "45892014"
            assert data["dni_last4"] == "2014"
            assert data["full_name"] == "MARIA ELENA QUISPE MAMANI"
            assert data["gender"] == "F"
            assert data["ubigeo"] == "150114"
            assert data["is_adult"] is True
            assert data["underage_blocked"] is False
            assert data["api_key_configured"] is True


def test_face_verification_unit():
    """Prueba unitaria aislada para comparación de rostro y prueba de vida."""
    selfie_bytes = create_sample_image(300, 400)
    dni_bytes = create_sample_image(400, 250)
    result = face_verification_service.verify_face_match(selfie_bytes, dni_bytes)
    assert result.is_match is True
    assert result.liveness_passed is True
    assert result.confidence_score >= 0.8
