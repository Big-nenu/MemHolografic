"""Servidor MCP de MemHolografic.

Variables de entorno opcionales (se ponen en la config del MCP en Cline):
  MEMHOLOGRAFIC_DB           ruta de la base de datos (default: memoria.db junto a este archivo)
  MEMHOLOGRAFIC_NAMESPACE    namespace activo (default: "default")
  MEMHOLOGRAFIC_EMBED_MODEL  modelo de embeddings en Ollama
  MEMHOLOGRAFIC_LLM_MODEL    modelo LLM en Ollama (fusiones, sueño, reflexión)
"""
import contextlib
import os
import sys
from pathlib import Path

from mcp.server.fastmcp import FastMCP

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

import mem_engine  # noqa: E402
from mem_engine import MemHolograficEngine  # noqa: E402

# El motor lee estas constantes al momento de usarlas, así que se pueden sobrescribir aquí.
mem_engine.EMBEDDING_MODEL = os.getenv("MEMHOLOGRAFIC_EMBED_MODEL", mem_engine.EMBEDDING_MODEL)
mem_engine.LLM_MODEL = os.getenv("MEMHOLOGRAFIC_LLM_MODEL", mem_engine.LLM_MODEL)

DB_PATH = os.getenv("MEMHOLOGRAFIC_DB", str(BASE_DIR / "memoria.db"))
NS = os.getenv("MEMHOLOGRAFIC_NAMESPACE", "default")

INSTRUCTIONS = (
    "Memoria persistente del usuario entre conversaciones. "
    "AL INICIO de cada conversación llama list_memories antes de responder. "
    "Cuando el usuario diga algo duradero sobre sí mismo, sus proyectos o sus decisiones, llama inject_memory. "
    "Antes de responder sobre el usuario o su historial, llama query_memory."
)

mcp = FastMCP("MemHolografic", instructions=INSTRUCTIONS)
engine = MemHolograficEngine(db_path=DB_PATH)


def _quiet():
    # Por stdio, stdout es el canal del protocolo MCP: un print() del motor lo corrompe.
    return contextlib.redirect_stdout(sys.stderr)


def _all_memories(limit: int = 30) -> str:
    with _quiet():
        facts = engine.get_all_facts(namespace=NS)
    if not facts:
        return "La memoria está vacía todavía."
    shown = facts[-limit:]
    text = "\n".join(f"- {f}" for f in shown)
    extra = f"\n(Se muestran los últimos {len(shown)} de {len(facts)})" if len(facts) > len(shown) else ""
    return f"Memoria ({len(facts)} recuerdos):\n{text}{extra}"


@mcp.tool()
def list_memories(limit: int = 30) -> str:
    """LLAMA ESTO AL INICIO DE CADA CONVERSACIÓN. Devuelve lo que ya se sabe del usuario:
    datos personales, proyectos, preferencias y decisiones guardadas."""
    return _all_memories(limit)


@mcp.tool()
def query_memory(text: str) -> str:
    """Busca recuerdos relacionados con un tema. Úsalo antes de responder preguntas
    sobre el usuario, sus proyectos o decisiones previas."""
    with _quiet():
        res = engine.query(text, namespace=NS)
    if isinstance(res, str):
        if res.startswith("Error"):
            return f"No se pudo buscar ({res}). Revisa que Ollama esté encendido y el modelo de embeddings descargado."
        return "Sin coincidencias exactas. Esto es lo guardado:\n" + _all_memories()
    if not res:
        return "Sin coincidencias exactas. Esto es lo guardado:\n" + _all_memories()
    lines = "\n".join(f"Sim: {sim:.2f} | {content}" for sim, fid, energy, content in res)
    return f"Recuerdos encontrados:\n{lines}"


@mcp.tool()
def inject_memory(content: str, energy: float = 0.5) -> str:
    """Guarda un dato duradero: preferencia, decisión, dato personal o técnico.
    Si es muy parecido a uno existente, se fusionan."""
    with _quiet():
        result = engine.inject(content, energy=energy, namespace=NS)
    result = str(result) if result is not None else "No se pudo guardar."
    if "ERROR" in result:
        result += " Revisa que Ollama esté encendido y el modelo de embeddings descargado."
    return result


@mcp.tool()
def force_dream() -> str:
    """Mantenimiento: consolida la memoria y manda lo poco relevante al sótano.
    Úsalo solo cuando el usuario lo pida."""
    with _quiet():
        result = engine.dream(namespace=NS)
    return str(result) if result is not None else "El proceso de sueño no generó resultados."


@mcp.tool()
def trigger_reflection() -> str:
    """Genera una intuición nueva conectando los recuerdos más fuertes. Úsalo solo si el usuario lo pide."""
    with _quiet():
        result = engine.reflect(namespace=NS)
    return str(result) if result is not None else "No se encontró una conexión interesante esta vez."


@mcp.tool()
def clear_memory(confirm: bool = False) -> str:
    """BORRA TODA la memoria. Irreversible. Solo úsalo si el usuario lo pide
    de forma explícita, y entonces pasa confirm=true."""
    if not confirm:
        return "Cancelado: falta confirm=true. No se borró nada."
    with _quiet():
        engine.clear_db(namespace=NS)
    return "Memoria borrada."


if __name__ == "__main__":
    mcp.run()
