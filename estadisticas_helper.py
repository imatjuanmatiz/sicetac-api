# estadisticas_helper.py


import pandas as pd

# Carga los archivos .xlsx con todas las estadísticas
# Mercancías por ruta (Top 20)
DF_MERCANCIAS_2024 = pd.read_excel("consolidacion_anual_mercancia_top20_2024.xlsx")
DF_MERCANCIAS_2025 = pd.read_excel("consolidacion_anual_mercancia_top20_2025.xlsx")

# Evolución de rutas por mes
DF_RUTAS_2024 = pd.read_excel("consolidacion_rutas_2024.xlsx")
DF_RUTAS_2025 = pd.read_excel("consolidacion_rutas_2025.xlsx")

# Destinos y Orígenes
DF_DESTINOS_2024 = pd.read_excel("red_top20_destinos_origen_2024.xlsx")
DF_DESTINOS_2025 = pd.read_excel("red_top20_destinos_origen_2025.xlsx")
DF_ORIGENES_2024 = pd.read_excel("red_top20_origenes_por_destino_2024.xlsx")
DF_ORIGENES_2025 = pd.read_excel("red_top20_origenes_por_destino_2025.xlsx")

# Vehículos por ruta
DF_VEHICULOS_2024 = pd.read_excel("consolidacion_rutas_vehiculo_2024.xlsx")
DF_VEHICULOS_2025 = pd.read_excel("consolidacion_rutas_vehiculo_2025.xlsx")


def obtener_evolucion_viajes_y_toneladas(origen, destino):
    """
    Retorna la evolución mensual de viajes y toneladas para una ruta específica.
    Combina datos de 2024 y 2025.
    """
    clave = f"{origen}-{destino}"
    
    # Filtrar datos de 2024
    df_2024 = DF_RUTAS_2024[DF_RUTAS_2024["RUTA"] == clave].copy()
    
    # Filtrar datos de 2025
    df_2025 = DF_RUTAS_2025[DF_RUTAS_2025["RUTA"] == clave].copy()
    
    # Combinar ambos dataframes
    df_combined = pd.concat([df_2024, df_2025], ignore_index=True)
    
    # Agrupar por mes y sumar (en caso de múltiples naturalezas de carga)
    df_grouped = df_combined.groupby('AÑOMES').agg({
        'TOTAL_VIAJES': 'sum',
        'TOTAL_KILOGRAMOS': 'sum',
        'TOTAL_GALONES': 'sum'
    }).reset_index()
    
    # Agregar columna de toneladas
    df_grouped['TONELADAS'] = df_grouped['TOTAL_KILOGRAMOS'] / 1000
    
    # Ordenar por mes
    df_grouped = df_grouped.sort_values('AÑOMES')
    
    return df_grouped.to_dict(orient="records")


def obtener_top_mercancias_ruta(origen, destino):
    """
    Retorna el top 20 de mercancías para una ruta específica en 2024 y 2025.
    """
    clave = f"{origen}-{destino}"
    
    # Filtrar mercancías 2024
    merc_2024 = DF_MERCANCIAS_2024[DF_MERCANCIAS_2024["RUTA"] == clave].copy()
    merc_2024 = merc_2024.sort_values("TONELADAS", ascending=False).head(20)
    
    # Filtrar mercancías 2025
    merc_2025 = DF_MERCANCIAS_2025[DF_MERCANCIAS_2025["RUTA"] == clave].copy()
    merc_2025 = merc_2025.sort_values("TONELADAS", ascending=False).head(20)
    
    return {
        "TOP_MERCANCIAS_2024": merc_2024[[
            "CODMERCANCIA", 
            "MERCANCIA", 
            "TOTAL_VIAJES",
            "TONELADAS", 
            "PCT_PARTICIPACION"
        ]].to_dict(orient="records"),
        "TOP_MERCANCIAS_2025": merc_2025[[
            "CODMERCANCIA", 
            "MERCANCIA", 
            "TOTAL_VIAJES",
            "TONELADAS", 
            "PCT_PARTICIPACION"
        ]].to_dict(orient="records")
    }


def obtener_top_destinos(cod_origen, anio=2025):
    """
    Retorna el top 20 de destinos para un origen específico.
    Por defecto usa datos de 2025, pero puede consultar 2024.
    """
    if anio == 2024:
        df = DF_DESTINOS_2024[DF_DESTINOS_2024["CODIGO_ORIGEN"] == int(cod_origen)].copy()
    else:
        df = DF_DESTINOS_2025[DF_DESTINOS_2025["CODIGO_ORIGEN"] == int(cod_origen)].copy()
    
    df = df.sort_values("TONELADAS", ascending=False).head(20)
    
    return df[[
        "CODIGO_DESTINO",
        "MUNICIPIO_DESTINO",
        "TOTAL_VIAJES",
        "TONELADAS"
    ]].to_dict(orient="records")


def obtener_top_origenes(cod_destino, anio=2025):
    """
    Retorna el top 20 de orígenes para un destino específico.
    Por defecto usa datos de 2025, pero puede consultar 2024.
    """
    if anio == 2024:
        df = DF_ORIGENES_2024[DF_ORIGENES_2024["CODIGO_DESTINO"] == int(cod_destino)].copy()
    else:
        df = DF_ORIGENES_2025[DF_ORIGENES_2025["CODIGO_DESTINO"] == int(cod_destino)].copy()
    
    df = df.sort_values("TONELADAS", ascending=False).head(20)
    
    return df[[
        "CODIGO_ORIGEN",
        "MUNICIPIO_ORIGEN",
        "TOTAL_VIAJES",
        "TONELADAS"
    ]].to_dict(orient="records")


def obtener_distribucion_vehiculos_ruta(origen, destino, anio=2025):
    """
    Retorna la distribución de tipos de vehículos para una ruta específica.
    Por defecto usa datos de 2025, pero puede consultar 2024.
    """
    clave = f"{origen}-{destino}"
    
    if anio == 2024:
        df = DF_VEHICULOS_2024[DF_VEHICULOS_2024["RUTA"] == clave].copy()
    else:
        df = DF_VEHICULOS_2025[DF_VEHICULOS_2025["RUTA"] == clave].copy()
    
    # Agrupar por configuración de vehículo y sumar
    df_grouped = df.groupby('COD_CONFIG_VEHICULO').agg({
        'TOTAL_VIAJES': 'sum',
        'TOTAL_KILOGRAMOS': 'sum',
        'TOTAL_GALONES': 'sum'
    }).reset_index()
    
    # Agregar columna de toneladas
    df_grouped['TONELADAS'] = df_grouped['TOTAL_KILOGRAMOS'] / 1000
    
    # Ordenar por número de viajes
    df_grouped = df_grouped.sort_values("TOTAL_VIAJES", ascending=False)
    
    return df_grouped[[
        "COD_CONFIG_VEHICULO",
        "TOTAL_VIAJES",
        "TONELADAS",
        "TOTAL_GALONES"
    ]].to_dict(orient="records")


def obtener_evolucion_por_naturaleza_carga(origen, destino, anio=2025):
    """
    Retorna la evolución mensual de una ruta específica separada por naturaleza de carga.
    Esta es una función adicional que puede ser útil.
    """
    clave = f"{origen}-{destino}"
    
    if anio == 2024:
        df = DF_RUTAS_2024[DF_RUTAS_2024["RUTA"] == clave].copy()
    else:
        df = DF_RUTAS_2025[DF_RUTAS_2025["RUTA"] == clave].copy()
    
    # Agregar columna de toneladas
    df['TONELADAS'] = df['TOTAL_KILOGRAMOS'] / 1000
    
    # Ordenar por mes
    df = df.sort_values('AÑOMES')
    
    return df[[
        "AÑOMES",
        "NATURALEZACARGA",
        "TOTAL_VIAJES",
        "TONELADAS",
        "TOTAL_GALONES"
    ]].to_dict(orient="records")


# Funciones auxiliares adicionales

def obtener_comparacion_anual_ruta(origen, destino):
    """
    Compara los totales anuales de una ruta entre 2024 y 2025.
    """
    clave = f"{origen}-{destino}"
    
    # Datos 2024
    df_2024 = DF_RUTAS_2024[DF_RUTAS_2024["RUTA"] == clave]
    total_2024 = {
        "anio": 2024,
        "total_viajes": df_2024['TOTAL_VIAJES'].sum(),
        "total_toneladas": df_2024['TOTAL_KILOGRAMOS'].sum() / 1000,
        "total_galones": df_2024['TOTAL_GALONES'].sum()
    }
    
    # Datos 2025
    df_2025 = DF_RUTAS_2025[DF_RUTAS_2025["RUTA"] == clave]
    total_2025 = {
        "anio": 2025,
        "total_viajes": df_2025['TOTAL_VIAJES'].sum(),
        "total_toneladas": df_2025['TOTAL_KILOGRAMOS'].sum() / 1000,
        "total_galones": df_2025['TOTAL_GALONES'].sum()
    }
    
    # Calcular variaciones porcentuales
    variacion = {
        "variacion_viajes_pct": ((total_2025["total_viajes"] - total_2024["total_viajes"]) / total_2024["total_viajes"] * 100) if total_2024["total_viajes"] > 0 else 0,
        "variacion_toneladas_pct": ((total_2025["total_toneladas"] - total_2024["total_toneladas"]) / total_2024["total_toneladas"] * 100) if total_2024["total_toneladas"] > 0 else 0,
        "variacion_galones_pct": ((total_2025["total_galones"] - total_2024["total_galones"]) / total_2024["total_galones"] * 100) if total_2024["total_galones"] > 0 else 0
    }
    
    return {
        "2024": total_2024,
        "2025": total_2025,
        "variacion": variacion
    }
