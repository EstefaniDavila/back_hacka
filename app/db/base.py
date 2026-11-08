from datetime import datetime, timezone
from sqlalchemy import DateTime
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Clase base declarativa de SQLAlchemy 2.0."""
    pass


class TimestampMixin:
    """Mixin para registrar fechas de creación y actualización en UTC."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


def load_all_models():
    """Importar modelos de módulos para que Base.metadata reconozca todas las tablas."""
    import app.modules.geo.models  
    import app.modules.users.models  
    import app.modules.commerce.models  
    import app.modules.solidarity.models  
    import app.modules.emergencies.models  
    import app.modules.interactions.models  
    import app.modules.notifications.models  
    import app.modules.ai.models  
    import app.modules.sync.models  
