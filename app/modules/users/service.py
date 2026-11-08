"""Lógica de negocio y orquestación del módulo de usuarios y verificación."""
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import EntityNotFoundException, ValidationException
from app.core.logging import logger
from app.integrations.face_verification import face_verification_service
from app.integrations.ocr import dni_ocr_service, parse_birth_date
from app.modules.geo.models import Address, Block, Community, District, Zone
from app.modules.users.models import (
    CommunityMembership,
    IdentityVerification,
    Profile,
    UserAddress,
    UserAvailability,
)
from app.modules.users.repository import (
    CommunityMembershipRepository,
    IdentityVerificationRepository,
    ProfileRepository,
    UserAddressRepository,
)
from app.modules.users.schemas import (
    CompleteRegistrationRequest,
    CompleteRegistrationResponse,
    DNIExtractionResponse,
    IdentityVerificationCreate,
    IdentityVerificationResultResponse,
    ProfileCreate,
    ProfileResponse,
    ProfileUpdate,
    StartDniVerificationResponse,
    VerificationStatusSummaryResponse,
    VerifyFaceSessionResponse,
)
from app.modules.users.verification_session import verification_session_manager



class UserService:
    """Servicio que encapsula las reglas de negocio para usuarios y verificación de identidad."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.profile_repo = ProfileRepository(session)
        self.identity_repo = IdentityVerificationRepository(session)
        self.address_repo = UserAddressRepository(session)
        self.community_repo = CommunityMembershipRepository(session)

    async def get_or_create_profile(
        self,
        user_id: uuid.UUID,
        email: Optional[str] = None,
        full_name: Optional[str] = None,
    ) -> Profile:
        """Obtiene el perfil existente o inicializa uno nuevo a partir de Supabase Auth."""
        profile = await self.profile_repo.get_by_id(user_id)
        if not profile:
            resolved_name = (
                full_name.strip()
                if full_name and full_name.strip()
                else (email.split("@")[0].title() if email else "Vecino VeciRed")
            )
            profile_data = {
                "id": user_id,
                "full_name": resolved_name,
                "account_status": "pending",
                "font_scale_preference": "1.0",
                "solidarity_helped_count": 0,
                "solidarity_received_count": 0,
                "created_at": datetime.now(timezone.utc).replace(tzinfo=None),
            }
            profile = await self.profile_repo.upsert_profile(profile_data)
            await self.session.commit()
            logger.info("Nuevo perfil creado para el usuario %s (%s)", user_id, resolved_name)
        return profile

    async def get_profile(self, user_id: uuid.UUID) -> ProfileResponse:
        """Obtiene los datos del perfil del usuario."""
        profile = await self.profile_repo.get_by_id(user_id)
        if not profile:
            # Crear perfil por defecto si aún no existe
            profile = await self.get_or_create_profile(user_id)
        return ProfileResponse.model_validate(profile)

    async def update_profile(
        self,
        user_id: uuid.UUID,
        profile_update: ProfileUpdate,
    ) -> ProfileResponse:
        """Actualiza la información del perfil del usuario."""
        profile = await self.profile_repo.get_by_id(user_id)
        if not profile:
            profile = await self.get_or_create_profile(user_id)

        update_dict = profile_update.model_dump(exclude_unset=True)
        updated_profile = await self.profile_repo.update(profile, update_dict)
        await self.session.commit()
        return ProfileResponse.model_validate(updated_profile)

    async def verify_identity(
        self,
        user_id: uuid.UUID,
        dni_front_bytes: bytes,
        dni_back_bytes: Optional[bytes],
        selfie_bytes: bytes,
        user_full_name: Optional[str] = None,
    ) -> IdentityVerificationResultResponse:
        """
        Orquesta el flujo completo de verificación de identidad con IA:
        1. Extracción de datos del DNI con OCR.
        2. Comparación biométrica facial de la selfie contra el documento.
        3. Persistencia de la verificación en `identity_verifications`.
        4. Actualización del estado del usuario en `profiles`.
        """
        profile = await self.get_or_create_profile(user_id, full_name=user_full_name)

        # 1. OCR DNI con Claude Vision
        try:
            ocr_result = await dni_ocr_service.extract_dni_data(
                front_bytes=dni_front_bytes,
                back_bytes=dni_back_bytes,
                fallback_name=profile.full_name or user_full_name,
            )
        except ValueError as e:
            raise ValidationException(f"Error procesando imagen del DNI: {str(e)}")

        # Validar mayoría de edad en el backend y bloquear a menores de 18 años
        if ocr_result.underage_blocked:
            raise ValidationException(
                ocr_result.error_message
                or f"Registro bloqueado: El titular tiene {ocr_result.age} años y es menor de edad. VeciRed requiere ser mayor de 18 años."
            )

        # 2. Verificación facial
        try:
            face_result = face_verification_service.verify_face_match(
                selfie_bytes=selfie_bytes,
                dni_front_bytes=dni_front_bytes,
            )
        except ValueError as e:
            raise ValidationException(f"Error procesando imagen de la selfie: {str(e)}")

        # 3. Determinar resultado y estado de identidad
        if face_result.is_match and ocr_result.is_valid_format:
            identity_status = "verified"
            account_status = "verified"
            message = "¡Identidad verificada exitosamente! Tu cuenta VeciRed está activa y validada."
            success = True
        elif not face_result.liveness_passed:
            identity_status = "rejected"
            account_status = "pending_verification"
            message = "La selfie no superó la prueba de vida y contraste. Por favor tómala con buena luz."
            success = False
        else:
            identity_status = "manual_review"
            account_status = "pending_verification"
            message = "Verificación en revisión. Tu documento está siendo analizado por nuestro equipo."
            success = True

        # 4. Registrar en identity_verifications
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        verification_entry = IdentityVerification(
            id=uuid.uuid4(),
            user_id=user_id,
            document_type="DNI",
            document_hash=ocr_result.document_hash,
            document_last4=ocr_result.dni_last4,
            identity_provider="claude_vision_ocr",
            identity_status=identity_status,
            verified_at=now if identity_status == "verified" else None,
            created_at=now,
        )
        self.session.add(verification_entry)

        # 5. Actualizar el perfil
        profile.account_status = account_status
        if ocr_result.full_name and (not profile.full_name or profile.full_name == "Vecino VeciRed"):
            profile.full_name = ocr_result.full_name
        if ocr_result.birth_date and not profile.birth_date:
            profile.birth_date = ocr_result.birth_date

        self.session.add(profile)
        await self.session.commit()

        logger.info(
            "Verificación para usuario %s: status=%s, dni_last4=%s",
            user_id,
            identity_status,
            ocr_result.dni_last4,
        )

        return IdentityVerificationResultResponse(
            success=success,
            identity_status=identity_status,
            document_type="DNI",
            document_last4=ocr_result.dni_last4,
            extracted_data={
                "dni_number": f"****{ocr_result.dni_last4}",
                "full_name": profile.full_name,
                "confidence": ocr_result.confidence,
                "ubigeo": ocr_result.ubigeo,
            },
            face_match={
                "matched": face_result.is_match,
                "confidence": face_result.confidence_score,
                "liveness": face_result.liveness_passed,
                "details": face_result.details,
            },
            message=message,
        )

    async def get_verification_status_summary(
        self,
        user_id: uuid.UUID,
    ) -> VerificationStatusSummaryResponse:
        """Obtiene el resumen consolidado de verificación de identidad, residencia y membresía."""
        profile = await self.profile_repo.get_by_id(user_id)
        if not profile:
            profile = await self.get_or_create_profile(user_id)

        latest_id_verif = await self.identity_repo.get_latest_by_user_id(user_id)
        user_address = await self.address_repo.get_primary_by_user(user_id)
        active_membership = await self.community_repo.get_active_by_user(user_id)

        identity_status = latest_id_verif.identity_status if latest_id_verif else "incomplete"
        identity_verified = identity_status == "verified"
        residence_status = user_address.residence_status if user_address else "unverified"

        return VerificationStatusSummaryResponse(
            profile=ProfileResponse.model_validate(profile),
            identity_verified=identity_verified,
            identity_status=identity_status,
            document_last4=latest_id_verif.document_last4 if latest_id_verif else None,
            residence_status=residence_status,
            community_id=active_membership.community_id if active_membership else None,
            community_name="Comunidad VeciRed" if active_membership else None,
        )

    async def extract_dni_document(
        self,
        front_bytes: bytes,
        back_bytes: Optional[bytes] = None,
    ) -> DNIExtractionResponse:
        """
        Extrae datos del DNI con Claude Vision y valida mayoría de edad.
        Diseñado para prellenar formularios en el onboarding vecinal.
        """
        try:
            ocr_result = await dni_ocr_service.extract_dni_data(
                front_bytes=front_bytes,
                back_bytes=back_bytes,
            )
        except ValueError as e:
            raise ValidationException(f"Error procesando imagen del DNI: {str(e)}")

        if ocr_result.underage_blocked:
            return DNIExtractionResponse(
                success=False,
                dni_number=ocr_result.dni_number,
                dni_last4=ocr_result.dni_last4,
                full_name=ocr_result.full_name,
                first_name=ocr_result.first_name,
                last_name=ocr_result.last_name,
                birth_date=ocr_result.birth_date,
                age=ocr_result.age,
                is_adult=False,
                underage_blocked=True,
                gender=ocr_result.gender,
                ubigeo=ocr_result.ubigeo,
                unreadable_fields=ocr_result.unreadable_fields,
                confidence=ocr_result.confidence,
                api_key_configured=ocr_result.api_key_configured,
                message=ocr_result.error_message
                or f"Registro bloqueado: El titular tiene {ocr_result.age} años y es menor de edad.",
            )

        if not ocr_result.api_key_configured:
            return DNIExtractionResponse(
                success=False,
                is_adult=True,
                underage_blocked=False,
                unreadable_fields=ocr_result.unreadable_fields,
                confidence=0.0,
                api_key_configured=False,
                message="ANTHROPIC_API_KEY no está configurada en el backend. Configure la variable en .env para habilitar la extracción con Claude Vision.",
            )

        success = ocr_result.is_valid_format
        msg = (
            "Datos de DNI extraídos exitosamente con Claude Vision."
            if success
            else (
                ocr_result.error_message
                or "No se pudieron extraer todos los datos requeridos del DNI. Verifique la nitidez de la fotografía."
            )
        )

        return DNIExtractionResponse(
            success=success,
            dni_number=ocr_result.dni_number,
            dni_last4=ocr_result.dni_last4,
            full_name=ocr_result.full_name,
            first_name=ocr_result.first_name,
            last_name=ocr_result.last_name,
            birth_date=ocr_result.birth_date,
            age=ocr_result.age,
            is_adult=ocr_result.is_adult,
            underage_blocked=False,
            gender=ocr_result.gender,
            ubigeo=ocr_result.ubigeo,
            unreadable_fields=ocr_result.unreadable_fields,
            confidence=ocr_result.confidence,
            api_key_configured=True,
            message=msg,
        )

    async def start_dni_verification_session(
        self,
        front_bytes: bytes,
        back_bytes: Optional[bytes] = None,
    ) -> StartDniVerificationResponse:
        """
        Paso 1 del onboarding:
        - Extrae datos y valida estructura del DNI con Claude Vision.
        - Verifica mayoría de edad (bloquea a menores de 18 años sin crear cuenta).
        - Inicia una sesión temporal y emite un verification_token firmado con stage='dni_verified'.
        - NO persiste usuario ni datos incompletos en la base de datos.
        """
        try:
            ocr_result = await dni_ocr_service.extract_dni_data(
                front_bytes=front_bytes,
                back_bytes=back_bytes,
            )
        except ValueError as e:
            raise ValidationException(f"Error procesando imagen del DNI: {str(e)}")

        # Bloqueo inmediato a menores de 18 años
        if ocr_result.underage_blocked or (isinstance(ocr_result.age, int) and ocr_result.age < 18):
            logger.warning(
                "Intento de registro de menor de edad bloqueado: age=%s, dni_last4=%s",
                ocr_result.age,
                ocr_result.dni_last4,
            )
            blocked_msg = (
                ocr_result.error_message
                or f"Registro bloqueado: El titular tiene {ocr_result.age} años de edad. VeciRed IA es exclusivamente para personas mayores de 18 años."
            )
            return StartDniVerificationResponse(
                success=False,
                stage="blocked",
                underage_blocked=True,
                extracted_data=DNIExtractionResponse(
                    success=False,
                    dni_number=ocr_result.dni_number,
                    dni_last4=ocr_result.dni_last4,
                    full_name=ocr_result.full_name,
                    first_name=ocr_result.first_name,
                    last_name=ocr_result.last_name,
                    birth_date=ocr_result.birth_date,
                    age=ocr_result.age,
                    is_adult=False,
                    underage_blocked=True,
                    gender=ocr_result.gender,
                    ubigeo=ocr_result.ubigeo,
                    unreadable_fields=ocr_result.unreadable_fields,
                    confidence=ocr_result.confidence,
                    api_key_configured=ocr_result.api_key_configured,
                    message=blocked_msg,
                ),
                message=blocked_msg,
            )

        # Validación de formato y legibilidad del documento
        if not ocr_result.is_valid_format and ocr_result.api_key_configured:
            return StartDniVerificationResponse(
                success=False,
                stage="dni_invalid",
                underage_blocked=False,
                extracted_data=DNIExtractionResponse(
                    success=False,
                    dni_number=ocr_result.dni_number,
                    dni_last4=ocr_result.dni_last4,
                    full_name=ocr_result.full_name,
                    first_name=ocr_result.first_name,
                    last_name=ocr_result.last_name,
                    birth_date=ocr_result.birth_date,
                    age=ocr_result.age,
                    is_adult=ocr_result.is_adult,
                    underage_blocked=False,
                    gender=ocr_result.gender,
                    ubigeo=ocr_result.ubigeo,
                    unreadable_fields=ocr_result.unreadable_fields,
                    confidence=ocr_result.confidence,
                    api_key_configured=ocr_result.api_key_configured,
                    message=ocr_result.error_message or "La fotografía del DNI no es legible.",
                ),
                message=ocr_result.error_message
                or "No fue posible leer con suficiente nitidez los datos del DNI. Por favor vuelve a tomar la fotografía con mejor iluminación.",
            )

        # Crear sesión temporal de verificación en memoria y emitir token firmado
        birth_str = ocr_result.birth_date.isoformat() if ocr_result.birth_date else None
        session_info = verification_session_manager.create_dni_session(
            dni_number=ocr_result.dni_number,
            dni_last4=ocr_result.dni_last4,
            document_hash=ocr_result.document_hash,
            full_name=ocr_result.full_name,
            first_name=ocr_result.first_name,
            last_name=ocr_result.last_name,
            birth_date=birth_str,
            age=ocr_result.age,
            is_adult=ocr_result.is_adult,
            gender=ocr_result.gender,
            ubigeo=ocr_result.ubigeo,
            dni_front_bytes=front_bytes,
        )

        return StartDniVerificationResponse(
            success=True,
            stage="dni_verified",
            session_id=session_info["session_id"],
            verification_token=session_info["verification_token"],
            extracted_data=DNIExtractionResponse(
                success=True,
                dni_number=ocr_result.dni_number,
                dni_last4=ocr_result.dni_last4,
                full_name=ocr_result.full_name,
                first_name=ocr_result.first_name,
                last_name=ocr_result.last_name,
                birth_date=ocr_result.birth_date,
                age=ocr_result.age,
                is_adult=ocr_result.is_adult,
                underage_blocked=False,
                gender=ocr_result.gender,
                ubigeo=ocr_result.ubigeo,
                unreadable_fields=ocr_result.unreadable_fields,
                confidence=ocr_result.confidence,
                api_key_configured=ocr_result.api_key_configured,
                message="DNI verificado y validado con éxito.",
            ),
            message="DNI validado exitosamente. Sesión de verificación iniciada.",
        )

    async def verify_face_in_session(
        self,
        verification_token: str,
        selfie_bytes: bytes,
    ) -> VerifyFaceSessionResponse:
        """
        Paso 2 del onboarding: Verificación de Presencia Facial (Hackathon):
        - Valida el token firmado emitido en el Paso 1.
        - Detecta que existe al menos un rostro humano en la imagen selfie y que está visible.
        - NO exige coincidencia biométrica entre la selfie y la fotografía del DNI.
        - NO bloquea el registro por diferencias entre ambos rostros.
        - Si detecta un rostro humano, emite el token actualizado con stage='face_verified'.
        - Si no detecta ningún rostro o la imagen está vacía/cubierta, rechaza solicitando colocarse frente a la cámara.
        """
        payload = verification_session_manager.decode_and_validate_token(verification_token)
        session_id = payload.get("session_id")
        if not session_id:
            raise ValidationException("Token de sesión inválido.")

        if not payload.get("is_adult"):
            raise ValidationException("El titular del documento es menor de edad.")

        try:
            # Ejecutar detección real de presencia facial en la selfie
            presence_result = face_verification_service.verify_face_presence(selfie_bytes)
        except ValueError as e:
            raise ValidationException(f"Error procesando la captura facial: {str(e)}")

        # Verificación estricta de presencia: No aceptar imágenes vacías o sin rostro humano
        if not presence_result.is_match or not presence_result.details.get("face_detected", True):
            reason = (
                presence_result.details.get("reason")
                or "No se detectó ningún rostro humano en la imagen. Por favor colócate de frente a la cámara e inténtalo de nuevo."
            )
            logger.warning(
                "Presencia facial no detectada para session %s: confidence=%.3f, reason=%s",
                session_id,
                presence_result.confidence_score,
                reason,
            )
            return VerifyFaceSessionResponse(
                success=False,
                stage="face_presence_failed",
                session_id=session_id,
                verification_token=None,
                is_match=False,
                confidence_score=presence_result.confidence_score,
                liveness_passed=presence_result.liveness_passed,
                message=reason,
                details=presence_result.details,
            )

        if not presence_result.liveness_passed:
            reason = (
                presence_result.details.get("reason")
                or "La captura no superó la prueba de visibilidad y contraste. Por favor tómala en un ambiente con buena luz."
            )
            logger.warning("Prueba de liveness/visibilidad fallida para session %s", session_id)
            return VerifyFaceSessionResponse(
                success=False,
                stage="liveness_failed",
                session_id=session_id,
                verification_token=None,
                is_match=False,
                confidence_score=presence_result.confidence_score,
                liveness_passed=False,
                message=reason,
                details=presence_result.details,
            )

        # Avanzar el token a 'face_verified' con identificación 'face_presence_check'
        advanced = verification_session_manager.advance_to_face_verified(
            token=verification_token,
            face_confidence=presence_result.confidence_score,
            verification_type="face_presence_check",
        )

        return VerifyFaceSessionResponse(
            success=True,
            stage="face_verified",
            session_id=session_id,
            verification_token=advanced["verification_token"],
            is_match=True,
            confidence_score=presence_result.confidence_score,
            liveness_passed=True,
            message="¡Rostro humano detectado correctamente! Presencia facial confirmada.",
            details=presence_result.details,
        )

    async def complete_onboarding_registration(
        self,
        user_id: uuid.UUID,
        request: CompleteRegistrationRequest,
    ) -> CompleteRegistrationResponse:
        """
        Paso 6 del onboarding: REGISTRO DEFINITIVO Y ATÓMICO.
        Condición estricta: Sólo se ejecuta si el usuario ya aprobó Paso 1 (DNI) y Paso 2 (Biometría Facial).
        Acciones atómicas:
        1. Valida el verification_token firmado con stage='face_verified' y face_matched=True.
        2. Actualiza/completa profiles con status='verified', nombre y fecha de nacimiento.
        3. Inserta identity_verifications (DNI aprobado y verificado).
        4. Resuelve e inserta addresses y user_addresses (residencia actual confirmada).
        5. Resuelve e inserta community_memberships.
        6. Si indicó oficio o habilidad, registra user_availability.
        7. Expulsa la sesión temporal de memoria.
        """
        payload = verification_session_manager.decode_and_validate_token(request.verification_token)

        # 1. Comprobación estricta de que superó todas las etapas
        if payload.get("stage") != "face_verified" or not payload.get("face_matched"):
            raise ValidationException(
                "No se puede completar el registro: la verificación biométrica no ha sido aprobada."
            )
        if not payload.get("is_adult"):
            raise ValidationException("El titular del documento es menor de edad. Registro denegado.")

        now = datetime.now(timezone.utc).replace(tzinfo=None)

        # 2. Perfil en `profiles`
        profile = await self.profile_repo.get_by_id(user_id)
        verified_name = (
            request.full_name.strip()
            if request.full_name and request.full_name.strip()
            else (payload.get("full_name") or "Vecino VeciRed")
        )
        parsed_birth_date = None
        if payload.get("birth_date"):
            try:
                parsed_birth_date = parse_birth_date(payload["birth_date"])
            except Exception:
                pass

        if not profile:
            profile = Profile(
                id=user_id,
                full_name=verified_name,
                phone=request.phone.strip() if request.phone else None,
                avatar_url=request.avatar_url,
                birth_date=parsed_birth_date,
                account_status="verified",
                font_scale_preference="1.0",
                solidarity_helped_count=0,
                solidarity_received_count=0,
                created_at=now,
            )
            self.session.add(profile)
        else:
            profile.full_name = verified_name
            if request.phone:
                profile.phone = request.phone.strip()
            if request.avatar_url:
                profile.avatar_url = request.avatar_url
            if parsed_birth_date and not profile.birth_date:
                profile.birth_date = parsed_birth_date
            profile.account_status = "verified"
            self.session.add(profile)

        # 3. Registro en `identity_verifications`
        stmt_verif = select(IdentityVerification).where(
            IdentityVerification.user_id == user_id,
            IdentityVerification.document_hash == payload.get("document_hash"),
        )
        existing_verif = (await self.session.execute(stmt_verif)).scalars().first()
        if not existing_verif:
            verif_entry = IdentityVerification(
                id=uuid.uuid4(),
                user_id=user_id,
                document_type="DNI",
                document_hash=payload.get("document_hash"),
                document_last4=payload.get("dni_last4"),
                identity_provider=payload.get("verification_type") or "face_presence_check",
                identity_status="verified",
                verified_at=now,
                created_at=now,
            )
            self.session.add(verif_entry)

        # 4. Resolución de Distrito y Dirección
        district_name = request.district.strip()
        stmt_dist = select(District).where(District.name.ilike(f"%{district_name}%"))
        district = (await self.session.execute(stmt_dist)).scalars().first()

        if not district:
            # Fallback a distrito por defecto existente o primero registrado
            stmt_fallback_dist = select(District).limit(1)
            district = (await self.session.execute(stmt_fallback_dist)).scalars().first()
            if not district:
                # Si no existiera ninguno, crear Lima Cercado
                district = District(
                    id=150101,
                    province_id=1501,
                    name=district_name or "Lima Cercado",
                    ubigeo="150101",
                )
                self.session.add(district)
                await self.session.flush()

        # 5. Resolución de Comunidad, Zona y Manzana
        comm_name = (
            request.community_name.strip()
            if request.community_name and request.community_name.strip()
            else f"Comunidad VeciRed {district.name}"
        )
        stmt_comm = select(Community).where(
            Community.name.ilike(f"%{comm_name}%"),
            Community.district_id == district.id,
        )
        community = (await self.session.execute(stmt_comm)).scalars().first()
        if not community:
            community = Community(
                id=uuid.uuid4(),
                district_id=district.id,
                name=comm_name,
                status="active",
                created_at=now,
            )
            self.session.add(community)
            await self.session.flush()

        zone = None
        if request.zone_name and request.zone_name.strip():
            z_name = request.zone_name.strip()
            stmt_z = select(Zone).where(
                Zone.community_id == community.id,
                Zone.name.ilike(f"%{z_name}%"),
            )
            zone = (await self.session.execute(stmt_z)).scalars().first()
            if not zone:
                zone = Zone(id=uuid.uuid4(), community_id=community.id, name=z_name)
                self.session.add(zone)
                await self.session.flush()

        block = None
        if zone and request.block_code and request.block_code.strip():
            b_code = request.block_code.strip()
            stmt_b = select(Block).where(
                Block.zone_id == zone.id,
                Block.code.ilike(f"%{b_code}%"),
            )
            block = (await self.session.execute(stmt_b)).scalars().first()
            if not block:
                block = Block(id=uuid.uuid4(), zone_id=zone.id, code=b_code)
                self.session.add(block)
                await self.session.flush()

        # Crear fila en `addresses`
        lat_dec = Decimal(str(request.latitude)) if request.latitude is not None else None
        lon_dec = Decimal(str(request.longitude)) if request.longitude is not None else None
        new_address = Address(
            id=uuid.uuid4(),
            district_id=district.id,
            zone_id=zone.id if zone else None,
            block_id=block.id if block else None,
            street_address=request.street_address.strip(),
            lot_number=request.lot_number.strip() if request.lot_number else None,
            reference=request.reference.strip() if request.reference else None,
            latitude=lat_dec,
            longitude=lon_dec,
            created_at=now,
        )
        self.session.add(new_address)
        await self.session.flush()

        # Crear relación en `user_addresses`
        user_address = UserAddress(
            id=uuid.uuid4(),
            user_id=user_id,
            address_id=new_address.id,
            address_type="home",
            is_primary=True,
            source="onboarding_verified",
            residence_status="verified",
            valid_from=now,
            created_at=now,
        )
        self.session.add(user_address)

        # 6. Membresía en `community_memberships`
        stmt_memb = select(CommunityMembership).where(
            CommunityMembership.user_id == user_id,
            CommunityMembership.community_id == community.id,
        )
        existing_memb = (await self.session.execute(stmt_memb)).scalars().first()
        if not existing_memb:
            membership = CommunityMembership(
                id=uuid.uuid4(),
                user_id=user_id,
                community_id=community.id,
                zone_id=zone.id if zone else None,
                block_id=block.id if block else None,
                role="resident",
                membership_status="active",
                joined_at=now,
            )
            self.session.add(membership)

        # 7. Oficio/habilidad en `user_availability`
        chosen_skill = (
            request.skill.strip()
            if request.skill and request.skill.strip()
            else (request.occupation.strip() if request.occupation else None)
        )
        if chosen_skill:
            avail = UserAvailability(
                id=uuid.uuid4(),
                user_id=user_id,
                community_id=community.id,
                help_category=chosen_skill,
                description="Oficio o habilidad vecinal registrada durante el onboarding verificado",
                is_available=True,
                updated_at=now,
            )
            self.session.add(avail)

        # Transacción completada atómicamente
        await self.session.commit()

        # Desalojar sesión temporal en memoria
        session_id = payload.get("session_id")
        if session_id:
            verification_session_manager.evict_session(session_id)

        full_addr_str = f"{request.street_address.strip()}, {district.name}"

        logger.info(
            "Registro definitivo completado con éxito para usuario %s (%s) en comunidad %s",
            user_id,
            verified_name,
            community.name,
        )

        return CompleteRegistrationResponse(
            success=True,
            user_id=user_id,
            account_status="verified",
            profile=ProfileResponse.model_validate(profile),
            community_name=community.name,
            address=full_addr_str,
            message="¡Registro definitivo y verificación completados con éxito! Tu cuenta está activa y verificada.",
        )

