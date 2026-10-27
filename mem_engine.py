import sqlite3
import json
import requests
import math
import time

# --- CONFIGURACIÓN ---
OLLAMA_URL = "http://localhost:11434/api/embeddings"
OLLAMA_GEN_URL = "http://localhost:11434/api/generate"
EMBEDDING_MODEL = "nomic-embed-text:latest"
LLM_MODEL = "tev1" 

class MemHolograficEngine:
    def __init__(self, db_path="prototype_memory.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            # Tabla de memoria activa con namespace
            cursor.execute("CREATE TABLE IF NOT EXISTS facts (id INTEGER PRIMARY KEY AUTOINCREMENT, namespace TEXT DEFAULT 'default', content TEXT, energy REAL, embedding TEXT)")
            # Tabla de memoria profunda con namespace
            cursor.execute("CREATE TABLE IF NOT EXISTS archived_facts (id INTEGER PRIMARY KEY AUTOINCREMENT, namespace TEXT DEFAULT 'default', content TEXT, energy REAL, embedding TEXT)")
            conn.commit()

    def clear_db(self, namespace=None):
        """Limpia la memoria. Si se provee namespace, limpia solo ese proyecto."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            if namespace:
                cursor.execute("DELETE FROM facts WHERE namespace=?", (namespace,))
                cursor.execute("DELETE FROM archived_facts WHERE namespace=?", (namespace,))
            else:
                cursor.execute("DELETE FROM facts")
                cursor.execute("DELETE FROM archived_//facts")
            conn.commit()

    def get_embedding(self, text, retries=3):
        for attempt in range(retries):
            try:
                r = requests.post(OLLAMA_URL, json={"model": EMBEDDING_MODEL, "prompt": text}, timeout=10)
                if r.status_code == 200:
                    emb = r.json().get("embedding")
                    if emb: return emb
                r = requests.post("http://localhost:11434/api/embed", json={"model": EMBEDDING_MODEL, "input": text}, timeout=10)
                if r.status_code == 200:
                    res = r.json()
                    emb_list = res.get("embeddings")
                    if isinstance(emb_list, list) and len(emb_list) > 0:
                        return emb_list[0]
                    return res.get("embedding")
            except Exception:
                time.sleep(1)
        return None

    def calc_sim(self, v1, v2):
        if not v1 or not v2: return 0.0
        dot = sum(a * b for a, b in zip(v1, v2))
        m1 = math.sqrt(sum(a * a for a in v1))
        m2 = math.sqrt(sum(a * a for a in v2))
        return dot / (m1 * m2) if m1 * m2 != 0 else 0.0

    def _ask_llm_conflict(self, t1, t2):
        prompt = f"Actua como un juez logico estricto. Analiza si la Frase 2 invalida o contradice la Frase 1. \n\nEjemplo de CONTRADICTORIO: 'El cielo es azul' vs 'El cielo es verde'.\nEjemplo de COMPLEMENTARIO: 'El cielo es azul' vs 'El cielo es inmenso'.\n\nFrase 1: {t1}\nFrase 2: {t2}\n\nResponde UNICAMENTE con la palabra 'CONTRADICTORIO' si la segunda frase anula la primera, o 'COMPLEMENTARIO' si ambas pueden coexistir. \n\nRespuesta:"
        try:
            r = requests.post(OLLAMA_GEN_URL, json={"model": LLM_MODEL, "prompt": prompt, "stream": False}, timeout=30)
            if r.status_code == 200:
                return r.json().get("response", "").strip().upper()
        except:
            pass
        return "COMPLEMENTARIO"

    def _ask_llm_synthesis(self, t1, t2):
        prompt = f"Eres un sintetizador de conocimiento. Tienes dos frases que dicen cosas similares. Crea una sola frase consolidada que mantenga la esencia de ambas, eliminando redundancias y siendo preciso. \n\nFrase 1: {t1}\nFrase 2: {t2}\n\nRespuesta (solo la frase sintetizada):"
        try:
            r = requests.post(OLLAMA_GEN_URL, json={"model": LLM_MODEL, "prompt": prompt, "stream": False}, timeout=30)
            if r.status_code == 200:
                return r.json().get("response", "").strip()
        except:
            pass
        return f"MERGED: {t1} | {t2}"

    def _ask_llm_reflection(self, facts_list):
        facts_str = "\n".join([f"- {f}" for f in facts_list])
        prompt = (
            f"Eres la unidad de reflexión de un cerebro digital. Tienes acceso a los siguientes recuerdos "
            f"de alta energía que parecen pertenecer a temas distintos, pero que el sistema considera interesantes: \n\n{facts_str}\n\n"
            f"Tu tarea es analizar estos datos y generar una HIPÓTESIS o INTUICIÓN. No resumas los datos, "
            f"busca una conexión oculta, una analogía o una pregunta filosófica que una estos temas. "
            f"La respuesta debe ser una sola frase corta que empiece con 'Intuición: '.\n\nRespuesta:"
        )
        try:
            r = requests.post(OLLAMA_GEN_URL, json={"model": LLM_MODEL, "prompt": prompt, "stream": False}, timeout=30)
            if r.status_code == 200:
                return r.json().get("response", "").strip()
        except:
            pass
        return None

    def merge_waves(self, t1, t2):
        return self._ask_llm_synthesis(t1, t2)

    def print_table(self, table="facts", namespace=None):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            if namespace:
                cursor.execute(f"SELECT id, energy, content FROM {table} WHERE namespace=?", (namespace,))
            else:
                cursor.execute(f"SELECT id, energy, content FROM {table}")
            rows = cursor.fetchall()
            print(f"\n--- TABLA {table.upper()} ({namespace if namespace else 'ALL'}) ---")
            print(f"{'ID':<5} | {'Energy':<10} | {'Content'}")
            print("-" * 100)
            for r in rows:
                e = float(r[1]) if r[1] is not None else 0.0
                print(f"{r[0]:<5} | {e:<10.2f} | {r[2]}")
            print("-" * 100)

    def inject(self, content, energy=0.5, namespace="default"):
        vec = self.get_embedding(content)
        if vec is None:
            return "❌ ERROR: No se obtuvo embedding."
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, content, embedding FROM facts WHERE namespace=?", (namespace,))
            existing = cursor.fetchall()
            best_collision_id = None
            max_sim = 0.0
            for fid, fcontent, fvec_blob in existing:
                try:
                    fvec = json.loads(fvec_blob)
                    sim = self.calc_sim(vec, fvec)
                    if sim > 0.8 and sim > max_sim:
                        max_sim = sim
                        best_collision_id = fid
                except: continue
            
            if best_collision_id:
                cursor.execute("SELECT energy, content FROM facts WHERE id=?", (best_collision_id,))
                res = cursor.fetchone()
                if res:
                    energy_old = float(res[0]) if res[0] is not None else 0.5
                    old_content = res[1]
                    decision = self._ask_llm_conflict(old_content, content)
                    if "CONTRADICTORIO" in decision:
                        cursor.execute("INSERT INTO facts (namespace, content, energy, embedding) VALUES (?, ?, ?, ?)", (namespace, content, energy, json.dumps(vec)))
                        conn.commit()
                        return f"🚫 CONTRADICCIÓN detectada. Guardado como dato independiente."
                    
                    new_energy = min(1.0, energy_old + 0.2)
                    new_content = self.merge_waves(old_content, content)
                    new_vec = self.get_embedding(new_content)
                    final_vec_blob = json.dumps(new_vec if new_vec else vec)
                    cursor.execute("UPDATE facts SET content=?, energy=?, embedding=? WHERE id=?", (new_content, new_energy, final_vec_blob, best_collision_id))
                    conn.commit()
                    return f"🌊 COLISION con ID {best_collision_id}! Sim: {max_sim:.2f} Energy: {new_energy:.2f}"
            else:
                cursor.execute("INSERT INTO facts (namespace, content, energy, embedding) VALUES (?, ?, ?, ?)", (namespace, content, energy, json.dumps(vec)))
                conn.commit()
                return "📍 NUEVA ONDA."

    def query(self, text, namespace="default"):
        vec = self.get_embedding(text)
        if vec is None: return "Error: No embedding"
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, energy, content, embedding FROM facts WHERE namespace=?", (namespace,))
            active_facts = cursor.fetchall()
            results = []
            for fid, fenergy, fcontent, fvec_blob in active_facts:
                try:
                    fvec = json.loads(fvec_blob)
                    sim = self.calc_sim(vec, fvec)
                    if sim > 0.5:
                        results.append((sim, fid, fenergy, fcontent))
                except: continue
            if results:
                results.sort(key=lambda x: x[0], reverse=True)
                return results[:3]
            
            print(f"🔍 Buscando en el Sótano ({namespace})...")
            cursor.execute("SELECT id, energy, content, embedding FROM archived_facts WHERE namespace=?", (namespace,))
            archived_facts = cursor.fetchall()
            archived_results = []
            for fid, fenergy, fcontent, fvec_blob in archived_facts:
                try:
                    fvec = json.loads(fvec_blob)
                    sim = self.calc_sim(vec, fvec)
                    if sim > 0.5:
                        archived_results.append((sim, fid, fenergy, fcontent))
                except: continue
            if archived_results:
                archived_results.sort(key=lambda x: x[0], reverse=True)
                best_sim, best_id, best_energy, best_content = archived_results[0]
                cursor.execute("SELECT embedding FROM archived_facts WHERE id=?", (best_id,))
                emb = cursor.fetchone()[0]
                cursor.execute("INSERT INTO facts (namespace, content, energy, embedding) VALUES (?, ?, ?, ?)", (namespace, best_content, best_energy + 0.2, emb))
                cursor.execute("DELETE FROM archived_facts WHERE id=?", (best_id,))
                conn.commit()
                return [(best_sim, -1, best_energy + 0.2, best_content)]
            return "No related memories found."

    def get_all_facts(self, namespace="default"):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT content FROM facts WHERE namespace=?", (namespace,))
            return [r[0] for r in cursor.fetchall()]

    def dream(self, namespace="default"):
        print(f"\n🌙 Iniciando Sleeptime para {namespace}...")
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, content, energy, embedding FROM facts WHERE namespace=?", (namespace,))
            facts = cursor.fetchall()
            processed_ids = set()
            changes_made = 0
            for i in range(len(facts)):
                id1, content1, energy1, vec1_blob = facts[i]
                if id1 in processed_ids: continue
                vec1 = json.loads(vec1_blob)
                if energy1 < 0.4:
                    print(f"📉 Energía baja (ID {id1}). Moviendo al sótano...")
                    cursor.execute("INSERT INTO archived_facts (namespace, content, energy, embedding) VALUES (?, ?, ?, ?)", (namespace, content1, energy1, vec1_blob))
                    cursor.execute("DELETE FROM facts WHERE id=?", (id1,))
                    processed_ids.add(id1)
                    changes_made += 1
                    continue
                for j in range(i + 1, len(facts)):
                    id2, content2, energy2, vec2_blob = facts[j]
                    if id2 in processed_ids: continue
                    vec2 = json.loads(vec2_blob)
                    sim = self.calc_sim(vec1, vec2)
                    if sim > 0.8:
                        print(f"  - Analizando colisión entre ID {id1} y ID {id2} (Sim: {sim:.4f})...")
                        decision = self._ask_llm_conflict(content1, content2)
                        if "CONTRADICTORIO" in decision:
                            print(f"    🚫 INTERFERENCIA DESTRUCTIVA: Archivando dato antiguo (ID {id1}).")
                            cursor.execute("INSERT INTO archived_facts (namespace, content, energy, embedding) VALUES (?, ?, ?, ?)", (namespace, content1, energy1, vec1_blob))
                            cursor.execute("DELETE FROM facts WHERE id=?", (id1,))
                            processed_ids.add(id1); processed_ids.add(id2); changes_made += 1; break 
                        else:
                            print(f"    ✨ INTERFERENCIA CONSTRUCTIVA: Fusionando ondas.")
                            merged_content = self.merge_waves(content1, content2)
                            new_vec = self.get_embedding(merged_content)
                            cursor.execute("UPDATE facts SET content=?, energy=?, embedding=? WHERE id=?", (merged_content, energy2 + 0.2, json.dumps(new_vec if new_vec else vec2), id2))
                            cursor.execute("DELETE FROM facts WHERE id=?", (id1,))
                            processed_ids.add(id1); processed_ids.add(id2); changes_made += 1; break
            conn.commit()
            return f"Sleeptime finalizado para {namespace}. Cambios realizados: {changes_made}"

    def reflect(self, namespace="default"):
        print(f"\n💭 Iniciando proceso de Reflexión Autónoma para {namespace}...")
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT content, embedding FROM facts WHERE namespace=? ORDER BY energy DESC LIMIT 20", (namespace,))
            candidates = cursor.fetchall()
            if len(candidates) < 2:
                return "No hay suficientes recuerdos fuertes para reflexionar."
            representatives = []
            rep_vecs = []
            first_content, first_vec_blob = candidates[0]
            first_vec = json.loads(first_vec_blob)
            representatives.append(first_content)
            rep_vecs.append(first_vec)
            for content, vec_blob in candidates[1:]:
                vec = json.loads(vec_blob)
                if all(self.calc_sim(vec, rv) < 0.6 for rv in rep_vecs):
                    representatives.append(content)
                    rep_vecs.append(vec)
                if len(representatives) >= 3: break
            if len(representatives) < 2:
                representatives = [c[0] for c in candidates[:3]]
            print(f"✨ tev está reflexionando sobre: {representatives}")
            reflection = self._ask_llm_reflection(representatives)
            if reflection:
                print(f"💡 Reflexión generada: {reflection}")
                self.inject(reflection, energy=0.3, namespace=namespace)
                return f"Reflexión autónoma inyectada en {namespace}: {reflection}"
            return "tev no pudo encontrar una conexión interesante esta vez."

if __name__ == "__main__":
    print("Motor de Memoria cargado. Usa mem_cli.py para interactuar.")
