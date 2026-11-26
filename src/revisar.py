"""Muestra el texto limpio alrededor de los artículos 175 a 177 para ver cómo viene en el PDF.
 
Uso (desde la raíz del proyecto):   python -m src.revisar
"""
import re
 
from src import procesar
 
lineas = procesar.limpiar(procesar.extraer_texto())
for i, linea in enumerate(lineas):
    if re.match(r"(?i)art[ií]culo\s+17[5-7]\b", linea):
        print(f"--- línea {i} ---")
        for x in lineas[max(0, i - 2): i + 4]:
            print("   ", x[:130])
 
