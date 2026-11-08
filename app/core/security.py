"""Módulo de seguridad y autenticación con Supabase JWT."""
import uuid
from typing import Any, Dict, Optional
import jwt
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.logging import logger

security_scheme = HTTPBearer(auto_error=False)


class CurrentUser(BaseModel):
    """Representación del usuario autenticado actual."""
    id: uuid.UUID
    email: Optional[str] = None
    role: Optional[str] = "authenticated"
    raw_claims: Dict[str, Any] = Field(default_factory=dict)


def decode_supabase_token(token: str) -> Dict[str, Any]:
    """
    Decodifica y valida un token JWT emitido por Supabase.
    Soporta verificación con SUPABASE_JWT_SECRET y decodificación
    controlada en modo desarrollo si el secreto no está provisto.
    """
    try:
        if settings.SUPABASE_JWT_SECRET:
            # Si el secreto está configurado, verificar la firma HS256
            payload = jwt.decode(
                token,
                settings.SUPABASE_JWT_SECRET,
                algorithms=["HS256"],
                options={"verify_aud": False},
            )
        else:
            # En desarrollo, decodificar el payload del token de Supabase
            payload = jwt.decode(
                token,
                options={"verify_signature": False, "verify_aud": False},
                algorithms=["HS256", "RS256", "ES256"],
            )
        return payload
    except jwt.ExpiredSignatureError:
        logger.warning("Token JWT expirado.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="El token de sesión ha expirado.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.PyJWTError as e:
        logger.warning("Error decodificando token JWT: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de autenticación inválido.",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_user(
    auth_header: Optional[HTTPAuthorizationCredentials] = Depends(security_scheme),
    x_test_user_id: Optional[str] = Header(None, alias="X-Test-User-Id"),
) -> CurrentUser:
    """
    Dependencia FastAPI que obtiene y valida el usuario actual.
    Soporta:
    1. Header estándar Authorization: Bearer <token_supabase>
    2. Header X-Test-User-Id en entorno development/debug para pruebas automatizadas.
    3. Usuario local por defecto en entorno development si no se envía header.
    """
    # 1. Bypass para pruebas si DEBUG está activo y viene header de test o fallback
    if settings.DEBUG:
        if x_test_user_id:
            try:
                user_uuid = uuid.UUID(x_test_user_id)
                return CurrentUser(
                    id=user_uuid,
                    email="test_user@vecired.local",
                    role="authenticated",
                    raw_claims={"sub": str(user_uuid), "test": True},
                )
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="X-Test-User-Id debe ser un UUID válido.",
                )
        if not auth_header or not auth_header.credentials:
            dev_user_uuid = uuid.UUID("a0000000-0000-0000-0000-000000000001")
            return CurrentUser(
                id=dev_user_uuid,
                email="vecino@vecired.local",
                role="authenticated",
                raw_claims={"sub": str(dev_user_uuid), "test": True},
            )

    # 2. Validación de Bearer Token
    if not auth_header or not auth_header.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Se requiere un token de autenticación.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_supabase_token(auth_header.credentials)
    sub = payload.get("sub")
    if not sub:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="El token no contiene un identificador de usuario válido.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        user_uuid = uuid.UUID(sub)
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="El identificador de usuario en el token no es un UUID válido.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    email = payload.get("email") or payload.get("user_metadata", {}).get("email")
    role = payload.get("role", "authenticated")

    return CurrentUser(
        id=user_uuid,
        email=email,
        role=role,
        raw_claims=payload,
    )
