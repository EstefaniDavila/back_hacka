"""Módulo de notificaciones para VeciRed IA."""
from .models import Notification, UserDevice
from .router import router

__all__ = ["Notification", "UserDevice", "router"]
