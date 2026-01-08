
mapeo_columnas_actualizado = {'plano': {'velocidad': 'PLANO VELOCIDAD PROMEDIO  CARGADO', 'consumo': 'PLANO CONSUMO DE COMBUSTIBLE  CARGADO'}, 'ondulado': {'velocidad': 'ONDULADO VELOCIDAD PROMEDIO CARGADO', 'consumo': 'ONDULADO CONSUMO DE COMBUSTIBLE CARGADO'}, 'montaña': {'velocidad': 'MONTAÑA VELOCIDAD PROMEDIO CARGADO', 'consumo': 'MONTAÑA CONSUMO DE COMBUSTIBLE CARGADO'}, 'urbano': {'velocidad': 'RECORRIDO URBANO VELOCIDAD PROMEDIO CARGADO', 'consumo': 'RECORRIDO URBANO CONSUMO DE COMBUSTIBLE CARGADO'}, 'despavimentado': {'velocidad': 'AFIRMADO VELOCIDAD PROMEDIO CARGADO', 'consumo': 'AFIRMADO CONSUMO DE COMBUSTIBLE CARGADO'}}


import pandas as pd

def calcular_modelo_sicetac_extendido(
    origen, destino, configuracion, serie, distancias,
    valor_peaje_manual, matriz_parametros, matriz_costos_fijos,
    matriz_vehicular, rutas_df, peajes_df,
    carroceria_especial=None, ruta_oficial=None, horas_logisticas=None
):
    # --- 1. Parámetros base por tipo de vehículo y mes ---
    fila_param = matriz_parametros[
        (matriz_parametros["TIPO_VEHICULO"] == configuracion) &
        (matriz_parametros["MES"] == serie)
    ].iloc[0]

    # --- 2. Configuración vehicular para obtener ejes y características ---
    fila_conf = matriz_vehicular[
        matriz_vehicular["TIPO_VEHICULO"] == configuracion
    ].iloc[0]

    # --- 3. Calcular horas y combustible por tipo de vía ---
    total_horas = 0
    total_combustible = 0
    detalle = {}

    mapeo_columnas = {
        'plano': distancias.get('KM_PLANO', 0),
        'ondulado': distancias.get('KM_ONDULADO', 0),
        'montaña': distancias.get('KM_MONTAÑOSO', 0),
        'urbano': distancias.get('KM_URBANO', 0),
        'despavimentado': distancias.get('KM_DESPAVIMENTADO', 0)
    }

    for tipo, km in mapeo_columnas.items():
        vel = fila_param[mapeo_columnas_actualizado[tipo]["velocidad"]]
        cons = fila_param[mapeo_columnas_actualizado[tipo]["consumo"]]
        hrs = km / vel if vel else 0
        gal = km / cons if cons else 0
        total_horas += hrs
        total_combustible += gal
        detalle[tipo] = {"km": km, "horas": hrs, "gal": gal}

    # --- 4. Horas logísticas ---
    horas_log = horas_logisticas if horas_logisticas is not None else (4 if total_horas < 8 else 8)
    horas_totales = total_horas + horas_log
    recorridos = max(1, round(288 / horas_totales, 4))

    # --- 5. Costo fijo por carrocería ---
    tipo_carroceria_objetivo = carroceria_especial.upper().strip() if carroceria_especial else "GENERAL"
    costo_fijo_match = matriz_costos_fijos[
        (matriz_costos_fijos["TIPO_VEHICULO"] == configuracion) &
        (matriz_costos_fijos["MES"] == serie) &
        (matriz_costos_fijos["TIPO_CARROCERIA"].str.upper().str.strip() == tipo_carroceria_objetivo)
    ]
    if not costo_fijo_match.empty:
        costo_fijo_mes = costo_fijo_match["COSTO FIJO"].values[0]
    else:
        raise ValueError(f"No se encontró costo fijo para {configuracion} - {serie} - {tipo_carroceria_objetivo}")
    costo_fijo_viaje = round(costo_fijo_mes / recorridos, 2)

    # --- 6. Combustible ---
    valor_acpm = fila_param["VALOR COMBUSTIBLE GALÓN ACPM"]
    costo_combustible = round(total_combustible * valor_acpm, 2)

    # --- 7. Peajes ---
    if ruta_oficial is not None:
        id_sice = ruta_oficial['ID_SICE']
        ejes = fila_conf['EJES_CONFIGURACION']
        fila_peaje = peajes_df[
            (peajes_df["ID_SICE"] == id_sice) &
            (peajes_df["EJES_CONFIGURACION"] == ejes)
        ]
        valor_peaje = fila_peaje["VALOR_PEAJE"].values[0] if not fila_peaje.empty else 0
    else:
        valor_peaje = valor_peaje_manual or 0

    # --- 8. Costos variables e imprevistos ---
    km_total = sum(mapeo_columnas.values())
    costo_variable_km = fila_param["COSTOS VARIABLES"]
    costo_variables = round(km_total * costo_variable_km, 2)
    imprevistos = round(costo_variables * 0.075, 2)
    total_variable = round(costo_combustible + valor_peaje + costo_variables + imprevistos, 2)

    # --- 9. Otros costos (administrativos, seguros, etc) ---
    otros_costos = round((costo_fijo_viaje + total_variable) * 0.199824, 2)

    # --- 10. Total ---
    total_viaje = round(costo_fijo_viaje + total_variable + otros_costos, 2)

    return {
        "origen": origen,
        "destino": destino,
        "configuracion": configuracion,
        "carroceria": tipo_carroceria_objetivo,
        "mes": serie,
        "horas_recorrido": round(total_horas, 2),
        "horas_logisticas": horas_log,
        "recorridos_mes": recorridos,
        "costo_fijo": costo_fijo_viaje,
        "combustible": costo_combustible,
        "peajes": valor_peaje,
        "mantenimiento": costo_variables,
        "imprevistos": imprevistos,
        "otros_costos": otros_costos,
        "total_viaje": total_viaje,
        "detalle_via": detalle
    }

