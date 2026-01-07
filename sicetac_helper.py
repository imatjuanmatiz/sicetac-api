import pandas as pd
from difflib import get_close_matches
import logging
import numpy as np

logging.basicConfig(level=logging.INFO)


class SICETACHelper:
    def __init__(self, archivo_municipios: str):
        """
        Helper para trabajar con municipios y rutas SICETAC.
        """
        self.df_municipios = pd.read_excel(archivo_municipios)
        self.columnas_municipios = [
            "nombre_oficial",
            "variacion_1",
            "variacion_2",
            "variacion_3",
        ]
        self.codigo_municipio_col = "codigo_dane"

    def _convertir_a_nativo(self, valor):
        """Convierte tipos de numpy a tipos nativos de Python."""
        if isinstance(valor, (np.integer, np.int64, np.int32)):
            return int(valor)
        elif isinstance(valor, (np.floating, np.float64, np.float32)):
            return float(valor)
        elif isinstance(valor, np.bool_):
            return bool(valor)
        elif pd.isna(valor):
            return None
        return valor

    def buscar_municipio(self, nombre_input: str):
        """Busca un municipio por nombre."""
        resultado = self._buscar_codigo(
            self.df_municipios,
            nombre_input,
            self.columnas_municipios,
            self.codigo_municipio_col,
            ["departamento", "nombre_oficial"],
        )
        if resultado:
            resultado = {k: self._convertir_a_nativo(v) for k, v in resultado.items()}
            logging.info(f"✓ Municipio encontrado: {resultado}")
        else:
            logging.warning(f"✘ Municipio NO encontrado: {nombre_input}")
        return resultado

    def _buscar_codigo(self, df, nombre_input, columnas_nombres, codigo_col, extra_cols=None):
        """Búsqueda exacta y luego aproximada por nombre."""
        nombre_input = str(nombre_input).strip().upper()

        # 1. Búsqueda exacta
        for col in columnas_nombres:
            if col in df.columns:
                match = df[df[col].astype(str).str.upper().fillna("") == nombre_input]
                if not match.empty:
                    row = match.iloc[0]
                    result = {codigo_col: row[codigo_col]}
                    if extra_cols:
                        for c in extra_cols:
                            if c in row:
                                result[c] = row[c]
                    return result

        # 2. Búsqueda aproximada
        for col in columnas_nombres:
            if col in df.columns:
                opciones = df[col].dropna().astype(str).str.upper().unique().tolist()
                cercanos = get_close_matches(nombre_input, opciones, n=1, cutoff=0.8)
                if cercanos:
                    match = df[df[col].astype(str).str.upper() == cercanos[0]]
                    if not match.empty:
                        row = match.iloc[0]
                        result = {codigo_col: row[codigo_col]}
                        if extra_cols:
                            for c in extra_cols:
                                if c in row:
                                    result[c] = row[c]
                        result["coincidencia_aproximada"] = cercanos[0]
                        return result
        return None

    def obtener_municipio_por_codigo(self, codigo_dane):
        """Devuelve municipio por código DANE."""
        try:
            codigo_dane = int(codigo_dane)
        except Exception:
            return None

        fila = self.df_municipios[self.df_municipios[self.codigo_municipio_col] == codigo_dane]
        if fila.empty:
            return None
        return fila.iloc[0]

    # -------------------------------------------------------------------------
    # 🔥 OPTIMIZADO: Búsqueda de rutas usando códigos directamente
    # -------------------------------------------------------------------------
    def buscar_todas_las_rutas_por_codigos(self, cod_origen: int, cod_destino: int, df_rutas: pd.DataFrame):
        """
        Busca TODAS las rutas usando códigos DANE directamente.
        OPTIMIZADO: No vuelve a buscar municipios.
        """
        # Buscar en ambos sentidos
        rutas_directas = df_rutas[
            (df_rutas["codigo_dane_origen"] == cod_origen) &
            (df_rutas["codigo_dane_destino"] == cod_destino)
        ]
        
        rutas_inversas = df_rutas[
            (df_rutas["codigo_dane_origen"] == cod_destino) &
            (df_rutas["codigo_dane_destino"] == cod_origen)
        ]

        todas_rutas = pd.concat([rutas_directas, rutas_inversas], ignore_index=True)

        if todas_rutas.empty:
            return [], {"encontradas": 0}

        # Convertir a lista
        lista_rutas = []
        for idx, row in todas_rutas.iterrows():
            ruta_info = {col: self._convertir_a_nativo(row[col]) for col in row.index}
            ruta_info["km_total"] = float(
                row.get("KM_PLANO", 0) +
                row.get("KM_ONDULADO", 0) +
                row.get("KM_MONTAÑOSO", 0) +
                row.get("KM_URBANO", 0) +
                row.get("KM_DESPAVIMENTADO", 0)
            )
            lista_rutas.append(ruta_info)

        return lista_rutas, {"encontradas": len(lista_rutas), "multiples_rutas": len(lista_rutas) > 1}

    def buscar_todas_las_rutas(self, origen_input: str, destino_input: str, df_rutas: pd.DataFrame):
        """
        Busca TODAS las rutas disponibles - Wrapper con búsqueda de municipios.
        """
        origen_info = self.buscar_municipio(origen_input)
        destino_info = self.buscar_municipio(destino_input)

        if not origen_info or not destino_info:
            return [], {
                "error": "Municipios no encontrados",
                "origen_valido": origen_info is not None,
                "destino_valido": destino_info is not None
            }

        cod_origen = int(origen_info["codigo_dane"])
        cod_destino = int(destino_info["codigo_dane"])

        lista_rutas, info = self.buscar_todas_las_rutas_por_codigos(cod_origen, cod_destino, df_rutas)

        if not lista_rutas:
            return [], {
                "encontradas": 0,
                "cod_origen": cod_origen,
                "cod_destino": cod_destino,
                "origen_nombre": origen_info.get("nombre_oficial"),
                "destino_nombre": destino_info.get("nombre_oficial"),
                "mensaje": f"No existen rutas entre {origen_info.get('nombre_oficial')} y {destino_info.get('nombre_oficial')}"
            }

        info.update({
            "cod_origen": cod_origen,
            "cod_destino": cod_destino,
            "origen_nombre": origen_info.get("nombre_oficial"),
            "destino_nombre": destino_info.get("nombre_oficial")
        })

        return lista_rutas, info

    def buscar_ruta_por_id(self, id_sice, df_rutas: pd.DataFrame):
        """Busca una ruta específica por ID_SICE."""
        try:
            id_sice_int = int(id_sice)
            ruta = df_rutas[df_rutas["ID_SICE"] == id_sice_int]
        except:
            ruta = df_rutas[df_rutas["ID_SICE"] == id_sice]
        
        if ruta.empty:
            return None, {"error": f"No se encontró ruta con ID_SICE: {id_sice}"}
        
        fila = ruta.iloc[0]
        info = {
            "encontrada": True,
            "id_sice": self._convertir_a_nativo(fila.get("ID_SICE")),
            "origen": self._convertir_a_nativo(fila.get("codigo_dane_origen")),
            "destino": self._convertir_a_nativo(fila.get("codigo_dane_destino")),
            "km_total": float(
                fila.get("KM_PLANO", 0) +
                fila.get("KM_ONDULADO", 0) +
                fila.get("KM_MONTAÑOSO", 0) +
                fila.get("KM_URBANO", 0) +
                fila.get("KM_DESPAVIMENTADO", 0)
            )
        }
        return fila, info

    def buscar_ruta(self, origen_input: str, destino_input: str, df_rutas: pd.DataFrame):
        """
        🔥 OPTIMIZADO: Busca municipios UNA SOLA VEZ y luego busca rutas.
        """
        info = {
            "origen_solicitado": origen_input,
            "destino_solicitado": destino_input,
            "codigo_origen_solicitado": None,
            "codigo_destino_solicitado": None,
            "nombre_origen": None,
            "nombre_destino": None,
            "ruta_encontrada": False,
            "ruta_id": None,
            "total_rutas_disponibles": 0,
            "rutas_alternativas": [],
            "mensaje": "",
            "requiere_distancias_manuales": False
        }

        # 1. Buscar municipios UNA SOLA VEZ
        origen_info = self.buscar_municipio(origen_input)
        destino_info = self.buscar_municipio(destino_input)

        if not origen_info:
            info["mensaje"] = f"Municipio de origen '{origen_input}' no encontrado."
            info["requiere_distancias_manuales"] = True
            return None, info

        if not destino_info:
            info["mensaje"] = f"Municipio de destino '{destino_input}' no encontrado."
            info["requiere_distancias_manuales"] = True
            return None, info

        cod_origen = int(origen_info["codigo_dane"])
        cod_destino = int(destino_info["codigo_dane"])
        
        info["codigo_origen_solicitado"] = cod_origen
        info["codigo_destino_solicitado"] = cod_destino
        info["nombre_origen"] = origen_info.get("nombre_oficial")
        info["nombre_destino"] = destino_info.get("nombre_oficial")

        # 2. Buscar rutas usando CÓDIGOS (sin volver a buscar municipios)
        lista_rutas, info_busqueda = self.buscar_todas_las_rutas_por_codigos(
            cod_origen, cod_destino, df_rutas
        )

        if not lista_rutas:
            # Ruta NO existe
            info["mensaje"] = (
                f"La ruta {info['nombre_origen']} → {info['nombre_destino']} "
                f"no está registrada en SICETAC. "
                f"Proporcione las distancias manualmente."
            )
            info["requiere_distancias_manuales"] = True
            logging.warning(f"⚠️ Ruta no encontrada: {origen_input} → {destino_input}")
            return None, info

        # Ruta EXISTE
        id_sice = lista_rutas[0]["ID_SICE"]
        fila_principal = df_rutas[df_rutas["ID_SICE"] == id_sice].iloc[0]
        
        info["ruta_encontrada"] = True
        info["ruta_id"] = self._convertir_a_nativo(id_sice)
        info["total_rutas_disponibles"] = len(lista_rutas)
        info["mensaje"] = f"Ruta encontrada en SICETAC: {info['nombre_origen']} → {info['nombre_destino']}"

        # Rutas alternativas
        if len(lista_rutas) > 1:
            info["rutas_alternativas"] = []
            for ruta in lista_rutas[1:]:
                info["rutas_alternativas"].append({
                    "id_sice": self._convertir_a_nativo(ruta.get("ID_SICE")),
                    "km_total": float(ruta.get("km_total", 0)),
                    "km_plano": float(ruta.get("KM_PLANO", 0)),
                    "km_ondulado": float(ruta.get("KM_ONDULADO", 0)),
                    "km_montañoso": float(ruta.get("KM_MONTAÑOSO", 0)),
                    "km_urbano": float(ruta.get("KM_URBANO", 0)),
                    "km_despavimentado": float(ruta.get("KM_DESPAVIMENTADO", 0))
                })
            info["mensaje"] += f" ({len(lista_rutas)} rutas disponibles)"

        logging.info(f"✓ Ruta encontrada: {origen_input} → {destino_input} (ID: {info['ruta_id']})")
        return fila_principal, info

    def obtener_estadisticas_rutas(self, df_rutas: pd.DataFrame):
        """Estadísticas generales de SICETAC."""
        total_rutas = len(df_rutas)
        rutas_unicas = len(df_rutas["ID_SICE"].unique())
        
        origenes = set(df_rutas["codigo_dane_origen"].unique())
        destinos = set(df_rutas["codigo_dane_destino"].unique())
        municipios_con_rutas = origenes.union(destinos)
        
        df_rutas_temp = df_rutas.copy()
        df_rutas_temp["par_origen_destino"] = (
            df_rutas_temp["codigo_dane_origen"].astype(str) + "-" + 
            df_rutas_temp["codigo_dane_destino"].astype(str)
        )
        rutas_con_alternativas = df_rutas_temp["par_origen_destino"].value_counts()
        rutas_con_multiples = len(rutas_con_alternativas[rutas_con_alternativas > 1])
        
        return {
            "total_registros_rutas": int(total_rutas),
            "rutas_unicas": int(rutas_unicas),
            "municipios_con_rutas": len(municipios_con_rutas),
            "total_municipios_db": len(self.df_municipios),
            "cobertura_pct": round(len(municipios_con_rutas) / len(self.df_municipios) * 100, 2),
            "pares_con_multiples_rutas": int(rutas_con_multiples)
        }