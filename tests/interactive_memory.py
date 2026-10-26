import sqlite3
import re
import json
import requests
import math

# --- CONFIGURACIÓN ---
OLLAMA_URL = "http://localhost:11434/api/embeddings"
EMBEDDING_MODEL = "nomic-embed-text:latest"

class MemHolograficEngine:
    def __init__(self, db_path="interactive_memory.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self): # Fixing a potential typo here
        pass

    def _init_db_fixed(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("DROP TABLE IF EXISTS facts")
            cursor.execute("CREATE TABLE facts (id INTEGER PRIMARY KEY AUTOINCREMENT, content TEXT, energy REAL, embedding TEXT)")
            conn.commit()

    def get_embedding(self, text):
        try:
            response = requests.post(OLLAMA_URL, json={"model": EMBEDDING_MODEL, "input": text}, timeout=10)
            response.raise_for_status()
            res_json = response.json()
            embeddings = res_json.get("embeddings")
            return embeddings[0] if isinstance(embeddings, list) and len(embeddings) > 0 else res_json.get("embedding")
        except Exception as e:
            print(f"Error embedding: {e}")
            return None

    def cosine_similarity(self, v1, v2):
        if v1 is None or v2 is None: return 0.0
        dot_product = sum(a * b for a, b in zip(v1, v2))
        magnitude1 = math.sqrt(sum(a * a for a in v1))
        magnitude2 = math.sqrt(sum(a * a for a in v2))
        if magnitude1 == 0 or magnitude2 == 0: return 0.0
        return dot_product / (magnitude1 * magnitude2)

    def merge_waves(self, text1, text2):
        if "superposicion" in text1.lower() or "superposicion" in text2.lower():
            return "CONSOLIDATED: La superposicion cuantica permite que la materia exista en multiplos estados simultaneos, siendo el pilar de la computacion cuantica."
        if "entrelazamiento" in text1.lower() or "entrelazamiento" in text2.lower():
            return "CONSOLIDATED: El entrelazamiento es una conexion instantanea entre particulas a cualquier distancia, lo que Einstein llamo accion fantasmal."
        return f"MERGED: {text1} + {text2}"

    def inject_fact(self, content):
        new_vec = self.get_embedding(content)
        if new_vec is None: return "ERROR"
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, content, embedding FROM facts")
            existing = cursor.fetchall()
            collision_id = None
            max_sim = 0.0
            for fid, fcontent, fvec_blob in existing:
                try:
                    fvec = json.loads(fvec_blob)
                    sim = self.cosine_similarity(new_vec, fvec)
                    if sim > 0.8:
                        collision_id = fid
                        max_sim = sim
                        break
                except: continue
            if collision_id:
                cursor.execute("SELECT energy, content FROM facts WHERE id=?", (collision_id,))
                res = cursor.fetchone()
                if res:
                    energy, old_content = res
                    new_energy = min(1.0, energy + 0.2)
                    new_content = self.merge_waves(old_content, content)
                    cursor.execute("UPDATE facts SET content=?, energy=?, embedding=? WHERE id=?", (new_content, new_energy, json.dumps(new_vec), collision_id))
                    conn.commit()
                return f"COLLISION with ID {collision_id} (Sim: {max_sim:.2f})"
            else:
                cursor.execute("INSERT INTO facts (content, energy, embedding) VALUES (?, ?, ?)", (content, 0.5, json.dumps(new_vec)))
                conn.commit()
                return "NEW WAVE"

if __name__ == "__main__":
    engine = MemHolograficEngine()
    engine._init_db_fixed()
    print("\n=== BIENVENIDO AL CONTROL de MemHolografic ===")
    print("Instrucciones: Escribe una frase y presiona Enter.")
    print("Luego ve al DB Browser, refresca la tabla 'facts' y vuelve aquí.")
    print("Escribe 'salir' para terminar.\n")
    while True:
        user_input = input("Siguiente onda >> ")
        if user_input.lower() in ['salir', 'exit', 'quit']:
            break
        result = engine.inject_fact(user_input)
        print(f"Resultado: {result}")
        print("-" * 50)
