"""Paso 7: evaluación del sistema con un conjunto fijo de preguntas.

Para cada pregunta guarda: qué artículos recuperó (con su distancia), si el artículo
esperado quedó entre los k recuperados, si el sistema se abstuvo de responder y la
respuesta completa. La CORRECCIÓN de la respuesta la juzgas tú leyendo el informe.

Uso (desde la raíz del proyecto):
    python -m src.evaluar          -> data/resultados_eval.md y .json
    python -m src.evaluar v2       -> data/resultados_eval_v2.md y .json (para comparar versiones)
"""
import json
import sys
import time

import src.config as config
from src.busqueda import conectar
from src.embeddings import crear_cliente
from src.rag import MENSAJE_SIN_RESPUESTA, responder

PAUSA = 8  # segundos entre preguntas, para no pasar el límite por minuto de la capa gratuita

# tipo: "directa" | "combinada" (necesita varios artículos) | "sin_respuesta"
# esperados: artículos que contienen la respuesta. VERIFÍCALOS tú en el texto de la
# Constitución: la evaluación es tan buena como esta lista.
PREGUNTAS = [
    # --- Directas ---
    {"id": "D1", "tipo": "directa", "esperados": ["86"],
     "pregunta": "¿Qué es la acción de tutela?"},
    {"id": "D2", "tipo": "directa", "esperados": ["10"],
     "pregunta": "¿Cuál es el idioma oficial de Colombia?"},
    {"id": "D3", "tipo": "directa", "esperados": ["190"],
     "pregunta": "¿Por cuántos años se elige al Presidente de la República?"},
    {"id": "D4", "tipo": "directa", "esperados": ["11"],
     "pregunta": "¿Existe la pena de muerte en Colombia?"},
    # --- Combinadas: hay que juntar varios fragmentos ---
    {"id": "C1", "tipo": "combinada", "esperados": ["86", "87"],
     "pregunta": "¿Cuál es la diferencia entre la acción de tutela y la acción de cumplimiento?"},
    {"id": "C2", "tipo": "combinada", "esperados": ["44", "45"],
     "pregunta": "¿Qué derechos tienen los niños y los adolescentes y quién debe protegerlos?"},
    {"id": "C3", "tipo": "combinada", "esperados": ["172", "177"],
     "pregunta": "¿Qué edad mínima se exige para ser senador y cuál para ser representante a la Cámara?"},
    # --- Sin respuesta en el corpus: el sistema debe abstenerse ---
    {"id": "S1", "tipo": "sin_respuesta", "esperados": [],
     "pregunta": "¿Cuántos años de cárcel se imponen por el delito de hurto?"},
    {"id": "S2", "tipo": "sin_respuesta", "esperados": [],
     "pregunta": "¿Qué dice la Constitución sobre las criptomonedas?"},
    {"id": "S3", "tipo": "sin_respuesta", "esperados": [],
     "pregunta": "¿Cuál es el valor del salario mínimo mensual en Colombia hoy?"},
    {"id": "S4", "tipo": "sin_respuesta", "esperados": [],
     "pregunta": "¿Quién ganó el Mundial de fútbol de 2014?"},
    # --- Difíciles: pensadas para buscar fallos (verifica los artículos esperados) ---
    {"id": "H1", "tipo": "directa", "esperados": ["197"],
     "pregunta": "¿Puede el Presidente de la República ser reelegido?"},          # ¿texto desactualizado?
    {"id": "H2", "tipo": "combinada", "esperados": ["100"],
     "pregunta": "¿Pueden votar los extranjeros residentes en Colombia?"},       # requiere interpretar
    {"id": "H3", "tipo": "combinada", "esperados": ["174", "175", "199"],
     "pregunta": "¿Qué pasa si el Presidente comete un delito durante su mandato?"},  # pregunta vaga
    {"id": "H4", "tipo": "directa", "esperados": ["13"],
     "pregunta": "¿Qué dice el artículo 13 de la Constitución?"},                # búsqueda por número
]


def evaluar_una(conn, client, p):
    try:
        respuesta, fragmentos = responder(conn, client, p["pregunta"])
    except Exception as e:  # un fallo de la API no debe tumbar toda la evaluación
        return {**p, "error": f"{type(e).__name__}: {e}", "recuperados": [], "respuesta": ""}

    articulos = [f["articulo"] for f in fragmentos]
    posiciones = [articulos.index(e) + 1 for e in p["esperados"] if e in articulos]
    return {
        **p,
        "recuperados": [
            {"articulo": f["articulo"], "distancia": round(f["distancia"], 4),
             "inicio": f["contenido"][:150]}
            for f in fragmentos
        ],
        "mejor_posicion": min(posiciones) if posiciones else None,
        "todos_esperados": bool(p["esperados"]) and len(posiciones) == len(p["esperados"]),
        "se_abstuvo": MENSAJE_SIN_RESPUESTA.lower() in respuesta.lower(),
        "respuesta": respuesta,
    }


def resumen(resultados):
    lineas = ["# Resultados de la evaluación", ""]
    con_esp = [r for r in resultados if r["esperados"] and "error" not in r]
    sin_resp = [r for r in resultados if r["tipo"] == "sin_respuesta" and "error" not in r]
    if con_esp:
        alguno = sum(1 for r in con_esp if r["mejor_posicion"])
        todos = sum(1 for r in con_esp if r["todos_esperados"])
        top1 = sum(1 for r in con_esp if r["mejor_posicion"] == 1)
        mrr = sum(1 / r["mejor_posicion"] for r in con_esp if r["mejor_posicion"]) / len(con_esp)
        lineas += [
            f"- Recuperación (preguntas con respuesta, n={len(con_esp)}):",
            f"  - Algún artículo esperado en el top-{config.TOP_K}: {alguno}/{len(con_esp)}",
            f"  - Todos los artículos esperados en el top-{config.TOP_K}: {todos}/{len(con_esp)}",
            f"  - Artículo esperado en la posición 1: {top1}/{len(con_esp)}",
            f"  - MRR (promedio de 1/posición): {mrr:.2f}",
        ]
    if sin_resp:
        abst = sum(1 for r in sin_resp if r["se_abstuvo"])
        lineas.append(f"- Abstención correcta en preguntas sin respuesta: {abst}/{len(sin_resp)}")
    errores = [r["id"] for r in resultados if "error" in r]
    if errores:
        lineas.append(f"- Preguntas con error de la API (repetir): {', '.join(errores)}")
    lineas.append("")
    return lineas


def a_markdown(resultados):
    lineas = resumen(resultados)
    for r in resultados:
        lineas += [f"## {r['id']} [{r['tipo']}] {r['pregunta']}", ""]
        if "error" in r:
            lineas += [f"**ERROR:** {r['error']}", ""]
            continue
        lineas.append(f"- Artículos esperados: {', '.join(r['esperados']) or '(ninguno)'}")
        rec = ", ".join(f"{x['articulo']} ({x['distancia']})" for x in r["recuperados"])
        lineas.append(f"- Recuperados (distancia): {rec}")
        if r["esperados"]:
            pos = r["mejor_posicion"]
            lineas.append(f"- Esperado en el top-{config.TOP_K}: "
                          f"{'sí, posición ' + str(pos) if pos else 'NO'}"
                          f" | todos los esperados: {'sí' if r['todos_esperados'] else 'no'}")
        lineas.append(f"- Se abstuvo de responder: {'sí' if r['se_abstuvo'] else 'no'}")
        lineas += ["", "**Respuesta del sistema:**", ""]
        lineas += [f"> {l}" for l in r["respuesta"].splitlines()]
        lineas += ["", "**Tu valoración (correcta / parcial / incorrecta) y por qué:**", "", "", ""]
    return "\n".join(lineas)


def main():
    client = crear_cliente()
    resultados = []
    with conectar() as conn:
        for i, p in enumerate(PREGUNTAS, 1):
            print(f"[{i}/{len(PREGUNTAS)}] {p['id']}: {p['pregunta']}")
            resultados.append(evaluar_una(conn, client, p))
            time.sleep(PAUSA)

    sufijo = f"_{sys.argv[1]}" if len(sys.argv) > 1 else ""
    config.DATA_DIR.mkdir(exist_ok=True)
    (config.DATA_DIR / f"resultados_eval{sufijo}.json").write_text(
        json.dumps(resultados, ensure_ascii=False, indent=2), encoding="utf-8")
    informe = a_markdown(resultados)
    (config.DATA_DIR / f"resultados_eval{sufijo}.md").write_text(informe, encoding="utf-8")
    print("\n" + "\n".join(resumen(resultados)))
    print(f"Informe completo en data/resultados_eval{sufijo}.md")


if __name__ == "__main__":
    main()