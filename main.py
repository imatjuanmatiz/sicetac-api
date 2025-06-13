from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import pandas as pd
from sicetac_helper import SICETACHelper
from modelo_sicetac import calcular_modelo_sicetac_extendido

app = FastAPI(title="API SICETAC", version="1.1")

class ConsultaInput(BaseModel):
    origen: str
    destino: str
    vehiculo: str = "C3S3"
    mes: int = 202506
    carroceria: str = "GENERAL"
    valor_peaje_manual: float = 0.0
    horas_logisticas: float = None

# Cargar archivos
ARCHIVOS = {
    "municipios": "municipios.xlsx",
    "vehiculos": "CONFIGURACION_VEHICULAR_LIMPIO.xlsx",
    "parametros": "MATRIZ_CAMBIOS_PARAMETROS_LIMPIO.xlsx",
    "costos_fijos": "COSTO_FIJO_ACTUALIZADO.xlsx",
    "peajes": "PEAJES_LIMPIO.xlsx",
    "rutas": "RUTA_DISTANCIA_LIMPIO.xlsx"
}

df_municipios = pd.read_excel(ARCHIVOS["municipios"])
df_vehiculos = pd.read_excel(ARCHIVOS["vehiculos"])
df_parametros = pd.read_excel(ARCHIVOS["parametros"])
df_costos_fijos = pd.read_excel(ARCHIVOS["costos_fijos"])
df_peajes = pd.read_excel(ARCHIVOS["peajes"])
df_rutas = pd.read_excel(ARCHIVOS["rutas"])

helper = SICETACHelper(ARCHIVOS["municipios"])

@app.post("/consulta")
def calcular_sicetac(data: ConsultaInput):
    # Validar origen y destino
    origen_info = helper.buscar_municipio(data.origen)
    destino_info = helper.buscar_municipio(data.destino)

    if not origen_info or not destino_info:
        raise HTTPException(status_code=404, detail="Origen o destino no encontrado")

    # Validar existencia de la ruta
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
            raise HTTPException(status_code=404, detail="Ruta no registrada entre los municipios seleccionados")

    fila_ruta = ruta.iloc[0]
    distancias = {
        'KM_PLANO': fila_ruta.get("KM_PLANO", 0),
        'KM_ONDULADO': fila_ruta.get("KM_ONDULADO", 0),
        'KM_MONTAÑOSO': fila_ruta.get("KM_MONTAÑOSO", 0),
        'KM_URBANO': fila_ruta.get("KM_URBANO", 0),
        'KM_DESPAVIMENTADO': fila_ruta.get("KM_DESPAVIMENTADO", 0),
    }

    # Validar vehículo directamente desde el DataFrame
    vehiculos_validos = df_vehiculos["TIPO_VEHICULO"].astype(str).str.upper().unique()
    if data.vehiculo.strip().upper() not in vehiculos_validos:
        raise HTTPException(
            status_code=400,
            detail=f"Vehículo '{data.vehiculo}' no encontrado. Opciones válidas: {', '.join(vehiculos_validos)}"
        )

    # Validar mes
    meses_validos = df_parametros["MES"].unique().tolist()
    if int(data.mes) not in meses_validos:
        raise HTTPException(
            status_code=400,
            detail=f"Mes '{data.mes}' no válido. Debe ser uno de: {meses_validos}"
        )

    # Ejecutar el modelo
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

    return resultado
