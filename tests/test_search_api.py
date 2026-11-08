"""Pruebas unitarias y de integración para el motor de búsqueda inteligente geolocalizada."""
import uuid
from decimal import Decimal
import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.modules.search.repository import (
    expand_query_terms,
    haversine_distance_km,
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
