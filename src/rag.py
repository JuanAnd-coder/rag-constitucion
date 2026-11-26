"""Paso 6: pipeline RAG completo.

    pregunta -> embedding -> pgvector (top-k) -> prompt aumentado -> Gemini -> respuesta con citas

Uso (desde la raíz del proyecto):
    python -m src.rag "¿Qué es la acción de tutela?"
    python -m src.rag "¿Qué es la acción de tutela?" --completo   # muestra el texto entero de los fragmentos
    python -m src.rag                                              # modo interactivo
"""
import sys

import src.config as config
from src.busqueda import buscar, conectar
from src.embeddings import crear_cliente
from src.llm import generar

MENSAJE_SIN_RESPUESTA = "El contexto recuperado no contiene la respuesta a esta pregunta."

# Instrucciones fijas del sistema: aquí se controla que el modelo NO invente.
INSTRUCCIONES = f"""Eres un asistente que responde preguntas sobre la Constitución Política de Colombia de 1991.

Reglas obligatorias:
1. Responde ÚNICAMENTE con la información de los FRAGMENTOS RECUPERADOS que se te entregan. No uses conocimiento propio ni de otras fuentes.
2. Cita el artículo que respalda cada afirmación, con el formato [Art. N] (por ejemplo [Art. 86]). Usa solo números de artículo que aparezcan en los fragmentos.
3. Puedes comparar, resumir o combinar la información de varios fragmentos (por ejemplo, explicar en qué se diferencian dos artículos), siempre que cada afirmación esté respaldada por algún fragmento. Una comparación basada en lo que dicen los fragmentos SÍ está en el contexto.
4. Solo si los fragmentos no contienen NINGUNA información útil para la pregunta, responde exactamente: "{MENSAJE_SIN_RESPUESTA}" y no agregues nada más.
5. Si los fragmentos responden solo una parte de la pregunta, responde esa parte y di claramente qué parte no está en el contexto.
6. Responde en español, de forma clara y concisa.
7. Algunos fragmentos incluyen notas editoriales (por ejemplo "Modificado por el Acto Legislativo..."); no las trates como parte del derecho a explicar, úsalas solo como contexto."""


def construir_prompt(pregunta, fragmentos):
    """Prompt aumentado: los fragmentos recuperados + la pregunta del usuario."""
    bloques = []
    for i, f in enumerate(fragmentos, 1):
        ubicacion = " | ".join(x for x in (f["titulo"], f["capitulo"]) if x)
        bloques.append(f"[Fragmento {i}] ({ubicacion})\n{f['contenido']}")
    contexto = "\n\n".join(bloques)
    return f"FRAGMENTOS RECUPERADOS:\n\n{contexto}\n\nPREGUNTA: {pregunta}\n\nRESPUESTA:"


def responder(conn, client, pregunta, k=config.TOP_K):
    fragmentos = buscar(conn, client, pregunta, k)
    prompt = construir_prompt(pregunta, fragmentos)
    respuesta = generar(client, prompt, INSTRUCCIONES)
    return respuesta, fragmentos


def mostrar(pregunta, respuesta, fragmentos, completo=False):
    print(f"\nPREGUNTA: {pregunta}")
    print(f"\nRESPUESTA:\n{respuesta}")
    print("\nFRAGMENTOS RECUPERADOS (menor distancia = más parecido):")
    for i, f in enumerate(fragmentos, 1):
        print(f"  {i}. dist={f['distancia']:.4f}  Art. {f['articulo']}  |  {f['titulo']}")
        texto = f["contenido"]
        if not completo and len(texto) > 200:
            texto = texto[:200] + "..."
        print(f"     {texto}")
    print()


def main():
    completo = "--completo" in sys.argv
    pregunta = " ".join(a for a in sys.argv[1:] if not a.startswith("--"))
    client = crear_cliente()
    with conectar() as conn:
        if pregunta:
            respuesta, fragmentos = responder(conn, client, pregunta)
            mostrar(pregunta, respuesta, fragmentos, completo)
            return
        while True:
            pregunta = input("Pregunta (Enter vacío para salir): ").strip()
            if not pregunta:
                break
            respuesta, fragmentos = responder(conn, client, pregunta)
            mostrar(pregunta, respuesta, fragmentos, completo)


if __name__ == "__main__":
    main()