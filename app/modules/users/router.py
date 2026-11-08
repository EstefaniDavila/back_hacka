"""Rutas de API v1 para el módulo de usuarios y verificación de identidad."""
from typing import Optional
from fastapi import APIRouter, Depends, File, Form, UploadFile, status

from app.core.logging import logger
from app.core.security import CurrentUser, get_current_user
from app.modules.users.dependencies import get_user_service
from app.modules.users.schemas import (
    DNIExtractionResponse,
    IdentityVerificationResultResponse,
    ProfileResponse,
    ProfileUpdate,
    VerificationStatusSummaryResponse,
)
from app.modules.users.service import UserService

router = APIRouter(prefix="/users", tags=["Usuarios y Verificación"])


@router.get(
    "/me",
    response_model=ProfileResponse,
    summary="Obtener perfil del usuario autenticado",
)
async def get_my_profile(
    current_user: CurrentUser = Depends(get_current_user),
    service: UserService = Depends(get_user_service),
):
    """
    Retorna el perfil del usuario actual a partir de su token de autenticación Supabase.
    Si el perfil no existía aún en la base de datos, lo crea automáticamente.
    """
    profile = await service.get_or_create_profile(
        user_id=current_user.id,
        email=current_user.email,
    )
    return ProfileResponse.model_validate(profile)


@router.put(
    "/me",
    response_model=ProfileResponse,
    summary="Actualizar perfil del usuario autenticado",
)
async def update_my_profile(
    profile_update: ProfileUpdate,
    current_user: CurrentUser = Depends(get_current_user),
    service: UserService = Depends(get_user_service),
):
    """Actualiza datos del perfil como nombre, teléfono o preferencia de tamaño de fuente."""
    return await service.update_profile(current_user.id, profile_update)


@router.post(
    "/extract-dni",
    response_model=DNIExtractionResponse,
    status_code=status.HTTP_200_OK,
    summary="Extraer automáticamente datos del DNI con Claude Vision",
)
async def extract_dni(
    dni_front: UploadFile = File(..., description="Foto del anverso del DNI"),
    dni_back: Optional[UploadFile] = File(None, description="Foto opcional del reverso del DNI"),
    service: UserService = Depends(get_user_service),
):
    """
    Extrae datos del DNI peruano (DNI, nombres, apellidos, fecha de nacimiento, sexo, ubigeo)
    usando Claude Vision. Calcula la edad y bloquea a menores de 18 años.
    No requiere autenticación previa para permitir autollenado durante el onboarding.
    """
    front_bytes = await dni_front.read()
    back_bytes = await dni_back.read() if dni_back else None

    logger.info(
        "Solicitud de extracción Claude Vision para DNI (anverso: %d bytes, reverso: %s)",
        len(front_bytes),
        f"{len(back_bytes)} bytes" if back_bytes else "None",
    )

    return await service.extract_dni_document(
        front_bytes=front_bytes,
        back_bytes=back_bytes,
    )


@router.post(
    "/verify-identity",
    response_model=IdentityVerificationResultResponse,
    status_code=status.HTTP_200_OK,
    summary="Verificar identidad con DNI y Selfie mediante IA",
)
async def verify_identity(
    dni_front: UploadFile = File(..., description="Foto del anverso del DNI"),
    selfie: UploadFile = File(..., description="Selfie con rostro claro tomada en vivo"),
    dni_back: Optional[UploadFile] = File(None, description="Foto opcional del reverso del DNI"),
    full_name: Optional[str] = Form(None, description="Nombre completo ingresado por el vecino"),
    current_user: CurrentUser = Depends(get_current_user),
    service: UserService = Depends(get_user_service),
):
    """
    Procesa la verificación de identidad mediante IA:
    - Extrae datos y valida estructura del DNI con OCR.
    - Compara biométricamente el rostro de la selfie con el DNI.
    - Registra el resultado en `identity_verifications` y actualiza el estado en `profiles`.
    """
    front_bytes = await dni_front.read()
    selfie_bytes = await selfie.read()
    back_bytes = await dni_back.read() if dni_back else None

    logger.info(
        "Iniciando verificación de identidad para usuario %s (front: %d bytes, selfie: %d bytes)",
        current_user.id,
        len(front_bytes),
        len(selfie_bytes),
    )

    result = await service.verify_identity(
        user_id=current_user.id,
        dni_front_bytes=front_bytes,
        dni_back_bytes=back_bytes,
        selfie_bytes=selfie_bytes,
        user_full_name=full_name,
    )
    return result


@router.get(
    "/verification-status",
    response_model=VerificationStatusSummaryResponse,
    summary="Consultar estado consolidado de verificación",
)
async def get_verification_status(
    current_user: CurrentUser = Depends(get_current_user),
    service: UserService = Depends(get_user_service),
):
    """
    Retorna el estado de verificación de identidad, residencia y membresía del usuario.
    Permite al frontend saber si el vecino está 'pending_verification', 'verified', etc.
    """
    return await service.get_verification_status_summary(current_user.id)
