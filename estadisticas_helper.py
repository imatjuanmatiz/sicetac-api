# estadisticas_helper.py - Versión Simplificada (Solo 2025)

import pandas as pd
from functools import lru_cache
import os

# Solo cargamos archivos cuando se necesitan (lazy loading)
# Para evolución: 2024 y 2025
# Para todo lo demás: solo 2025

@lru_cache(maxsize=2)
def _cargar_rutas(anio):
    """Carga el archivo de rutas solo cuando se necesita (2024 o 2025)"""
    archivo = f"consolidacion_rutas_{anio}.xlsx"
    if not os.path.exists(archivo):
        return pd.DataFrame()
    return pd.read_excel(archivo)

@lru_cache(maxsize=1)
def _cargar_mercancias():
    """Carga el archivo de mercancías de 2025"""
    archivo = "consolidacion_anual_mercancia_top20_2025.xlsx"
    if not os.path.exists(archivo):
        return pd.DataFrame()
    return pd.read_excel(archivo)

@lru_cache(maxsize=1)
def _cargar_destinos():
    """Carga el archivo de destinos de 2025"""
    archivo = "red_top20_destinos_origen_2025.xlsx"
    if not os.path.exists(archivo):
        return pd.DataFrame()
    return pd.read_excel(archivo)

@lru_cache(maxsize=1)
def _cargar_origenes():
    """Carga el archivo de orígenes de 2025"""
    archivo = "red_top20_origenes_por_destino_2025.xlsx"
    if not os.path.exists(archivo):
        return pd.DataFrame()
    return pd.read_excel(archivo)

@lru_cache(maxsize=1)
def _cargar_vehiculos():
    """Carga el archivo de vehículos de 2025"""
    archivo = "consolidacion_rutas_vehiculo_2025.xlsx"
    if not os.path.exists(archivo):
        return pd.DataFrame()
    return pd.read_excel(archivo)


def obtener_evolucion_viajes_y_toneladas(origen, destino):
    """
    Retorna la evolución mensual de viajes y toneladas para una ruta específica.
    Compara datos de 2024 y 2025 para ver la evolución.
    """
    clave = f"{origen}-{destino}"
    
    # Cargar ambos años para comparación
    df_2024 = _cargar_rutas(2024)
    df_2025 = _cargar_rutas(2025)
    
    # Filtrar datos de ambos años
    df_2024_filtrado = df_2024[df_2024["RUTA"] == clave].copy() if not df_2024.empty else pd.DataFrame()
    df_2025_filtrado = df_2025[df_2025["RUTA"] == clave].copy() if not df_2025.empty else pd.DataFrame()
    
    # Combinar
    df_combined = pd.concat([df_2024_filtrado, df_2025_filtrado], ignore_index=True)
    
    if df_combined.empty:
        return []
    
    # Agrupar por mes y sumar (en caso de múltiples naturalezas de carga)
    df_grouped = df_combined.groupby('AÑOMES', as_index=False).agg({
        'TOTAL_VIAJES': 'sum',
        'TOTAL_KILOGRAMOS': 'sum',
        'TOTAL_GALONES': 'sum'
    })
    
    # Agregar columna de toneladas
    df_grouped['TONELADAS'] = df_grouped['TOTAL_KILOGRAMOS'] / 1000
    
    # Ordenar por mes
    df_grouped = df_grouped.sort_values('AÑOMES')
    
    # Liberar memoria
    del df_2024_filtrado, df_2025_filtrado, df_combined
    
    return df_grouped.to_dict(orient="records")


def obtener_top_mercancias_ruta(origen, destino):
    """
    Retorna el top 20 de mercancías para una ruta específica en 2025.
    """
    clave = f"{origen}-{destino}"
    
    # Cargar mercancías de 2025
    df = _cargar_mercancias()
    
    if df.empty:
        return []
    
    # Filtrar por ruta
    df_filtrado = df[df["RUTA"] == clave].copy()
    
    if df_filtrado.empty:
        return []
    
    # Ordenar y tomar top 20
    df_filtrado = df_filtrado.sort_values("TONELADAS", ascending=False).head(20)
    
    resultado = df_filtrado[[
        "CODMERCANCIA", 
        "MERCANCIA", 
        "TOTAL_VIAJES",
        "TONELADAS", 
        "PCT_PARTICIPACION"
    ]].to_dict(orient="records")
    
    del df_filtrado
    return resultado


def obtener_top_destinos(cod_origen):
    """
    Retorna el top 20 de destinos para un origen específico en 2025.
    """
    df = _cargar_destinos()
    
    if df.empty:
        return []
    
    df_filtrado = df[df["CODIGO_ORIGEN"] == int(cod_origen)].copy()
    
    if df_filtrado.empty:
        return []
    
    df_filtrado = df_filtrado.sort_values("TONELADAS", ascending=False).head(20)
    
    resultado = df_filtrado[[
        "CODIGO_DESTINO",
        "MUNICIPIO_DESTINO",
        "TOTAL_VIAJES",
        "TONELADAS"
    ]].to_dict(orient="records")
    
    del df_filtrado
    return resultado


def obtener_top_origenes(cod_destino):
    """
    Retorna el top 20 de orígenes para un destino específico en 2025.
    """
    df = _cargar_origenes()
    
    if df.empty:
        return []
    
    df_filtrado = df[df["CODIGO_DESTINO"] == int(cod_destino)].copy()
    
    if df_filtrado.empty:
        return []
    
    df_filtrado = df_filtrado.sort_values("TONELADAS", ascending=False).head(20)
    
    resultado = df_filtrado[[
        "CODIGO_ORIGEN",
        "MUNICIPIO_ORIGEN",
        "TOTAL_VIAJES",
        "TONELADAS"
    ]].to_dict(orient="records")
    
    del df_filtrado
    return resultado


def obtener_distribucion_vehiculos_ruta(origen, destino):
    """
    Retorna la distribución de tipos de vehículos para una ruta específica en 2025.
    """
    clave = f"{origen}-{destino}"
    
    df = _cargar_vehiculos()
    
    if df.empty:
        return []
    
    df_filtrado = df[df["RUTA"] == clave].copy()
    
    if df_filtrado.empty:
        return []
    
    # Agrupar por configuración de vehículo
    df_grouped = df_filtrado.groupby('COD_CONFIG_VEHICULO', as_index=False).agg({
        'TOTAL_VIAJES': 'sum',
        'TOTAL_KILOGRAMOS': 'sum',
        'TOTAL_GALONES': 'sum'
    })
    
    # Agregar toneladas
    df_grouped['TONELADAS'] = df_grouped['TOTAL_KILOGRAMOS'] / 1000
    
    # Ordenar por número de viajes
    df_grouped = df_grouped.sort_values("TOTAL_VIAJES", ascending=False)
    
    resultado = df_grouped[[
        "COD_CONFIG_VEHICULO",
        "TOTAL_VIAJES",
        "TONELADAS",
        "TOTAL_GALONES"
    ]].to_dict(orient="records")
    
    del df_filtrado, df_grouped
    return resultado


def obtener_evolucion_por_naturaleza_carga(origen, destino):
    """
    Retorna la evolución mensual de una ruta específica en 2025,
    separada por naturaleza de carga (General, Perecedero, etc.).
    """
    clave = f"{origen}-{destino}"
    
    df = _cargar_rutas(2025)
    
    if df.empty:
        return []
    
    df_filtrado = df[df["RUTA"] == clave].copy()
    
    if df_filtrado.empty:
        return []
    
    # Agregar toneladas
    df_filtrado['TONELADAS'] = df_filtrado['TOTAL_KILOGRAMOS'] / 1000
    
    # Ordenar por mes
    df_filtrado = df_filtrado.sort_values('AÑOMES')
    
    resultado = df_filtrado[[
        "AÑOMES",
        "NATURALEZACARGA",
        "TOTAL_VIAJES",
        "TONELADAS",
        "TOTAL_GALONES"
    ]].to_dict(orient="records")
    
    del df_filtrado
    return resultado


def obtener_comparacion_anual_ruta(origen, destino):
    """
    Compara los totales anuales de una ruta entre 2024 y 2025.
    Útil para ver el crecimiento/decrecimiento de la ruta.
    """
    clave = f"{origen}-{destino}"
    
    # Datos 2024
    df_2024 = _cargar_rutas(2024)
    total_2024 = {
        "anio": 2024,
        "total_viajes": 0,
        "total_toneladas": 0.0,
        "total_galones": 0.0
    }
    
    if not df_2024.empty:
        df_2024_filtrado = df_2024[df_2024["RUTA"] == clave]
        if not df_2024_filtrado.empty:
            total_2024 = {
                "anio": 2024,
                "total_viajes": int(df_2024_filtrado['TOTAL_VIAJES'].sum()),
                "total_toneladas": round(df_2024_filtrado['TOTAL_KILOGRAMOS'].sum() / 1000, 2),
                "total_galones": round(df_2024_filtrado['TOTAL_GALONES'].sum(), 2)
            }
        del df_2024_filtrado
    
    # Datos 2025
    df_2025 = _cargar_rutas(2025)
    total_2025 = {
        "anio": 2025,
        "total_viajes": 0,
        "total_toneladas": 0.0,
        "total_galones": 0.0
    }
    
    if not df_2025.empty:
        df_2025_filtrado = df_2025[df_2025["RUTA"] == clave]
        if not df_2025_filtrado.empty:
            total_2025 = {
                "anio": 2025,
                "total_viajes": int(df_2025_filtrado['TOTAL_VIAJES'].sum()),
                "total_toneladas": round(df_2025_filtrado['TOTAL_KILOGRAMOS'].sum() / 1000, 2),
                "total_galones": round(df_2025_filtrado['TOTAL_GALONES'].sum(), 2)
            }
        del df_2025_filtrado
    
    # Calcular variaciones porcentuales
    variacion = {
        "variacion_viajes_pct": 0.0,
        "variacion_toneladas_pct": 0.0,
        "variacion_galones_pct": 0.0
    }
    
    if total_2024["total_viajes"] > 0:
        variacion["variacion_viajes_pct"] = round(
            ((total_2025["total_viajes"] - total_2024["total_viajes"]) / total_2024["total_viajes"] * 100), 2
        )
    
    if total_2024["total_toneladas"] > 0:
        variacion["variacion_toneladas_pct"] = round(
            ((total_2025["total_toneladas"] - total_2024["total_toneladas"]) / total_2024["total_toneladas"] * 100), 2
        )
    
    if total_2024["total_galones"] > 0:
        variacion["variacion_galones_pct"] = round(
            ((total_2025["total_galones"] - total_2024["total_galones"]) / total_2024["total_galones"] * 100), 2
        )
    
    return {
        "2024": total_2024,
        "2025": total_2025,
        "variacion": variacion
    }


def obtener_resumen_ruta(origen, destino):
    """
    Retorna un resumen completo de una ruta específica en 2025.
    Incluye: totales, top mercancías, distribución de vehículos.
    """
    clave = f"{origen}-{destino}"
    
    # Obtener datos de rutas 2025
    df = _cargar_rutas(2025)
    
    if df.empty:
        return {
            "ruta": clave,
            "datos_disponibles": False
        }
    
    df_ruta = df[df["RUTA"] == clave]
    
    if df_ruta.empty:
        return {
            "ruta": clave,
            "datos_disponibles": False
        }
    
    # Calcular totales
    totales = {
        "total_viajes": int(df_ruta['TOTAL_VIAJES'].sum()),
        "total_toneladas": round(df_ruta['TOTAL_KILOGRAMOS'].sum() / 1000, 2),
        "total_galones": round(df_ruta['TOTAL_GALONES'].sum(), 2)
    }
    
    # Top mercancías
    top_mercancias = obtener_top_mercancias_ruta(origen, destino)
    
    # Distribución de vehículos
    vehiculos = obtener_distribucion_vehiculos_ruta(origen, destino)
    
    return {
        "ruta": clave,
        "datos_disponibles": True,
        "anio": 2025,
        "totales": totales,
        "top_mercancias": top_mercancias[:5],  # Solo top 5 para el resumen
        "vehiculos": vehiculos[:5]  # Solo top 5 para el resumen
    }


# Función para limpiar cache si es necesario
def limpiar_cache():
    """Limpia el cache de archivos cargados para liberar memoria"""
    _cargar_rutas.cache_clear()
    _cargar_mercancias.cache_clear()
    _cargar_destinos.cache_clear()
    _cargar_origenes.cache_clear()
    _cargar_vehiculos.cache_clear()
