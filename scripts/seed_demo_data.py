"""
Script de reconstrucción completa del entorno de datos de demostración para VeciRed IA en Arequipa, Perú.

Características principales:
1. Limpieza selectiva y segura: elimina exclusivamente registros sintéticos anteriores y deja intactos los datos reales.
2. Genera backup en JSON de los datos anteriores antes de borrar.
3. Configuración geográfica estructurada para Arequipa (Cayma, Yanahuara, Cerro Colorado, Cercado, José Luis Bustamante y Rivero).
4. 25 perfiles de demostración distribuidos en 5 grupos geográficos de 5 vecinos (distancias relativas: 0m, 80m, 150m, 220m, 300m).
5. 80 registros exactos:
   - 20 Servicios (4 por zona)
   - 20 Productos (4 por zona)
   - 20 Solicitudes de Ayuda Solidaria (4 por zona)
   - 20 Emergencias de prueba (4 por zona)
6. Contenido en español peruano natural sin etiquetas visibles como DEMO, TEST, PRUEBA o [DEMO].
7. Conserva identificación interna mediante UUIDv5 deterministas para garantizar idempotencia.
8. Direcciones estructuradas con Departamento, Provincia, Distrito, Urbanización, Calle, Mz/Lote sintéticos y referencias verificables.
9. Direcciones marcadas como 'declared'/'pending', NUNCA como verificadas.
10. Soporte para modo simulación (--dry-run) y ejecución real (--execute).
"""
import argparse
import asyncio
import json
import math
import os
import sys
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, "/home/tefa/hack/back")
os.chdir("/home/tefa/hack/back")

from sqlalchemy import delete, func, or_, select, text

from app.db.session import get_session_factory
from app.modules.commerce.models import (
    Business,
    Product,
    ProductCategory,
    Service,
    ServiceCategory,
)
from app.modules.emergencies.models import Emergency
from app.modules.geo.models import Address, Community, Department, District, Province
from app.modules.interactions.models import Review
from app.modules.solidarity.models import SolidarityPost
from app.modules.users.models import CommunityMembership, Profile, UserAddress

# Namespace determinista v5 para todos los registros sintéticos de VeciRed IA
DEMO_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_DNS, "demo.vecired.pe")
AREQUIPA_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_DNS, "arequipa.demo.vecired.pe")

def get_demo_uuid(kind: str, index: int) -> uuid.UUID:
    """Retorna un UUIDv5 determinista para garantizar idempotencia e identificación interna."""
    return uuid.uuid5(DEMO_NAMESPACE, f"{kind}_{index}")

def get_aqp_uuid(kind: str, index: int) -> uuid.UUID:
    """UUIDv5 determinista para los nuevos datos de Arequipa."""
    return uuid.uuid5(AREQUIPA_NAMESPACE, f"{kind}_{index}")

def calculate_offset_coords(center_lat: float, center_lon: float, distance_meters: float, angle_degrees: float) -> Tuple[float, float]:
    """Calcula coordenadas con precisión geodésica para Arequipa (Lat ~ -16.4)."""
    rad = math.radians(angle_degrees)
    # 1 deg latitud ~ 111,139 m
    # 1 deg longitud en lat -16.4 deg ~ 106,600 m
    d_lat = (distance_meters * math.cos(rad)) / 111139.0
    d_lon = (distance_meters * math.sin(rad)) / 106600.0
    return round(center_lat + d_lat, 7), round(center_lon + d_lon, 7)


# ----------------------------------------------------------------------
# CARTOGRAFÍA OFICIAL DE AREQUIPA SEGÚN INEI
# ----------------------------------------------------------------------
AREQUIPA_GEO_CONFIG = {
    "department": {"id": 4, "name": "Arequipa", "ubigeo": "04"},
    "province": {"id": 401, "name": "Arequipa", "department_id": 4, "ubigeo": "0401"},
    "districts": [
        {"id": 40103, "name": "Cayma", "province_id": 401, "ubigeo": "040103", "center_lat": -16.3815000, "center_lon": -71.5450000},
        {"id": 40126, "name": "Yanahuara", "province_id": 401, "ubigeo": "040126", "center_lat": -16.3870000, "center_lon": -71.5415000},
        {"id": 40104, "name": "Cerro Colorado", "province_id": 401, "ubigeo": "040104", "center_lat": -16.3680000, "center_lon": -71.5650000},
        {"id": 40101, "name": "Arequipa", "province_id": 401, "ubigeo": "040101", "center_lat": -16.4010000, "center_lon": -71.5375000},
        {"id": 40129, "name": "José Luis Bustamante y Rivero", "province_id": 401, "ubigeo": "040129", "center_lat": -16.4250000, "center_lon": -71.5230000},
    ]
}

# ----------------------------------------------------------------------
# 25 VECINOS DISTRIBUIDOS EN 5 GRUPOS GEOGRÁFICOS
# ----------------------------------------------------------------------
DEMO_NEIGHBORS_AREQUIPA = [
    # GRUPO 1: CAYMA (Vecinos 1 al 5)
    {
        "index": 1,
        "name": "Carlos Mendoza Salas",
        "phone": "+51954110001",
        "district_id": 40103,
        "district_name": "Cayma",
        "zone_name": "Cayma Tradicional",
        "urbanization": "Urb. Cayma",
        "street": "Av. Cayma 605",
        "lot_number": "Mz. A Lote 4",
        "reference": "A 1 cuadra de la Plaza Principal de Cayma",
        "distance_m": 0.0,
        "angle": 0.0,
        "helped_count": 0,
        "reputation_profile": "Nuevo vecino sin reseñas",
    },
    {
        "index": 2,
        "name": "Elena Ramos Cornejo",
        "phone": "+51954110002",
        "district_id": 40103,
        "district_name": "Cayma",
        "zone_name": "La Tomilla",
        "urbanization": "Urb. La Tomilla",
        "street": "Calle Tronchadero 214",
        "lot_number": "Mz. C Lote 12",
        "reference": "Frente al Complejo Deportivo La Tomilla",
        "distance_m": 80.0,
        "angle": 35.0,
        "helped_count": 2,
        "reputation_profile": "1 reseña de 5 estrellas",
    },
    {
        "index": 3,
        "name": "Jorge Quispe Vilca",
        "phone": "+51954110003",
        "district_id": 40103,
        "district_name": "Cayma",
        "zone_name": "Carmen Alto",
        "urbanization": "Urb. Tronchadero",
        "street": "Calle Dean Valdivia 318",
        "lot_number": "Mz. B Lote 8",
        "reference": "A espaldas de la Parroquia San Miguel Arcángel",
        "distance_m": 150.0,
        "angle": 90.0,
        "helped_count": 5,
        "reputation_profile": "3 reseñas (4.8 estrellas)",
    },
    {
        "index": 4,
        "name": "Rosa Morales Paredes",
        "phone": "+51954110004",
        "district_id": 40103,
        "district_name": "Cayma",
        "zone_name": "Acequia Alta",
        "urbanization": "Urb. Carmen Alto",
        "street": "Calle Miguel Grau 142",
        "lot_number": "Mz. F Lote 15",
        "reference": "Cerca al Mirador de Carmen Alto",
        "distance_m": 220.0,
        "angle": 145.0,
        "helped_count": 8,
        "reputation_profile": "Consolidada con 7 reseñas (4.9 estrellas)",
    },
    {
        "index": 5,
        "name": "Manuel Valdivia Cáceres",
        "phone": "+51954110005",
        "district_id": 40103,
        "district_name": "Cayma",
        "zone_name": "Bolognesi",
        "urbanization": "Urb. Bolognesi",
        "street": "Pasaje Santa Rosa 108",
        "lot_number": "Mz. D Lote 3",
        "reference": "A media cuadra de la posta médica de Cayma",
        "distance_m": 300.0,
        "angle": 215.0,
        "helped_count": 14,
        "reputation_profile": "Alta reputación (12 reseñas, 5.0)",
    },

    # GRUPO 2: YANAHUARA (Vecinos 6 al 10)
    {
        "index": 6,
        "name": "Lucía Fernández Guillén",
        "phone": "+51954110006",
        "district_id": 40126,
        "district_name": "Yanahuara",
        "zone_name": "Yanahuara Tradicional",
        "urbanization": "Urb. Yanahuara Tradicional",
        "street": "Calle Cuesta del Ángel 112",
        "lot_number": "Mz. A Lote 6",
        "reference": "A media cuadra del Mirador de Yanahuara",
        "distance_m": 0.0,
        "angle": 0.0,
        "helped_count": 1,
        "reputation_profile": "1 reseña de 5.0",
    },
    {
        "index": 7,
        "name": "Víctor Cárdenas Becerra",
        "phone": "+51954110007",
        "district_id": 40126,
        "district_name": "Yanahuara",
        "zone_name": "Antiquilla",
        "urbanization": "Urb. Cortadores",
        "street": "Calle Lima 304",
        "lot_number": "Mz. C Lote 9",
        "reference": "Costado de la Parroquia San Juan Bautista",
        "distance_m": 85.0,
        "angle": 40.0,
        "helped_count": 18,
        "reputation_profile": "Líder comunal consolidado (15 reseñas)",
    },
    {
        "index": 8,
        "name": "Camila Torres Zegarra",
        "phone": "+51954110008",
        "district_id": 40126,
        "district_name": "Yanahuara",
        "zone_name": "Piedra Santa",
        "urbanization": "Urb. Piedra Santa",
        "street": "Calle Jerusalén 415",
        "lot_number": "Mz. E Lote 11",
        "reference": "Frente al Parque de la Tradición",
        "distance_m": 160.0,
        "angle": 105.0,
        "helped_count": 0,
        "reputation_profile": "Nueva vecina sin reseñas",
    },
    {
        "index": 9,
        "name": "Raúl Huamán Chávez",
        "phone": "+51954110009",
        "district_id": 40126,
        "district_name": "Yanahuara",
        "zone_name": "Umacollo Norte",
        "urbanization": "Urb. Umacollo Norte",
        "street": "Calle Misti 228",
        "lot_number": "Mz. B Lote 7",
        "reference": "A 1 cuadra de la Comisaría de Yanahuara",
        "distance_m": 230.0,
        "angle": 170.0,
        "helped_count": 4,
        "reputation_profile": "3 reseñas (4.7 estrellas)",
    },
    {
        "index": 10,
        "name": "Patricia Benítez Rivera",
        "phone": "+51954110010",
        "district_id": 40126,
        "district_name": "Yanahuara",
        "zone_name": "Los Sauces",
        "urbanization": "Urb. Los Sauces",
        "street": "Pasaje Beaterio 116",
        "lot_number": "Mz. D Lote 14",
        "reference": "A media cuadra de la Alameda Bolognesi",
        "distance_m": 310.0,
        "angle": 250.0,
        "helped_count": 6,
        "reputation_profile": "5 reseñas (4.8 estrellas)",
    },

    # GRUPO 3: CERRO COLORADO (Vecinos 11 al 15)
    {
        "index": 11,
        "name": "Álvaro Delgado Portugal",
        "phone": "+51954110011",
        "district_id": 40104,
        "district_name": "Cerro Colorado",
        "zone_name": "La Libertad",
        "urbanization": "Urb. La Libertad",
        "street": "Av. Alfonso Ugarte 520",
        "lot_number": "Mz. K Lote 2",
        "reference": "Frente al Mercado La Libertad",
        "distance_m": 0.0,
        "angle": 0.0,
        "helped_count": 3,
        "reputation_profile": "2 reseñas (5.0)",
    },
    {
        "index": 12,
        "name": "Beatriz Alarcón Fuentes",
        "phone": "+51954110012",
        "district_id": 40104,
        "district_name": "Cerro Colorado",
        "zone_name": "Mariscal Castilla",
        "urbanization": "Urb. Mariscal Castilla",
        "street": "Calle Melgar 315",
        "lot_number": "Mz. M Lote 16",
        "reference": "A 2 cuadras de la Plaza Las Américas",
        "distance_m": 90.0,
        "angle": 55.0,
        "helped_count": 0,
        "reputation_profile": "Nueva vecina sin reseñas",
    },
    {
        "index": 13,
        "name": "Gonzalo Pacheco Medina",
        "phone": "+51954110013",
        "district_id": 40104,
        "district_name": "Cerro Colorado",
        "zone_name": "Río Seco",
        "urbanization": "Asoc. Villa Las Canteras",
        "street": "Calle Bolognesi 410",
        "lot_number": "Mz. P Lote 5",
        "reference": "Cerca a la Parroquia Nuestra Señora de la Asunción",
        "distance_m": 170.0,
        "angle": 120.0,
        "helped_count": 7,
        "reputation_profile": "5 reseñas (4.9 estrellas)",
    },
    {
        "index": 14,
        "name": "Silvia Barreda Montoya",
        "phone": "+51954110014",
        "district_id": 40104,
        "district_name": "Cerro Colorado",
        "zone_name": "Zamácola",
        "urbanization": "Urb. Zamácola",
        "street": "Calle Pumacahua 205",
        "lot_number": "Mz. R Lote 9",
        "reference": "A espaldas del Estadio Mariscal Castilla",
        "distance_m": 240.0,
        "angle": 195.0,
        "helped_count": 10,
        "reputation_profile": "Alta experiencia (8 reseñas)",
    },
    {
        "index": 15,
        "name": "Marcos Linares Tejada",
        "phone": "+51954110015",
        "district_id": 40104,
        "district_name": "Cerro Colorado",
        "zone_name": "Challapampa",
        "urbanization": "Urb. Challapampa",
        "street": "Pasaje Arequipa 118",
        "lot_number": "Mz. T Lote 18",
        "reference": "Frente al Colegio San Jerónimo",
        "distance_m": 320.0,
        "angle": 280.0,
        "helped_count": 1,
        "reputation_profile": "1 reseña (4.0 estrellas)",
    },

    # GRUPO 4: CERCADO DE AREQUIPA (Vecinos 16 al 20)
    {
        "index": 16,
        "name": "Diana Bustamante Pinto",
        "phone": "+51954110016",
        "district_id": 40101,
        "district_name": "Arequipa",
        "zone_name": "Vallecito",
        "urbanization": "Urb. Vallecito",
        "street": "Calle San Agustín 340",
        "lot_number": "Mz. B Lote 5",
        "reference": "Frente al Parque Infantil de Vallecito",
        "distance_m": 0.0,
        "angle": 0.0,
        "helped_count": 5,
        "reputation_profile": "4 reseñas (4.8 estrellas)",
    },
    {
        "index": 17,
        "name": "Fernando Ballón Lazo",
        "phone": "+51954110017",
        "district_id": 40101,
        "district_name": "Arequipa",
        "zone_name": "Centro Histórico",
        "urbanization": "Centro Histórico",
        "street": "Calle Álvarez Thomas 218",
        "lot_number": "Mz. D Lote 12",
        "reference": "A 3 cuadras de la Plaza de Armas",
        "distance_m": 75.0,
        "angle": 45.0,
        "helped_count": 12,
        "reputation_profile": "Consolidado (10 reseñas, 5.0)",
    },
    {
        "index": 18,
        "name": "Mónica Cornejo Polar",
        "phone": "+51954110018",
        "district_id": 40101,
        "district_name": "Arequipa",
        "zone_name": "La Merced",
        "urbanization": "Urb. Victoria",
        "street": "Calle La Merced 412",
        "lot_number": "Mz. G Lote 8",
        "reference": "Cerca a la Iglesia de La Merced",
        "distance_m": 140.0,
        "angle": 110.0,
        "helped_count": 0,
        "reputation_profile": "Nueva vecina sin reseñas",
    },
    {
        "index": 19,
        "name": "César Montoya Beltrán",
        "phone": "+51954110019",
        "district_id": 40101,
        "district_name": "Arequipa",
        "zone_name": "El Filtro",
        "urbanization": "Urb. El Filtro",
        "street": "Calle Consuelo 105",
        "lot_number": "Mz. I Lote 14",
        "reference": "Frente al Hospital Goyeneche",
        "distance_m": 210.0,
        "angle": 180.0,
        "helped_count": 3,
        "reputation_profile": "2 reseñas (4.5 estrellas)",
    },
    {
        "index": 20,
        "name": "Gabriela Vera Arispe",
        "phone": "+51954110020",
        "district_id": 40101,
        "district_name": "Arequipa",
        "zone_name": "San Lázaro",
        "urbanization": "Barrio San Lázaro",
        "street": "Pasaje Romero 204",
        "lot_number": "Mz. L Lote 3",
        "reference": "En el Callejón de Bayoneta, San Lázaro",
        "distance_m": 290.0,
        "angle": 260.0,
        "helped_count": 7,
        "reputation_profile": "6 reseñas (4.9 estrellas)",
    },

    # GRUPO 5: JOSÉ LUIS BUSTAMANTE Y RIVERO (Vecinos 21 al 25)
    {
        "index": 21,
        "name": "Renato Carpio Manchego",
        "phone": "+51954110021",
        "district_id": 40129,
        "district_name": "José Luis Bustamante y Rivero",
        "zone_name": "Dolores",
        "urbanization": "Urb. La Pampilla",
        "street": "Av. Dolores 415",
        "lot_number": "Mz. C Lote 7",
        "reference": "A espaldas del Parque Zonal Dolores",
        "distance_m": 0.0,
        "angle": 0.0,
        "helped_count": 4,
        "reputation_profile": "3 reseñas (5.0 estrellas)",
    },
    {
        "index": 22,
        "name": "Vanessa Yáñez Bedregal",
        "phone": "+51954110022",
        "district_id": 40129,
        "district_name": "José Luis Bustamante y Rivero",
        "zone_name": "Monterrey",
        "urbanization": "Urb. Monterrey",
        "street": "Av. Estados Unidos 812",
        "lot_number": "Mz. E Lote 19",
        "reference": "Cerca al cruce con Av. Dolores",
        "distance_m": 85.0,
        "angle": 50.0,
        "helped_count": 0,
        "reputation_profile": "Nueva vecina sin reseñas",
    },
    {
        "index": 23,
        "name": "Héctor Maldonado Zevallos",
        "phone": "+51954110023",
        "district_id": 40129,
        "district_name": "José Luis Bustamante y Rivero",
        "zone_name": "Satélite",
        "urbanization": "Urb. Ciudad Satélite",
        "street": "Calle Colombia 305",
        "lot_number": "Mz. H Lote 10",
        "reference": "A 2 cuadras de la Parroquia Nuestra Señora de Guadalupe",
        "distance_m": 155.0,
        "angle": 115.0,
        "helped_count": 9,
        "reputation_profile": "7 reseñas (4.9 estrellas)",
    },
    {
        "index": 24,
        "name": "Karina Vizcarra Polar",
        "phone": "+51954110024",
        "district_id": 40129,
        "district_name": "José Luis Bustamante y Rivero",
        "zone_name": "La Alborada",
        "urbanization": "Urb. La Alborada",
        "street": "Calle Argentina 140",
        "lot_number": "Mz. J Lote 4",
        "reference": "Frente al Complejo Recreacional La Alborada",
        "distance_m": 225.0,
        "angle": 185.0,
        "helped_count": 15,
        "reputation_profile": "Veterana comunal (12 reseñas)",
    },
    {
        "index": 25,
        "name": "Javier Rospigliosi Begazo",
        "phone": "+51954110025",
        "district_id": 40129,
        "district_name": "José Luis Bustamante y Rivero",
        "zone_name": "Lanificio",
        "urbanization": "Urb. Lanificio",
        "street": "Pasaje Brasil 218",
        "lot_number": "Mz. M Lote 13",
        "reference": "Cerca a la Av. Paseo de la Cultura",
        "distance_m": 305.0,
        "angle": 275.0,
        "helped_count": 2,
        "reputation_profile": "1 reseña (4.0 estrellas)",
    },
]

# ----------------------------------------------------------------------
# 20 SERVICIOS DISTRIBUIDOS (4 POR ZONA)
# ----------------------------------------------------------------------
SERVICES_AREQUIPA = [
    # Cayma
    {"index": 1, "user_index": 1, "title": "Instalación y Mantenimiento Eléctrico Residencial", "category_name": "Electricidad y Cableado", "price": Decimal("60.00"), "unit": "servicio", "desc": "Instalación de interruptores termomagnéticos, cableado para termas solares y solución de cortocircuitos domiciliarios."},
    {"index": 2, "user_index": 2, "title": "Reparación de Fugas de Agua y Mantenimiento de Grifería", "category_name": "Gasfitería y Plomería", "price": Decimal("50.00"), "unit": "visita", "desc": "Atención especializada en tuberías de cobre y PVC, termas solares, llaves de paso y desatoro de tuberías."},
    {"index": 3, "user_index": 3, "title": "Carpintería Fina y Reparación de Muebles en Madera", "category_name": "Carpintería y Muebles", "price": Decimal("85.00"), "unit": "mueble", "desc": "Restauración de reposteros, comedores, puertas de cedro y confección de muebles a medida para el hogar."},
    {"index": 4, "user_index": 4, "title": "Limpieza Integral y Desinfección de Departamentos", "category_name": "Limpieza y Hogar", "price": Decimal("45.00"), "unit": "hora", "desc": "Limpieza profunda de cocinas, vidrios, alfombras y desinfección de baños con productos biodegradables."},
    # Yanahuara
    {"index": 5, "user_index": 6, "title": "Corte y Estilismo Capilar a Domicilio", "category_name": "Belleza y Cuidado Personal", "price": Decimal("35.00"), "unit": "corte", "desc": "Cortes clásicos y modernos para damas y caballeros, peinados y tratamientos capilares en la comodidad de su hogar."},
    {"index": 6, "user_index": 7, "title": "Mantenimiento Preventivo y Reparación de Computadoras", "category_name": "Reparación de Computadoras", "price": Decimal("70.00"), "unit": "equipo", "desc": "Limpieza de hardware, optimización de velocidad, eliminación de virus y configuración de redes Wi-Fi."},
    {"index": 7, "user_index": 8, "title": "Clases Particulares de Matemática y Razonamiento", "category_name": "Clases y Apoyo Escolar", "price": Decimal("30.00"), "unit": "hora", "desc": "Nivelación y refuerzo escolar en álgebra, geometría y trigonometría para secundaria y preparación preuniversitaria."},
    {"index": 8, "user_index": 9, "title": "Jardinería, Poda y Cuidado de Áreas Verdes", "category_name": "Jardinería y Poda", "price": Decimal("40.00"), "unit": "hora", "desc": "Poda de rosales, mantenimiento de césped, aplicación de abono orgánico y control ecológico de plagas de jardín."},
    # Cerro Colorado
    {"index": 9, "user_index": 11, "title": "Pintado de Fachadas e Interiores con Látex Lavable", "category_name": "Albañilería y Pintura", "price": Decimal("130.00"), "unit": "ambiente", "desc": "Resane de grietas, empastado fino, impermeabilización de techos y pintura de muros interiores y exteriores."},
    {"index": 10, "user_index": 12, "title": "Fletes y Transporte Local en Camioneta", "category_name": "Fletes y Movilidad", "price": Decimal("65.00"), "unit": "viaje", "desc": "Traslado rápido de muebles, materiales de construcción y compras pesadas dentro de Arequipa metropolitana."},
    {"index": 11, "user_index": 13, "title": "Revisión de Tableros Eléctricos y Cableado Oculto", "category_name": "Electricidad y Cableado", "price": Decimal("75.00"), "unit": "servicio", "desc": "Detección de sobrecargas, puesta a tierra, balanceo de fases y protección contra descargas para viviendas y talleres."},
    {"index": 12, "user_index": 14, "title": "Desatoro Mecánico de Tuberías y Desagües", "category_name": "Gasfitería y Plomería", "price": Decimal("55.00"), "unit": "servicio", "desc": "Desatoros de cajas de registro, bajadas de lluvia, lavaderos y reparación de inodoros empotrados."},
    # Cercado de Arequipa
    {"index": 13, "user_index": 16, "title": "Confección e Instalación de Repisas y Muebles de Melamina", "category_name": "Carpintería y Muebles", "price": Decimal("110.00"), "unit": "mueble", "desc": "Optimización de espacios con repisas flotantes, alacenas y escritorios resistentes a la humedad."},
    {"index": 14, "user_index": 17, "title": "Lavado al Seco de Muebles y Tapicería", "category_name": "Limpieza y Hogar", "price": Decimal("80.00"), "unit": "juego", "desc": "Extracción profunda de ácaros y manchas en sillones, colchones y sillas de comedor con secado rápido."},
    {"index": 15, "user_index": 18, "title": "Manicure y Pedicure Spa con Esmaltado Permanente", "category_name": "Belleza y Cuidado Personal", "price": Decimal("40.00"), "unit": "sesión", "desc": "Exfoliación, hidratación profunda y esmaltado en gel de larga duración con esterilización estricta de implementos."},
    {"index": 16, "user_index": 19, "title": "Formateo e Instalación de Software Libre y Ofimática", "category_name": "Reparación de Computadoras", "price": Decimal("50.00"), "unit": "servicio", "desc": "Instalación de sistemas operativos, drivers oficiales, programas de oficina y respaldo seguro de documentos."},
    # José Luis Bustamante y Rivero
    {"index": 17, "user_index": 21, "title": "Refuerzo Escolar en Comunicación y Comprensión Lectora", "category_name": "Clases y Apoyo Escolar", "price": Decimal("25.00"), "unit": "hora", "desc": "Técnicas de estudio, redacción de ensayos, ortografía y preparación para evaluaciones académicas escolares."},
    {"index": 18, "user_index": 22, "title": "Mantenimiento y Recuperación de Césped Natural", "category_name": "Jardinería y Poda", "price": Decimal("45.00"), "unit": "hora", "desc": "Nivelación de terreno, resiembra de pasto, aireación de tierra y fertilización balanceada para jardines."},
    {"index": 19, "user_index": 23, "title": "Tarrajeo Fino y Reparación de Humedades en Paredes", "category_name": "Albañilería y Pintura", "price": Decimal("140.00"), "unit": "ambiente", "desc": "Tratamiento contra el salitre, enlucido de yeso o cemento y sellado antihumedad garantizado."},
    {"index": 20, "user_index": 24, "title": "Traslado Seguro de Enseres y Mudanzas Pequeñas", "category_name": "Fletes y Movilidad", "price": Decimal("85.00"), "unit": "viaje", "desc": "Servicio de flete con apoyo de estiba cuidadosa, mantas protectoras y sogas de amarre seguro."},
]

# ----------------------------------------------------------------------
# 20 PRODUCTOS DISTRIBUIDOS (4 POR ZONA)
# ----------------------------------------------------------------------
PRODUCTS_AREQUIPA = [
    # Cayma
    {"index": 1, "user_index": 1, "name": "Pan de Tres Puntas Tradicional de Horno de Leña", "category_name": "Panadería y Masas", "price": Decimal("9.00"), "stock": 25, "desc": "Bolsa de 6 panes tradicionales arequipeños de corteza crujiente recién salidos del horno artesanal."},
    {"index": 2, "user_index": 2, "name": "Pastel de Papa Arequipeño Artesanal", "category_name": "Comida Casera y Menú", "price": Decimal("28.00"), "stock": 10, "desc": "Porción familiar elaborada con papa blanca seleccionada, queso paria fresco de Majes y rocoto picado."},
    {"index": 3, "user_index": 3, "name": "Queso Paria Artesanal Pasteurizado de Valle del Colca", "category_name": "Productos Naturales", "price": Decimal("26.00"), "stock": 15, "desc": "Molde de 1 kg de queso tradicional madurado, ideal para ensaladas, tequeños y pastel de papa."},
    {"index": 4, "user_index": 4, "name": "Miel Pura de Abeja de Valle de Vítor", "category_name": "Productos Naturales", "price": Decimal("30.00"), "stock": 20, "desc": "Frasco de 600g de miel 100% pura cosechada en apiarios locales sin aditivos ni preservantes."},
    # Yanahuara
    {"index": 5, "user_index": 6, "name": "Empanadas de Queso y Rocoto Relleno Horneadas", "category_name": "Panadería y Masas", "price": Decimal("22.00"), "stock": 18, "desc": "Caja de 6 empanadas con masa hojaldrada crujiente rellenas de picadillo criollo de carne y queso fundido."},
    {"index": 6, "user_index": 7, "name": "Polos de Algodón Peruano con Diseños de Arequipa", "category_name": "Artesanía y Confección", "price": Decimal("45.00"), "stock": 30, "desc": "Polos unisex de punto fino con estampados artísticos del volcán Misti y el sillar arequipeño."},
    {"index": 7, "user_index": 8, "name": "Chompas Tejidas en Lana de Alpaca para Invierno", "category_name": "Artesanía y Confección", "price": Decimal("95.00"), "stock": 12, "desc": "Prenda abrigadora elaborada por artesanas locales con lana suave de alpaca en tonos naturales."},
    {"index": 8, "user_index": 9, "name": "Cargador Rápido de 65W GaN Tipo C", "category_name": "Tecnología y Accesorios", "price": Decimal("52.00"), "stock": 16, "desc": "Adaptador universal compacto compatible con teléfonos inteligentes, tabletas y laptops modernas."},
    # Cerro Colorado
    {"index": 9, "user_index": 11, "name": "Auriculares Inalámbricos con Cancelación de Ruido", "category_name": "Tecnología y Accesorios", "price": Decimal("68.00"), "stock": 14, "desc": "Sonido estéreo de alta fidelidad, micrófono para llamadas y estuche con carga para 20 horas de uso."},
    {"index": 10, "user_index": 12, "name": "Canasta Semanal de Frutas y Verduras de Campiña", "category_name": "Verduras, Frutas y Abarrotes", "price": Decimal("38.00"), "stock": 15, "desc": "Papas de variedad única, cebolla arequipeña, ajos de Tiabaya, paltas y naranjas recién cosechadas."},
    {"index": 11, "user_index": 13, "name": "Juego de Sábanas de 2 Plazas de Algodón Suave", "category_name": "Artículos para el Hogar", "price": Decimal("65.00"), "stock": 12, "desc": "Incluye sábana plana, bajera elastizada y fundas a juego con costuras reforzadas para uso diario."},
    {"index": 12, "user_index": 14, "name": "Pack de Canastas Organizadoras para Despensa y Baño", "category_name": "Artículos para el Hogar", "price": Decimal("26.00"), "stock": 22, "desc": "Set de 3 organizadores plásticos resistentes para mantener el orden en armarios y repisas."},
    # Cercado de Arequipa
    {"index": 13, "user_index": 16, "name": "Lámpara LED Regulable para Estudio y Lectura", "category_name": "Artículos para el Hogar", "price": Decimal("36.00"), "stock": 18, "desc": "Brazo flexible, tres niveles de luz cálida y blanca, con alimentación por cable USB o batería interna."},
    {"index": 14, "user_index": 17, "name": "Pack Escolar de Cuadernos Cuadriculados y Lapiceros", "category_name": "Útiles Escolares", "price": Decimal("28.00"), "stock": 35, "desc": "Cuatro cuadernos empastados de 100 hojas, juego de lapiceros de tinta seca, regla y borrador."},
    {"index": 15, "user_index": 18, "name": "Estuche de Colores y Plumones Escolares Lavables", "category_name": "Útiles Escolares", "price": Decimal("24.00"), "stock": 25, "desc": "Caja de 24 lápices de colores triangulares de mina resistente y 12 marcadores de punta media."},
    {"index": 16, "user_index": 19, "name": "Mochila Ergonómica Escolar con Espaldar Acolchado", "category_name": "Útiles Escolares", "price": Decimal("58.00"), "stock": 15, "desc": "Mochila juvenil reforzada con bolsillos laterales para tomatodo y compartimento para carpetas."},
    # José Luis Bustamante y Rivero
    {"index": 17, "user_index": 21, "name": "Jabones Artesanales de Manzanilla y Avena Andina", "category_name": "Productos Naturales", "price": Decimal("14.00"), "stock": 30, "desc": "Barra de jabón vegetal hidratante elaborado con aceites naturales para el cuidado de pieles delicadas."},
    {"index": 18, "user_index": 22, "name": "Infusiones Naturales de Muña, Chachacoma y Cedrón", "category_name": "Productos Naturales", "price": Decimal("16.00"), "stock": 25, "desc": "Caja de 25 filtrantes con hierbas digestivas recolectadas en las faldas de la cordillera volcánica."},
    {"index": 19, "user_index": 23, "name": "Detergente Ecológico Biodegradable para Ropa Blanca y Color", "category_name": "Limpieza y Aseo Personal", "price": Decimal("32.00"), "stock": 20, "desc": "Galón de 4 litros con extractos cítricos naturales que cuidan las fibras y son gentiles con el ambiente."},
    {"index": 20, "user_index": 24, "name": "Velas Aromáticas con Fragancia de Canela y Flores del Valle", "category_name": "Otros Productos del Barrio", "price": Decimal("19.00"), "stock": 18, "desc": "Vela en vaso de vidrio reutilizable con cera vegetal de combustión limpia y aroma relajante."},
]

# ----------------------------------------------------------------------
# 20 SOLICITUDES Y OFRECIMIENTOS SOLIDARIOS (4 POR ZONA)
# ----------------------------------------------------------------------
SOLIDARITY_AREQUIPA = [
    # Cayma
    {"index": 1, "user_index": 1, "title": "Víveres no perecibles para ollita común del sector alto", "category": "Alimentos", "post_type": "request", "status": "open", "desc": "Solicitamos arroz, azúcar, menestras y fideos para apoyar en el almuerzo diario de familias vecinas vulnerables."},
    {"index": 2, "user_index": 2, "title": "Donación de verduras y hortalizas cosechadas en huerto familiar", "category": "Alimentos", "post_type": "donation", "status": "open", "desc": "Tenemos cuatro canastas con acelgas, lechugas y zanahorias frescas disponibles para quienes lo necesiten."},
    {"index": 3, "user_index": 3, "title": "Ropa abrigadora y casacas para niños de primaria", "category": "Ropa", "post_type": "request", "status": "in_progress", "desc": "Buscamos prendas de abrigo en buen estado para dos hermanitos de 6 y 9 años ante las bajas temperaturas."},
    {"index": 4, "user_index": 4, "title": "Donación de frazadas y mantas polares para adultos mayores", "category": "Ropa", "post_type": "donation", "status": "open", "desc": "Disponemos de seis mantas limpias listas para entregar a vecinos adultos mayores que requieran abrigo."},
    # Yanahuara
    {"index": 5, "user_index": 6, "title": "Se requiere jarabe de paracetamol y antialérgico pediátrico", "category": "Medicamentos", "post_type": "request", "status": "open", "desc": "Apoyo con medicamentos básicos con precinto de seguridad para botiquín de primeros auxilios del sector."},
    {"index": 6, "user_index": 7, "title": "Préstamo temporal de tensiómetro digital para control médico", "category": "Medicamentos", "post_type": "request", "status": "in_progress", "desc": "Solicitamos el préstamo por cuatro días para monitorear la presión de una vecina en recuperación postoperatoria."},
    {"index": 7, "user_index": 8, "title": "Voluntarios para apoyo en tareas escolares los sábados", "category": "Apoyo escolar", "post_type": "request", "status": "open", "desc": "Convocamos a estudiantes o docentes del barrio para dictar dos horas de refuerzo de lectura y números a niños."},
    {"index": 8, "user_index": 9, "title": "Donación de enciclopedias y textos escolares para biblioteca comunal", "category": "Apoyo escolar", "post_type": "donation", "status": "open", "desc": "Entregamos un lote de libros de consulta escolar en excelente estado para el salón comunal de la zona."},
    # Cerro Colorado
    {"index": 9, "user_index": 11, "title": "Apoyo con movilidad para traslado de vecina a centro de salud", "category": "Transporte", "post_type": "request", "status": "open", "desc": "Necesitamos apoyo con vehículo particular para trasladar a vecina con muletas a su terapia física programada."},
    {"index": 10, "user_index": 12, "title": "Ofrezco traslado solidario para citas médicas los domingos", "category": "Transporte", "post_type": "offer", "status": "open", "desc": "Pongo a disposición mi automóvil en horario matutino para trámites de salud de adultos mayores del barrio."},
    {"index": 11, "user_index": 13, "title": "Donación de andador ortopédico y bastón regulable", "category": "Donaciones", "post_type": "donation", "status": "open", "desc": "Implementos ortopédicos limpios y operativos disponibles para quien se encuentre en rehabilitación."},
    {"index": 12, "user_index": 14, "title": "Se solicita silla de ruedas en préstamo para paciente convaleciente", "category": "Donaciones", "post_type": "request", "status": "in_progress", "desc": "Buscamos silla de ruedas durante dos semanas mientras dura la recuperación de fractura de un vecino."},
    # Cercado de Arequipa
    {"index": 13, "user_index": 16, "title": "Préstamo de escalera telescópica y taladro para faena barrial", "category": "Herramientas", "post_type": "request", "status": "open", "desc": "Requerimos herramientas para colocar luminarias LED en el pasaje peatonal durante el fin de semana."},
    {"index": 14, "user_index": 17, "title": "Ofrecimiento de herramientas manuales para reparaciones del pasaje", "category": "Herramientas", "post_type": "offer", "status": "open", "desc": "Tengo juego de llaves, martillo y nivel de mano para prestar a vecinos que hagan arreglos en sus casas."},
    {"index": 15, "user_index": 18, "title": "Pañales para adulto mayor y toallitas húmedas para familia vecina", "category": "Apoyo comunitario", "post_type": "request", "status": "open", "desc": "Apoyo solidario con insumos de higiene para abuelita de escasos recursos económicos de nuestra cuadra."},
    {"index": 16, "user_index": 19, "title": "Donación de ropa de cama y sábanas limpias para albergue", "category": "Apoyo comunitario", "post_type": "donation", "status": "open", "desc": "Disponemos de cuatro juegos completos de sábanas limpias y planchadas para familias damnificadas."},
    # José Luis Bustamante y Rivero
    {"index": 17, "user_index": 21, "title": "Taller gratuito de alfabetización digital básica para adultos mayores", "category": "Apoyo escolar", "post_type": "offer", "status": "open", "desc": "Enseño a utilizar WhatsApp, llamadas de emergencia y videollamadas a vecinos mayores en el parque."},
    {"index": 18, "user_index": 22, "title": "Donación de gasas estériles, vendas elásticas y alcohol de 70°", "category": "Medicamentos", "post_type": "donation", "status": "closed", "desc": "Insumos entregados satisfactoriamente para la atención de primeros auxilios del comité vecinal."},
    {"index": 19, "user_index": 23, "title": "Convocatoria para faena de barrido y jardinería en el parque", "category": "Apoyo comunitario", "post_type": "request", "status": "closed", "desc": "Jornada de limpieza culminada exitosamente con la participación entusiasta de veinte vecinos."},
    {"index": 20, "user_index": 24, "title": "Traslado solidario de donaciones hacia albergue infantil", "category": "Transporte", "post_type": "request", "status": "closed", "desc": "Carga de víveres y libros entregada en su destino gracias a la coordinación de la red comunitaria."},
]

# ----------------------------------------------------------------------
# 20 EMERGENCIAS SINTÉTICAS (4 POR ZONA)
# ----------------------------------------------------------------------
EMERGENCIES_AREQUIPA = [
    # Cayma
    {"index": 1, "user_index": 1, "title": "Fuga de gas licuado en cocina del segundo piso", "type": "fuga_gas", "severity": "CRITICAL", "status": "active", "desc": "Olor persistente a gas en el pasaje peatonal. Se pide apoyo a serenazgo y bomberos para verificar balones."},
    {"index": 2, "user_index": 2, "title": "Descompensación repentina de adulto mayor en vereda", "type": "medica", "severity": "CRITICAL", "status": "in_progress", "desc": "Persona mayor sentada con mareos y dificultad respiratoria. Se requiere presencia de paramédicos de posta cercana."},
    {"index": 3, "user_index": 3, "title": "Rotura de tubería de agua potable con anegamiento de vía", "type": "infraestructura", "severity": "HIGH", "status": "active", "desc": "Caudal abundante de agua potable saliendo de vereda hacia la pista principal. Se coordina cierre de válvula general."},
    {"index": 4, "user_index": 4, "title": "Vehículo sospechoso rondando las viviendas sin placa visible", "type": "seguridad", "severity": "MEDIUM", "status": "reported", "desc": "Auto oscuro estacionado reiteradas veces frente a cocheras residenciales. Vecinos en alerta comunitaria preventiva."},
    # Yanahuara
    {"index": 5, "user_index": 6, "title": "Chispas y recalentamiento en cableado aéreo de poste", "type": "electricidad", "severity": "CRITICAL", "status": "active", "desc": "Cortocircuito en cables de media tensión frente a viviendas coloniales. Riesgo de caída de líneas de energía."},
    {"index": 6, "user_index": 7, "title": "Cilindro de gas doméstico con fuga en válvula de alivio", "type": "fuga_gas", "severity": "CRITICAL", "status": "active", "desc": "Escape continuo de gas en patio posterior de vivienda. Se evacuó temporalmente a los residentes contiguos."},
    {"index": 7, "user_index": 8, "title": "Muro perimétrico de sillar con desprendimiento parcial de piedras", "type": "infraestructura", "severity": "HIGH", "status": "active", "desc": "Pared antigua con grieta visible desprendiendo cascote hacia la vereda peatonal tras paso de vehículo pesado."},
    {"index": 8, "user_index": 9, "title": "Perro comunitario herido tras ser atropellado por moto", "type": "rescate_animal", "severity": "MEDIUM", "status": "active", "desc": "Mascota echada en la esquina con dificultad para pararse. Se solicita apoyo de veterinario o rescatista de la zona."},
    # Cerro Colorado
    {"index": 9, "user_index": 11, "title": "Fuego en pastizal seco cercano a almacén de reciclaje", "type": "incendio", "severity": "CRITICAL", "status": "active", "desc": "Llamas de mediana altura alimentadas por el viento de la tarde amenazando construcciones de drywall vecinas."},
    {"index": 10, "user_index": 12, "title": "Caída de persona desde escalera en obra doméstica menor", "type": "medica", "severity": "CRITICAL", "status": "active", "desc": "Albañil presenta golpe fuerte en pierna tras resbalar de dos metros de altura. Se pide ambulancia inmediata."},
    {"index": 11, "user_index": 13, "title": "Poste de alumbrado público quebrado en su base", "type": "infraestructura", "severity": "HIGH", "status": "active", "desc": "Camión de reparto impactó levemente contra el poste de concreto dejándolo sostenido por el cableado."},
    {"index": 12, "user_index": 14, "title": "Arrebato de pertenencias reportado cerca al paradero", "type": "seguridad", "severity": "HIGH", "status": "reported", "desc": "Dos sujetos en motocicleta arrebataron teléfono a estudiante y huyeron con dirección a la variante."},
    # Cercado de Arequipa
    {"index": 13, "user_index": 16, "title": "Humo denso saliendo por ventana de oficina en casona", "type": "incendio", "severity": "CRITICAL", "status": "active", "desc": "Principio de incendio presumiblemente por electrodoméstico conectado. Sirena comunal activada en la cuadra."},
    {"index": 14, "user_index": 17, "title": "Olor penetrante a gas en callejón tradicional del centro", "type": "fuga_gas", "severity": "HIGH", "status": "active", "desc": "Vecinos perciben olor a combustible en pasaje peatonal estrecho sin ventilación directa. Se inspecciona acometida."},
    {"index": 15, "user_index": 18, "title": "Buzón de alcantarillado sin tapa en cruce peatonal escolar", "type": "infraestructura", "severity": "HIGH", "status": "active", "desc": "Abertura peligrosa de más de un metro de profundidad en zona de alto tránsito de niños y escolares."},
    {"index": 16, "user_index": 19, "title": "Alarma de sensor perimétrico sonando de manera continua", "type": "seguridad", "severity": "LOW", "status": "resolved", "desc": "Falla de batería en sensor de puerta de local comercial. Propietario acudió y normalizó el sistema."},
    # José Luis Bustamante y Rivero
    {"index": 17, "user_index": 21, "title": "Accidente vehicular con motociclista tendido sobre el asfalto", "type": "medica", "severity": "CRITICAL", "status": "active", "desc": "Colisión leve entre mototaxi y moto lineal en esquina sin semáforo. Conductor consciente pero con dolor dorsal."},
    {"index": 18, "user_index": 22, "title": "Cables eléctricos sueltos colgando a la altura de los peatones", "type": "electricidad", "severity": "HIGH", "status": "active", "desc": "Línea de acometida descolgada rozando techos de calaminas con presencia de llovizna intermitente."},
    {"index": 19, "user_index": 23, "title": "Gatito atrapado en copa de árbol de más de seis metros", "type": "rescate_animal", "severity": "MEDIUM", "status": "active", "desc": "Mascota asustada por ladridos de perros maullando desde la mañana sin poder descender por sus medios."},
    {"index": 20, "user_index": 24, "title": "Restos de desmonte y poda abandonados bloqueando rampa", "type": "servicios_publicos", "severity": "LOW", "status": "reported", "desc": "Sacos con tierra y ramas secas depositados sobre la rampa de acceso a personas con discapacidad en la esquina."},
]


# ----------------------------------------------------------------------
# LÓGICA DEL SEEDER: LIMPIEZA, ESTRUCTURACIÓN Y SIEMBRA
# ----------------------------------------------------------------------
async def inspect_and_backup(session) -> Dict[str, Any]:
    """Genera inventario detallado y archivo de respaldo de datos anteriores."""
    # Servicios demo
    all_svc = (await session.execute(select(Service))).scalars().all()
    demo_svc = [s for s in all_svc if s.id in [get_demo_uuid("service", i) for i in range(1, 40)] or "(Demo)" in (s.title or "")]

    # Productos demo
    all_prod = (await session.execute(select(Product))).scalars().all()
    demo_prod = [p for p in all_prod if p.id in [get_demo_uuid("product", i) for i in range(1, 40)] or "(Demo)" in (p.name or "")]

    # Solidaridad demo
    all_sol = (await session.execute(select(SolidarityPost))).scalars().all()
    demo_sol = [s for s in all_sol if s.id in [get_demo_uuid("solidarity", i) for i in range(1, 40)] or "(Demo)" in (s.title or "")]

    # Emergencias demo
    all_emg = (await session.execute(select(Emergency))).scalars().all()
    demo_emg = [
        e for e in all_emg
        if e.id in [get_demo_uuid("emergency", i) for i in range(1, 40)]
        or "[DEMO]" in (e.title or "")
        or "(Demo)" in (e.title or "")
        or "Manzana 2" in (e.title or "")
    ]

    # Reseñas demo
    all_rev = (await session.execute(select(Review))).scalars().all()
    demo_rev = [r for r in all_rev if r.id in [get_demo_uuid("review", i) for i in range(1, 60)]]

    # Comercios demo
    all_biz = (await session.execute(select(Business))).scalars().all()
    demo_biz = [b for b in all_biz if b.id in [get_demo_uuid("business", i) for i in range(1, 40)] or "(Demo)" in (b.business_name or "")]

    # Direcciones demo
    all_addr = (await session.execute(select(Address))).scalars().all()
    demo_addr = [
        a for a in all_addr
        if a.id in [get_demo_uuid("address", i) for i in range(1, 60)]
        or "(Demo" in (a.street_address or "")
        or "demostración" in (a.reference or "")
    ]

    backup_data = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "services": [{"id": str(s.id), "title": s.title} for s in demo_svc],
        "products": [{"id": str(p.id), "name": p.name} for p in demo_prod],
        "solidarity": [{"id": str(s.id), "title": s.title} for s in demo_sol],
        "emergencies": [{"id": str(e.id), "title": e.title} for e in demo_emg],
        "reviews": [{"id": str(r.id), "rating": r.rating} for r in demo_rev],
        "businesses": [{"id": str(b.id), "business_name": b.business_name} for b in demo_biz],
        "addresses": [{"id": str(a.id), "street_address": a.street_address} for a in demo_addr],
    }

    backup_path = "/home/tefa/hack/back/scripts/backup_demo_data_before_cleanup.json"
    with open(backup_path, "w", encoding="utf-8") as f:
        json.dump(backup_data, f, indent=2, ensure_ascii=False)

    return {
        "services_count": len(demo_svc),
        "products_count": len(demo_prod),
        "solidarity_count": len(demo_sol),
        "emergencies_count": len(demo_emg),
        "reviews_count": len(demo_rev),
        "businesses_count": len(demo_biz),
        "addresses_count": len(demo_addr),
        "backup_path": backup_path,
        "demo_svc_ids": [s.id for s in demo_svc],
        "demo_prod_ids": [p.id for p in demo_prod],
        "demo_sol_ids": [s.id for s in demo_sol],
        "demo_emg_ids": [e.id for e in demo_emg],
        "demo_rev_ids": [r.id for r in demo_rev],
        "demo_biz_ids": [b.id for b in demo_biz],
        "demo_addr_ids": [a.id for a in demo_addr],
    }


async def run_clean_and_seed(execute: bool = False):
    """Ejecuta el ciclo de vida completo de siembra para Arequipa."""
    print("=" * 75)
    print("VECIRED IA — RECONSTRUCCIÓN DE DATOS DE DEMOSTRACIÓN EN AREQUIPA")
    print(f"Modo de ejecución: {'EJECUCIÓN REAL (--execute)' if execute else 'SIMULACIÓN SEGURA (DRY-RUN)'}")
    print("=" * 75)

    factory = get_session_factory()
    async with factory() as session:
        # PASO 1: Inventario y respaldo de datos anteriores
        print("\n1. Generando inventario de registros sintéticos anteriores y respaldo...")
        inv = await inspect_and_backup(session)

        print(f"   • Servicios demo anteriores a eliminar:       {inv['services_count']}")
        print(f"   • Productos demo anteriores a eliminar:       {inv['products_count']}")
        print(f"   • Publicaciones solidarias a eliminar:        {inv['solidarity_count']}")
        print(f"   • Emergencias sintéticas a eliminar:          {inv['emergencies_count']}")
        print(f"   • Reseñas sintéticas anteriores a eliminar:   {inv['reviews_count']}")
        print(f"   • Comercios de prueba anteriores a eliminar:  {inv['businesses_count']}")
        print(f"   • Direcciones de prueba a actualizar/limpiar: {inv['addresses_count']}")
        print(f"   ✓ Respaldo de seguridad guardado en: {inv['backup_path']}")

        if not execute:
            print("\n[MODO SIMULACIÓN] No se aplicaron cambios destructivos ni inserciones en la base de datos.")
            print("Para aplicar la reconstrucción completa en Supabase, ejecute:")
            print("  python scripts/seed_demo_data.py --execute")
            return

        # PASO 2: Eliminación selectiva de registros demo anteriores
        print("\n2. Ejecutando limpieza segura de registros sintéticos...")

        # A. Reseñas demo anteriores
        if inv["demo_rev_ids"]:
            await session.execute(delete(Review).where(Review.id.in_(inv["demo_rev_ids"])))

        # B. Servicios demo anteriores
        if inv["demo_svc_ids"]:
            await session.execute(delete(Service).where(Service.id.in_(inv["demo_svc_ids"])))

        # C. Productos demo anteriores
        if inv["demo_prod_ids"]:
            await session.execute(delete(Product).where(Product.id.in_(inv["demo_prod_ids"])))

        # D. Solidaridad demo anterior
        if inv["demo_sol_ids"]:
            await session.execute(delete(SolidarityPost).where(SolidarityPost.id.in_(inv["demo_sol_ids"])))

        # E. Emergencias demo anteriores
        if inv["demo_emg_ids"]:
            await session.execute(delete(Emergency).where(Emergency.id.in_(inv["demo_emg_ids"])))

        # F. Comercios demo anteriores
        if inv["demo_biz_ids"]:
            await session.execute(delete(Business).where(Business.id.in_(inv["demo_biz_ids"])))

        # G. Direcciones demo anteriores
        if inv["demo_addr_ids"]:
            await session.execute(delete(UserAddress).where(UserAddress.address_id.in_(inv["demo_addr_ids"])))
            await session.execute(delete(Address).where(Address.id.in_(inv["demo_addr_ids"])))

        await session.flush()
        print("   ✓ Registros anteriores eliminados sin afectar a ningún usuario real.")

        # PASO 3: Asegurar estructura geográfica de Arequipa (Departamento, Provincia, Distritos)
        print("\n3. Configurando cartografía oficial de Arequipa...")

        # Departamento
        dep_data = AREQUIPA_GEO_CONFIG["department"]
        await session.execute(
            text("""
                INSERT INTO public.departments (id, name, ubigeo)
                VALUES (:id, :name, :ubigeo)
                ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, ubigeo = EXCLUDED.ubigeo
            """),
            dep_data
        )

        # Provincia
        prov_data = AREQUIPA_GEO_CONFIG["province"]
        await session.execute(
            text("""
                INSERT INTO public.provinces (id, department_id, name, ubigeo)
                VALUES (:id, :department_id, :name, :ubigeo)
                ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, ubigeo = EXCLUDED.ubigeo
            """),
            prov_data
        )

        # Distritos
        for dist in AREQUIPA_GEO_CONFIG["districts"]:
            await session.execute(
                text("""
                    INSERT INTO public.districts (id, province_id, name, ubigeo)
                    VALUES (:id, :province_id, :name, :ubigeo)
                    ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, ubigeo = EXCLUDED.ubigeo
                """),
                {
                    "id": dist["id"],
                    "province_id": dist["province_id"],
                    "name": dist["name"],
                    "ubigeo": dist["ubigeo"],
                }
            )

        # PASO 4: Asegurar Comunidades por Distrito en Arequipa
        communities_map: Dict[int, uuid.UUID] = {}
        for dist in AREQUIPA_GEO_CONFIG["districts"]:
            comm_id = uuid.uuid5(AREQUIPA_NAMESPACE, f"community_{dist['id']}")
            comm_name = f"Comunidad Vecinal {dist['name']}"
            await session.execute(
                text("""
                    INSERT INTO public.communities (id, district_id, name, description, status, created_at)
                    VALUES (:id, :dist_id, :name, :desc, 'active', now())
                    ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, district_id = EXCLUDED.district_id
                """),
                {
                    "id": comm_id,
                    "dist_id": dist["id"],
                    "name": comm_name,
                    "desc": f"Red vecinal organizada del distrito de {dist['name']}, Arequipa",
                }
            )
            communities_map[dist["id"]] = comm_id

        await session.flush()
        print("   ✓ Departamento, provincia, 5 distritos y 5 comunidades configuradas en Arequipa.")

        # PASO 5: Asegurar Categorías de Servicios y Productos
        service_cat_map: Dict[str, uuid.UUID] = {}
        res_scats = await session.execute(select(ServiceCategory))
        for sc in res_scats.scalars().all():
            service_cat_map[sc.name.lower()] = sc.id

        product_cat_map: Dict[str, uuid.UUID] = {}
        res_pcats = await session.execute(select(ProductCategory))
        for pc in res_pcats.scalars().all():
            product_cat_map[pc.name.lower()] = pc.id

        # PASO 6: Crear o Actualizar 25 Perfiles Vecinales de Arequipa (5 por distrito)
        print("\n4. Registrando 25 perfiles vecinales estructurados en Arequipa...")
        dist_centers = {d["id"]: (d["center_lat"], d["center_lon"]) for d in AREQUIPA_GEO_CONFIG["districts"]}

        for neighbor in DEMO_NEIGHBORS_AREQUIPA:
            idx = neighbor["index"]
            u_id = get_aqp_uuid("user", idx)
            email = f"vecino.arequipa.{idx}@vecired.pe"

            # Coordenadas exactas en base al centro de cada distrito
            c_lat, c_lon = dist_centers[neighbor["district_id"]]
            lat, lon = calculate_offset_coords(c_lat, c_lon, neighbor["distance_m"], neighbor["angle"])

            # A. auth.users (mecanismo oficial con fallback idempotente)
            await session.execute(
                text("""
                    INSERT INTO auth.users (id, email, raw_user_meta_data, is_sso_user, is_anonymous, created_at, updated_at)
                    VALUES (:id, :email, :meta, false, false, now(), now())
                    ON CONFLICT (id) DO UPDATE SET
                        email = EXCLUDED.email,
                        raw_user_meta_data = EXCLUDED.raw_user_meta_data,
                        updated_at = now()
                """),
                {
                    "id": u_id,
                    "email": email,
                    "meta": f'{{"full_name": "{neighbor["name"]}", "phone": "{neighbor["phone"]}", "city": "Arequipa"}}',
                }
            )

            # B. public.profiles
            await session.execute(
                text("""
                    INSERT INTO public.profiles (id, full_name, phone, account_status, solidarity_helped_count, solidarity_received_count, created_at)
                    VALUES (:id, :name, :phone, 'active', :helped, 0, now())
                    ON CONFLICT (id) DO UPDATE SET
                        full_name = EXCLUDED.full_name,
                        phone = EXCLUDED.phone,
                        account_status = 'active',
                        solidarity_helped_count = EXCLUDED.solidarity_helped_count
                """),
                {
                    "id": u_id,
                    "name": neighbor["name"],
                    "phone": neighbor["phone"],
                    "helped": neighbor["helped_count"],
                }
            )

            # C. Dirección estructurada en public.addresses
            addr_id = get_aqp_uuid("address", idx)
            full_street = f"{neighbor['street']}, {neighbor['urbanization']}"
            await session.execute(
                text("""
                    INSERT INTO public.addresses (id, district_id, street_address, lot_number, reference, latitude, longitude, created_at)
                    VALUES (:id, :dist_id, :street, :lot, :ref, :lat, :lon, now())
                    ON CONFLICT (id) DO UPDATE SET
                        district_id = EXCLUDED.district_id,
                        street_address = EXCLUDED.street_address,
                        lot_number = EXCLUDED.lot_number,
                        reference = EXCLUDED.reference,
                        latitude = EXCLUDED.latitude,
                        longitude = EXCLUDED.longitude
                """),
                {
                    "id": addr_id,
                    "dist_id": neighbor["district_id"],
                    "street": full_street,
                    "lot": neighbor["lot_number"],
                    "ref": neighbor["reference"],
                    "lat": lat,
                    "lon": lon,
                }
            )

            # D. Vinculación en public.user_addresses (DECLARED, NO VERIFIED)
            u_addr_id = get_aqp_uuid("user_addr", idx)
            await session.execute(
                text("""
                    INSERT INTO public.user_addresses (id, user_id, address_id, address_type, is_primary, source, residence_status, created_at)
                    VALUES (:id, :user_id, :addr_id, 'home', true, 'declared_form', 'declared', now())
                    ON CONFLICT (id) DO UPDATE SET
                        user_id = EXCLUDED.user_id,
                        address_id = EXCLUDED.address_id,
                        is_primary = true,
                        source = 'declared_form',
                        residence_status = 'declared'
                """),
                {
                    "id": u_addr_id,
                    "user_id": u_id,
                    "addr_id": addr_id,
                }
            )

            # E. Membresía comunitaria en el distrito
            cm_id = get_aqp_uuid("comm_mem", idx)
            comm_id = communities_map[neighbor["district_id"]]
            await session.execute(
                text("""
                    INSERT INTO public.community_memberships (id, user_id, community_id, role, membership_status, joined_at)
                    VALUES (:id, :user_id, :comm_id, 'neighbor', 'active', now())
                    ON CONFLICT (id) DO UPDATE SET
                        community_id = EXCLUDED.community_id,
                        membership_status = 'active'
                """),
                {
                    "id": cm_id,
                    "user_id": u_id,
                    "comm_id": comm_id,
                }
            )

            # F. Negocio barrial para propietarios de comercios
            biz_id = get_aqp_uuid("business", idx)
            biz_name = f"Comercial {neighbor['name'].split()[0]}"
            await session.execute(
                text("""
                    INSERT INTO public.businesses (id, owner_id, community_id, address_id, business_name, description, status, created_at)
                    VALUES (:id, :owner_id, :comm_id, :addr_id, :name, :desc, 'active', now())
                    ON CONFLICT (id) DO UPDATE SET
                        owner_id = EXCLUDED.owner_id,
                        community_id = EXCLUDED.community_id,
                        address_id = EXCLUDED.address_id,
                        business_name = EXCLUDED.business_name,
                        status = 'active'
                """),
                {
                    "id": biz_id,
                    "owner_id": u_id,
                    "comm_id": comm_id,
                    "addr_id": addr_id,
                    "name": biz_name,
                    "desc": f"Emprendimiento familiar en {neighbor['urbanization']}, {neighbor['district_name']}",
                }
            )

            print(f"   [{idx}/25] {neighbor['name']} -> {neighbor['district_name']} ({neighbor['urbanization']}) | {int(neighbor['distance_m'])}m")

        await session.flush()

        # PASO 7: Generar exactamente 20 Servicios (4 por zona)
        print("\n5. Registrando 20 Servicios comunitarios de Arequipa...")
        for s in SERVICES_AREQUIPA:
            s_id = get_aqp_uuid("service", s["index"])
            provider_id = get_aqp_uuid("user", s["user_index"])
            addr_id = get_aqp_uuid("address", s["user_index"])
            neighbor = DEMO_NEIGHBORS_AREQUIPA[s["user_index"] - 1]
            comm_id = communities_map[neighbor["district_id"]]
            cat_id = service_cat_map.get(s["category_name"].lower(), list(service_cat_map.values())[0])

            await session.execute(
                text("""
                    INSERT INTO public.services (
                        id, provider_id, category_id, community_id, address_id,
                        title, description, price_from, price_unit, availability, status, created_at
                    )
                    VALUES (
                        :id, :provider_id, :cat_id, :comm_id, :addr_id,
                        :title, :desc, :price, :unit, 'Lunes a Sábado', 'active', now()
                    )
                    ON CONFLICT (id) DO UPDATE SET
                        title = EXCLUDED.title,
                        description = EXCLUDED.description,
                        price_from = EXCLUDED.price_from,
                        price_unit = EXCLUDED.price_unit,
                        status = 'active',
                        address_id = EXCLUDED.address_id,
                        category_id = EXCLUDED.category_id,
                        community_id = EXCLUDED.community_id
                """),
                {
                    "id": s_id,
                    "provider_id": provider_id,
                    "cat_id": cat_id,
                    "comm_id": comm_id,
                    "addr_id": addr_id,
                    "title": s["title"],
                    "desc": s["desc"],
                    "price": s["price"],
                    "unit": s["unit"],
                }
            )
            print(f"   [Servicio {s['index']}/20] {s['title'][:45]}... ({neighbor['district_name']})")

        # PASO 8: Generar exactamente 20 Productos (4 por zona)
        print("\n6. Registrando 20 Productos locales de Arequipa...")
        for p in PRODUCTS_AREQUIPA:
            p_id = get_aqp_uuid("product", p["index"])
            biz_id = get_aqp_uuid("business", p["user_index"])
            neighbor = DEMO_NEIGHBORS_AREQUIPA[p["user_index"] - 1]
            cat_id = product_cat_map.get(p["category_name"].lower(), list(product_cat_map.values())[0])

            await session.execute(
                text("""
                    INSERT INTO public.products (
                        id, business_id, category_id, name, description,
                        price, stock, status, created_at
                    )
                    VALUES (
                        :id, :biz_id, :cat_id, :name, :desc,
                        :price, :stock, 'active', now()
                    )
                    ON CONFLICT (id) DO UPDATE SET
                        name = EXCLUDED.name,
                        description = EXCLUDED.description,
                        price = EXCLUDED.price,
                        stock = EXCLUDED.stock,
                        status = 'active',
                        category_id = EXCLUDED.category_id,
                        business_id = EXCLUDED.business_id
                """),
                {
                    "id": p_id,
                    "biz_id": biz_id,
                    "cat_id": cat_id,
                    "name": p["name"],
                    "desc": p["desc"],
                    "price": p["price"],
                    "stock": p["stock"],
                }
            )
            print(f"   [Producto {p['index']}/20] {p['name'][:45]}... ({neighbor['district_name']})")

        # PASO 9: Generar exactamente 20 Solicitudes Solidarias (4 por zona)
        print("\n7. Registrando 20 Casos y Ofrecimientos Solidarios en Arequipa...")
        for sol in SOLIDARITY_AREQUIPA:
            sol_id = get_aqp_uuid("solidarity", sol["index"])
            author_id = get_aqp_uuid("user", sol["user_index"])
            neighbor = DEMO_NEIGHBORS_AREQUIPA[sol["user_index"] - 1]
            comm_id = communities_map[neighbor["district_id"]]

            await session.execute(
                text("""
                    INSERT INTO public.solidarity_posts (
                        id, author_id, community_id, category, post_type,
                        title, description, status, created_at
                    )
                    VALUES (
                        :id, :author_id, :comm_id, :cat, :post_type,
                        :title, :desc, :status, now()
                    )
                    ON CONFLICT (id) DO UPDATE SET
                        title = EXCLUDED.title,
                        description = EXCLUDED.description,
                        category = EXCLUDED.category,
                        post_type = EXCLUDED.post_type,
                        status = EXCLUDED.status,
                        author_id = EXCLUDED.author_id,
                        community_id = EXCLUDED.community_id
                """),
                {
                    "id": sol_id,
                    "author_id": author_id,
                    "comm_id": comm_id,
                    "cat": sol["category"],
                    "post_type": sol["post_type"],
                    "title": sol["title"],
                    "desc": sol["desc"],
                    "status": sol["status"],
                }
            )
            print(f"   [Solidario {sol['index']}/20] {sol['title'][:45]}... ({neighbor['district_name']})")

        # PASO 10: Generar exactamente 20 Emergencias Sintéticas (4 por zona)
        print("\n8. Registrando 20 Alertas de Emergencia sintéticas en Arequipa...")
        for emg in EMERGENCIES_AREQUIPA:
            emg_id = get_aqp_uuid("emergency", emg["index"])
            reporter_id = get_aqp_uuid("user", emg["user_index"])
            addr_id = get_aqp_uuid("address", emg["user_index"])
            neighbor = DEMO_NEIGHBORS_AREQUIPA[emg["user_index"] - 1]
            comm_id = communities_map[neighbor["district_id"]]

            await session.execute(
                text("""
                    INSERT INTO public.emergencies (
                        id, reported_by, community_id, address_id, emergency_type,
                        title, description, severity, status, occurred_at, created_at
                    )
                    VALUES (
                        :id, :reported_by, :comm_id, :addr_id, :type,
                        :title, :desc, :severity, :status, now(), now()
                    )
                    ON CONFLICT (id) DO UPDATE SET
                        title = EXCLUDED.title,
                        description = EXCLUDED.description,
                        severity = EXCLUDED.severity,
                        status = EXCLUDED.status,
                        emergency_type = EXCLUDED.emergency_type,
                        address_id = EXCLUDED.address_id,
                        reported_by = EXCLUDED.reported_by,
                        community_id = EXCLUDED.community_id
                """),
                {
                    "id": emg_id,
                    "reported_by": reporter_id,
                    "comm_id": comm_id,
                    "addr_id": addr_id,
                    "type": emg["type"],
                    "title": emg["title"],
                    "desc": emg["desc"],
                    "severity": emg["severity"],
                    "status": emg["status"],
                }
            )
            print(f"   [Emergencia {emg['index']}/20] {emg['title'][:45]}... ({emg['severity']} - {neighbor['district_name']})")

        # PASO 11: Asignar Reseñas Sintéticas exclusivamente entre vecinos de Arequipa
        print("\n9. Asignando historial de reseñas verosímiles entre vecinos de Arequipa...")
        reviews_plan = [
            # Cayma
            (2, 1, 2, 5, "Atendió una fuga de agua en la madrugada con mucha amabilidad y rapidez."),
            (3, 1, 3, 5, "Excelente restauración de nuestro comedor de cedro."),
            (3, 4, 3, 5, "Trabajo impecable y muy puntual en la entrega."),
            (4, 1, 4, 5, "Muy detallista con la limpieza de cocina y vidrios altos."),
            (4, 2, 4, 5, "Persona honrada y de confianza en el vecindario."),
            (4, 3, 4, 4, "Buen servicio, llegó a la hora acordada."),
            (5, 1, 5, 5, "Instaló la llave general de la casa con total garantía."),
            # Yanahuara
            (6, 7, 5, 5, "Corte de cabello impecable a domicilio."),
            (7, 8, 6, 5, "Solucionó el problema de mi laptop en el mismo día."),
            (7, 9, 6, 5, "Gran conocimiento técnico y precio justo."),
            (9, 7, 8, 5, "Excelente mantenimiento del jardín, dejó el pasto parejo."),
            (10, 6, 8, 5, "Muy dedicada y atenta con las plantas de sombra."),
            # Cerro Colorado
            (11, 12, 9, 5, "Pintó la sala y fachada sin manchar los zócalos."),
            (13, 14, 11, 5, "Arregló el cortocircuito del taller rápidamente."),
            (13, 15, 11, 5, "Puntual y profesional con los tableros."),
            (14, 11, 12, 5, "Desatoró el desagüe con máquina sin romper nada."),
            # Cercado
            (16, 17, 13, 5, "Instaló los reposteros de melamina con acabados finos."),
            (17, 18, 14, 5, "Lavado de muebles que eliminó manchas difíciles."),
            (17, 19, 14, 5, "Sillones quedaron como nuevos y secaron rápido."),
            (19, 16, 16, 4, "Buena atención al formatear la computadora de estudio."),
            # José Luis Bustamante y Rivero
            (21, 22, 17, 5, "Muy buena profesora de matemática, paciente y clara."),
            (23, 24, 19, 5, "Excelente resane de humedad en los muros del patio."),
            (23, 25, 19, 5, "Acabado liso listo para pintar, muy ordenado."),
            (24, 21, 20, 5, "Traslado de enseres seguro y sin golpes."),
        ]

        for rev_idx, (revd_idx, revr_idx, s_idx, rating, comment) in enumerate(reviews_plan, 1):
            rev_id = get_aqp_uuid("review", rev_idx)
            reviewed_id = get_aqp_uuid("user", revd_idx)
            reviewer_id = get_aqp_uuid("user", revr_idx)
            service_id = get_aqp_uuid("service", s_idx)

            await session.execute(
                text("""
                    INSERT INTO public.reviews (
                        id, reviewer_id, reviewed_user_id, service_id,
                        rating, comment, moderation_status, created_at
                    )
                    VALUES (
                        :id, :reviewer_id, :reviewed_id, :service_id,
                        :rating, :comment, 'approved', now()
                    )
                    ON CONFLICT (id) DO UPDATE SET
                        rating = EXCLUDED.rating,
                        comment = EXCLUDED.comment,
                        moderation_status = 'approved'
                """),
                {
                    "id": rev_id,
                    "reviewer_id": reviewer_id,
                    "reviewed_id": reviewed_id,
                    "service_id": service_id,
                    "rating": rating,
                    "comment": comment,
                }
            )

        await session.commit()

        print("\n" + "=" * 75)
        print("✓ RECONSTRUCCIÓN COMPLETADA EXITOSAMENTE EN AREQUIPA")
        print("=" * 75)
        print("• Perfiles vecinales generados:        25 usuarios (5 por distrito)")
        print("• Grupos geográficos estructurados:    Cayma, Yanahuara, Cerro Colorado, Cercado, JLByR")
        print("• Servicios comunitarios creados:      20 registros (4 por zona)")
        print("• Productos locales creados:           20 registros (4 por zona)")
        print("• Solicitudes solidarias creadas:      20 registros (4 por zona)")
        print("• Emergencias de prueba creadas:       20 alertas (4 por zona)")
        print("• Total de registros generados:        80 registros comunitarios exactos")
        print("• Reseñas aprobadas vinculadas:        24 valoraciones entre vecinos demo")
        print("• Direcciones residenciales:           Estructuradas (declaradas, no verificadas)")
        print("• Integraciones externas:              0 notificaciones disparadas (aislamiento total)")
        print("=" * 75)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seeder de datos de demostración en Arequipa para VeciRed IA.")
    parser.add_argument("--execute", action="store_true", help="Ejecuta la limpieza y creación real en la base de datos.")
    parser.add_argument("--dry-run", action="store_true", help="Modo simulación (comportamiento por defecto).")
    args = parser.parse_args()

    asyncio.run(run_clean_and_seed(execute=args.execute))
