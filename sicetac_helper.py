import pandas as pd
from difflib import get_close_matches
import logging
import numpy as np

logging.basicConfig(level=logging.INFO)


class SICETACHelper:
    def __init__(self, archivo_municipios: str):
        """
        Helper para trabajar con municipios y rutas SICETAC.
        Carga el archivo de municipios, que debe incluir:
        - codigo_dane
        - nombre_oficial
        - variacion_1, variacion_2, variacion_3 (nombres alternos)
        - departamento
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
        """
        Convierte tipos de numpy a tipos nativos de Python.
        Esto es crítico para la serialización JSON.
        """
        if isinstance(valor, (np.integer, np.int64, np.int32)):
            return int(valor)
        elif isinstance(valor, (np.floating, np.float64, np.float32)):
            return float(valor)
        elif isinstance(valor, np.bool_):
            return bool(valor)
        elif pd.isna(valor):
            return None
        return valor

    # -------------------------------------------------------------------------
    # BÚSQUEDA DE MUNICIPIOS
    # -------------------------------------------------------------------------
    def buscar_municipio(self, nombre_input: str):
        """
        Busca un municipio por nombre (oficial o variaciones).
        Devuelve dict con:
        - codigo_dane (int nativo, NO numpy)
        - departamento
        - nombre_oficial
        - (opcional) coincidencia_aproximada
        """
        resultado = self._buscar_codigo(
            self.df_municipios,
            nombre_input,
            self.columnas_municipios,
            self.codigo_municipio_col,
            ["departamento", "nombre_oficial"],
        )
        if resultado:
            # Convertir todos los valores a tipos nativos
            resultado = {k: self._convertir_a_nativo(v) for k, v in resultado.items()}
            logging.info(f"✓ Municipio encontrado: {resultado}")
        else:
            logging.warning(f"✘ Municipio NO encontrado: {nombre_input}")
        return resultado

    def _buscar_codigo(
        self,
        df: pd.DataFrame,
        nombre_input: str,
        columnas_nombres,
        codigo_col: str,
        extra_cols=None,
    ):
        """
        Búsqueda exacta y luego aproximada por nombre.
        """
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

        # 2. Búsqueda aproximada (fuzzy)
        for col in columnas_nombres:
            if col in df.columns:
                opciones = (
                    df[col].dropna().astype(str).str.upper().unique().tolist()
                )
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
        """
        Devuelve la fila del municipio (Series) dado su código DANE,
        o None si no existe.
        """
        try:
            codigo_dane = int(codigo_dane)
        except Exception:
            return None

        fila = self.df_municipios[
            self.df_municipios[self.codigo_municipio_col] == codigo_dane
        ]
        if fila.empty:
            return None
        return fila.iloc[0]

    # -------------------------------------------------------------------------
    # 🆕 BÚSQUEDA DE TODAS LAS RUTAS (MÚLTIPLES VÍAS)
    # -------------------------------------------------------------------------
    def buscar_todas_las_rutas(self, origen_input: str, destino_input: str, df_rutas: pd.DataFrame):
        """
        Busca TODAS las rutas disponibles entre origen y destino.
        Útil cuando existen vías alternativas.
        
        Retorna:
        - lista de rutas (dict con info de cada ruta)
        - info sobre la búsqueda
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

        # Buscar en ambos sentidos
        rutas_directas = df_rutas[
            (df_rutas["codigo_dane_origen"] == cod_origen)
            & (df_rutas["codigo_dane_destino"] == cod_destino)
        ]
        
        rutas_inversas = df_rutas[
            (df_rutas["codigo_dane_origen"] == cod_destino)
            & (df_rutas["codigo_dane_destino"] == cod_origen)
        ]

        # Combinar resultados
        todas_rutas = pd.concat([rutas_directas, rutas_inversas], ignore_index=True)

        if todas_rutas.empty:
            return [], {
                "encontradas": 0,
                "cod_origen": cod_origen,
                "cod_destino": cod_destino,
                "origen_nombre": origen_info.get("nombre_oficial"),
                "destino_nombre": destino_info.get("nombre_oficial"),
                "mensaje": f"No existen rutas registradas en SICETAC entre {origen_info.get('nombre_oficial')} y {destino_info.get('nombre_oficial')}"
            }

        # Convertir a lista de diccionarios con tipos nativos
        lista_rutas = []
        for idx, row in todas_rutas.iterrows():
            ruta_info = {}
            for col in row.index:
                ruta_info[col] = self._convertir_a_nativo(row[col])
            
            # Agregar información adicional
            ruta_info["km_total"] = (
                float(row.get("KM_PLANO", 0)) +
                float(row.get("KM_ONDULADO", 0)) +
                float(row.get("KM_MONTAÑOSO", 0)) +
                float(row.get("KM_URBANO", 0)) +
                float(row.get("KM_DESPAVIMENTADO", 0))
            )
            lista_rutas.append(ruta_info)

        info = {
            "encontradas": len(lista_rutas),
            "multiples_rutas": len(lista_rutas) > 1,
            "cod_origen": cod_origen,
            "cod_destino": cod_destino,
            "origen_nombre": origen_info.get("nombre_oficial"),
            "destino_nombre": destino_info.get("nombre_oficial")
        }

        return lista_rutas, info

    # -------------------------------------------------------------------------
    # 🆕 BUSCAR RUTA POR ID_SICE ESPECÍFICO
    # -------------------------------------------------------------------------
    def buscar_ruta_por_id(self, id_sice: str, df_rutas: pd.DataFrame):
        """
        Busca una ruta específica por su ID_SICE.
        Útil cuando el usuario quiere usar una ruta alternativa específica.
        """
        # Convertir id_sice a tipo apropiado
        try:
            id_sice_int = int(id_sice)
            ruta = df_rutas[df_rutas["ID_SICE"] == id_sice_int]
        except:
            ruta = df_rutas[df_rutas["ID_SICE"] == id_sice]
        
        if ruta.empty:
            return None, {"error": f"No se encontró ruta con ID_SICE: {id_sice}"}
        
        fila = ruta.iloc[0]
        
        # Convertir valores a tipos nativos
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

    # -------------------------------------------------------------------------
    # ✨ BÚSQUEDA SIMPLE Y CLARA DE RUTA
    # -------------------------------------------------------------------------
    def buscar_ruta(self, origen_input: str, destino_input: str, df_rutas: pd.DataFrame):
        """
        Busca una ruta exacta origen-destino en SICETAC.
        
        SI LA RUTA NO EXISTE: Retorna None y mensaje claro pidiendo distancias manuales.
        NO HACE APROXIMACIONES GEOGRÁFICAS.
        
        Devuelve (fila_ruta, info_ruta), donde:
        - fila_ruta: row de df_rutas (primera ruta si hay múltiples) o None
        - info_ruta: dict con información detallada (tipos nativos Python)
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

        # 1. Buscar códigos DANE de municipios
        origen_info = self.buscar_municipio(origen_input)
        destino_info = self.buscar_municipio(destino_input)

        if not origen_info:
            info["mensaje"] = f"Municipio de origen '{origen_input}' no encontrado en la base de datos."
            info["requiere_distancias_manuales"] = True
            return None, info

        if not destino_info:
            info["mensaje"] = f"Municipio de destino '{destino_input}' no encontrado en la base de datos."
            info["requiere_distancias_manuales"] = True
            return None, info

        cod_origen = int(origen_info["codigo_dane"])
        cod_destino = int(destino_info["codigo_dane"])
        
        info["codigo_origen_solicitado"] = cod_origen
        info["codigo_destino_solicitado"] = cod_destino
        info["nombre_origen"] = origen_info.get("nombre_oficial")
        info["nombre_destino"] = destino_info.get("nombre_oficial")

        # 2. Buscar todas las rutas disponibles
        lista_rutas, info_busqueda = self.buscar_todas_las_rutas(origen_input, destino_input, df_rutas)

        if not lista_rutas:
            # ❌ RUTA NO EXISTE EN SICETAC
            info["mensaje"] = (
                f"La ruta {info['nombre_origen']} → {info['nombre_destino']} "
                f"no está registrada en SICETAC. "
                f"Por favor, proporcione las distancias manualmente (km_plano, km_ondulado, etc.)."
            )
            info["requiere_distancias_manuales"] = True
            logging.warning(f"⚠️ Ruta no encontrada: {origen_input} → {destino_input}")
            return None, info

        # ✅ RUTA EXISTE
        # Buscar la fila completa en el DataFrame
        id_sice = lista_rutas[0]["ID_SICE"]
        fila_principal = df_rutas[df_rutas["ID_SICE"] == id_sice].iloc[0]
        
        info["ruta_encontrada"] = True
        info["ruta_id"] = self._convertir_a_nativo(id_sice)
        info["total_rutas_disponibles"] = len(lista_rutas)
        info["mensaje"] = f"Ruta encontrada en SICETAC: {info['nombre_origen']} → {info['nombre_destino']}"

        # Si hay múltiples rutas, listar las alternativas
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
            
            info["mensaje"] += f" (Se encontraron {len(lista_rutas)} rutas alternativas)"

        logging.info(f"✓ Ruta encontrada: {origen_input} → {destino_input} (ID: {info['ruta_id']})")
        return fila_principal, info

    # -------------------------------------------------------------------------
    # 📊 ESTADÍSTICAS DE RUTAS
    # -------------------------------------------------------------------------
    def obtener_estadisticas_rutas(self, df_rutas: pd.DataFrame):
        """
        Retorna estadísticas generales sobre las rutas en SICETAC.
        Útil para informar al usuario sobre la cobertura del sistema.
        """
        total_rutas = len(df_rutas)
        rutas_unicas = len(df_rutas["ID_SICE"].unique())
        
        # Municipios con rutas registradas
        origenes = set(df_rutas["codigo_dane_origen"].unique())
        destinos = set(df_rutas["codigo_dane_destino"].unique())
        municipios_con_rutas = origenes.union(destinos)
        
        # Rutas más comunes (origen-destino)
        df_rutas["par_origen_destino"] = (
            df_rutas["codigo_dane_origen"].astype(str) + "-" + 
            df_rutas["codigo_dane_destino"].astype(str)
        )
        rutas_con_alternativas = df_rutas["par_origen_destino"].value_counts()
        rutas_con_multiples = len(rutas_con_alternativas[rutas_con_alternativas > 1])
        
        return {
            "total_registros_rutas": int(total_rutas),
            "rutas_unicas": int(rutas_unicas),
            "municipios_con_rutas": len(municipios_con_rutas),
            "total_municipios_db": len(self.df_municipios),
            "cobertura_pct": round(len(municipios_con_rutas) / len(self.df_municipios) * 100, 2),
            "pares_con_multiples_rutas": int(rutas_con_multiples)
        }