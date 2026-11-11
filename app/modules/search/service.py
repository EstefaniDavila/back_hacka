"""Servicio de lógica de negocio y ranking para el motor de búsqueda inteligente."""
import difflib
import json
import math
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.logging import logger

from app.modules.search.repository import (
    SearchRepository,
    expand_query_terms,
    haversine_distance_km,
    haversine_distance_meters,
    strip_accents,
)
from app.modules.search.schemas import (
    EmergencySearchResult,
    GlobalSearchResponse,
    PaginatedEmergenciesSearch,
    PaginatedProductsSearch,
    PaginatedServicesSearch,
    PaginatedSolidaritySearch,
    ProductSearchResult,
    SearchLocationMeta,
    SearchPaginationMeta,
    SearchSort,
    ServiceSearchResult,
    SolidaritySearchResult,
    UnifiedSearchResultItem,
)


def classify_proximity_tier(dist_meters: Optional[float]) -> Tuple[Optional[int], str]:
    """
    Clasifica la distancia en los 5 niveles progresivos barriales:
    Tier 1: <= 150m        -> 'En tu misma manzana (<150m)'
    Tier 2: > 150m y <= 500m -> 'Manzanas colindantes (<500m)'
    Tier 3: > 500m y <= 1500m-> 'Resto de la urbanización (<1.5 km)'
    Tier 4: > 1500m y <= 5000m-> 'Zonas cercanas del distrito (<5 km)'
    Tier 5: > 5000m y <= 10000m-> 'Otras zonas cercanas (<10 km)'
    Sin GPS: None          -> 'Sin coordenadas GPS'
    """
    if dist_meters is None:
        return None, "Sin coordenadas GPS"
    if dist_meters <= 150.0:
        return 1, "En tu misma manzana (<150m)"
    elif dist_meters <= 500.0:
        return 2, "Manzanas colindantes (<500m)"
    elif dist_meters <= 1500.0:
        return 3, "Resto de la urbanización (<1.5 km)"
    elif dist_meters <= 5000.0:
        return 4, "Zonas cercanas del distrito (<5 km)"
    elif dist_meters <= 10000.0:
        return 5, "Otras zonas cercanas (<10 km)"
    else:
        return None, "Fuera de rango (>10 km)"


class SearchService:
    """
    Servicio de búsqueda inteligente geolocalizada con ranking multidimensional ponderado:
    - Coincidencia textual (40%)
    - Proximidad barrial (25%)
    - Reputación bayesiana (25%)
    - Experiencia comprobada (10%)
    """

    def __init__(self, session: AsyncSession):
        self.session = session
        self.repository = SearchRepository(session)

    # ------------------------------------------------------------------
    # MÉTODOS AUXILIARES DE RANKING Y PUNTUACIÓN
    # ------------------------------------------------------------------
    def _build_location_meta(
        self,
        latitude: Optional[float],
        longitude: Optional[float],
        radius_km: Optional[float],
        items: List[Any],
    ) -> SearchLocationMeta:
        """Construye los metadatos de ubicación, tier alcanzado y expansión progresiva."""
        if latitude is None or longitude is None:
            return SearchLocationMeta(
                latitude=latitude,
                longitude=longitude,
                radius_km=radius_km,
                reference=None,
                tier_reached=None,
                expansion_label="Ubicación no especificada. Mostrando catálogo comunitario.",
                tier_counts={},
            )

        tier_counts = {
            "tier_1": 0,
            "tier_2": 0,
            "tier_3": 0,
            "tier_4": 0,
            "tier_5": 0,
            "sin_coordenadas": 0,
        }

        tiers_found = []
        for it in items:
            tier = getattr(it, "proximity_tier", None)
            if tier is not None and 1 <= tier <= 5:
                tier_counts[f"tier_{tier}"] += 1
                tiers_found.append(tier)
            else:
                tier_counts["sin_coordenadas"] += 1

        tier_reached = min(tiers_found) if tiers_found else None

        if len(items) == 0:
            expansion_label = "No se encontraron resultados dentro del radio máximo de 10 km"
        elif tier_reached == 1:
            expansion_label = "Resultados en tu misma manzana (<150m)"
        elif tier_reached == 2:
            expansion_label = "Búsqueda ampliada a manzanas colindantes (<500m)"
        elif tier_reached == 3:
            expansion_label = "Búsqueda ampliada al resto de la urbanización (<1.5 km)"
        elif tier_reached == 4:
            expansion_label = "Búsqueda ampliada a zonas cercanas del distrito (<5 km)"
        elif tier_reached == 5:
            expansion_label = "Búsqueda ampliada a otras zonas cercanas (<10 km)"
        else:
            expansion_label = "Resultados comunitarios disponibles (sin coordenadas GPS registradas)"

        return SearchLocationMeta(
            latitude=latitude,
            longitude=longitude,
            radius_km=radius_km or 10.0,
            tier_reached=tier_reached,
            expansion_label=expansion_label,
            tier_counts=tier_counts,
        )

    def _calculate_text_match_score(
        self,
        query: Optional[str],
        title: str,
        description: Optional[str] = None,
        category: Optional[str] = None,
        extra: Optional[str] = None,
    ) -> float:
        """Calcula la coincidencia semántica y difusa entre 0.0 y 1.0 sin llamadas externas."""
        if not query or not query.strip():
            return 1.0

        q_clean = strip_accents(query.strip())
        t_clean = strip_accents(title or "")
        c_clean = strip_accents(category or "")
        d_clean = strip_accents(description or "")
        e_clean = strip_accents(extra or "")

        # 1. Coincidencia exacta de frase en título
        if q_clean == t_clean:
            return 1.0
        if q_clean in t_clean:
            return 0.95

        # 2. Coincidencia exacta de frase en categoría
        if q_clean == c_clean or q_clean in c_clean:
            return 0.90

        # 3. Tokenización y búsqueda expandida con sinónimos
        q_tokens = [t for t in q_clean.split() if len(t) > 1]
        expanded_tokens = expand_query_terms(query)

        token_hits = 0
        total_tokens = max(1, len(q_tokens))

        for t in q_tokens:
            if t in t_clean:
                token_hits += 1.0
            elif t in c_clean:
                token_hits += 0.85
            elif t in d_clean:
                token_hits += 0.65
            elif t in e_clean:
                token_hits += 0.50

        token_score = min(1.0, token_hits / total_tokens)

        # 4. Chequeo de sinónimos si los tokens directos no alcanzaron el 100%
        synonym_bonus = 0.0
        for syn in expanded_tokens:
            if syn not in q_tokens:
                if syn in t_clean:
                    synonym_bonus = max(synonym_bonus, 0.80)
                elif syn in c_clean:
                    synonym_bonus = max(synonym_bonus, 0.75)
                elif syn in d_clean:
                    synonym_bonus = max(synonym_bonus, 0.60)

        # 5. Similitud trigrama / difusa con el título para mitigar errores ortográficos
        fuzzy_sim = difflib.SequenceMatcher(None, q_clean, t_clean).ratio()
        fuzzy_score = (fuzzy_sim * 0.85) if fuzzy_sim >= 0.45 else 0.0

        best_score = max(token_score, synonym_bonus, fuzzy_score)
        return round(min(1.0, max(0.0, best_score)), 3)

    def _calculate_distance_and_score(
        self,
        user_lat: Optional[float],
        user_lon: Optional[float],
        item_lat: Optional[float],
        item_lon: Optional[float],
        radius_km: Optional[float] = None,
    ) -> Tuple[Optional[float], Optional[float], float, bool, Optional[int], str]:
        """
        Retorna (distance_km, distance_meters, distance_score, within_radius, proximity_tier, proximity_label).
        - Mide distancia real en metros usando Haversine.
        - Límite máximo de proximidad progresiva: 10 km (10,000 m), o radius_km si se especifica.
        - Si el item no tiene coordenadas, retorna within_radius=True con tier=None y label="Sin coordenadas GPS".
        - Si supera el límite de 10 km, within_radius=False.
        """
        if user_lat is None or user_lon is None:
            if item_lat is not None and item_lon is not None:
                return None, None, 0.50, True, None, "Ubicación del usuario no especificada"
            return None, None, 0.50, True, None, "Sin coordenadas GPS"

        if item_lat is None or item_lon is None:
            return None, None, 0.0, True, None, "Sin coordenadas GPS"

        dist_meters = haversine_distance_meters(user_lat, user_lon, item_lat, item_lon)
        dist_km = round(dist_meters / 1000.0, 3)

        max_allowed_meters = (radius_km * 1000.0) if radius_km is not None else 10000.0

        if dist_meters > max_allowed_meters:
            tier, label = classify_proximity_tier(dist_meters)
            return dist_km, dist_meters, 0.0, False, tier, label

        tier, label = classify_proximity_tier(dist_meters)
        # Normalización continua de proximidad: a 0 m -> 1.0; a max_allowed_meters -> 0.0
        dist_score = max(0.0, min(1.0, 1.0 - (dist_meters / max_allowed_meters)))

        return dist_km, dist_meters, round(dist_score, 4), True, tier, label

    def _calculate_bayesian_reputation(
        self,
        reviews_count: int,
        rating_avg: float,
        prior_mean: float = 4.2,
        min_reviews_threshold: int = 3,
    ) -> Tuple[float, float, bool]:
        """
        Calcula el promedio ponderado bayesiano de reputación y detecta usuarios nuevos.
        Retorna (bayesian_rating_1_to_5, reputation_score_0_to_1, is_new).
        No penaliza a nuevos vecinos (les asigna línea base justa de 4.2 estrellas / 0.84).
        """
        if reviews_count == 0:
            return prior_mean, 0.84, True

        v = float(reviews_count)
        r = float(rating_avg)
        m = float(min_reviews_threshold)
        c = float(prior_mean)

        bayesian_rating = (v * r + m * c) / (v + m)
        reputation_score = bayesian_rating / 5.0
        return round(bayesian_rating, 2), round(min(1.0, max(0.1, reputation_score)), 3), False

    def _calculate_experience_score(self, completed_interactions: int, is_new: bool = False) -> float:
        """Puntúa la experiencia comprobada sin penalizar a nuevos vecinos."""
        if is_new or completed_interactions <= 0:
            return 0.70  # Línea base positiva para nuevos vecinos
        # 1 trabajo = 0.73 | 5 trabajos = 0.85 | 10+ trabajos = 1.0
        score = 0.70 + 0.03 * min(10, completed_interactions)
        return round(min(1.0, score), 3)

    # ------------------------------------------------------------------
    # 1. BÚSQUEDA DE SERVICIOS
    # ------------------------------------------------------------------
    async def search_services(
        self,
        query: Optional[str] = None,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
        radius_km: Optional[float] = None,
        category_id: Optional[uuid.UUID] = None,
        community_id: Optional[uuid.UUID] = None,
        sort: SearchSort = SearchSort.RECOMMENDED,
        page: int = 1,
        page_size: int = 20,
        user_id: Optional[uuid.UUID] = None,
    ) -> PaginatedServicesSearch:
        """Búsqueda especializada en oficios y servicios comunitarios."""
        raw_items = await self.repository.search_services_raw(
            query=query,
            category_id=category_id,
            community_id=community_id,
        )

        items_within_range: List[ServiceSearchResult] = []
        items_without_coords: List[ServiceSearchResult] = []

        for item in raw_items:
            dist_km, dist_meters, dist_score, within_radius, tier, label = self._calculate_distance_and_score(
                latitude, longitude, item["latitude"], item["longitude"], radius_km
            )
            if not within_radius:
                continue

            match_score = self._calculate_text_match_score(
                query,
                item["title"],
                item["description"],
                item["category_name"],
                item["provider_name"],
            )

            # Si se buscó un término específico y la coincidencia es nula, descartar
            if query and query.strip() and match_score < 0.15:
                continue

            bayes_rating, rep_score, is_new = self._calculate_bayesian_reputation(
                item["reviews_count"], item["rating_avg"]
            )

            completed = item["reviews_count"] + item["provider_helped_count"]
            exp_score = self._calculate_experience_score(completed, is_new=is_new)

            # Ponderación requerida:
            # 55% Proximidad
            # 25% Relevancia
            # 15% Reputación
            # 5% Experiencia
            final_score = (
                0.55 * dist_score
                + 0.25 * match_score
                + 0.15 * rep_score
                + 0.05 * exp_score
            )

            if item["ai_score"] is not None:
                final_score = min(1.0, final_score + 0.03 * item["ai_score"])

            final_score = min(1.0, max(0.0, final_score))
            score_val = round(final_score, 4)
            is_verified = item["provider_status"] in ("verified", "active")

            svc_result = ServiceSearchResult(
                id=item["id"],
                title=item["title"],
                description=item["description"],
                category_id=item["category_id"],
                category_name=item["category_name"],
                category_icon=item["category_icon"],
                price_from=item["price_from"],
                price_unit=item["price_unit"],
                availability=item["availability"],
                provider_id=item["provider_id"],
                provider_name=item["provider_name"],
                provider_avatar=item["provider_avatar"],
                provider_phone=item["provider_phone"],
                is_verified=is_verified,
                is_new=is_new,
                rating_avg=item["rating_avg"],
                reviews_count=item["reviews_count"],
                bayesian_rating=bayes_rating,
                completed_interactions=completed,
                distance_km=dist_km,
                distance_meters=dist_meters,
                proximity_tier=tier,
                proximity_label=label,
                community_id=item["community_id"],
                community_name=item["community_name"],
                district_name=item["district_name"],
                score=score_val,
                ranking_score=score_val,
                score_breakdown={
                    "match_score": match_score,
                    "distance_score": dist_score,
                    "reputation_score": rep_score,
                    "experience_score": exp_score,
                    "distance_meters": dist_meters,
                    "final_score": score_val,
                    "algorithm_notes": f"55% prox ({dist_meters}m), 25% rel, 15% rep, 5% exp",
                },
                created_at=item["created_at"],
            )

            if dist_meters is not None:
                items_within_range.append(svc_result)
            else:
                items_without_coords.append(svc_result)

        # Ordenamiento progresivo por proximidad
        if latitude is not None and longitude is not None:
            if len(items_within_range) == 0:
                ranked = []
            else:
                self._sort_items(items_within_range, sort)
                items_without_coords.sort(key=lambda x: -getattr(x, "score", 0.0))
                ranked = items_within_range + items_without_coords
        else:
            ranked = items_within_range + items_without_coords
            self._sort_items(ranked, sort)

        # Persistir recomendaciones Top en ai_recommendations si el usuario está autenticado y es orden recomendado
        if user_id and sort == SearchSort.RECOMMENDED:
            await self._persist_recommendations(user_id, "service", ranked)

        # Paginación
        total = len(ranked)
        skip = (page - 1) * page_size
        paginated_items = ranked[skip : skip + page_size]
        total_pages = max(1, math.ceil(total / page_size))

        return PaginatedServicesSearch(
            items=paginated_items,
            meta=SearchPaginationMeta(
                total=total,
                page=page,
                limit=page_size,
                total_pages=total_pages,
            ),
            location_applied=self._build_location_meta(latitude, longitude, radius_km, ranked),
            sort_applied=sort.value,
        )

    # ------------------------------------------------------------------
    # 2. BÚSQUEDA DE PRODUCTOS
    # ------------------------------------------------------------------
    async def search_products(
        self,
        query: Optional[str] = None,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
        radius_km: Optional[float] = None,
        category_id: Optional[uuid.UUID] = None,
        community_id: Optional[uuid.UUID] = None,
        sort: SearchSort = SearchSort.RECOMMENDED,
        page: int = 1,
        page_size: int = 20,
        user_id: Optional[uuid.UUID] = None,
    ) -> PaginatedProductsSearch:
        """Búsqueda especializada en productos y comercios barriales."""
        raw_items = await self.repository.search_products_raw(
            query=query,
            category_id=category_id,
            community_id=community_id,
        )

        items_within_range: List[ProductSearchResult] = []
        items_without_coords: List[ProductSearchResult] = []

        for item in raw_items:
            dist_km, dist_meters, dist_score, within_radius, tier, label = self._calculate_distance_and_score(
                latitude, longitude, item["latitude"], item["longitude"], radius_km
            )
            if not within_radius:
                continue

            match_score = self._calculate_text_match_score(
                query,
                item["name"],
                item["description"],
                item["category_name"],
                item["business_name"],
            )

            if query and query.strip() and match_score < 0.15:
                continue

            bayes_rating, rep_score, is_new = self._calculate_bayesian_reputation(
                item["reviews_count"], item["rating_avg"]
            )

            exp_score = self._calculate_experience_score(item["reviews_count"], is_new=is_new)
            # Ponderación requerida: 55% Proximidad, 25% Relevancia, 15% Reputación, 5% Experiencia
            final_score = (
                0.55 * dist_score
                + 0.25 * match_score
                + 0.15 * rep_score
                + 0.05 * exp_score
            )

            if item["ai_score"] is not None:
                final_score = min(1.0, final_score + 0.03 * item["ai_score"])

            final_score = min(1.0, max(0.0, final_score))
            score_val = round(final_score, 4)
            is_verified = item["owner_status"] in ("verified", "active")

            prod_result = ProductSearchResult(
                id=item["id"],
                name=item["name"],
                description=item["description"],
                price=item["price"],
                stock=item["stock"],
                image_url=item["image_url"],
                business_id=item["business_id"],
                business_name=item["business_name"],
                category_id=item["category_id"],
                category_name=item["category_name"],
                owner_id=item["owner_id"],
                owner_name=item["owner_name"],
                is_verified=is_verified,
                is_new=is_new,
                rating_avg=item["rating_avg"],
                reviews_count=item["reviews_count"],
                bayesian_rating=bayes_rating,
                distance_km=dist_km,
                distance_meters=dist_meters,
                proximity_tier=tier,
                proximity_label=label,
                community_name=item["community_name"],
                district_name=item["district_name"],
                score=score_val,
                ranking_score=score_val,
                score_breakdown={
                    "match_score": match_score,
                    "distance_score": dist_score,
                    "reputation_score": rep_score,
                    "experience_score": exp_score,
                    "distance_meters": dist_meters,
                    "final_score": score_val,
                    "algorithm_notes": f"55% prox ({dist_meters}m), 25% rel, 15% rep, 5% exp",
                },
                created_at=item["created_at"],
            )

            if dist_meters is not None:
                items_within_range.append(prod_result)
            else:
                items_without_coords.append(prod_result)

        # Ordenamiento progresivo por proximidad
        if latitude is not None and longitude is not None:
            if len(items_within_range) == 0:
                ranked = []
            else:
                self._sort_items(items_within_range, sort)
                items_without_coords.sort(key=lambda x: -getattr(x, "score", 0.0))
                ranked = items_within_range + items_without_coords
        else:
            ranked = items_within_range + items_without_coords
            self._sort_items(ranked, sort)

        if user_id and sort == SearchSort.RECOMMENDED:
            await self._persist_recommendations(user_id, "product", ranked)

        total = len(ranked)
        skip = (page - 1) * page_size
        paginated_items = ranked[skip : skip + page_size]
        total_pages = max(1, math.ceil(total / page_size))

        return PaginatedProductsSearch(
            items=paginated_items,
            meta=SearchPaginationMeta(
                total=total,
                page=page,
                limit=page_size,
                total_pages=total_pages,
            ),
            location_applied=self._build_location_meta(latitude, longitude, radius_km, ranked),
            sort_applied=sort.value,
        )

    # ------------------------------------------------------------------
    # 3. BÚSQUEDA DE SOLIDARIDAD
    # ------------------------------------------------------------------
    async def search_solidarity(
        self,
        query: Optional[str] = None,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
        radius_km: Optional[float] = None,
        post_type: Optional[str] = None,
        community_id: Optional[uuid.UUID] = None,
        sort: SearchSort = SearchSort.RECOMMENDED,
        page: int = 1,
        page_size: int = 20,
        user_id: Optional[uuid.UUID] = None,
    ) -> PaginatedSolidaritySearch:
        """Búsqueda en el muro solidario. No usa estrellas para ordenar necesidades urgentes."""
        raw_items = await self.repository.search_solidarity_raw(
            query=query,
            post_type=post_type,
            community_id=community_id,
        )

        items_within_range: List[SolidaritySearchResult] = []
        items_without_coords: List[SolidaritySearchResult] = []

        for item in raw_items:
            dist_km, dist_meters, dist_score, within_radius, tier, label = self._calculate_distance_and_score(
                latitude, longitude, item["latitude"], item["longitude"], radius_km
            )
            if not within_radius:
                continue

            match_score = self._calculate_text_match_score(
                query,
                item["title"],
                item["description"],
                item["category"],
            )

            if query and query.strip() and match_score < 0.15:
                continue

            # Prioridad de urgencia: pedidos de auxilio tienen mayor ponderación que ofertas
            is_urgent = item["post_type"] in ("request", "necesidad", "urgencia")
            type_weight = 1.0 if is_urgent else 0.70
            status_weight = 1.0 if item["status"] in ("open", "active") else 0.40
            urgency_score = round(type_weight * status_weight, 3)

            # Fórmula Solidaridad: 55% Proximidad, 25% Coincidencia, 20% Urgencia
            final_score = (
                0.55 * dist_score
                + 0.25 * match_score
                + 0.20 * urgency_score
            )
            final_score = min(1.0, max(0.0, final_score))
            score_val = round(final_score, 4)

            is_verified = item["author_status"] in ("verified", "active")

            sol_result = SolidaritySearchResult(
                id=item["id"],
                title=item["title"],
                description=item["description"],
                category=item["category"],
                post_type=item["post_type"],
                status=item["status"],
                author_id=item["author_id"],
                author_name=item["author_name"],
                author_avatar=item["author_avatar"],
                is_verified=is_verified,
                is_urgent=is_urgent,
                distance_km=dist_km,
                distance_meters=dist_meters,
                proximity_tier=tier,
                proximity_label=label,
                community_name=item["community_name"],
                district_name=item["district_name"],
                score=score_val,
                ranking_score=score_val,
                score_breakdown={
                    "match_score": match_score,
                    "distance_score": dist_score,
                    "urgency_score": urgency_score,
                    "distance_meters": dist_meters,
                    "final_score": score_val,
                    "algorithm_notes": f"55% prox ({dist_meters}m), 25% rel, 20% urgencia",
                },
                created_at=item["created_at"],
            )

            if dist_meters is not None:
                items_within_range.append(sol_result)
            else:
                items_without_coords.append(sol_result)

        # Ordenamiento progresivo por proximidad
        if latitude is not None and longitude is not None:
            if len(items_within_range) == 0:
                ranked = []
            else:
                self._sort_items(items_within_range, sort)
                items_without_coords.sort(key=lambda x: -getattr(x, "score", 0.0))
                ranked = items_within_range + items_without_coords
        else:
            ranked = items_within_range + items_without_coords
            self._sort_items(ranked, sort)

        if user_id and sort == SearchSort.RECOMMENDED:
            await self._persist_recommendations(user_id, "solidarity", ranked)

        total = len(ranked)
        skip = (page - 1) * page_size
        paginated_items = ranked[skip : skip + page_size]
        total_pages = max(1, math.ceil(total / page_size))

        return PaginatedSolidaritySearch(
            items=paginated_items,
            meta=SearchPaginationMeta(
                total=total,
                page=page,
                limit=page_size,
                total_pages=total_pages,
            ),
            location_applied=self._build_location_meta(latitude, longitude, radius_km, ranked),
            sort_applied=sort.value,
        )

    # ------------------------------------------------------------------
    # 4. BÚSQUEDA DE EMERGENCIAS
    # ------------------------------------------------------------------
    async def search_emergencies(
        self,
        query: Optional[str] = None,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
        radius_km: Optional[float] = None,
        severity: Optional[str] = None,
        community_id: Optional[uuid.UUID] = None,
        sort: SearchSort = SearchSort.RECOMMENDED,
        page: int = 1,
        page_size: int = 20,
        user_id: Optional[uuid.UUID] = None,
    ) -> PaginatedEmergenciesSearch:
        """Búsqueda en emergencias. Prioriza gravedad, cercanía y estado. NUNCA reputación."""
        raw_items = await self.repository.search_emergencies_raw(
            query=query,
            severity=severity,
            community_id=community_id,
        )

        items_within_range: List[EmergencySearchResult] = []
        items_without_coords: List[EmergencySearchResult] = []

        SEVERITY_WEIGHTS = {
            "critical": 1.0,
            "high": 0.85,
            "medium": 0.55,
            "low": 0.30,
        }

        STATUS_WEIGHTS = {
            "active": 1.0,
            "reported": 1.0,
            "in_progress": 0.65,
            "resolved": 0.15,
            "closed": 0.10,
        }

        for item in raw_items:
            dist_km, dist_meters, dist_score, within_radius, tier, label = self._calculate_distance_and_score(
                latitude, longitude, item["latitude"], item["longitude"], radius_km
            )
            if not within_radius:
                continue

            match_score = self._calculate_text_match_score(
                query,
                item["title"],
                item["description"],
                item["emergency_type"],
            )

            if query and query.strip() and match_score < 0.15:
                continue

            sev_val = str(item["severity"]).lower()
            sev_score = SEVERITY_WEIGHTS.get(sev_val, 0.40)

            stat_val = str(item["status"]).lower()
            stat_score = STATUS_WEIGHTS.get(stat_val, 0.40)

            severity_composite = round(sev_score * 0.70 + stat_score * 0.30, 3)

            # Fórmula Emergencias: 50% Gravedad/Estado, 35% Cercanía, 15% Coincidencia
            final_score = (
                0.50 * severity_composite
                + 0.35 * dist_score
                + 0.15 * match_score
            )
            final_score = min(1.0, max(0.0, final_score))
            score_val = round(final_score, 4)

            emg_result = EmergencySearchResult(
                id=item["id"],
                title=item["title"],
                description=item["description"],
                emergency_type=item["emergency_type"],
                severity=item["severity"],
                status=item["status"],
                reported_by=item["reported_by"],
                reporter_name=item["reporter_name"],
                occurred_at=item["occurred_at"],
                distance_km=dist_km,
                distance_meters=dist_meters,
                proximity_tier=tier,
                proximity_label=label,
                community_name=item["community_name"],
                district_name=item["district_name"],
                score=score_val,
                ranking_score=score_val,
                score_breakdown={
                    "severity_score": severity_composite,
                    "distance_score": dist_score,
                    "match_score": match_score,
                    "distance_meters": dist_meters,
                    "final_score": score_val,
                    "algorithm_notes": f"50% gravedad ({item['severity']}), 35% prox ({dist_meters}m), 15% rel",
                },
                created_at=item["created_at"],
            )

            if dist_meters is not None:
                items_within_range.append(emg_result)
            else:
                items_without_coords.append(emg_result)

        # Ordenamiento especializado de seguridad para emergencias
        if latitude is not None and longitude is not None:
            if len(items_within_range) == 0:
                ranked = []
            else:
                ranked = items_within_range + items_without_coords
                self._sort_emergencies(ranked, sort)
        else:
            ranked = items_within_range + items_without_coords
            self._sort_emergencies(ranked, sort)

        if user_id and sort == SearchSort.RECOMMENDED:
            await self._persist_recommendations(user_id, "emergency", ranked)

        total = len(ranked)
        skip = (page - 1) * page_size
        paginated_items = ranked[skip : skip + page_size]
        total_pages = max(1, math.ceil(total / page_size))

        return PaginatedEmergenciesSearch(
            items=paginated_items,
            meta=SearchPaginationMeta(
                total=total,
                page=page,
                limit=page_size,
                total_pages=total_pages,
            ),
            location_applied=self._build_location_meta(latitude, longitude, radius_km, ranked),
            sort_applied=sort.value,
        )

    # ------------------------------------------------------------------
    # 5. BÚSQUEDA GLOBAL / CONSOLIDADA (GET /api/v1/search)
    # ------------------------------------------------------------------
    async def search_all(
        self,
        query: Optional[str] = None,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
        radius_km: Optional[float] = None,
        community_id: Optional[uuid.UUID] = None,
        sort: SearchSort = SearchSort.RECOMMENDED,
        page: int = 1,
        page_size: int = 20,
        user_id: Optional[uuid.UUID] = None,
        include_emergencies: bool = True,
        modules: Optional[str] = None,
    ) -> GlobalSearchResponse:
        """Búsqueda general transversal que combina e intercala servicios, productos, solidaridad y emergencias."""
        parsed_modules = set([m.strip().lower() for m in modules.split(",") if m.strip()]) if modules else None

        fetch_services = parsed_modules is None or "services" in parsed_modules
        fetch_products = parsed_modules is None or "products" in parsed_modules
        fetch_solidarity = parsed_modules is None or "solidarity" in parsed_modules
        fetch_emergencies = include_emergencies and (parsed_modules is None or "emergencies" in parsed_modules)

        empty_pagination = SearchPaginationMeta(total=0, page=1, limit=30, total_pages=1)

        services_res = await self.search_services(
            query=query,
            latitude=latitude,
            longitude=longitude,
            radius_km=radius_km,
            community_id=community_id,
            sort=sort,
            page=1,
            page_size=30,
            user_id=user_id,
        ) if fetch_services else PaginatedServicesSearch(items=[], meta=empty_pagination)

        products_res = await self.search_products(
            query=query,
            latitude=latitude,
            longitude=longitude,
            radius_km=radius_km,
            community_id=community_id,
            sort=sort,
            page=1,
            page_size=30,
            user_id=user_id,
        ) if fetch_products else PaginatedProductsSearch(items=[], meta=empty_pagination)

        solidarity_res = await self.search_solidarity(
            query=query,
            latitude=latitude,
            longitude=longitude,
            radius_km=radius_km,
            community_id=community_id,
            sort=sort,
            page=1,
            page_size=30,
            user_id=user_id,
        ) if fetch_solidarity else PaginatedSolidaritySearch(items=[], meta=empty_pagination)

        emergencies_res = await self.search_emergencies(
            query=query,
            latitude=latitude,
            longitude=longitude,
            radius_km=radius_km,
            community_id=community_id,
            sort=sort,
            page=1,
            page_size=30,
            user_id=user_id,
        ) if fetch_emergencies else PaginatedEmergenciesSearch(items=[], meta=empty_pagination)

        unified_list: List[UnifiedSearchResultItem] = []

        # 1. Adaptar Servicios
        for s in services_res.items:
            price_str = f"S/ {s.price_from}" if s.price_from else "A cotizar"
            if s.price_unit:
                price_str += f" /{s.price_unit}"

            unified_list.append(
                UnifiedSearchResultItem(
                    id=s.id,
                    module="services",
                    title=s.title,
                    subtitle=s.provider_name,
                    description=s.description,
                    category=s.category_name,
                    icon=s.category_icon or "🛠️",
                    badge="Verificado" if s.is_verified else ("Nuevo" if s.is_new else None),
                    price_label=price_str,
                    distance_km=s.distance_km,
                    distance_meters=s.distance_meters,
                    proximity_tier=s.proximity_tier,
                    proximity_label=s.proximity_label,
                    location_label=s.district_name or s.community_name,
                    rating=s.rating_avg if s.reviews_count > 0 else None,
                    reviews_count=s.reviews_count,
                    is_new=s.is_new,
                    is_verified=s.is_verified,
                    score=s.score,
                    ranking_score=s.ranking_score,
                    score_breakdown=s.score_breakdown,
                    detail_path=f"/services/{s.id}",
                )
            )

        # 2. Adaptar Productos
        for p in products_res.items:
            unified_list.append(
                UnifiedSearchResultItem(
                    id=p.id,
                    module="products",
                    title=p.name,
                    subtitle=p.business_name,
                    description=p.description,
                    category=p.category_name,
                    icon="🛒",
                    badge="En Stock" if (p.stock is None or p.stock > 0) else "Agotado",
                    price_label=f"S/ {p.price}",
                    distance_km=p.distance_km,
                    distance_meters=p.distance_meters,
                    proximity_tier=p.proximity_tier,
                    proximity_label=p.proximity_label,
                    location_label=p.district_name or p.community_name,
                    rating=p.rating_avg if p.reviews_count > 0 else None,
                    reviews_count=p.reviews_count,
                    is_new=p.is_new,
                    is_verified=p.is_verified,
                    score=p.score,
                    ranking_score=p.ranking_score,
                    score_breakdown=p.score_breakdown,
                    detail_path=f"/products/{p.id}",
                )
            )

        # 3. Adaptar Solidaridad
        for sol in solidarity_res.items:
            type_label = "Necesidad de Ayuda" if sol.is_urgent else "Ofrecimiento Solidario"
            unified_list.append(
                UnifiedSearchResultItem(
                    id=sol.id,
                    module="solidarity",
                    title=sol.title,
                    subtitle=f"{type_label} • {sol.author_name}",
                    description=sol.description,
                    category=sol.category or "Solidaridad",
                    icon="🤝",
                    badge="URGENTE" if sol.is_urgent else "Muro Comunal",
                    price_label="Gratuito",
                    distance_km=sol.distance_km,
                    distance_meters=sol.distance_meters,
                    proximity_tier=sol.proximity_tier,
                    proximity_label=sol.proximity_label,
                    location_label=sol.district_name or sol.community_name,
                    rating=None,
                    reviews_count=None,
                    is_new=False,
                    is_verified=sol.is_verified,
                    score=sol.score,
                    ranking_score=sol.ranking_score,
                    score_breakdown=sol.score_breakdown,
                    detail_path=f"/solidarity/posts/{sol.id}",
                )
            )

        # 4. Adaptar Emergencias
        for emg in emergencies_res.items:
            unified_list.append(
                UnifiedSearchResultItem(
                    id=emg.id,
                    module="emergencies",
                    title=f"🚨 {emg.title}",
                    subtitle=f"Tipo: {emg.emergency_type} • Estado: {emg.status}",
                    description=emg.description,
                    category=emg.emergency_type,
                    icon="🚨",
                    badge=f"Severidad: {emg.severity.upper()}",
                    price_label="Emergencia Activa",
                    distance_km=emg.distance_km,
                    distance_meters=emg.distance_meters,
                    proximity_tier=emg.proximity_tier,
                    proximity_label=emg.proximity_label,
                    location_label=emg.district_name or emg.community_name,
                    rating=None,
                    reviews_count=None,
                    is_new=False,
                    is_verified=True,
                    score=emg.score,
                    ranking_score=emg.ranking_score,
                    score_breakdown=emg.score_breakdown,
                    detail_path=f"/emergencies/{emg.id}",
                )
            )

        # Ordenar lista consolidada
        if sort == SearchSort.DISTANCE:
            unified_list.sort(
                key=lambda x: (
                    x.distance_meters is None,
                    x.distance_meters if x.distance_meters is not None else float("inf"),
                    -x.score,
                )
            )
        else:
            # RECOMMENDED: Emergencias críticas activas conservan máxima prioridad;
            # luego proximidad por distancia real ascendente, y desempate por score
            def unified_sort_key(item: UnifiedSearchResultItem):
                is_crit_emergency = (
                    item.module == "emergencies"
                    and ("CRITICAL" in (item.badge or "").upper() or "CRITICA" in (item.badge or "").upper())
                )
                return (
                    not is_crit_emergency,  # 0 para emergencias críticas activas, 1 para el resto
                    item.distance_meters is None,  # Con GPS primero
                    item.distance_meters if item.distance_meters is not None else float("inf"),  # Distancia ascendente
                    -round(item.score, 2),  # Criterio secundario
                )
            unified_list.sort(key=unified_sort_key)

        total = len(unified_list)
        skip = (page - 1) * page_size
        paginated_items = unified_list[skip : skip + page_size]
        total_pages = max(1, math.ceil(total / page_size))

        return GlobalSearchResponse(
            query=query,
            location_applied=self._build_location_meta(latitude, longitude, radius_km, unified_list),
            sort_applied=sort.value,
            total_results=total,
            page=page,
            limit=page_size,
            total_pages=total_pages,
            items=paginated_items,
            sections_summary={
                "services": services_res.meta.total,
                "products": products_res.meta.total,
                "solidarity": solidarity_res.meta.total,
                "emergencies": emergencies_res.meta.total,
            },
            top_sections={
                "services": [s.model_dump() for s in services_res.items[:3]],
                "products": [p.model_dump() for p in products_res.items[:3]],
                "solidarity": [sol.model_dump() for sol in solidarity_res.items[:3]],
                "emergencies": [emg.model_dump() for emg in emergencies_res.items[:3]],
            },
        )

    def _sort_items(self, items: List[Any], sort: SearchSort) -> None:
        """
        Aplica la estrategia de ordenamiento sobre los resultados rankeados:
        1. Priorizar siempre los registros más cercanos (distancia real ascendente).
        2. Registros sin coordenadas van al final.
        3. Criterios secundarios (score, coincidencia, reputación) para desempate.
        """
        if sort == SearchSort.DISTANCE:
            # Estrictamente por distancia ascendente en metros; sin GPS al final
            items.sort(
                key=lambda x: (
                    x.distance_meters is None,
                    x.distance_meters if x.distance_meters is not None else float("inf"),
                    -getattr(x, "score", 0.0),
                )
            )
        elif sort == SearchSort.RELEVANCE:
            # Mayor coincidencia textual, luego proximidad
            items.sort(
                key=lambda x: (
                    -(x.score_breakdown.get("match_score", 0.0) if getattr(x, "score_breakdown", None) else 0.0),
                    x.distance_meters is None,
                    x.distance_meters if x.distance_meters is not None else float("inf"),
                    -round(getattr(x, "score", 0.0), 2),
                )
            )
        else:  # RECOMMENDED
            # Proximidad primero (distancia real ascendente); sin GPS al final
            # Score (relevancia + reputación + experiencia) como desempate
            items.sort(
                key=lambda x: (
                    x.distance_meters is None,
                    x.distance_meters if x.distance_meters is not None else float("inf"),
                    -getattr(x, "score", 0.0),
                )
            )

    def _sort_emergencies(self, emergencies: List[EmergencySearchResult], sort: SearchSort) -> None:
        """
        Ordenamiento especializado de seguridad para emergencias:
        REGLA CRÍTICA: NUNCA alterar la prioridad de seguridad de emergencias.
        1. Estado: Activas / Reportadas / En proceso van primero; cerradas/resueltas al final.
        2. Gravedad: Crítica > Alta > Media > Baja.
        3. Distancia ascendente en metros dentro de cada nivel de gravedad y estado.
        4. Antigüedad: más recientes primero.
        """
        SEVERITY_ORDER = {
            "critical": 0,
            "critica": 0,
            "high": 1,
            "alta": 1,
            "medium": 2,
            "media": 2,
            "low": 3,
            "baja": 3,
        }
        INACTIVE_STATUSES = {"resolved", "resuelto", "resuelta", "closed", "cerrado", "cerrada", "cancelada", "cancelled"}

        def emergency_key(emg: EmergencySearchResult):
            status_val = str(emg.status).lower().strip()
            is_inactive = 1 if status_val in INACTIVE_STATUSES else 0

            sev_val = str(emg.severity).lower().strip()
            sev_rank = SEVERITY_ORDER.get(sev_val, 4)

            has_no_dist = emg.distance_meters is None
            dist_m = emg.distance_meters if emg.distance_meters is not None else float("inf")

            created_ts = -emg.created_at.timestamp() if emg.created_at else 0.0

            if sort == SearchSort.DISTANCE:
                return (
                    is_inactive,
                    has_no_dist,
                    dist_m,
                    sev_rank,
                    created_ts,
                )
            else:  # RECOMMENDED
                return (
                    is_inactive,
                    sev_rank,
                    has_no_dist,
                    dist_m,
                    created_ts,
                )

        emergencies.sort(key=emergency_key)

    async def _persist_recommendations(
        self,
        user_id: Optional[uuid.UUID],
        rec_type: str,
        items: list,
    ) -> None:
        """Persiste las recomendaciones del usuario mediante upsert atómico evitando duplicados."""
        if not user_id or not items:
            return

        top_items = items[:10]
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        for it in top_items:
            score_val = round(float(getattr(it, "score", 0.0) or getattr(it, "match_score", 0.0) or 0.0), 4)
            breakdown = getattr(it, "score_breakdown", {}) or {}
            item_id = it.id

            if rec_type == "service":
                stmt = text("""
                    INSERT INTO ai_recommendations (id, user_id, recommendation_type, service_id, score, score_breakdown, algorithm_version, created_at)
                    VALUES (:id, :user_id, :rec_type, :item_id, :score, :breakdown, 'v1.0', :created_at)
                    ON CONFLICT (user_id, service_id) WHERE service_id IS NOT NULL
                    DO UPDATE SET 
                        score = EXCLUDED.score,
                        score_breakdown = EXCLUDED.score_breakdown,
                        created_at = EXCLUDED.created_at;
                """)
            elif rec_type == "product":
                stmt = text("""
                    INSERT INTO ai_recommendations (id, user_id, recommendation_type, product_id, score, score_breakdown, algorithm_version, created_at)
                    VALUES (:id, :user_id, :rec_type, :item_id, :score, :breakdown, 'v1.0', :created_at)
                    ON CONFLICT (user_id, product_id) WHERE product_id IS NOT NULL
                    DO UPDATE SET 
                        score = EXCLUDED.score,
                        score_breakdown = EXCLUDED.score_breakdown,
                        created_at = EXCLUDED.created_at;
                """)
            elif rec_type == "solidarity":
                stmt = text("""
                    INSERT INTO ai_recommendations (id, user_id, recommendation_type, solidarity_post_id, score, score_breakdown, algorithm_version, created_at)
                    VALUES (:id, :user_id, :rec_type, :item_id, :score, :breakdown, 'v1.0', :created_at)
                    ON CONFLICT (user_id, solidarity_post_id) WHERE solidarity_post_id IS NOT NULL
                    DO UPDATE SET 
                        score = EXCLUDED.score,
                        score_breakdown = EXCLUDED.score_breakdown,
                        created_at = EXCLUDED.created_at;
                """)
            elif rec_type == "emergency":
                stmt = text("""
                    INSERT INTO ai_recommendations (id, user_id, recommendation_type, emergency_id, score, score_breakdown, algorithm_version, created_at)
                    VALUES (:id, :user_id, :rec_type, :item_id, :score, :breakdown, 'v1.0', :created_at)
                    ON CONFLICT (user_id, emergency_id) WHERE emergency_id IS NOT NULL
                    DO UPDATE SET 
                        score = EXCLUDED.score,
                        score_breakdown = EXCLUDED.score_breakdown,
                        created_at = EXCLUDED.created_at;
                """)
            else:
                continue

            try:
                await self.session.execute(
                    stmt,
                    {
                        "id": uuid.uuid4(),
                        "user_id": user_id,
                        "rec_type": rec_type,
                        "item_id": item_id,
                        "score": score_val,
                        "breakdown": json.dumps(breakdown),
                        "created_at": now,
                    },
                )
            except Exception as e:
                logger.warning("Error persistiendo ai_recommendation: %s", str(e))

        try:
            await self.session.commit()
        except Exception:
            await self.session.rollback()

    async def get_user_recommendations(
        self,
        user_id: uuid.UUID,
        rec_type: Optional[str] = None,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """Recupera las recomendaciones persistidas más recientes para el usuario desde ai_recommendations."""
        query_sql = """
            SELECT 
                r.id,
                r.recommendation_type,
                r.service_id,
                r.product_id,
                r.solidarity_post_id,
                r.emergency_id,
                r.score,
                r.score_breakdown,
                r.algorithm_version,
                r.created_at,
                COALESCE(s.title, p.name, sol.title, em.title) AS title
            FROM ai_recommendations r
            LEFT JOIN services s ON r.service_id = s.id
            LEFT JOIN products p ON r.product_id = p.id
            LEFT JOIN solidarity_posts sol ON r.solidarity_post_id = sol.id
            LEFT JOIN emergencies em ON r.emergency_id = em.id
            WHERE r.user_id = :user_id
        """
        params = {"user_id": user_id, "limit": limit}
        if rec_type:
            query_sql += " AND r.recommendation_type = :rec_type"
            params["rec_type"] = rec_type
        query_sql += " ORDER BY r.score DESC, r.created_at DESC LIMIT :limit"

        res = await self.session.execute(text(query_sql), params)
        rows = res.mappings().all()
        return [dict(r) for r in rows]
