"""Configuración compartida por todos los scripts.
 
Lee las variables del archivo .env que está en la raíz del proyecto
(la carpeta que contiene docker-compose.yml). Este archivo va dentro de src/.
"""
import os
from pathlib import Path
 
from dotenv import load_dotenv
 
ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
 
# ---------- Archivos ----------
DATA_DIR = ROOT / "data"
PDF_PATH = DATA_DIR / "constitucion.pdf"
TXT_PATH = DATA_DIR / "constitucion.txt"   # alternativa si el PDF se extrae mal
CHUNKS_PATH = DATA_DIR / "chunks.json"
 
DOCUMENTO = "Constitución Política de Colombia 1991"
 
# ---------- Fragmentación (decisiones que hay que justificar en el video) ----------
MAX_CHARS = 1500      # tamaño máximo de un fragmento, en caracteres (unos 350-400 tokens)
SOLAPE_CHARS = 200    # caracteres que se repiten entre fragmentos consecutivos del mismo artículo
 
# ---------- Embeddings ----------
EMBEDDING_MODEL = "gemini-embedding-001"
EMBEDDING_DIM = 768   # DEBE coincidir con vector(768) de db/init.sql
 
# ---------- Base de datos ----------
DB_CONFIG = {
    "host": os.getenv("POSTGRES_HOST", "localhost"),
    "port": int(os.getenv("POSTGRES_PORT", "5432")),
    "dbname": os.getenv("POSTGRES_DB", "constitucion_rag"),
    "user": os.getenv("POSTGRES_USER", "rag"),
    "password": os.getenv("POSTGRES_PASSWORD", ""),
}
 
# ---------- Gemini ----------
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
 
# ---------- Recuperación y generación ----------
TOP_K = 5
GENERATION_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")