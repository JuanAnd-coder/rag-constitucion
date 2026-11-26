"""Lista los modelos de Gemini que pueden generar texto con tu clave.

Uso (desde la raíz del proyecto):   python -m src.modelos
Copia el nombre de un modelo "flash" al archivo .env como GEMINI_MODEL=nombre
"""
from src.embeddings import crear_cliente

EXCLUIR = ("image", "tts", "live", "audio", "embedding", "robotics", "computer-use", "veo", "imagen")

client = crear_cliente()
for m in client.models.list():
    nombre = m.name.replace("models/", "")
    if "generateContent" in (m.supported_actions or []) and not any(x in nombre for x in EXCLUIR):
        print(nombre)