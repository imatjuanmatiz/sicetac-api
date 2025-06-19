from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import pandas as pd
from fastapi.responses import JSONResponse
from sicetac_helper import SICETACHelper
from modelo_sicetac import calcular_modelo_sicetac_extendido

app = FastAPI(title="API SICETAC", version="1.2")

class ConsultaInput(BaseModel):
    origen: str
    destino: str
    vehiculo: str = "C3S3"
    mes: int = 202506
    carroceria: str = "GENERAL"
    valor_peaje_manual: float = 0.0
    horas_logisticas: float = None
    km_plano: float = 0
    km_ondulado: float = 0
    km_montañoso: float = 0
    km_urbano: float = 0
    km_despavimentado: float = 0

ARCHIVOS = {
    "municipios": "municipios.xlsx",
    "vehiculos": "CONFIGURACION_VEHICULAR_LIMPIO.xlsx",
    "parametros": "MATRIZ_CAMBIOS_PARAMETROS_LIMPIO.xlsx",
    "costos_fijos": "COSTO_FIJO_ACTUALIZADO.xlsx",
    "peajes": "PEAJES_LIMPIO.xlsx",
    "rutas": "RUTA_DISTANCIA_LIMPIO.xlsx"
}

# Archivos extendidos
df_municipios = pd.read_excel(ARCHIVOS["municipios"])
df_vehiculos = pd.read_excel(ARCHIVOS["vehiculos"])
df_parametros = pd.read_excel(ARCHIVOS["parametros"])
df_costos_fijos = pd.read_excel(ARCHIVOS["costos_fijos"])
df_peajes = pd.read_excel(ARCHIVOS["peajes"])
df_rutas = pd.read_excel(ARCHIVOS["rutas"])

# Nuevas fuentes de contexto
df_valores_mercado = pd.read_csv("VALORES_CONSOLIDADOS_2025.csv")
df_indicadores = pd.read_csv("indice_cargue_descargue_consolidado_04.csv")
df_competitividad = pd.read_csv("competitividad_rutas_2025.csv")

helper = SICETACHelper(ARCHIVOS["municipios"])

def convertir_nativos(d):
    if isinstance(d, dict):
        return {k: convertir_nativos(v) for k, v in d.items()}
    elif isinstance(d, list):
        return [convertir_nativos(v) for v in d]
    elif hasattr(d, 'item'):
        return d.item()
    else:
        return d

def obtener_valor_mercado(mes, ruta_config):
    fila = df_valores_mercado[(df_valores_mercado["MES"] == mes) & (df_valores_mercado["RUTA_CONFIGURACION"] == ruta_config)]
    if fila.empty:
        return "No disponible"
    return round(fila.iloc[0]["VALOR_PROMEDIO_MERCADO"], 0)

def obtener_indicadores(codigo):
    df_fil = df_indicadores[df_indicadores["CODIGO_OBJETIVO"] == codigo]
    if df_fil.empty:
        return {"viajes_cargue": "ND", "viajes_descargue": "ND", "indice": "ND"}
    resumen = df_fil.groupby("CODIGO_OBJETIVO").agg({
        "VIAJES_ORIGINADOS": "sum",
        "VIAJES_DESCARGADOS": "sum",
        "INDICE_CARGUE_DESCARGUE": "mean"
    }).reset_index()
    fila = resumen.iloc[0]
    return {
        "viajes_cargue": int(fila["VIAJES_ORIGINADOS"]),
        "viajes_descargue": int(fila["VIAJES_DESCARGADOS"]),
        "indice": round(fila["INDICE_CARGUE_DESCARGUE"], 2)
    }

def evaluar_competitividad(cod_origen, cod_destino, config):
    fila = df_competitividad[
        (df_competitividad["CODIGO_ORIGEN"] == cod_origen) &
        (df_competitividad["CODIGO_DESTINO"] == cod_destino) &
        (df_competitividad["CONFIGURACION"] == config)
    ]
    if fila.empty:
        return {"nivel": "ND", "empresas": "ND", "participacion": "ND"}

    f = fila.iloc[0]
    top1 = f["PARTICIPACION_MAXIMA"]
    if top1 >= 0.6:
        nivel = "Muy baja"
    elif top1 >= 0.4:
        nivel = "Baja"
    elif top1 >= 0.25:
        nivel = "Media"
    else:
        nivel = "Alta"
    return {
        "nivel": nivel,
        "empresas": int(f["NUM_EMPRESAS"]),
        "participacion": round(top1 * 100, 1)
    }

@app.post("/consulta")
def calcular_sicetac(data: ConsultaInput):
    origen_info = helper.buscar_municipio(data.origen)
    destino_info = helper.buscar_municipio(data.destino)

    if not origen_info or not destino_info:
        raise HTTPException(status_code=404, detail="Origen o destino no encontrado")

    cod_origen = origen_info["codigo_dane"]
    cod_destino = destino_info["codigo_dane"]

    ruta = df_rutas[
        (df_rutas["codigo_dane_origen"] == cod_origen) &
        (df_rutas["codigo_dane_destino"] == cod_destino)
    ]
    if ruta.empty:
        ruta = df_rutas[
            (df_rutas["codigo_dane_origen"] == cod_destino) &
            (df_rutas["codigo_dane_destino"] == cod_origen)
        ]

    if ruta.empty:
        if any([data.km_plano, data.km_ondulado, data.km_montañoso, data.km_urbano, data.km_despavimentado]):
            fila_ruta = None
            distancias = {
                'KM_PLANO': data.km_plano,
                'KM_ONDULADO': data.km_ondulado,
                'KM_MONTAÑOSO': data.km_montañoso,
                'KM_URBANO': data.km_urbano,
                'KM_DESPAVIMENTADO': data.km_despavimentado,
            }
        else:
            raise HTTPException(status_code=404, detail="Ruta no registrada y no se proporcionaron distancias manuales")
    else:
        fila_ruta = ruta.iloc[0]
        distancias = {
            'KM_PLANO': fila_ruta.get("KM_PLANO", 0),
            'KM_ONDULADO': fila_ruta.get("KM_ONDULADO", 0),
            'KM_MONTAÑOSO': fila_ruta.get("KM_MONTAÑOSO", 0),
            'KM_URBANO': fila_ruta.get("KM_URBANO", 0),
            'KM_DESPAVIMENTADO': fila_ruta.get("KM_DESPAVIMENTADO", 0),
        }

    vehiculos_validos = df_vehiculos["TIPO_VEHICULO"].astype(str).str.upper().unique()
    if data.vehiculo.strip().upper() not in vehiculos_validos:
        raise HTTPException(
            status_code=400,
            detail=f"Vehículo '{data.vehiculo}' no encontrado. Opciones válidas: {', '.join(vehiculos_validos)}"
        )

    meses_validos = df_parametros["MES"].unique().tolist()
    if int(data.mes) not in meses_validos:
        raise HTTPException(
            status_code=400,
            detail=f"Mes '{data.mes}' no válido. Debe ser uno de: {meses_validos}"
        )

    resultado = calcular_modelo_sicetac_extendido(
        origen=data.origen,
        destino=data.destino,
        configuracion=data.vehiculo,
        serie=int(data.mes),
        distancias=distancias,
        valor_peaje_manual=data.valor_peaje_manual,
        matriz_parametros=df_parametros,
        matriz_costos_fijos=df_costos_fijos,
        matriz_vehicular=df_vehiculos,
        rutas_df=df_rutas,
        peajes_df=df_peajes,
        carroceria_especial=data.carroceria,
        ruta_oficial=fila_ruta,
        horas_logisticas=data.horas_logisticas
    )

    resultado_convertido = convertir_nativos(resultado)

    # Enriquecimiento de contexto
    clave_ruta_config = f"{cod_origen}-{cod_destino}-{data.vehiculo}"
    valor_mercado = obtener_valor_mercado(data.mes, clave_ruta_config)
    ind_origen = obtener_indicadores(cod_origen)
    ind_destino = obtener_indicadores(cod_destino)
    competitividad = evaluar_competitividad(cod_origen, cod_destino, data.vehiculo)

    respuesta = {
        "SICETAC": resultado_convertido,
        "VALOR_MERCADO_2025": valor_mercado,
        "INDICADORES_ORIGEN": ind_origen,
        "INDICADORES_DESTINO": ind_destino,
        "COMPETITIVIDAD": competitividad
    }

    return JSONResponse(content=respuesta)
