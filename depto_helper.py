import pandas as pd
from difflib import get_close_matches

class DeptoHelper:
    def __init__(self, archivo):
        self.df = pd.read_excel(archivo)
        self.variantes = [col for col in self.df.columns if col.startswith('VARIANTE') or col == 'DEPARTAMENTO']
        self.col_id = 'ID DEPTO'
        
    def buscar_id(self, nombre):
        nombre = str(nombre).strip().upper()
        for col in self.variantes:
            if col in self.df.columns:
                match = self.df[self.df[col].astype(str).str.upper().fillna('') == nombre]
                if not match.empty:
                    return int(match.iloc[0][self.col_id])
        for col in self.variantes:
            if col in self.df.columns:
                opciones = self.df[col].dropna().astype(str).str.upper().unique().tolist()
                cercanos = get_close_matches(nombre, opciones, n=1, cutoff=0.8)
                if cercanos:
                    match = self.df[self.df[col].astype(str).str.upper() == cercanos[0]]
                    if not match.empty:
                        return int(match.iloc[0][self.col_id])
        return None

    def buscar_nombre(self, id_depto):
        match = self.df[self.df[self.col_id] == id_depto]
        if not match.empty:
            return str(match.iloc[0]['DEPARTAMENTO'])
        return None
