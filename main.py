from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import pandas as pd
from fastapi.responses import JSONResponse
from sicetac_helper import SICETACHelper
from modelo_sicetac import calcular_modelo_sicetac_extendido
from contexto_helper import (
    obtener_valores_promedio_mercado,
    obtener_indicadores,
    evaluar_competitividad,
    obtener_meses_disponibles_mercado,
    obtener_meses_disponibles_indicador
)

app = FastAPI(title="API SICETAC", version="1.4")

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

# Carga fija
helper = SICETACHelper(ARCHIVOS["municipios"])
df_vehiculos = pd.read_excel(ARCHIVOS["vehiculos"])
df_parametros = pd.read_excel(ARCHIVOS["parametros"])
df_costos_fijos = pd.read_excel(ARCHIVOS["costos_fijos"])
df_peajes = pd.read_excel(ARCHIVOS["peajes"])
df_rutas = pd.read_excel(ARCHIVOS["rutas"])
df_indicadores = pd.read_excel("indice_cargue_descargue_resumen_mensual.xlsx")

def convertir_nativos(d):
    if isinstance(d, dict):
        return {k: convertir_nativos(v) for k, v in d.items()}
    elif isinstance(d, list):
        return [convertir_nativos(v) for v in d]
    elif hasattr(d, 'item'):
        return d.item()
    else:
        return d

@app.post("/consulta")
def calcular_sicetac(data: ConsultaInput):
    origen_info = helper.buscar_municipio(data.origen)
    destino_info = helper.buscar_municipio(data.destino)

    if not origen_info or not destino_info:
        raise HTTPException(status_code=404, detail="Origen o destino no encontrado")

    cod_origen = origen_info["codigo_dane"]
    cod_destino = destino_info["codigo_dane"]

    # Buscar ruta en la base
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

    vehiculo_upper = data.vehiculo.strip().upper().replace("C", "")
    vehiculos_validos = df_vehiculos["TIPO_VEHICULO"].astype(str).str.upper().str.replace("C", "").unique()

    if vehiculo_upper not in vehiculos_validos:
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

    # Calcular SICETAC
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

    # Compilar respuesta
    respuesta = {
        "SICETAC": resultado_convertido,
        "HISTORICO_VALOR_MERCADO": obtener_valores_promedio_mercado(cod_origen, cod_destino, vehiculo_upper),
        "INDICADORES_ORIGEN": obtener_indicadores(cod_origen, vehiculo_upper),
        "INDICADORES_DESTINO": obtener_indicadores(cod_destino, vehiculo_upper),
        "COMPETITIVIDAD": evaluar_competitividad(cod_origen, cod_destino, vehiculo_upper),
        "MESES_MERCADO_DISPONIBLES": obtener_meses_disponibles_mercado(cod_origen, cod_destino, vehiculo_upper),
        "MESES_INDICADORES_ORIGEN": obtener_meses_disponibles_indicador(df_indicadores, cod_origen, vehiculo_upper),
        "MESES_INDICADORES_DESTINO": obtener_meses_disponibles_indicador(df_indicadores, cod_destino, vehiculo_upper)
    }

    return JSONResponse(content=respuesta)
