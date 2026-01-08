# contexto_helper.py
from __future__ import annotations

import logging
from typing import Any

from mercado_helper import obtener_historico_por_llave

logger = logging.getLogger("contexto_helper")

# (Opcional) para compatibilidad con imports antiguos
_MODO_VIAJE = "CARGADO"

def set_modo_viaje(modo: str | None):
    global _MODO_VIAJE
    if not modo:
        _MODO_VIAJE = "CARGADO"
        return
    m = str(modo).strip().upper()
    _MODO_VIAJE = "VACIO" if m in {"VACIO", "VACÍO"} else "CARGADO"


def obtener_valores_promedio_mercado_por_llave(ruta_config: str) -> list[dict[str, Any]]:
    """
    Wrapper estable para Mercado RNDC.

    ruta_config: 'COD_ORIGEN-COD_DESTINO-CONFIG' (✅ SIEMPRE con '-')
    Ej: '11001000-13001000-3S3'
    """
    try:
        return obtener_historico_por_llave(ruta_config)
    except Exception as e:
        logger.warning(f"⚠️ Falló mercado (contexto_helper) para {ruta_config}: {e}")
        return []
