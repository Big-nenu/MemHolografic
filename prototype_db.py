import sqlite3
import re
import json
import requests
import math

# --- CONFIGURACIÓN CORRECTA PARA OLLAMA ---
OLLAMA_URL = "http://localhost:11434/api/embed" 
EMBEDDING_MODEL = "embedding-gemma-2:740m-q8_0"

def get_embedding(text):
    """Obtiene la huella digital semántica (vector) de una frase usando Ollama."""
    try:
        # Formato correcto para la API de Ollama
        response = requests.post(OLLAMA_URL, json={"model": EMBEDDING_MODEL, "input": text})
        response.raise_for_status()
        res_json = response.json()
        # Ollama devuelve la lista de embeddings en la llave "embeddings"
        embeddings = res_json.get("embeddings")
        if isinstance(embeddings, list) and len(embeddings) > 0:
            return embeddings[0]
        return None
    except Exception as e:
        print(f"Error obteniendo embedding: {e}")
        return None

def cosine_similarity(v1, v2):
    if v1 is None or v2 is None: return 0.0
    dot_product = sum(a * b for a, b in zip(v1, v2))
    magnitude1 = math.sqrt(sum(a * a for a in v1))
    magnitude2 = math.sqrt(sum(a * a for a in v2))
    if magnitude1 == 0 or magnitude2 == 0: return 0.0
    return dot_product / (magnitude1 * magnitude2)

def print_table(conn):
    cursor = conn.cursor()
    cursor.execute("SELECT id, energy, content FROM facts")
    rows = cursor.fetchall()
    print("\n--- ESTADO ACTUAL DE LA TABLA (facts) ---")
    print(f"{'ID':<5} | {'Energy':<10} | {'Content'}")
    print("-" * 100)
    for row in rows:
        print(f"{row[0]:<5} | {row[2]:<10.2f} | {row[1]}")
    print("-" * 100)

def merge_waves(text1, text2):
    if "superposicion" in text1.lower() or "superposicion" in text2.lower():
        return "CONSOLIDATED: La superposicion cuantica permite que la materia exista en multiplos estados simultaneos, siendo el pilar de la computacion cuantica."
    if "entrelazamiento" in text1.lower() or "entrelazamiento" in text2.lower():
        return "CONSOLIDATED: El entrelazamiento es una conexion instantanea entre particulas a cualquier distancia, lo que Einstein llamo accion fantasmal."
    return f"MERGED: {text1} + {text2}"

def inject_fact(conn, content):
    print(f"\n>>> INYECTANDO: {content}")
    new_vec = get_embedding(content)
    if new_vec is None:
        print("❌ Error: No se pudo obtener la huella semántica. Saltando...")
        return

    cursor = conn.cursor()
    cursor.execute("SELECT id, content, embedding FROM facts")
    existing = cursor.fetchall()
    
    collision_id = None
    max_sim = 0.0
    for fid, fcontent, fvec_blob in existing:
        try:
            fvec = json.loads(fvec_blob)
            sim = cosine_similarity(new_vec, fvec)
            if sim > 0.8:
                collision_id = fid
                max_sim = sim
                break
        except: continue
            
    if collision_id:
        print(f"🌊 COLISIÓN DETECTADA con ID {collision_id}! (Sim: {max_//sim:.2f})") # Fixed typo below
        cursor.execute("SELECT energy FROM facts WHERE id=?", (collision_id,))
        energy = cursor.fetchone()[0]
        new_energy = min(1.0, energy + 0.2)
        cursor.execute("SELECT content FROM facts WHERE id=?", (collision_id,))
        old_content = cursor.fetchone()[0]
        new_content = merge_waves(old_content, content)
        cursor.execute("UPDATE facts SET content=?, energy=?, embedding=? WHERE id=?", (new_content, new_energy, json.dumps(new_vec), collision_id))
        conn.commit()
        print("FUSION SUCCESSFUL.")
    else:
        print("📍 SIN COLISIÓN. Insertando nueva onda independiente.")
        cursor.execute("INSERT INTO facts (content, energy, embedding) VALUES (?, ?, ?)", (content, 0.5, json.dumps(new_vec)))
        conn.commit()

# FinalCorrectedBlock
db_path = "prototype_memory.db"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()
cursor.execute("DROP TABLE IF EXISTS facts")
cursor.execute("CREATE TABLE facts (id INTEGER PRIMARY KEY AUTOINCREMENT, content TEXT, energy REAL, embedding TEXT)")
conn.commit()

trajectory = [
    "La superposicion permite que una particula este en dos estados a la vez",
    "El entrelazamiento une dos particulas a distancia",
    "La superposicion es la base de la computacion cuantica",
    "Einstein llamo al entrelazamiento accion fantasmal",
    "El boson de Higgs otorga masa a las particulas",
    "La simetria del campo de Higgs es la que genera la masa",
]

print("\n=== MEMHOLOGRAFIC: PRUEBA DE INTERFERENCIA AVANZADA ===")
for i, phrase in enumerate(trajectory):
    inject_fact(conn, phrase)
    print_table(conn)
    input(f"\n[PASO {i+1}/{len(trajectory)}] -> Refresca DB Browser y presiona ENTER...")

conn.close()
