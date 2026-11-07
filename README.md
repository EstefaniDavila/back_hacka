# VeciRed IA — Backend

Backend robusto, modular y asíncrono para **VeciRed IA**, plataforma móvil de economía local, solidaridad vecinal y gestión de emergencias.

---

## 1. Stack Tecnológico

- **Lenguaje:** Python 3.12+
- **Framework Web:** FastAPI
- **Base de Datos:** PostgreSQL en Supabase
- **ORM:** SQLAlchemy 2.0 (modo asíncrono)
- **Driver de BD:** asyncpg
- **Control de Migraciones:** Alembic
- **Validación y Configuración:** Pydantic v2 & Pydantic-Settings
- **Servidor ASGI:** Uvicorn
- **Pruebas:** Pytest + pytest-asyncio + HTTPX

---

## 2. Estructura del Proyecto

```text
vecired-backend/
│
├── app/
│   ├── main.py               # Entrada de FastAPI, ciclo de vida (lifespan) y middlewares
│   │
│   ├── core/                 # Componentes transversales del sistema
│   │   ├── config.py         # Configuración central tipada con Pydantic v2
│   │   ├── exceptions.py     # Jerarquía de excepciones y manejadores globales
│   │   ├── logging.py        # Configuración estructurada de logs
│   │   └── health.py         # Router de verificación de salud (/api/v1/health)
│   │
│   ├── db/                   # Capa de base de datos
│   │   ├── base.py           # DeclarativeBase y mixins reutilizables
│   │   ├── session.py        # Motor asíncrono, sesión y verificación de conexión
│   │   └── dependencies.py   # Inyección de dependencia (get_db_session)
│   │
│   ├── modules/              # Módulos funcionales (preparado para Fase 2+)
│   │   └── __init__.py       # (usuarios, emergencias, publicaciones, etc.)
│   │
│   ├── integrations/         # Integraciones con servicios externos (IA, Notificaciones)
│   │   └── __init__.py
│   │
│   └── shared/               # Esquemas, utilidades y helpers compartidos
│       └── __init__.py
│
├── tests/                    # Pruebas automatizadas puntuales
│   ├── conftest.py           # Fixtures para AsyncClient
│   └── test_health.py        # Pruebas del endpoint de salud y root
│
├── alembic/                  # Control de versiones de esquema con soporte async
│   ├── versions/             # Scripts de migración generados
│   ├── env.py                # Configuración asíncrona de Alembic con SQLAlchemy 2.0
│   └── script.py.mako        # Plantilla para nuevas migraciones
│
├── .env.example              # Plantilla documentada de variables de entorno
├── .gitignore                # Reglas de exclusión de Git
├── alembic.ini               # Archivo de configuración de Alembic
├── requirements.txt          # Dependencias del proyecto
└── README.md                 # Documentación técnica
```

---

## 3. Requisitos Previos

- Python 3.12 o superior.
- Git.
- WSL (Ubuntu) o entorno Linux/macOS/Windows con soporte para sockets y Python.
- Cuenta o proyecto en [Supabase](https://supabase.com).

---

## 4. Instalación y Puesta en Marcha

### 4.1. Clonar y situarse en el repositorio

```bash
cd ~/hack/back
```

### 4.2. Crear y activar el entorno virtual

```bash
python3 -m venv .venv
source .venv/bin/activate
```

*(En Windows PowerShell nativo sería: `.venv\\Scripts\\Activate.ps1`)*

### 4.3. Instalar dependencias

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

---

## 5. Configuración de Variables de Entorno (.env)

Copia el archivo de ejemplo para crear tu configuración local:

```bash
cp .env.example .env
```

Edita `.env` con los parámetros de tu proyecto en Supabase:

### Conexión con Supabase (PostgreSQL)

Supabase ofrece distintas modalidades de conexión:

1. **Transaction Pooler (Puerto 6543 - Recomendado):**
   ```env
   DATABASE_URL=postgresql+asyncpg://postgres.[PROJECT_REF]:[PASSWORD]@aws-0-[REGION].pooler.supabase.com:6543/[DB_NAME]
   ```
   *Nota:* Para evitar conflictos con PgBouncer, el pool ya tiene configurado `statement_cache_size=0`.

2. **Session Pooler (Puerto 5432):**
   ```env
   DATABASE_URL=postgresql+asyncpg://postgres.[PROJECT_REF]:[PASSWORD]@aws-0-[REGION].pooler.supabase.com:5432/[DB_NAME]
   ```

3. **Conexión Directa (Puerto 5432):**
   ```env
   DATABASE_URL=postgresql+asyncpg://postgres:[PASSWORD]@db.[PROJECT_REF].supabase.co:5432/[DB_NAME]
   ```

---

## 6. Ejecución del Servidor

Con el entorno virtual activado:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

---

## 7. Acceso a Documentación Interactiva (Swagger / OpenAPI)

Una vez iniciado el servidor, abre en tu navegador:

- **Swagger UI:** [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- **ReDoc:** [http://127.0.0.1:8000/redoc](http://127.0.0.1:8000/redoc)

---

## 8. Verificación de Salud del Sistema

Endpoint:
```http
GET /api/v1/health
```

Respuesta esperada:

```json
{
  "status": "healthy",
  "app": {
    "name": "VeciRed IA Backend",
    "version": "1.0.0",
    "environment": "development"
  },
  "services": {
    "database": {
      "status": "connected",
      "message": "Conexión con PostgreSQL exitosa"
    }
  },
  "timestamp": "2026-11-07T07:30:00.000000+00:00"
}
```

Si la base de datos aún no está configurada o se encuentra inaccesible, el endpoint informará `disconnected` con el motivo correspondiente, sin exponer credenciales ni credenciales de conexión.

---

## 9. Verificación de Alembic

Para comprobar que Alembic lee correctamente la configuración sin aplicar cambios a la base de datos:

```bash
alembic current
```

---

## 10. Ejecución de Pruebas

Para ejecutar las verificaciones automatizadas:

```bash
pytest
```
