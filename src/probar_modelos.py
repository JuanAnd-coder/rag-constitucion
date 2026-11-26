"""Prueba qué modelos "flash" responden de verdad con tu clave.

Hace UNA llamada muy pequeña por modelo (con pausa entre llamadas).
Uso (desde la raíz del proyecto):   python -m src.probar_modelos
"""
import time

from google.genai import errors, types

from src.embeddings import crear_cliente

EXCLUIR = ("image", "tts", "live", "audio", "embedding", "banana", "omni",
           "preview", "robotics", "computer-use")

client = crear_cliente()
nombres = [
    m.name.replace("models/", "")
    for m in client.models.list()
    if "generateContent" in (m.supported_actions or [])
]
candidatos = [n for n in nombres if "flash" in n and not any(x in n for x in EXCLUIR)]
print(f"Probando {len(candidatos)} modelos...\n")

for nombre in candidatos:
    try:
        client.models.generate_content(
            model=nombre,
            contents="Responde solo con la palabra OK.",
            config=types.GenerateContentConfig(max_output_tokens=50),
        )
        print(f"  FUNCIONA  {nombre}")
    except errors.APIError as e:
        detalle = str(getattr(e, "message", e)).replace("\n", " ")[:90]
        print(f"  error {e.code}  {nombre}  {detalle}")
    time.sleep(6)

print("\n(error 429 = el modelo existe pero no tienes cupo en este momento)")