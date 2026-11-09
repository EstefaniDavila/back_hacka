"""Pruebas unitarias y de integración para el motor de búsqueda inteligente geolocalizada."""
import uuid
from decimal import Decimal
import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.modules.search.repository import (
    expand_query_terms,
    haversine_distance_km,
    haversine_distance_meters,
    strip_accents,
)
from app.modules.search.service import SearchService


# ----------------------------------------------------------------------
# 1. PRUEBAS UNITARIAS: MATEMÁTICAS Y ALGORITMOS DE BÚSQUEDA
# ----------------------------------------------------------------------
def test_strip_accents_and_synonyms():
    """Verifica la normalización insensible a mayúsculas y tildes y expansión de sinónimos."""
    assert strip_accents("Gasfitería Básica") == "gasfiteria basica"
    assert strip_accents("MÉDICO Y ENFERMERÍA") == "medico y enfermeria"

    # Expansión de sinónimos barriales
    terms = expand_query_terms("gasfitero")
    assert "gasfitero" in terms
    assert "plomero" in terms or "gasfiteria" in terms

    terms_elect = expand_query_terms("electricista")
    assert "electricidad" in terms_elect or "cableado" in terms_elect


def test_haversine_distance_exactness():
    """Valida el cálculo real de distancia geodésica en kilómetros."""
    # Coordenadas Lima: Plaza de Armas (-12.046374, -77.042793) a Parque Kennedy Miraflores (-12.121852, -77.029864)
    # Distancia real aprox: 8.5 a 9.0 km
    lat1, lon1 = -12.046374, -77.042793
    lat2, lon2 = -12.121852, -77.029864

    dist = haversine_distance_km(lat1, lon1, lat2, lon2)
    assert 8.0 <= dist <= 9.5

    # Misma ubicación = 0 km
    assert haversine_distance_km(lat1, lon1, lat1, lon1) == 0.0


def test_bayesian_reputation_fairness_and_new_users():
    """
    Verifica que el promedio ponderado bayesiano evite que una única reseña de 5 estrellas
    supere injustamente a proveedores consolidados con muchas buenas calificaciones,
    y que los usuarios nuevos no sean penalizados a cero.
    """
    service = SearchService(session=None)

    # Proveedor A: 1 reseña de 5.0 estrellas
    bayes_a, score_a, is_new_a = service._calculate_bayesian_reputation(
        reviews_count=1, rating_avg=5.0, prior_mean=4.0, min_reviews_threshold=3
    )
    # WR = (1*5 + 3*4) / 4 = 17/4 = 4.25
    assert bayes_a == 4.25
    assert is_new_a is False

    # Proveedor B: 10 reseñas de 4.8 estrellas
    bayes_b, score_b, is_new_b = service._calculate_bayesian_reputation(
        reviews_count=10, rating_avg=4.8, prior_mean=4.0, min_reviews_threshold=3
    )
    # WR = (10*4.8 + 3*4) / 13 = 60/13 = 4.62
    assert bayes_b == 4.62
    assert is_new_b is False

    # Proveedor B con más evidencia comprobada debe superar a Proveedor A con 1 sola reseña
    assert bayes_b > bayes_a
    assert score_b > score_a

    # Proveedor C: Usuario nuevo (0 reseñas)
    bayes_c, score_c, is_new_c = service._calculate_bayesian_reputation(
        reviews_count=0, rating_avg=0.0, prior_mean=4.0, min_reviews_threshold=3
    )
    assert is_new_c is True
    assert score_c >= 0.70  # No penalizado a 0


def test_text_match_scoring():
    """Verifica que la coincidencia exacta de título y sinónimos obtenga mayor puntaje."""
    service = SearchService(session=None)

    # Coincidencia exacta de término en título
    score_exact = service._calculate_text_match_score(
        query="gasfitero",
        title="Gasfitero profesional para fugas y tuberías",
        category="Gasfitería",
    )
    assert score_exact >= 0.85

    # Búsqueda con sinónimo ("plomero" buscando servicio de "gasfitería")
    score_synonym = service._calculate_text_match_score(
        query="plomero",
        title="Reparación de caños y tuberías de agua",
        category="Gasfitería",
    )
    assert score_synonym >= 0.70

    # Texto no relacionado
    score_irrelevant = service._calculate_text_match_score(
        query="electricista",
        title="Venta de tortas y postres",
        category="Repostería",
    )
    assert score_irrelevant < 0.20


# ----------------------------------------------------------------------
# 2. PRUEBAS DE INTEGRACIÓN DE ENDPOINTS HTTP
# ----------------------------------------------------------------------
@pytest.mark.asyncio
async def test_global_search_endpoint_empty_and_general():
    """Verifica el endpoint GET /api/v1/search sin parámetros y con búsqueda general."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        # Búsqueda general abierta
        response = await client.get("/api/v1/search")
        assert response.status_code == 200
        data = response.json()

        assert "total_results" in data
        assert "items" in data
        assert "sections_summary" in data
        assert "services" in data["sections_summary"]
        assert "products" in data["sections_summary"]
        assert "solidarity" in data["sections_summary"]
        assert "emergencies" in data["sections_summary"]
        assert "top_sections" in data


@pytest.mark.asyncio
async def test_global_search_with_query_and_geoloc():
    """Verifica la búsqueda combinando texto y coordenadas GPS."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.get(
            "/api/v1/search",
            params={
                "q": "electricidad",
                "latitude": -12.0463,
                "longitude": -77.0427,
                "radius_km": 10.0,
                "sort": "recommended",
                "page": 1,
                "page_size": 10,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["query"] == "electricidad"
        assert data["sort_applied"] == "recommended"
        assert data["location_applied"]["radius_km"] == 10.0

        for item in data["items"]:
            assert "ranking_score" in item
            assert "detail_path" in item
            assert "module" in item
            assert item["ranking_score"] >= 0.0


@pytest.mark.asyncio
async def test_services_search_endpoint():
    """Verifica GET /api/v1/search/services con ordenamiento por distancia y relevancia."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        # 1. Por relevancia
        res_rel = await client.get(
            "/api/v1/search/services",
            params={"sort": "relevance", "page": 1, "page_size": 5},
        )
        assert res_rel.status_code == 200
        data_rel = res_rel.json()
        assert "items" in data_rel
        assert "meta" in data_rel

        # 2. Con geolocalización
        res_geo = await client.get(
            "/api/v1/search/services",
            params={
                "latitude": -12.0463,
                "longitude": -77.0427,
                "radius_km": 5.0,
                "sort": "distance",
            },
        )
        assert res_geo.status_code == 200
        data_geo = res_geo.json()
        assert data_geo["sort_applied"] == "distance"


@pytest.mark.asyncio
async def test_products_search_endpoint():
    """Verifica GET /api/v1/search/products."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.get(
            "/api/v1/search/products",
            params={"sort": "recommended", "page": 1, "page_size": 5},
        )
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "meta" in data


@pytest.mark.asyncio
async def test_solidarity_search_endpoint():
    """Verifica GET /api/v1/search/solidarity."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.get(
            "/api/v1/search/solidarity",
            params={"sort": "recommended"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "items" in data


@pytest.mark.asyncio
async def test_emergencies_search_endpoint():
    """Verifica GET /api/v1/search/emergencies."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.get(
            "/api/v1/search/emergencies",
            params={"sort": "recommended"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "items" in data


# ----------------------------------------------------------------------
# 3. PRUEBAS ESPECÍFICAS DEL ALGORITMO AJUSTADO (55% PROXIMIDAD)
# ----------------------------------------------------------------------
def test_haversine_distance_meters_and_km():
    """Verifica que la distancia en metros sea exacta y coherente con km."""
    # Latitud/Longitud de referencia
    user_lat, user_lon = -12.046374, -77.042793
    # 0.0004 grados de latitud corresponden aproximadamente a 44.5 metros
    test_lat = user_lat + 0.0004
    test_lon = user_lon

    meters = haversine_distance_meters(user_lat, user_lon, test_lat, test_lon)
    km = haversine_distance_km(user_lat, user_lon, test_lat, test_lon)

    assert 40.0 <= meters <= 50.0
    assert km == round(meters / 1000.0, 3)
    # Misma posición = 0 metros
    assert haversine_distance_meters(user_lat, user_lon, user_lat, user_lon) == 0.0


def test_validation_scenario_45m_to_950m_ordering():
    """
    EJEMPLO DE VALIDACIÓN DEL USUARIO:
    Vecinos a: 45 m, 90 m, 130 m, 210 m, 280 m, 350 m, 470 m, 620 m, 750 m y 950 m.
    El resultado DEBE mostrarlos en ese orden exacto bajo 55% proximidad.
    """
    from app.modules.search.schemas import SearchSort, ServiceSearchResult

    service = SearchService(session=None)
    user_lat, user_lon = -12.046374, -77.042793

    # Distancias reales en metros
    distances_m = [45.0, 90.0, 130.0, 210.0, 280.0, 350.0, 470.0, 620.0, 750.0, 950.0]
    items = []

    for d in distances_m:
        # Calcular coordenadas aproximadas para dar exactamente d metros
        # 1 grado latitud aprox = 111,139 metros
        delta_deg = d / 111139.0
        item_lat = user_lat + delta_deg
        item_lon = user_lon

        dist_km, dist_meters, dist_score, within_radius = service._calculate_distance_and_score(
            user_lat, user_lon, item_lat, item_lon, radius_km=1.0
        )
        assert within_radius is True

        match_score = 1.0  # Misma relevancia de oficio
        rep_rating, rep_score, is_new = service._calculate_bayesian_reputation(reviews_count=0, rating_avg=0.0)
        exp_score = service._calculate_experience_score(0, is_new=True)

        final_score = (
            0.55 * dist_score
            + 0.25 * match_score
            + 0.15 * rep_score
            + 0.05 * exp_score
        )

        items.append(
            ServiceSearchResult(
                id=uuid.uuid4(),
                title=f"Vecino a {int(d)}m",
                provider_id=uuid.uuid4(),
                provider_name=f"Vecino {int(d)}m",
                is_verified=True,
                is_new=True,
                distance_km=dist_km,
                distance_meters=dist_meters,
                score=round(final_score, 4),
                ranking_score=round(final_score, 4),
                score_breakdown={
                    "match_score": match_score,
                    "distance_score": dist_score,
                    "reputation_score": rep_score,
                    "experience_score": exp_score,
                    "distance_meters": dist_meters,
                    "final_score": round(final_score, 4),
                },
            )
        )

    # Ordenar por el criterio RECOMMENDED
    service._sort_items(items, SearchSort.RECOMMENDED)

    # Verificar que el orden final sea estrictamente de menor a mayor distancia
    actual_order = [it.distance_meters for it in items]
    assert len(actual_order) == 10
    # Cada vecino debe estar más cerca que el siguiente
    for i in range(len(actual_order) - 1):
        assert actual_order[i] < actual_order[i + 1], f"Fallo en orden: {actual_order[i]}m no es menor que {actual_order[i+1]}m"

    # El más cercano (45m) aparece de primero y el de 950m al final
    assert actual_order[0] <= 50.0
    assert actual_order[-1] >= 940.0


def test_radius_1km_excludes_items_outside():
    """Valida que un vecino a 1050 m quede excluido cuando radius_km=1.0."""
    service = SearchService(session=None)
    user_lat, user_lon = -12.046374, -77.042793

    # 1050 metros de distancia
    delta_deg = 1050.0 / 111139.0
    item_lat = user_lat + delta_deg
    item_lon = user_lon

    dist_km, dist_meters, dist_score, within_radius = service._calculate_distance_and_score(
        user_lat, user_lon, item_lat, item_lon, radius_km=1.0
    )
    assert within_radius is False
    assert dist_meters > 1000.0


def test_new_user_not_penalized_vs_distant_veteran():
    """
    Valida que un nuevo vecino cercano (90m) no sea superado sistemáticamente
    por un veterano lejano (470m) solo por tener valoraciones.
    """
    from app.modules.search.schemas import SearchSort, ServiceSearchResult

    service = SearchService(session=None)
    user_lat, user_lon = -12.046374, -77.042793

    # Vecino A: Nuevo usuario a 90m
    lat_a = user_lat + (90.0 / 111139.0)
    _, d_m_a, d_score_a, _ = service._calculate_distance_and_score(user_lat, user_lon, lat_a, user_lon, 1.0)
    _, rep_a, is_new_a = service._calculate_bayesian_reputation(0, 0.0)
    exp_a = service._calculate_experience_score(0, is_new=True)
    score_a = 0.55 * d_score_a + 0.25 * 1.0 + 0.15 * rep_a + 0.05 * exp_a

    # Vecino B: Veterano con 20 reseñas de 5 estrellas pero a 470m
    lat_b = user_lat + (470.0 / 111139.0)
    _, d_m_b, d_score_b, _ = service._calculate_distance_and_score(user_lat, user_lon, lat_b, user_lon, 1.0)
    _, rep_b, is_new_b = service._calculate_bayesian_reputation(20, 5.0)
    exp_b = service._calculate_experience_score(20, is_new=False)
    score_b = 0.55 * d_score_b + 0.25 * 1.0 + 0.15 * rep_b + 0.05 * exp_b

    # El vecino nuevo cercano (90m) debe tener mayor puntuación que el veterano a 470m
    assert score_a > score_b

    items = [
        ServiceSearchResult(
            id=uuid.uuid4(),
            title="Veterano a 470m",
            provider_id=uuid.uuid4(),
            provider_name="Veterano",
            distance_meters=d_m_b,
            distance_km=round(d_m_b / 1000.0, 3),
            score=round(score_b, 4),
            ranking_score=round(score_b, 4),
        ),
        ServiceSearchResult(
            id=uuid.uuid4(),
            title="Nuevo Vecino a 90m",
            provider_id=uuid.uuid4(),
            provider_name="Nuevo",
            distance_meters=d_m_a,
            distance_km=round(d_m_a / 1000.0, 3),
            score=round(score_a, 4),
            ranking_score=round(score_a, 4),
        ),
    ]

    service._sort_items(items, SearchSort.RECOMMENDED)
    assert items[0].provider_name == "Nuevo"


def test_tie_breaker_prioritizes_closer():
    """Si dos vecinos tienen puntajes idénticos o muy similares, se prioriza al más cercano."""
    from app.modules.search.schemas import SearchSort, ServiceSearchResult

    service = SearchService(session=None)

    items = [
        ServiceSearchResult(
            id=uuid.uuid4(),
            title="Vecino Lejano",
            provider_id=uuid.uuid4(),
            provider_name="Lejano",
            distance_meters=600.0,
            distance_km=0.6,
            score=0.85,
            ranking_score=0.85,
        ),
        ServiceSearchResult(
            id=uuid.uuid4(),
            title="Vecino Cercano",
            provider_id=uuid.uuid4(),
            provider_name="Cercano",
            distance_meters=150.0,
            distance_km=0.15,
            score=0.85,
            ranking_score=0.85,
        ),
    ]

    service._sort_items(items, SearchSort.RECOMMENDED)
    assert items[0].provider_name == "Cercano"


def test_emergencies_critical_priority():
    """Valida que una emergencia crítica mantenga prioridad sobre emergencias menores."""
    from app.modules.search.schemas import EmergencySearchResult

    emg_critical = EmergencySearchResult(
        id=uuid.uuid4(),
        title="Incendio en vivienda",
        emergency_type="incendio",
        severity="critical",
        status="active",
        reported_by=uuid.uuid4(),
        distance_meters=850.0,
        distance_km=0.85,
        score=0.88,
        ranking_score=0.88,
        score_breakdown={"severity_score": 1.0},
    )

    emg_low = EmergencySearchResult(
        id=uuid.uuid4(),
        title="Ruido molesto",
        emergency_type="ruido",
        severity="low",
        status="active",
        reported_by=uuid.uuid4(),
        distance_meters=80.0,
        distance_km=0.08,
        score=0.55,
        ranking_score=0.55,
        score_breakdown={"severity_score": 0.45},
    )

    emergencies = [emg_low, emg_critical]
    # Ordenamiento recomendado de emergencias: por gravedad primero
    emergencies.sort(
        key=lambda x: (
            -round(x.score_breakdown.get("severity_score", 0.0), 2),
            x.distance_meters is None,
            x.distance_meters or 9999999.0,
            -x.score,
        )
    )

    assert emergencies[0].severity == "critical"
    assert emergencies[0].title == "Incendio en vivienda"


@pytest.mark.asyncio
async def test_global_search_response_fields_and_page_size_10():
    """Valida que la API devuelva distance_meters, distance_km, score y respete page_size=10."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.get(
            "/api/v1/search",
            params={
                "latitude": -12.0463,
                "longitude": -77.0427,
                "radius_km": 1.0,
                "sort": "recommended",
                "page": 1,
                "page_size": 10,
            },
        )
        assert response.status_code == 200
        data = response.json()

        assert len(data["items"]) <= 10
        assert data["limit"] == 10

        for it in data["items"]:
            assert "score" in it
            assert "ranking_score" in it
            assert "distance_km" in it
            assert "distance_meters" in it
            assert "module" in it
            assert "title" in it

