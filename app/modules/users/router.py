import base64
"""Rutas de API v1 para el módulo de usuarios y verificación de identidad."""
from typing import Optional
from fastapi import APIRouter, Depends, File, Form, UploadFile, status

from app.core.logging import logger
from app.core.security import CurrentUser, get_current_user
from app.modules.users.dependencies import get_user_service
from app.modules.users.schemas import (
    CompleteRegistrationRequest,
    CompleteRegistrationResponse,
    DNIExtractionResponse,
    IdentityVerificationResultResponse,
    ProfileResponse,
    ProfileUpdate,
    StartDniVerificationResponse,
    VerificationStatusSummaryResponse,
    VerifyFaceSessionResponse,
)
from app.modules.users.service import UserService

router = APIRouter(prefix="/users", tags=["Usuarios y Verificación"])


@router.post(
    "/verification-session/start-dni",
    response_model=StartDniVerificationResponse,
    status_code=status.HTTP_200_OK,
    summary="Paso 1: OCR de DNI e inicio de sesión temporal de verificación",
)
async def start_dni_verification(
    dni_front: UploadFile = File(..., description="Foto del anverso del DNI"),
    dni_back: Optional[UploadFile] = File(None, description="Foto opcional del reverso del DNI"),
    service: UserService = Depends(get_user_service),
):
    """
    Paso 1 del Onboarding VeciRed:
    - Extrae datos de DNI con Claude Vision.
    - Valida mayoría de edad (bloquea a menores de 18 años).
    - Emite un token firmado con expiración para continuar al Paso 2.
    - NO guarda usuarios ni datos en la base de datos hasta completar el flujo.
    """
    front_bytes = await dni_front.read()
    back_bytes = await dni_back.read() if dni_back else None

    logger.info(
        "Iniciando sesión de verificación DNI (anverso: %d bytes, reverso: %s)",
        len(front_bytes),
        f"{len(back_bytes)} bytes" if back_bytes else "None",
    )

    return await service.start_dni_verification_session(
        front_bytes=front_bytes,
        back_bytes=back_bytes,
    )


@router.post(
    "/verification-session/verify-face",
    response_model=VerifyFaceSessionResponse,
    status_code=status.HTTP_200_OK,
    summary="Paso 2: Comparación facial biométrica con InsightFace",
)
async def verify_face_session(
    verification_token: str = Form(..., description="Token firmado del Paso 1"),
    selfie: UploadFile = File(..., description="Foto selfie tomada con la cámara frontal"),
    service: UserService = Depends(get_user_service),
):
    """
    Paso 2 del Onboarding VeciRed:
    - Compara el rostro de la selfie en vivo contra el rostro del DNI en memoria usando InsightFace.
    - Valida liveness (prueba de vida) y distancia euclidiana/coseno de vectores faciales.
    - Emite un token actualizado con stage='face_verified'.
    - NO auto-aprueba en caso de discrepancia biométrica.
    """
    selfie_bytes = await selfie.read()

    logger.info(
        "Ejecutando verificación facial para sesión temporal (selfie: %d bytes)",
        len(selfie_bytes),
    )

    return await service.verify_face_in_session(
        verification_token=verification_token,
        selfie_bytes=selfie_bytes,
    )


@router.post(
    "/complete-onboarding-registration",
    response_model=CompleteRegistrationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Paso 6: Registro definitivo y persistencia atómica en base de datos",
)
async def complete_onboarding_registration(
    request: CompleteRegistrationRequest,
    current_user: CurrentUser = Depends(get_current_user),
    service: UserService = Depends(get_user_service),
):
    """
    Paso 6 del Onboarding VeciRed:
    - Exige que el usuario haya sido creado en Supabase Auth y suministre su token JWT.
    - Valida que el verification_token contenga la aprobación facial estricta.
    - Persiste atómicamente: perfil, verificación de DNI, dirección actual, membresía y oficio.
    """
    logger.info(
        "Completando registro definitivo para usuario autenticado %s",
        current_user.id,
    )

    return await service.complete_onboarding_registration(
        user_id=current_user.id,
        request=request,
    )



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
    """Actualiza datos del perfil como nombre, teléfono, habilidades o preferencia de tamaño de fuente."""
    return await service.update_profile(current_user.id, profile_update)


@router.post(
    "/me/avatar",
    response_model=ProfileResponse,
    summary="Subir o actualizar foto de avatar del perfil (cámara o galería)",
)
async def upload_my_avatar(
    avatar: UploadFile = File(..., description="Archivo de imagen para avatar"),
    current_user: CurrentUser = Depends(get_current_user),
    service: UserService = Depends(get_user_service),
):
    """Actualiza el avatar del perfil procesando la foto tomada con la cámara."""
    avatar_bytes = await avatar.read()
    content_type = avatar.content_type or "image/jpeg"
    b64_str = base64.b64encode(avatar_bytes).decode("utf-8")
    avatar_url = f"data:{content_type};base64,{b64_str}"

    profile_update = ProfileUpdate(avatar_url=avatar_url)
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
    summary="Verificar identidad con DNI (frontal/posterior) y Selfie mediante IA",
)
async def verify_identity(
    dni_front: UploadFile = File(..., description="Foto del anverso del DNI"),
    selfie: Optional[UploadFile] = File(None, description="Selfie con rostro claro tomada en vivo"),
    dni_back: Optional[UploadFile] = File(None, description="Foto del reverso del DNI"),
    full_name: Optional[str] = Form(None, description="Nombre completo ingresado por el vecino"),
    current_user: CurrentUser = Depends(get_current_user),
    service: UserService = Depends(get_user_service),
):
    """
    Procesa la verificación de identidad mediante IA:
    - Extrae datos y valida estructura del DNI con OCR en ambas caras.
    - Si se incluye selfie, realiza comparación facial biométrica.
    - Registra el resultado en `identity_verifications` y actualiza el estado en `profiles`.
    """
    front_bytes = await dni_front.read()
    selfie_bytes = await selfie.read() if selfie else None
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

@router.post(
    "/camera-capture",
    response_model=IdentityVerificationResultResponse,
    status_code=status.HTTP_200_OK,
    summary="Capturar fotos frontal y posterior del documento con la cámara",
)
async def camera_capture_documents(
    dni_front: UploadFile = File(..., description="Foto del anverso del DNI tomada con cámara"),
    dni_back: UploadFile = File(..., description="Foto del reverso del DNI tomada con cámara"),
    full_name: Optional[str] = Form(None, description="Nombre completo ingresado por el vecino"),
    current_user: CurrentUser = Depends(get_current_user),
    service: UserService = Depends(get_user_service),
):
    """Permite el escaneo rápido de ambas caras del DNI con la cámara en el login o registro."""
    front_bytes = await dni_front.read()
    back_bytes = await dni_back.read()
    return await service.verify_identity(
        user_id=current_user.id,
        dni_front_bytes=front_bytes,
        dni_back_bytes=back_bytes,
        selfie_bytes=None,
        user_full_name=full_name,
    )
