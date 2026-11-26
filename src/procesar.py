"""Paso 3: PDF (o TXT) -> texto limpio -> artículos -> fragmentos.

Resultado: data/chunks.json (un archivo que puedes abrir y revisar a mano).

Uso (desde la raíz del proyecto):   python -m src.procesar
"""
import json
import re
import statistics

import src.config as config

# ---------------------------------------------------------------
# 1. Patrones para reconocer la estructura del texto
# ---------------------------------------------------------------
# Líneas que se repiten en cada página y no son contenido.
# Ajusta esta lista después de mirar el texto extraído.
RUIDO = [
    re.compile(r"^\[\s*\d+\s*\]$"),                                  # "[ 13 ]"
    re.compile(r"^Constituci[oó]n Pol[ií]tica de Colombia( 1991)?$", re.IGNORECASE),
    re.compile(r"^Sala Administrativa$", re.IGNORECASE),
    re.compile(r"^Consejo Superior de la Judicatura$"),
]

# (?i:...) hace insensible a mayúsculas solo la palabra; los números romanos
# deben ir en mayúscula para no confundir "Título civil..." con un encabezado.
RE_TITULO = re.compile(r"^(?i:T[IÍ]TULO)\s+([IVXLC]+)\b[\s.\-–]*(.*)$")
RE_CAPITULO = re.compile(r"^(?i:CAP[IÍ]TULO)\s+(\d+|[IVXLC]+|(?i:[UÚ]NICO))\b[\s.\-–]*(.*)$")
# "ARTÍCULO 1º.", "Artículo 10.", "ARTÍCULO TRANSITORIO 3.", "ARTÍCULO 12 TRANSITORIO."
# Exige un punto o guion después del número: así "artículo 12 de esta
# Constitución" al inicio de una línea NO se confunde con un encabezado.
# Excepción: "Artículo 176 Modificado por el Acto Legislativo..." (sin punto), que
# es como esta edición presenta algunos artículos reformados.
RE_ARTICULO = re.compile(
    r"^(?i:ART[IÍ]CULO)\s+((?i:TRANSITORIO)\s+)?(\d+)\s*[ºo°]?\s*((?i:TRANSITORIO))?\s*"
    r"(?:[.\-–]+|(?=(?i:modificado|adicionado|derogado|subrogado)\b))\s*(.*)$"
)


# Un encabezado "Artículo N" solo cuenta como artículo nuevo si N es MAYOR que
# el último artículo aceptado. Esta edición de la Constitución incluye dentro del
# texto la numeración de los Actos Legislativos ("Artículo 2º. El cual quedará
# así: ..."), que NO son artículos nuevos: su número es menor que el del artículo
# que se está leyendo, así que se descartan.


# ---------------------------------------------------------------
# 2. Extracción y limpieza
# ---------------------------------------------------------------
def extraer_texto():
    """Devuelve el texto crudo. Usa data/constitucion.txt si existe; si no, el PDF."""
    if config.TXT_PATH.exists():
        print(f"Leyendo {config.TXT_PATH.name}")
        return config.TXT_PATH.read_text(encoding="utf-8")
    from pypdf import PdfReader  # import aquí para no exigirlo si usas el TXT

    print(f"Leyendo {config.PDF_PATH.name}")
    lector = PdfReader(config.PDF_PATH)
    return "\n".join((pagina.extract_text() or "") for pagina in lector.pages)


def limpiar(texto):
    """Quita ruido de página, une palabras cortadas con guion y devuelve una lista de líneas."""
    texto = texto.replace("\r", "")
    # "or-\nganizado" -> "organizado"
    texto = re.sub(r"(?<=\w)-\n(?=[a-záéíóúñ])", "", texto)
    lineas = []
    for linea in texto.split("\n"):
        linea = re.sub(r"\s+", " ", linea).strip()
        if not linea:
            continue
        if any(patron.match(linea) for patron in RUIDO):
            continue
        lineas.append(linea)
    return lineas


# ---------------------------------------------------------------
# 3. Reconocer títulos, capítulos y artículos
# ---------------------------------------------------------------
def parsear_articulos(lineas):
    # El índice del PDF también menciona los títulos: empezamos en el
    # encabezado del Título I que precede al artículo 1.
    inicio = 0
    for i, linea in enumerate(lineas):
        m = RE_ARTICULO.match(linea)
        if m and not m.group(1) and not m.group(3) and m.group(2) == "1":
            inicio = i
            for j in range(i - 1, max(i - 8, -1), -1):
                if RE_TITULO.match(lineas[j]):
                    inicio = j
                    break
            break

    estado = {"titulo": "", "capitulo": "", "pendiente": None}
    articulos, vistos = [], {}
    actual = None
    ultimo = 0  # último número de artículo (no transitorio) aceptado

    def fijar_nombre():
        """Termina de armar la etiqueta de un título/capítulo cuyo nombre venía en líneas siguientes."""
        pend = estado["pendiente"]
        if pend:
            clave, prefijo, partes = pend
            estado[clave] = f"{prefijo} - {' '.join(partes)}" if partes else prefijo
            estado["pendiente"] = None

    for linea in lineas[inicio:]:
        m_tit = RE_TITULO.match(linea)
        m_cap = RE_CAPITULO.match(linea)
        m_art = RE_ARTICULO.match(linea)

        if m_tit or m_cap or m_art:
            fijar_nombre()

        if m_tit:
            actual = None
            estado["capitulo"] = ""
            partes = [m_tit.group(2)] if m_tit.group(2) else []
            estado["pendiente"] = ["titulo", f"Título {m_tit.group(1)}", partes]
            continue

        if m_cap:
            actual = None
            partes = [m_cap.group(2)] if m_cap.group(2) else []
            estado["pendiente"] = ["capitulo", f"Capítulo {m_cap.group(1)}", partes]
            continue

        if m_art:
            transitorio = bool(m_art.group(1) or m_art.group(3))
            numero = m_art.group(2)

            if not transitorio:
                n = int(numero)
                if n <= ultimo:
                    # No es un artículo nuevo: es la numeración de un Acto Legislativo
                    # dentro del artículo actual. Conservamos solo su texto.
                    print(f"  Aviso: se ignora el encabezado 'Artículo {n}' (último válido: {ultimo})")
                    if actual is not None and m_art.group(4):
                        actual["lineas"].append(m_art.group(4))
                    continue
                if n > ultimo + 1:
                    print(f"  Aviso: salto de artículo {ultimo} a {n}")
                ultimo = n

            etiqueta = f"transitorio {numero}" if transitorio else numero
            veces = vistos.get(etiqueta, 0)
            vistos[etiqueta] = veces + 1
            if veces:  # etiqueta repetida: la hacemos única para no pisar datos
                print(f"  Aviso: artículo {etiqueta} aparece más de una vez")
                etiqueta = f"{etiqueta} (repetido {veces})"
            actual = {
                "etiqueta": etiqueta,
                "numero": None if transitorio else int(numero),
                "titulo": estado["titulo"],
                "capitulo": estado["capitulo"],
                "lineas": [m_art.group(4)] if m_art.group(4) else [],
            }
            articulos.append(actual)
            continue

        # Línea normal. Si estamos esperando el nombre de un título/capítulo
        # y la línea está TODA en mayúsculas, es parte de ese nombre.
        if estado["pendiente"] and linea.isupper():
            estado["pendiente"][2].append(linea)
            continue
        fijar_nombre()
        if actual is not None:
            actual["lineas"].append(linea)

    return articulos


# ---------------------------------------------------------------
# 4. Fragmentación
# ---------------------------------------------------------------
def dividir(texto, max_chars=config.MAX_CHARS, solape=config.SOLAPE_CHARS):
    """Parte un texto largo en trozos de ~max_chars con solape, sin cortar palabras."""
    if len(texto) <= max_chars:
        return [texto]
    partes, inicio = [], 0
    while inicio < len(texto):
        fin = min(inicio + max_chars, len(texto))
        if fin < len(texto):
            corte = texto.rfind(" ", inicio, fin)
            if corte > inicio:
                fin = corte
        partes.append(texto[inicio:fin].strip())
        if fin >= len(texto):
            break
        inicio = max(fin - solape, inicio + 1)
        sig = texto.find(" ", inicio, fin)       # empezar en el inicio de una palabra
        if sig != -1:
            inicio = sig + 1
    return partes


def fragmentar(articulos):
    chunks = []
    for art in articulos:
        texto = " ".join(art["lineas"]).strip()
        if not texto:
            print(f"  Aviso: artículo {art['etiqueta']} sin texto, se omite")
            continue
        for i, parte in enumerate(dividir(texto)):
            chunks.append({
                "documento": config.DOCUMENTO,
                "titulo": art["titulo"],
                "capitulo": art["capitulo"],
                "articulo": art["etiqueta"],
                "chunk_index": i,
                "contenido": f"Artículo {art['etiqueta']}. {parte}",
            })
    return chunks


# ---------------------------------------------------------------
# 5. Diagnóstico: ¿salió bien el parseo?
# ---------------------------------------------------------------
def diagnostico(articulos, chunks):
    numeros = {a["numero"] for a in articulos if a["numero"] is not None}
    faltantes = sorted(set(range(1, 381)) - numeros)
    largos = [len(c["contenido"]) for c in chunks]

    print("\n=== DIAGNÓSTICO ===")
    print(f"Artículos detectados: {len(articulos)} (esperado: 380 + transitorios)")
    print(f"Artículos numerados faltantes entre 1 y 380: {len(faltantes)} {faltantes[:30]}")
    print(f"Fragmentos generados: {len(chunks)}")
    if largos:
        print(f"Largo de fragmento (caracteres): mín {min(largos)}, "
              f"mediana {int(statistics.median(largos))}, máx {max(largos)}")
    divididos = {c["articulo"] for c in chunks if c["chunk_index"] > 0}
    print(f"Artículos divididos en más de un fragmento: {len(divididos)}")
    print("Títulos encontrados:")
    for t in dict.fromkeys(a["titulo"] for a in articulos):
        print("  -", t or "(sin título)")
    print("\nEjemplo de fragmento:")
    if chunks:
        print(json.dumps(chunks[0], ensure_ascii=False, indent=2))


def main():
    lineas = limpiar(extraer_texto())
    print(f"Líneas de texto limpias: {len(lineas)}")
    articulos = parsear_articulos(lineas)
    chunks = fragmentar(articulos)
    config.DATA_DIR.mkdir(exist_ok=True)
    config.CHUNKS_PATH.write_text(
        json.dumps(chunks, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"Guardado en {config.CHUNKS_PATH}")
    diagnostico(articulos, chunks)


if __name__ == "__main__":
    main()