"""
Script de generación automática de datos de demostración para VeciRed IA.
Genera exactamente:
- 20 Servicios en diversas categorías.
- 20 Productos en diversas categorías.
- 20 Solicitudes de ayuda solidaria en diversos estados.
- 10 Emergencias de prueba con severidades CRITICAL, HIGH, MEDIUM y LOW.
Total: 70 registros.

Características:
- Idempotente: utiliza UUIDs deterministas basados en namespace; ejecutarlo varias veces no duplica datos.
- Geolocalización real distribuida: asigna coordenadas exactas alrededor del centro de prueba a 50m, 100m, 200m, 350m, 500m, 700m y 950m.
- Perfiles de vecinos diversos: nuevos sin reseñas, con pocas valoraciones, con buena reputación y con experiencia.
- No modifica usuarios reales ni tablas ajenas.
"""
import asyncio
import math
import os
import sys
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, List, Optional

from sqlalchemy import delete, func, select, text
from sqlalchemy.dialects.postgresql import insert

# Asegurar importaciones del backend
sys.path.insert(0, "/home/tefa/hack/back")
os.chdir("/home/tefa/hack/back")

from app.db.session import get_session_factory
from app.modules.commerce.models import (
    Business,
    Product,
    ProductCategory,
    Service,
    ServiceCategory,
)
from app.modules.emergencies.models import Emergency
from app.modules.geo.models import Address, Community, District
from app.modules.interactions.models import Review
from app.modules.solidarity.models import SolidarityPost
from app.modules.users.models import CommunityMembership, Profile, UserAddress

# Namespace determinista para generar siempre los mismos UUIDs
DEMO_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_DNS, "demo.vecired.pe")

# Centro de referencia para las pruebas de proximidad (Los Olivos / Lima Norte)
CENTER_LAT = -11.9865000
CENTER_LON = -77.0682000


def get_demo_uuid(kind: str, index: int) -> uuid.UUID:
    """Retorna un UUIDv5 determinista para garantizar idempotencia."""
    return uuid.uuid5(DEMO_NAMESPACE, f"{kind}_{index}")


def calculate_coordinates(center_lat: float, center_lon: float, distance_meters: float, angle_degrees: float):
    """Calcula latitud y longitud a una distancia métrica y ángulo específicos."""
    rad = math.radians(angle_degrees)
    # 1 grado latitud ~ 111,139 metros
    # 1 grado longitud a lat -11.98 ~ 108,715 metros
    d_lat = (distance_meters * math.cos(rad)) / 111139.0
    d_lon = (distance_meters * math.sin(rad)) / 108715.0
    return round(center_lat + d_lat, 7), round(center_lon + d_lon, 7)


# ----------------------------------------------------------------------
# DEFINICIÓN DE PERFILES DE VECINOS DE PRUEBA
# ----------------------------------------------------------------------
DEMO_USERS_CONFIG = [
    {
        "index": 1,
        "name": "Carlos Mendoza (Demo)",
        "phone": "+51991111001",
        "distance_m": 50.0,
        "angle": 0.0,
        "street": "Jr. Los Olivos 102 (Demo)",
        "helped_count": 0,
        "is_new": True,
        "profile_type": "Nuevo vecino sin reseñas",
    },
    {
        "index": 2,
        "name": "Elena Ramos (Demo)",
        "phone": "+51991111002",
        "distance_m": 100.0,
        "angle": 45.0,
        "street": "Calle Las Palmeras 210 (Demo)",
        "helped_count": 2,
        "is_new": False,
        "profile_type": "Pocas valoraciones (1 reseña de 5.0)",
    },
    {
        "index": 3,
        "name": "Jorge Quispe (Demo)",
        "phone": "+51991111003",
        "distance_m": 200.0,
        "angle": 90.0,
        "street": "Av. Antúnez de Mayolo 305 (Demo)",
        "helped_count": 4,
        "is_new": False,
        "profile_type": "Buena reputación (3 reseñas, 4.8)",
    },
    {
        "index": 4,
        "name": "Rosa Morales (Demo)",
        "phone": "+51991111004",
        "distance_m": 350.0,
        "angle": 135.0,
        "street": "Pasaje San Martín 140 (Demo)",
        "helped_count": 7,
        "is_new": False,
        "profile_type": "Consolidada con experiencia comprobada (8 reseñas, 4.9)",
    },
    {
        "index": 5,
        "name": "Manuel Valdivia (Demo)",
        "phone": "+51991111005",
        "distance_m": 500.0,
        "angle": 180.0,
        "street": "Jr. Huandoy 512 (Demo)",
        "helped_count": 12,
        "is_new": False,
        "profile_type": "Veterano con alta experiencia (15 reseñas, 5.0)",
    },
    {
        "index": 6,
        "name": "Lucía Fernández (Demo)",
        "phone": "+51991111006",
        "distance_m": 700.0,
        "angle": 225.0,
        "street": "Calle Los Pinos 408 (Demo)",
        "helped_count": 3,
        "is_new": False,
        "profile_type": "Reputación intermedia (2 reseñas, 4.5)",
    },
    {
        "index": 7,
        "name": "Víctor Cárdenas (Demo)",
        "phone": "+51991111007",
        "distance_m": 950.0,
        "angle": 270.0,
        "street": "Av. Carlos Izaguirre 820 (Demo)",
        "helped_count": 22,
        "is_new": False,
        "profile_type": "Líder comunal consolidado a 950m (25 reseñas)",
    },
    {
        "index": 8,
        "name": "Camila Torres (Demo)",
        "phone": "+51991111008",
        "distance_m": 150.0,
        "angle": 315.0,
        "street": "Calle Los Sauces 115 (Demo)",
        "helped_count": 0,
        "is_new": True,
        "profile_type": "Nueva vecina emprendedora (sin reseñas)",
    },
    {
        "index": 9,
        "name": "Raúl Huamán (Demo)",
        "phone": "+51991111009",
        "distance_m": 400.0,
        "angle": 30.0,
        "street": "Jr. Mercurio 230 (Demo)",
        "helped_count": 6,
        "is_new": False,
        "profile_type": "Emprendedor activo (5 reseñas, 4.8)",
    },
    {
        "index": 10,
        "name": "Patricia Benítez (Demo)",
        "phone": "+51991111010",
        "distance_m": 800.0,
        "angle": 210.0,
        "street": "Av. Las Palmeras 910 (Demo)",
        "helped_count": 1,
        "is_new": False,
        "profile_type": "Vecina con 1 reseña (4.0)",
    },
]

# ----------------------------------------------------------------------
# 20 SERVICIOS
# ----------------------------------------------------------------------
SERVICES_DATA = [
    {
        "index": 1,
        "title": "Instalación y Mantenimiento Eléctrico Domiciliario (Demo)",
        "category_slug": "electricidad",
        "category_name": "Electricidad y Cableado",
        "category_icon": "flash",
        "user_index": 1,  # 50m
        "price_from": Decimal("60.00"),
        "price_unit": "servicio",
        "description": "Instalación de tomacorrientes, llaves térmicas y detección de fugas eléctricas en el hogar.",
    },
    {
        "index": 2,
        "title": "Reparación Urgente de Fugas y Tuberías (Demo)",
        "category_slug": "gasfiteria",
        "category_name": "Gasfitería y Plomería",
        "category_icon": "wrench",
        "user_index": 2,  # 100m
        "price_from": Decimal("50.00"),
        "price_unit": "visita",
        "description": "Atención rápida a fugas de agua, cambio de griferías, desatoro de cañerías y sanitarios.",
    },
    {
        "index": 3,
        "title": "Carpintería y Restauración de Muebles de Madera (Demo)",
        "category_slug": "carpinteria",
        "category_name": "Carpintería y Muebles",
        "category_icon": "saw",
        "user_index": 3,  # 200m
        "price_from": Decimal("80.00"),
        "price_unit": "mueble",
        "description": "Reparación de sillas, mesas, puertas caídas y fabricación de repisas a medida.",
    },
    {
        "index": 4,
        "title": "Limpieza Profunda de Casas y Departamentos (Demo)",
        "category_slug": "limpieza",
        "category_name": "Limpieza y Hogar",
        "category_icon": "broom",
        "user_index": 4,  # 350m
        "price_from": Decimal("45.00"),
        "price_unit": "hora",
        "description": "Servicio de limpieza completa de cocinas, baños, ventanas y pisos con insumos propios.",
    },
    {
        "index": 5,
        "title": "Corte de Cabello y Estilismo a Domicilio (Demo)",
        "category_slug": "belleza",
        "category_name": "Belleza y Cuidado Personal",
        "category_icon": "scissors",
        "user_index": 5,  # 500m
        "price_from": Decimal("35.00"),
        "price_unit": "corte",
        "description": "Corte para damas, caballeros y niños en la comodidad de su hogar con medidas de higiene.",
    },
    {
        "index": 6,
        "title": "Reparación y Mantenimiento de Laptops y PC (Demo)",
        "category_slug": "computadoras",
        "category_name": "Reparación de Computadoras",
        "category_icon": "laptop",
        "user_index": 6,  # 700m
        "price_from": Decimal("70.00"),
        "price_unit": "equipo",
        "description": "Limpieza interna, cambio de pasta térmica, formateo y optimización de computadoras lentas.",
    },
    {
        "index": 7,
        "title": "Clases Particulares de Matemáticas y Física (Demo)",
        "category_slug": "clases",
        "category_name": "Clases y Apoyo Escolar",
        "category_icon": "school",
        "user_index": 7,  # 950m
        "price_from": Decimal("30.00"),
        "price_unit": "hora",
        "description": "Refuerzo escolar para primaria y secundaria en álgebra, geometría y preparación preuniversitaria.",
    },
    {
        "index": 8,
        "title": "Jardinería, Poda y Diseño de Áreas Verdes (Demo)",
        "category_slug": "jardineria",
        "category_name": "Jardinería y Poda",
        "category_icon": "leaf",
        "user_index": 8,  # 150m
        "price_from": Decimal("40.00"),
        "price_unit": "hora",
        "description": "Poda de árboles ornamentales, corte de césped, abono y control ecológico de plagas.",
    },
    {
        "index": 9,
        "title": "Pintura de Fachadas e Interiores Residenciales (Demo)",
        "category_slug": "pintura",
        "category_name": "Albañilería y Pintura",
        "category_icon": "color-fill",
        "user_index": 9,  # 400m
        "price_from": Decimal("120.00"),
        "price_unit": "ambiente",
        "description": "Pintado profesional con látex lavable, empastado de grietas y acabados de primera calidad.",
    },
    {
        "index": 10,
        "title": "Flete y Transporte Vecinal en Furgón Pequeño (Demo)",
        "category_slug": "transporte",
        "category_name": "Fletes y Movilidad",
        "category_icon": "truck",
        "user_index": 10,  # 800m
        "price_from": Decimal("60.00"),
        "price_unit": "viaje",
        "description": "Traslado seguro de compras grandes, electrodomésticos y cajas dentro del distrito.",
    },
    {
        "index": 11,
        "title": "Revisión de Tableros Eléctricos y Cortocircuitos (Demo)",
        "category_slug": "electricidad",
        "category_name": "Electricidad y Cableado",
        "category_icon": "flash",
        "user_index": 1,  # 50m
        "price_from": Decimal("75.00"),
        "price_unit": "servicio",
        "description": "Solución de cortes imprevistos de luz y balanceo de cargas eléctricas en casas de varios pisos.",
    },
    {
        "index": 12,
        "title": "Desatoro de Desagües e Instalación de Grifería (Demo)",
        "category_slug": "gasfiteria",
        "category_name": "Gasfitería y Plomería",
        "category_icon": "wrench",
        "user_index": 2,  # 100m
        "price_from": Decimal("55.00"),
        "price_unit": "servicio",
        "description": "Instalación de duchas, inodoros, trampas de lavadero y desatoros con sonda mecánica.",
    },
    {
        "index": 13,
        "title": "Fabricación de Repisas y Puertas de Madera (Demo)",
        "category_slug": "carpinteria",
        "category_name": "Carpintería y Muebles",
        "category_icon": "saw",
        "user_index": 3,  # 200m
        "price_from": Decimal("110.00"),
        "price_unit": "mueble",
        "description": "Diseño de closets, repisas flotantes en melamina y madera maciza para optimizar espacios.",
    },
    {
        "index": 14,
        "title": "Lavado de Muebles, Colchones y Alfombras (Demo)",
        "category_slug": "limpieza",
        "category_name": "Limpieza y Hogar",
        "category_icon": "broom",
        "user_index": 4,  # 350m
        "price_from": Decimal("85.00"),
        "price_unit": "juego",
        "description": "Lavado al seco y desinfección a vapor contra ácaros y manchas difíciles.",
    },
    {
        "index": 15,
        "title": "Manicure, Pedicure y Tratamientos Faciales (Demo)",
        "category_slug": "belleza",
        "category_name": "Belleza y Cuidado Personal",
        "category_icon": "sparkles",
        "user_index": 5,  # 500m
        "price_from": Decimal("40.00"),
        "price_unit": "sesión",
        "description": "Cuidado de uñas en gel, acrílicas y limpiezas faciales hidratantes con productos de calidad.",
    },
    {
        "index": 16,
        "title": "Formateo e Instalación de Programas y Antivirus (Demo)",
        "category_slug": "computadoras",
        "category_name": "Reparación de Computadoras",
        "category_icon": "laptop",
        "user_index": 6,  # 700m
        "price_from": Decimal("50.00"),
        "price_unit": "servicio",
        "description": "Instalación limpia de Windows, Office, respaldo seguro de archivos y eliminación de malware.",
    },
    {
        "index": 17,
        "title": "Apoyo Escolar en Lectura y Comunicación (Demo)",
        "category_slug": "clases",
        "category_name": "Clases y Apoyo Escolar",
        "category_icon": "school",
        "user_index": 7,  # 950m
        "price_from": Decimal("25.00"),
        "price_unit": "hora",
        "description": "Comprensión lectora, caligrafía, ortografía y desarrollo de habilidades de redacción escolar.",
    },
    {
        "index": 18,
        "title": "Mantenimiento de Césped y Fumigación de Jardín (Demo)",
        "category_slug": "jardineria",
        "category_name": "Jardinería y Poda",
        "category_icon": "leaf",
        "user_index": 8,  # 150m
        "price_from": Decimal("45.00"),
        "price_unit": "hora",
        "description": "Deshierbe, perfilado de bordes, aplicación de abono orgánico y control de hormigas.",
    },
    {
        "index": 19,
        "title": "Tarrajeo, Empastado y Pintado de Paredes (Demo)",
        "category_slug": "pintura",
        "category_name": "Albañilería y Pintura",
        "category_icon": "color-fill",
        "user_index": 9,  # 400m
        "price_from": Decimal("150.00"),
        "price_unit": "ambiente",
        "description": "Arreglo de humedades, resane de muros, tarrajeo fino y acabado liso para pintar.",
    },
    {
        "index": 20,
        "title": "Mudanzas Pequeñas y Traslado de Carga Ligera (Demo)",
        "category_slug": "transporte",
        "category_name": "Fletes y Movilidad",
        "category_icon": "truck",
        "user_index": 10,  # 800m
        "price_from": Decimal("80.00"),
        "price_unit": "viaje",
        "description": "Servicio de mudanza barrial con ayudante para carga y descarga cuidadosa.",
    },
]

# ----------------------------------------------------------------------
# 20 PRODUCTOS
# ----------------------------------------------------------------------
PRODUCTS_DATA = [
    {
        "index": 1,
        "name": "Pan Artesanal de Masa Madre (Demo)",
        "category_name": "Panadería y Masas",
        "price": Decimal("8.50"),
        "user_index": 1,  # 50m
        "stock": 25,
        "description": "Pan campesino de fermentación lenta de 24 horas, corteza crujiente y miga suave.",
    },
    {
        "index": 2,
        "name": "Queque Casero de Plátano y Nuez (Demo)",
        "category_name": "Repostería y Postres",
        "price": Decimal("25.00"),
        "user_index": 2,  # 100m
        "stock": 10,
        "description": "Queque recién horneado con plátanos maduros, nueces picadas y harina integral.",
    },
    {
        "index": 3,
        "name": "Canasta de Verduras y Frutas Frescas (Demo)",
        "category_name": "Verduras, Frutas y Abarrotes",
        "price": Decimal("35.00"),
        "user_index": 3,  # 200m
        "stock": 15,
        "description": "Selección de tomates, lechuga hidropónica, palta fuerte, manzanas y mandarinas.",
    },
    {
        "index": 4,
        "name": "Miel de Abeja 100% Pura de Oxapampa (Demo)",
        "category_name": "Productos Naturales",
        "price": Decimal("28.00"),
        "user_index": 4,  # 350m
        "stock": 20,
        "description": "Frasco de 500g de miel pura de bosque montano, sin azúcares añadidos ni conservantes.",
    },
    {
        "index": 5,
        "name": "Aceite de Oliva Extra Virgen Prensado en Frío (Demo)",
        "category_name": "Productos Naturales",
        "price": Decimal("32.00"),
        "user_index": 5,  # 500m
        "stock": 12,
        "description": "Botella de vidrio oscuro de 500ml originario de Tacna, acidez menor a 0.2%.",
    },
    {
        "index": 6,
        "name": "Polos de Algodón Pima Peruano Cuello Redondo (Demo)",
        "category_name": "Artesanía y Confección",
        "price": Decimal("45.00"),
        "user_index": 6,  # 700m
        "stock": 30,
        "description": "Polos básicos unisex de tacto ultrasuave, no se deforman al lavado. Tallas S, M y L.",
    },
    {
        "index": 7,
        "name": "Casacas Térmicas Impermeables con Capucha (Demo)",
        "category_name": "Artesanía y Confección",
        "price": Decimal("85.00"),
        "user_index": 7,  # 950m
        "stock": 8,
        "description": "Casacas para el frío de invierno con forro polar interior y bolsillos reforzados.",
    },
    {
        "index": 8,
        "name": "Cargador Rápido USB-C 65W GaN (Demo)",
        "category_name": "Tecnología y Accesorios",
        "price": Decimal("49.00"),
        "user_index": 8,  # 150m
        "stock": 18,
        "description": "Cargador compacto para celulares y laptops con protección contra sobrecalentamiento.",
    },
    {
        "index": 9,
        "name": "Auriculares Bluetooth Inalámbricos con Micrófono (Demo)",
        "category_name": "Tecnología y Accesorios",
        "price": Decimal("65.00"),
        "user_index": 9,  # 400m
        "stock": 14,
        "description": "Batería de larga duración de hasta 24 horas con estuche de carga y sonido nítido.",
    },
    {
        "index": 10,
        "name": "Mouse Inalámbrico Ergonómico Silencioso (Demo)",
        "category_name": "Tecnología y Accesorios",
        "price": Decimal("38.00"),
        "user_index": 10,  # 800m
        "stock": 20,
        "description": "Diseño ergonómico para evitar fatiga en la muñeca con conexión 2.4G y Bluetooth.",
    },
    {
        "index": 11,
        "name": "Juego de Sábanas 2 Plazas 100% Algodón (Demo)",
        "category_name": "Artículos para el Hogar",
        "price": Decimal("65.00"),
        "user_index": 1,  # 50m
        "stock": 10,
        "description": "Incluye sábana plana, sábana ajustable y 2 fundas de almohada de 200 hilos.",
    },
    {
        "index": 12,
        "name": "Organizadores de Cocina Multiuso de Acrílico (Demo)",
        "category_name": "Artículos para el Hogar",
        "price": Decimal("24.00"),
        "user_index": 2,  # 100m
        "stock": 25,
        "description": "Caja organizadora transparente ideal para refrigerador, alacena y condimentos.",
    },
    {
        "index": 13,
        "name": "Lámpara LED de Escritorio Recargable con 3 Tonos (Demo)",
        "category_name": "Artículos para el Hogar",
        "price": Decimal("35.00"),
        "user_index": 3,  # 200m
        "stock": 16,
        "description": "Brazo flexible 360°, control táctil de intensidad y batería recargable por USB.",
    },
    {
        "index": 14,
        "name": "Pack de Cuadernos y Útiles Escolares Básicos (Demo)",
        "category_name": "Útiles Escolares",
        "price": Decimal("28.00"),
        "user_index": 4,  # 350m
        "stock": 35,
        "description": "Incluye 4 cuadernos cuadriculados, lapiceros, regla, lápices y borrador.",
    },
    {
        "index": 15,
        "name": "Set de Plumones y Colores Profesionales (Demo)",
        "category_name": "Útiles Escolares",
        "price": Decimal("22.00"),
        "user_index": 5,  # 500m
        "stock": 22,
        "description": "Caja de 24 colores triangulares resistentes y 12 plumones de punta fina lavables.",
    },
    {
        "index": 16,
        "name": "Mochila Escolar Ergonómica Reforzada (Demo)",
        "category_name": "Útiles Escolares",
        "price": Decimal("55.00"),
        "user_index": 6,  # 700m
        "stock": 12,
        "description": "Espaldar acolchado transpirable, compartimento para laptop y costuras dobles.",
    },
    {
        "index": 17,
        "name": "Jabones Artesanales de Avena y Miel de Abeja (Demo)",
        "category_name": "Productos Naturales",
        "price": Decimal("12.00"),
        "user_index": 7,  # 950m
        "stock": 40,
        "description": "Jabón exfoliante suave elaborado a mano sin sulfatos ni parabenos para piel sensible.",
    },
    {
        "index": 18,
        "name": "Infusiones Andinas Orgánicas de Muña y Manzanilla (Demo)",
        "category_name": "Productos Naturales",
        "price": Decimal("15.00"),
        "user_index": 8,  # 150m
        "stock": 30,
        "description": "Caja con 25 pirámides filtrantes con hierbas aromáticas deshidratadas del Cusco.",
    },
    {
        "index": 19,
        "name": "Detergente Ecológico y Suavizante Biodegradable (Demo)",
        "category_name": "Limpieza y Aseo Personal",
        "price": Decimal("30.00"),
        "user_index": 9,  # 400m
        "stock": 15,
        "description": "Galón de 4 litros con aroma a lavanda que protege los tejidos y cuida el agua.",
    },
    {
        "index": 20,
        "name": "Velas Aromáticas de Cera de Soya en Frasco (Demo)",
        "category_name": "Otros Productos del Barrio",
        "price": Decimal("18.00"),
        "user_index": 10,  # 800m
        "stock": 20,
        "description": "Vela aromática de combustión limpia con aceites esenciales de canela y vainilla.",
    },
]

# ----------------------------------------------------------------------
# 20 SOLICITUDES Y OFRECIMIENTOS SOLIDARIOS
# ----------------------------------------------------------------------
SOLIDARITY_DATA = [
    {
        "index": 1,
        "title": "Se solicitan víveres no perecibles para olla común barrial (Demo)",
        "category": "Alimentos",
        "post_type": "request",
        "status": "open",
        "user_index": 1,  # 50m
        "description": "Requerimos arroz, fideos, menestras y conservas para alimentar a 40 familias vulnerables.",
    },
    {
        "index": 2,
        "title": "Donación de canastas de verduras y hortalizas frescas (Demo)",
        "category": "Alimentos",
        "post_type": "donation",
        "status": "open",
        "user_index": 2,  # 100m
        "description": "Tenemos 6 canastas de verduras variadas recolectadas del mercado para compartir.",
    },
    {
        "index": 3,
        "title": "Ropa abrigadora para niños de 4 a 8 años (Demo)",
        "category": "Ropa",
        "post_type": "request",
        "status": "in_progress",
        "user_index": 3,  # 200m
        "description": "Familia vecina recién mudada necesita chompas, casacas y pantalones en buen estado.",
    },
    {
        "index": 4,
        "title": "Donación de casacas y chompas de lana para adultos (Demo)",
        "category": "Ropa",
        "post_type": "donation",
        "status": "open",
        "user_index": 4,  # 350m
        "description": "Lote de 10 abrigos limpios y en perfecto estado listos para quien los necesite.",
    },
    {
        "index": 5,
        "title": "Se necesita jarabe de Paracetamol e Ibuprofeno para posta médica (Demo)",
        "category": "Medicamentos",
        "post_type": "request",
        "status": "open",
        "user_index": 5,  # 500m
        "description": "Apoyo con medicamentos básicos pediátricos con fecha de vencimiento vigente.",
    },
    {
        "index": 6,
        "title": "Préstamo temporal de tensiómetro digital para adulto mayor (Demo)",
        "category": "Medicamentos",
        "post_type": "request",
        "status": "in_progress",
        "user_index": 6,  # 700m
        "description": "Requerimos monitorear la presión arterial de nuestro abuelito durante 5 días.",
    },
    {
        "index": 7,
        "title": "Voluntarios para clases de refuerzo escolar en primaria (Demo)",
        "category": "Apoyo escolar",
        "post_type": "request",
        "status": "open",
        "user_index": 7,  # 950m
        "description": "Buscamos jóvenes o profesores jubilados para apoyar los sábados en matemática y lectura.",
    },
    {
        "index": 8,
        "title": "Donación de libros de texto escolar y cuentos infantiles (Demo)",
        "category": "Apoyo escolar",
        "post_type": "donation",
        "status": "open",
        "user_index": 8,  # 150m
        "description": "Donamos biblioteca escolar para el local comunal con más de 30 libros educativos.",
    },
    {
        "index": 9,
        "title": "Apoyo con movilidad para traslado a cita médica en hospital (Demo)",
        "category": "Transporte",
        "post_type": "request",
        "status": "open",
        "user_index": 9,  # 400m
        "description": "Vecina con dificultad de movilidad requiere traslado ida y vuelta al Hospital Cayetano.",
    },
    {
        "index": 10,
        "title": "Ofrezco movilidad solidaria los domingos por la mañana (Demo)",
        "category": "Transporte",
        "post_type": "offer",
        "status": "open",
        "user_index": 10,  # 800m
        "description": "Pongo a disposición mi vehículo particular para emergencias o trámites de salud vecinales.",
    },
    {
        "index": 11,
        "title": "Donación de coche de bebé y corralito plegable (Demo)",
        "category": "Donaciones",
        "post_type": "donation",
        "status": "open",
        "user_index": 1,  # 50m
        "description": "Cochecito en óptimas condiciones para mamá o papá que lo esté necesitando.",
    },
    {
        "index": 12,
        "title": "Se requiere silla de ruedas en préstamo temporal (Demo)",
        "category": "Donaciones",
        "post_type": "request",
        "status": "in_progress",
        "user_index": 2,  # 100m
        "description": "Para vecina en proceso de rehabilitación de fractura durante 3 semanas.",
    },
    {
        "index": 13,
        "title": "Préstamo de taladro percutor y brocas para faena vecinal (Demo)",
        "category": "Otros",
        "post_type": "request",
        "status": "open",
        "user_index": 3,  # 200m
        "description": "Instalación de cámaras de seguridad vecinales en el pasaje.",
    },
    {
        "index": 14,
        "title": "Intercambio de plantas ornamentales y maceteros reciclados (Demo)",
        "category": "Otros",
        "post_type": "exchange",
        "status": "open",
        "user_index": 4,  # 350m
        "description": "Intercambio esquejes de suculentas y sábila por tierra preparada o macetas.",
    },
    {
        "index": 15,
        "title": "Leche en fórmula y pañales talla M para madre soltera (Demo)",
        "category": "Alimentos",
        "post_type": "request",
        "status": "open",
        "user_index": 5,  # 500m
        "description": "Apoyo solidario urgente para bebé de 6 meses con pañales y suplemento.",
    },
    {
        "index": 16,
        "title": "Donación de frazadas térmicas para familias de zonas altas (Demo)",
        "category": "Ropa",
        "post_type": "donation",
        "status": "open",
        "user_index": 6,  # 700m
        "description": "Disponemos de 8 frazadas tigre limpias para proteger del frío a nuestros vecinos.",
    },
    {
        "index": 17,
        "title": "Clases gratuitas de inglés conversacional para jóvenes (Demo)",
        "category": "Apoyo escolar",
        "post_type": "offer",
        "status": "open",
        "user_index": 7,  # 950m
        "description": "Estudiante universitario ofrece 2 horas semanales de práctica de inglés.",
    },
    {
        "index": 18,
        "title": "Donación de botiquín comunal con gasas, alcohol y vendas (Demo)",
        "category": "Medicamentos",
        "post_type": "donation",
        "status": "closed",
        "user_index": 8,  # 150m
        "description": "Insumos entregados exitosamente a la directiva del comité vecinal.",
    },
    {
        "index": 19,
        "title": "Herramientas de jardinería para limpieza del parque barrial (Demo)",
        "category": "Otros",
        "post_type": "request",
        "status": "closed",
        "user_index": 9,  # 400m
        "description": "Faena comunal concluida con apoyo de rastrillos y tijeras de podar de los vecinos.",
    },
    {
        "index": 20,
        "title": "Traslado de víveres recolectados hacia comedor popular (Demo)",
        "category": "Transporte",
        "post_type": "request",
        "status": "closed",
        "user_index": 10,  # 800m
        "description": "Entrega concluida exitosamente gracias a la solidaridad vecinal.",
    },
]

# ----------------------------------------------------------------------
# 10 EMERGENCIAS DE PRUEBA
# ----------------------------------------------------------------------
EMERGENCIES_DATA = [
    {
        "index": 1,
        "title": "[DEMO] Fuga de gas activa en cocina multifamiliar",
        "emergency_type": "fuga_gas",
        "severity": "CRITICAL",
        "status": "active",
        "user_index": 1,  # 50m
        "description": "Fuerte olor a gas licuado en el primer piso del pasaje. Se solicita apoyo de bomberos y corte de pase.",
    },
    {
        "index": 2,
        "title": "[DEMO] Principio de incendio por cortocircuito en poste eléctrico",
        "emergency_type": "incendio",
        "severity": "CRITICAL",
        "status": "active",
        "user_index": 2,  # 100m
        "description": "Chispas constantes y humo saliendo del cableado aéreo. Vecinos reunidos con extintores PQS.",
    },
    {
        "index": 3,
        "title": "[DEMO] Adulto mayor descompensado requiere primeros auxilios urgente",
        "emergency_type": "medica",
        "severity": "CRITICAL",
        "status": "in_progress",
        "user_index": 3,  # 200m
        "description": "Vecino de 78 años con pérdida momentánea de conciencia. Se requiere personal médico o paramédico.",
    },
    {
        "index": 4,
        "title": "[DEMO] Rotura de tubería matriz e inundación de calle",
        "emergency_type": "infraestructura",
        "severity": "HIGH",
        "status": "active",
        "user_index": 4,  # 350m
        "description": "Fuga de agua potable a alta presión anegando veredas y amenazando con ingresar a las viviendas.",
    },
    {
        "index": 5,
        "title": "[DEMO] Poste de alumbrado inclinado con riesgo de caída",
        "emergency_type": "infraestructura",
        "severity": "HIGH",
        "status": "active",
        "user_index": 5,  # 500m
        "description": "Vehículo pesado rozó el poste dejándolo inclinado sobre el cableado de telecomunicaciones.",
    },
    {
        "index": 6,
        "title": "[DEMO] Intento de robo a transeúnte reportado por vecinos",
        "emergency_type": "seguridad",
        "severity": "HIGH",
        "status": "reported",
        "user_index": 6,  # 700m
        "description": "Dos sujetos sospechosos en moto lineal intentaron arrebatar pertenencias en la esquina del parque.",
    },
    {
        "index": 7,
        "title": "[DEMO] Rama de gran tamaño a punto de caer sobre vereda",
        "emergency_type": "infraestructura",
        "severity": "MEDIUM",
        "status": "active",
        "user_index": 7,  # 950m
        "description": "Árbol ficus con rama partida colgando peligrosamente sobre el paso peatonal escolar.",
    },
    {
        "index": 8,
        "title": "[DEMO] Mascota atrapada en rejilla de canal de desagüe",
        "emergency_type": "rescate_animal",
        "severity": "MEDIUM",
        "status": "active",
        "user_index": 8,  # 150m
        "description": "Perrito comunitario con la pata atascada en el enrejado metálico del parque.",
    },
    {
        "index": 9,
        "title": "[DEMO] Alarma vecinal activada por error técnico",
        "emergency_type": "seguridad",
        "severity": "LOW",
        "status": "resolved",
        "user_index": 9,  # 400m
        "description": "Activación accidental por corte de energía. Situación verificada y normalizada por serenazgo.",
    },
    {
        "index": 10,
        "title": "[DEMO] Acumulación de desmonte en vía pública",
        "emergency_type": "servicios_publicos",
        "severity": "LOW",
        "status": "reported",
        "user_index": 10,  # 800m
        "description": "Sacos de desmonte obstruyendo rampa para personas con discapacidad en la esquina.",
    },
]


async def seed_demo_system():
    """Ejecuta el proceso completo de siembra idempotente de datos demo."""
    print("=" * 70)
    print("VECIRED IA — INICIANDO SEEDER DE DATOS DE DEMOSTRACIÓN")
    print("=" * 70)

    factory = get_session_factory()
    async with factory() as session:
        # 1. Obtener o verificar Comunidad y Distrito de referencia
        res_comm = await session.execute(select(Community).limit(1))
        community = res_comm.scalar_one_or_none()

        if not community:
            print("ERROR: No se encontró ninguna comunidad registrada en la base de datos.")
            return

        community_id = community.id
        district_id = community.district_id
        print(f"Comunidad seleccionada: '{community.name}' (ID: {community_id}, Distrito: {district_id})")

        # 2. Asegurar Categorías de Servicio y Mapeo
        service_cat_map: Dict[str, uuid.UUID] = {}
        res_scats = await session.execute(select(ServiceCategory))
        for sc in res_scats.scalars().all():
            service_cat_map[sc.name.lower()] = sc.id

        # Categorías faltantes a crear si no existen
        required_scats = [
            ("Electricidad y Cableado", "flash"),
            ("Gasfitería y Plomería", "wrench"),
            ("Carpintería y Muebles", "saw"),
            ("Limpieza y Hogar", "broom"),
            ("Belleza y Cuidado Personal", "sparkles"),
            ("Reparación de Computadoras", "laptop"),
            ("Clases y Apoyo Escolar", "school"),
            ("Jardinería y Poda", "leaf"),
            ("Albañilería y Pintura", "color-fill"),
            ("Fletes y Movilidad", "truck"),
        ]

        for cat_name, icon in required_scats:
            key = cat_name.lower()
            if key not in service_cat_map:
                cat_id = uuid.uuid5(DEMO_NAMESPACE, f"service_cat_{cat_name}")
                new_cat = ServiceCategory(id=cat_id, name=cat_name, icon=icon)
                session.add(new_cat)
                service_cat_map[key] = cat_id

        # 3. Asegurar Categorías de Producto y Mapeo
        product_cat_map: Dict[str, uuid.UUID] = {}
        res_pcats = await session.execute(select(ProductCategory))
        for pc in res_pcats.scalars().all():
            product_cat_map[pc.name.lower()] = pc.id

        required_pcats = [
            "Panadería y Masas",
            "Comida Casera y Menú",
            "Verduras, Frutas y Abarrotes",
            "Repostería y Postres",
            "Artesanía y Confección",
            "Tecnología y Accesorios",
            "Artículos para el Hogar",
            "Útiles Escolares",
            "Productos Naturales",
            "Limpieza y Aseo Personal",
            "Otros Productos del Barrio",
        ]

        for pcat_name in required_pcats:
            key = pcat_name.lower()
            if key not in product_cat_map:
                pcat_id = uuid.uuid5(DEMO_NAMESPACE, f"prod_cat_{pcat_name}")
                new_pcat = ProductCategory(id=pcat_id, name=pcat_name)
                session.add(new_pcat)
                product_cat_map[key] = pcat_id

        await session.flush()

        # 4. Crear o Actualizar Usuarios de Demostración, Perfiles y Direcciones
        print("\n1. Registrando perfiles y coordenadas geolocalizadas de vecinos...")
        for u_cfg in DEMO_USERS_CONFIG:
            u_id = get_demo_uuid("user", u_cfg["index"])
            email = f"demo.vecino.{u_cfg['index']}@vecired.pe"
            lat, lon = calculate_coordinates(CENTER_LAT, CENTER_LON, u_cfg["distance_m"], u_cfg["angle"])

            # A. auth.users
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
                    "meta": f'{{"full_name": "{u_cfg["name"]}", "phone": "{u_cfg["phone"]}"}}',
                },
            )

            # B. public.profiles
            await session.execute(
                text("""
                    INSERT INTO public.profiles (id, full_name, phone, account_status, solidarity_helped_count, solidarity_received_count, created_at)
                    VALUES (:id, :name, :phone, 'verified', :helped, 0, now())
                    ON CONFLICT (id) DO UPDATE SET
                        full_name = EXCLUDED.full_name,
                        phone = EXCLUDED.phone,
                        account_status = 'verified',
                        solidarity_helped_count = EXCLUDED.solidarity_helped_count
                """),
                {
                    "id": u_id,
                    "name": u_cfg["name"],
                    "phone": u_cfg["phone"],
                    "helped": u_cfg["helped_count"],
                },
            )

            # C. addresses
            addr_id = get_demo_uuid("address", u_cfg["index"])
            await session.execute(
                text("""
                    INSERT INTO public.addresses (id, district_id, street_address, latitude, longitude, reference, created_at)
                    VALUES (:id, :dist_id, :street, :lat, :lon, :ref, now())
                    ON CONFLICT (id) DO UPDATE SET
                        district_id = EXCLUDED.district_id,
                        street_address = EXCLUDED.street_address,
                        latitude = EXCLUDED.latitude,
                        longitude = EXCLUDED.longitude,
                        reference = EXCLUDED.reference
                """),
                {
                    "id": addr_id,
                    "dist_id": district_id,
                    "street": u_cfg["street"],
                    "lat": lat,
                    "lon": lon,
                    "ref": f"Ubicación de demostración a {int(u_cfg['distance_m'])}m del centro",
                },
            )

            # D. user_addresses
            u_addr_id = get_demo_uuid("user_addr", u_cfg["index"])
            await session.execute(
                text("""
                    INSERT INTO public.user_addresses (id, user_id, address_id, address_type, is_primary, residence_status, created_at)
                    VALUES (:id, :user_id, :addr_id, 'home', true, 'verified', now())
                    ON CONFLICT (id) DO UPDATE SET
                        user_id = EXCLUDED.user_id,
                        address_id = EXCLUDED.address_id,
                        is_primary = true,
                        residence_status = 'verified'
                """),
                {
                    "id": u_addr_id,
                    "user_id": u_id,
                    "addr_id": addr_id,
                },
            )

            # E. community_memberships
            cm_id = get_demo_uuid("comm_mem", u_cfg["index"])
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
                    "comm_id": community_id,
                },
            )

            # F. Business (para dueños de productos)
            biz_id = get_demo_uuid("business", u_cfg["index"])
            await session.execute(
                text("""
                    INSERT INTO public.businesses (id, owner_id, community_id, address_id, business_name, description, status, created_at)
                    VALUES (:id, :owner_id, :comm_id, :addr_id, :biz_name, :desc, 'active', now())
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
                    "comm_id": community_id,
                    "addr_id": addr_id,
                    "biz_name": f"Emprendimiento {u_cfg['name'].split()[0]} (Demo)",
                    "desc": f"Comercio barrial de {u_cfg['name']}",
                },
            )

            print(f"  ✓ {u_cfg['name']} -> {u_cfg['distance_m']}m ({u_cfg['profile_type']})")

        await session.flush()

        # 5. Generar 20 Servicios
        print("\n2. Registrando 20 Servicios en diferentes categorías...")
        services_created = 0
        for s_data in SERVICES_DATA:
            s_id = get_demo_uuid("service", s_data["index"])
            provider_id = get_demo_uuid("user", s_data["user_index"])
            addr_id = get_demo_uuid("address", s_data["user_index"])
            cat_id = service_cat_map.get(s_data["category_name"].lower())

            if not cat_id:
                # Fallback al primer ID de categoría de servicios
                cat_id = list(service_cat_map.values())[0]

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
                        category_id = EXCLUDED.category_id
                """),
                {
                    "id": s_id,
                    "provider_id": provider_id,
                    "cat_id": cat_id,
                    "comm_id": community_id,
                    "addr_id": addr_id,
                    "title": s_data["title"],
                    "desc": s_data["description"],
                    "price": s_data["price_from"],
                    "unit": s_data["price_unit"],
                },
            )
            services_created += 1
            print(f"  [{services_created}/20] Servicio: {s_data['title']} (Usuario #{s_data['user_index']})")

        # 6. Generar 20 Productos
        print("\n3. Registrando 20 Productos en diferentes categorías...")
        products_created = 0
        for p_data in PRODUCTS_DATA:
            p_id = get_demo_uuid("product", p_data["index"])
            biz_id = get_demo_uuid("business", p_data["user_index"])
            cat_id = product_cat_map.get(p_data["category_name"].lower())

            if not cat_id:
                cat_id = list(product_cat_map.values())[0]

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
                    "name": p_data["name"],
                    "desc": p_data["description"],
                    "price": p_data["price"],
                    "stock": p_data["stock"],
                },
            )
            products_created += 1
            print(f"  [{products_created}/20] Producto: {p_data['name']} (Negocio #{p_data['user_index']})")

        # 7. Generar 20 Solicitudes de Ayuda Solidaria
        print("\n4. Registrando 20 Solicitudes y Ofrecimientos Solidarios...")
        solidarity_created = 0
        for sol_data in SOLIDARITY_DATA:
            sol_id = get_demo_uuid("solidarity", sol_data["index"])
            author_id = get_demo_uuid("user", sol_data["user_index"])

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
                        author_id = EXCLUDED.author_id
                """),
                {
                    "id": sol_id,
                    "author_id": author_id,
                    "comm_id": community_id,
                    "cat": sol_data["category"],
                    "post_type": sol_data["post_type"],
                    "title": sol_data["title"],
                    "desc": sol_data["description"],
                    "status": sol_data["status"],
                },
            )
            solidarity_created += 1
            print(f"  [{solidarity_created}/20] Solidaridad: {sol_data['title'][:55]}... ({sol_data['status']})")

        # 8. Generar 10 Emergencias de Prueba
        print("\n5. Registrando 10 Emergencias de prueba...")
        emergencies_created = 0
        for emg_data in EMERGENCIES_DATA:
            emg_id = get_demo_uuid("emergency", emg_data["index"])
            reporter_id = get_demo_uuid("user", emg_data["user_index"])
            addr_id = get_demo_uuid("address", emg_data["user_index"])

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
                        reported_by = EXCLUDED.reported_by
                """),
                {
                    "id": emg_id,
                    "reported_by": reporter_id,
                    "comm_id": community_id,
                    "addr_id": addr_id,
                    "type": emg_data["emergency_type"],
                    "title": emg_data["title"],
                    "desc": emg_data["description"],
                    "severity": emg_data["severity"],
                    "status": emg_data["status"],
                },
            )
            emergencies_created += 1
            print(f"  [{emergencies_created}/10] Emergencia: {emg_data['title'][:55]}... ({emg_data['severity']})")

        # 9. Crear Reseñas Reales para Configurar Reputación y Experiencia
        print("\n6. Asignando historial de valoraciones a perfiles de prueba...")
        # Definir reseñas entre usuarios demo exclusivamente
        reviews_plan = [
            # Usuario 2 (Elena Ramos): 1 reseña (5 estrellas)
            (2, 1, 2, 5, "Excelente atención, muy atenta y puntual."),
            # Usuario 3 (Jorge Quispe): 3 reseñas (4.7 estrellas)
            (3, 1, 3, 5, "Trabajo impecable, restauró la mesa como nueva."),
            (3, 4, 3, 5, "Muy recomendado en el barrio."),
            (3, 5, 3, 4, "Buen acabado, cumplió los tiempos acordados."),
            # Usuario 4 (Rosa Morales): 8 reseñas (4.9 estrellas)
            (4, 1, 4, 5, "La mejor limpieza que hemos contratado."),
            (4, 2, 4, 5, "Muy honesta y detallista."),
            (4, 3, 4, 5, "Dejó los ambientes impecables."),
            (4, 6, 4, 5, "Excelente servicio recomendado para familias."),
            (4, 7, 4, 5, "Súper puntual y cuidadosa con los muebles."),
            (4, 8, 4, 4, "Muy buen trabajo en general."),
            (4, 9, 4, 5, "100% recomendada en la comunidad."),
            (4, 10, 4, 5, "Gran disposición y amabilidad."),
            # Usuario 5 (Manuel Valdivia): 15 reseñas (5.0 estrellas)
            (5, 1, 5, 5, "Corte impecable, muy profesional."),
            (5, 2, 5, 5, "Gran trato y cuidado."),
            (5, 3, 5, 5, "Puntualidad y excelente técnica."),
            (5, 4, 5, 5, "El barbero de confianza de la familia."),
            (5, 6, 5, 5, "Muy higiénico con sus herramientas."),
            # Usuario 6 (Lucía Fernández): 2 reseñas (4.5 estrellas)
            (6, 1, 6, 5, "Reparó mi laptop en menos de 24 horas."),
            (6, 2, 6, 4, "Buen diagnóstico y precio justo."),
            # Usuario 7 (Víctor Cárdenas): 5 reseñas registradas
            (7, 1, 7, 5, "Profesor con mucha paciencia, mi hijo mejoró notas."),
            (7, 2, 7, 5, "Metodología clara y didáctica."),
            (7, 3, 7, 5, "Muy buen docente de matemática."),
            (7, 4, 7, 5, "Puntual y muy comprometido."),
            (7, 5, 7, 5, "Excelente profesor recomendado."),
            # Usuario 9 (Raúl Huamán): 3 reseñas (4.8 estrellas)
            (9, 1, 9, 5, "Pintó la fachada en el tiempo prometido."),
            (9, 2, 9, 5, "Trabajo muy limpio y sin manchas."),
            (9, 3, 9, 4, "Buen acabado en los interiores."),
            # Usuario 10 (Patricia Benítez): 1 reseña (4.0 estrellas)
            (10, 1, 10, 4, "Flete seguro y sin inconvenientes."),
        ]

        review_index = 0
        for reviewed_u_idx, reviewer_u_idx, s_idx, rating, comment in reviews_plan:
            review_index += 1
            rev_id = get_demo_uuid("review", review_index)
            reviewed_id = get_demo_uuid("user", reviewed_u_idx)
            reviewer_id = get_demo_uuid("user", reviewer_u_idx)
            service_id = get_demo_uuid("service", s_idx)

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
                },
            )

        await session.commit()

        print("\n" + "=" * 70)
        print("✓ SEEDER COMPLETADO CON ÉXITO")
        print("=" * 70)
        print(f"• Servicios creados/actualizados:     {services_created} (esperado: 20)")
        print(f"• Productos creados/actualizados:     {products_created} (esperado: 20)")
        print(f"• Solicitudes solidarias registradas: {solidarity_created} (esperado: 20)")
        print(f"• Emergencias de prueba registradas:  {emergencies_created} (esperado: 10)")
        print(f"• Total de registros generados:       {services_created + products_created + solidarity_created + emergencies_created} (esperado: 70)")
        print(f"• Perfiles vecinales configurados:    {len(DEMO_USERS_CONFIG)} usuarios")
        print(f"• Reseñas aprobadas vinculadas:       {review_index} valoraciones")
        print(f"• Coordenadas base de prueba:         Lat {CENTER_LAT}, Lon {CENTER_LON}")
        print("=" * 70)


if __name__ == "__main__":
    asyncio.run(seed_demo_system())
