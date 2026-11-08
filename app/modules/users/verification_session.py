"""Módulo de gestión de sesiones de verificación temporal con tokens firmados."""
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
import uuid
import jwt
from fastapi import HTTPException, status

from app.core.config import settings
from app.core.logging import logger

VERIFICATION_TOKEN_ALGORITHM = "HS256"
VERIFICATION_TOKEN_EXPIRE_MINUTES = 45


def _get_signing_key() -> str:
    """Obtiene la clave de firma segura para los tokens de verificación."""
    key = settings.SUPABASE_JWT_SECRET or "vecired-verification-session-secret-2026"
    return key


class VerificationSessionManager:
    """
    Administrador en memoria de sesiones temporales de verificación biométrica y documental.
    Permite almacenar temporalmente los bytes del anverso del DNI para compararlos
    con la selfie en el Paso 2 sin persistir registros en base de datos.
    """

    def __init__(self) -> None:
        self._sessions: Dict[str, Dict[str, Any]] = {}

    def _cleanup_expired(self) -> None:
        """Elimina sesiones en memoria que hayan superado el tiempo de expiración."""
        now = datetime.now(timezone.utc)
        expired_keys = [
            k
            for k, v in self._sessions.items()
            if v.get("expires_at") and v["expires_at"] < now
        ]
        for k in expired_keys:
            self._sessions.pop(k, None)

    def create_dni_session(
        self,
        dni_number: Optional[str],
        dni_last4: Optional[str],
        document_hash: Optional[str],
        full_name: Optional[str],
        first_name: Optional[str],
        last_name: Optional[str],
        birth_date: Optional[str],
        age: Optional[int],
        is_adult: bool,
        gender: Optional[str],
        ubigeo: Optional[str],
        dni_front_bytes: bytes,
    ) -> Dict[str, Any]:
        """Crea una nueva sesión tras aprobar el Paso 1 (DNI OCR) y genera el token firmado."""
        self._cleanup_expired()
        session_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(minutes=VERIFICATION_TOKEN_EXPIRE_MINUTES)

        payload = {
            "session_id": session_id,
            "stage": "dni_verified",
            "dni_number": dni_number,
            "dni_last4": dni_last4,
            "document_hash": document_hash,
            "full_name": full_name,
            "first_name": first_name,
            "last_name": last_name,
            "birth_date": birth_date,
            "age": age,
            "is_adult": is_adult,
            "gender": gender,
            "ubigeo": ubigeo,
            "face_matched": False,
            "face_confidence": 0.0,
            "iat": int(now.timestamp()),
            "exp": int(expires_at.timestamp()),
        }

        token = jwt.encode(payload, _get_signing_key(), algorithm=VERIFICATION_TOKEN_ALGORITHM)

        self._sessions[session_id] = {
            "created_at": now,
            "expires_at": expires_at,
            "dni_front_bytes": dni_front_bytes,
            "data": payload,
        }

        logger.info("Sesión de verificación DNI creada: session_id=%s, dni_last4=%s", session_id, dni_last4)
        return {
            "session_id": session_id,
            "verification_token": token,
            "stage": "dni_verified",
            "data": payload,
        }

    def decode_and_validate_token(self, token: str) -> Dict[str, Any]:
        """Valida la firma criptográfica y expiración del token de verificación."""
        try:
            payload = jwt.decode(
                token,
                _get_signing_key(),
                algorithms=[VERIFICATION_TOKEN_ALGORITHM],
                options={"verify_exp": True},
            )
            return payload
        except jwt.ExpiredSignatureError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="La sesión de verificación ha expirado. Por favor vuelve a escanear tu DNI.",
            )
        except jwt.PyJWTError as e:
            logger.warning("Token de verificación inválido: %s", str(e))
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Token de verificación de identidad inválido o manipulado.",
            )

    def get_cached_dni_bytes(self, session_id: str) -> Optional[bytes]:
        """Obtiene los bytes del anverso del DNI asociados a la sesión."""
        self._cleanup_expired()
        session = self._sessions.get(session_id)
        if not session:
            return None
        return session.get("dni_front_bytes")

    def advance_to_face_verified(
        self,
        token: str,
        face_confidence: float,
        verification_type: str = "face_presence_check",
    ) -> Dict[str, Any]:
        """Actualiza el estado de la sesión a 'face_verified' tras superar la detección de presencia facial."""
        payload = self.decode_and_validate_token(token)
        session_id = payload.get("session_id")

        if not payload.get("is_adult"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="El titular del documento es menor de edad. Registro denegado.",
            )

        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(minutes=VERIFICATION_TOKEN_EXPIRE_MINUTES)

        updated_payload = dict(payload)
        updated_payload["stage"] = "face_verified"
        updated_payload["face_matched"] = True
        updated_payload["face_confidence"] = float(face_confidence)
        updated_payload["verification_type"] = verification_type
        updated_payload["iat"] = int(now.timestamp())
        updated_payload["exp"] = int(expires_at.timestamp())

        new_token = jwt.encode(
            updated_payload,
            _get_signing_key(),
            algorithm=VERIFICATION_TOKEN_ALGORITHM,
        )

        if session_id in self._sessions:
            self._sessions[session_id]["data"] = updated_payload
            self._sessions[session_id]["expires_at"] = expires_at

        logger.info(
            "Sesión avanzada a 'face_verified': session_id=%s, confidence=%.3f",
            session_id,
            face_confidence,
        )
        return {
            "session_id": session_id,
            "verification_token": new_token,
            "stage": "face_verified",
            "data": updated_payload,
        }

    def evict_session(self, session_id: str) -> None:
        """Elimina una sesión completada o revocada."""
        self._sessions.pop(session_id, None)


verification_session_manager = VerificationSessionManager()
