import os
import sqlite3
import json
import requests
import math
import time

# --- CONFIGURACIÓN ---
OLLAMA_URL = "http://localhost:11434/api/embeddings"
OLLAMA_GEN_URL = "http://localhost:11434/api/generate"
OLLAMA_SYSTEMONE_URL = "http://localhost:11434/v1/systemone"
EMBEDDING_MODEL = os.getenv("MEMHOLOGRAFIC_EMBED_MODEL", "embeddinggemma-2:270m")
LLM_MODEL = os.getenv("MEMHOLOGRAFIC_LLM_MODEL", "tev1:0.8b")
# Modelo ligero para síntesis y reflexión (generación de prose). tev1 es solo de decisiones.
SYNTHESIS_MODEL = os.getenv("MEMHOLOGRAFIC_SYNTHESIS_MODEL", "qwen2.5:0.5b")

# Generador de grafo (opcional, bajo demanda, ligero)
GRAPH_ENABLED = os.getenv("MEMHOLOGRAFIC_GRAPH_ENABLED", "false").lower() == "true"
GRAPH_MODEL = os.getenv("MEMHOLOGRAFIC_GRAPH_MODEL", SYNTHESIS_MODEL)  # qwen2.5:0.5b recomendado para NER
GRAPH_OUTPUT_PATH = os.getenv("MEMHOLOGRAFIC_GRAPH_OUTPUT", "memoria_grafo.html")

# Mapeo para normalizar nombres de entidades (unificar duplicados)
ENTITY_ALIASES = {
    "luis": "Luis Hernandez",
    "luis hernandez": "Luis Hernandez",
}

def _normalize_entity_name(nombre):
    """Normaliza nombres de entidades para evitar duplicados (ej. 'Luis' -> 'Luis Hernandez')."""
    nombre_lower = nombre.strip().lower()
    return ENTITY_ALIASES.get(nombre_lower, nombre.strip())

# Lista de temas predefinidos para clasificación automática
CLASSIFICATION_TOPICS = [
    "identidad", "proyecto", "trabajo", "estudios", "tecnologia",
    "fisica", "mecanica_cuantica", "astrofisica", "ciberseguridad",
    "videojuegos", "preferencias", "otro"
]

class MemHolograficEngine:
    def __init__(self, db_path="data/memoria-2.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            # Tabla de memoria activa con namespace
            cursor.execute("CREATE TABLE IF NOT EXISTS facts (id INTEGER PRIMARY KEY AUTOINCREMENT, namespace TEXT DEFAULT 'default', content TEXT, energy REAL, embedding TEXT)")
            # Tabla de memoria profunda con namespace
            cursor.execute("CREATE TABLE IF NOT EXISTS archived_facts (id INTEGER PRIMARY KEY AUTOINCREMENT, namespace TEXT DEFAULT 'default', content TEXT, energy REAL, embedding TEXT)")
            # Tabla de temas para búsqueda por temas
            cursor.execute("CREATE TABLE IF NOT EXISTS topics (id INTEGER PRIMARY KEY AUTOINCREMENT, topic_name TEXT UNIQUE NOT NULL, description TEXT)")
            # Relación muchos-a-muchos entre hechos y temas
            cursor.execute("CREATE TABLE IF NOT EXISTS fact_topics (fact_id INTEGER NOT NULL, topic_id INTEGER NOT NULL, FOREIGN KEY (fact_id) REFERENCES facts(id), FOREIGN KEY (topic_id) REFERENCES topics(id), PRIMARY KEY (fact_id, topic_id))")
            # Índices para búsquedas rápidas
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_facts_namespace ON facts(namespace)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_fact_topics_topic ON fact_topics(topic_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_fact_topics_fact ON fact_topics(fact_id)")
            # Insertar temas predefinidos si no existen
            for topic in CLASSIFICATION_TOPICS:
                cursor.execute("INSERT OR IGNORE INTO topics (topic_name, description) VALUES (?, ?)", (topic, f"Tema: {topic}"))
            # Tablas para el grafo de relaciones (opcional, solo se usan si está habilitado)
            cursor.execute("CREATE TABLE IF NOT EXISTS entities (id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT UNIQUE NOT NULL, tipo TEXT, embedding TEXT)")
            cursor.execute("CREATE TABLE IF NOT EXISTS relationships (id INTEGER PRIMARY KEY AUTOINCREMENT, entidad_origen TEXT NOT NULL, entidad_destino TEXT NOT NULL, tipo_relacion TEXT NOT NULL, hecho_origen_id INTEGER, peso REAL DEFAULT 1.0, FOREIGN KEY (hecho_origen_id) REFERENCES facts(id))")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_entities_nombre ON entities(nombre)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_relationships_origen ON relationships(entidad_origen)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_relationships_destino ON relationships(entidad_destino)")
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
                cursor.execute("DELETE FROM archived_facts")
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

    def classify_topics(self, text):
        """Clasifica un texto en temas usando tev1:0.8b vía /v1/systemone (modelo de decisiones).
        Devuelve lista de nombres de temas detectados."""
        try:
            # Para 'choice', criterios mapea nombre de tema -> descripción
            criteria = {topic: f"El texto trata sobre {topic}" for topic in CLASSIFICATION_TOPICS}
            payload = {
                "model": LLM_MODEL,
                "state": text,
                "questions": {
                    "temas": {
                        "type": "choice",
                        "instructions": "Selecciona el tema que mejor se aplique a este texto.",
                        "criteria": criteria
                    }
                }
            }
            r = requests.post(OLLAMA_SYSTEMONE_URL, json=payload, timeout=30)
            if r.status_code == 200:
                data = r.json()
                answers = data.get("answers", {})
                temas_res = answers.get("temas", {})
                # Para 'choice', la respuesta viene en .choice
                choice = temas_res.get("choice", "")
                if isinstance(choice, str) and choice in CLASSIFICATION_TOPICS:
                    return [choice]
                # Fallback: si devuelve una lista
                picks = temas_res.get("picks", [])
                if isinstance(picks, list):
                    return [p for p in picks if p in CLASSIFICATION_TOPICS]
        except Exception:
            pass
        return []

    def _store_topics(self, cursor, fact_id, topics):
        """Guarda la relación entre un hecho y sus temas en fact_topics."""
        for topic_name in topics:
            cursor.execute("SELECT id FROM topics WHERE topic_name=?", (topic_name,))
            row = cursor.fetchone()
            if row:
                topic_id = row[0]
                cursor.execute(
                    "INSERT OR IGNORE INTO fact_topics (fact_id, topic_id) VALUES (?, ?)",
                    (fact_id, topic_id)
                )

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
            r = requests.post(OLLAMA_GEN_URL, json={"model": SYNTHESIS_MODEL, "prompt": prompt, "stream": False}, timeout=30)
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
            r = requests.post(OLLAMA_GEN_URL, json={"model": SYNTHESIS_MODEL, "prompt": prompt, "stream": False}, timeout=30)
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
                        fact_id = cursor.lastrowid
                        topics = self.classify_topics(content)
                        self._store_topics(cursor, fact_id, topics)
                        conn.commit()
                        return f"🚫 CONTRADICCIÓN detectada. Guardado como dato independiente."
                    
                    new_energy = min(1.0, energy_old + 0.2)
                    new_content = self.merge_waves(old_content, content)
                    new_vec = self.get_embedding(new_content)
                    final_vec_blob = json.dumps(new_vec if new_vec else vec)
                    cursor.execute("UPDATE facts SET content=?, energy=?, embedding=? WHERE id=?", (new_content, new_energy, final_vec_blob, best_collision_id))
                    # Actualizar temas del hecho fusionado
                    cursor.execute("DELETE FROM fact_topics WHERE fact_id=?", (best_collision_id,))
                    new_topics = self.classify_topics(new_content)
                    self._store_topics(cursor, best_collision_id, new_topics)
                    conn.commit()
                    if new_topics:
                        return f"🌊 COLISION con ID {best_collision_id}! Sim: {max_sim:.2f} Energy: {new_energy:.2f} Temas: {', '.join(new_topics)}"
                    return f"🌊 COLISION con ID {best_collision_id}! Sim: {max_sim:.2f} Energy: {new_energy:.2f}"
            else:
                cursor.execute("INSERT INTO facts (namespace, content, energy, embedding) VALUES (?, ?, ?, ?)", (namespace, content, energy, json.dumps(vec)))
                fact_id = cursor.lastrowid
                topics = self.classify_topics(content)
                self._store_topics(cursor, fact_id, topics)
                conn.commit()
                if topics:
                    return f"📍 NUEVA ONDA. Temas: {', '.join(topics)}"
                return "📍 NUEVA ONDA."

    def query(self, text, namespace="default"):
        vec = self.get_embedding(text)
        if vec is None: return "Error: No embedding"
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            # Paso 1: Clasificar la consulta en temas
            query_topics = self.classify_topics(text)
            
            # Paso 2: Obtener IDs de hechos filtrados por temas (si hay temas detectados)
            topic_filtered_ids = None
            if query_topics:
                placeholders = ",".join(["?"] * len(query_topics))
                cursor.execute(
                    f"SELECT DISTINCT ft.fact_id FROM fact_topics ft "
                    f"JOIN topics t ON ft.topic_id = t.id "
                    f"WHERE t.topic_name IN ({placeholders})",
                    query_topics
                )
                topic_filtered_ids = {row[0] for row in cursor.fetchall()}
            
            # Paso 3: Buscar en hechos activos (filtrados por temas si aplica)
            cursor.execute("SELECT id, energy, content, embedding FROM facts WHERE namespace=?", (namespace,))
            active_facts = cursor.fetchall()
            results = []
            for fid, fenergy, fcontent, fvec_blob in active_facts:
                # Si hay filtro de temas, saltar hechos no relacionados
                if topic_filtered_ids is not None and fid not in topic_filtered_ids:
                    continue
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

    # --- GENERADOR DE GRAFO (opcional, bajo demanda) ---

    def extract_graph_entities(self, text):
        """Usa qwen2.5:0.5b para extraer entidades y relaciones de un texto.
        Devuelve lista de tuplas: (origen, destino, tipo_relacion, contexto_breve)."""
        prompt = f"""Eres un extractor de entidades y relaciones para un grafo del conocimiento.
Analiza el siguiente texto y devuelve SOLO un JSON válido con esta estructura:
{{"entidades": [{{"nombre": "...", "tipo": "..."}}], "relaciones": [{{"origen": "...", "destino": "...", "relacion": "..."}}]}}

Reglas importantes:
- Identifica a la persona principal (ej. "Luis Hernandez") como entidad de tipo "persona".
- Extrae todas las entidades nombradas: proyectos, tecnologías, lugares, conceptos, juegos.
- Tipos de entidad válidos: persona, proyecto, tecnologia, lugar, concepto, habilidad, juego.
- Relaciones válidas: trabaja_en, estudio_en, usa, vive_en, gusta_de, interesa_en, escribio, creo, es_de, relacionado_con.
- Si hay una persona, crea relaciones DESDE esa persona HACIA las otras entidades.
- No inventes entidades que no estén en el texto.
- Si no hay entidades claras, devuelve arrays vacíos.

Texto: {text}

JSON:"""
        try:
            r = requests.post(OLLAMA_GEN_URL, json={"model": GRAPH_MODEL, "prompt": prompt, "stream": False}, timeout=30)
            if r.status_code == 200:
                response = r.json().get("response", "").strip()
                start = response.find("{")
                end = response.rfind("}")
                if start != -1 and end != -1 and end > start:
                    json_str = response[start:end+1]
                    import json as _json
                    data = _json.loads(json_str)
                    entidades = data.get("entidades", [])
                    relaciones = data.get("relaciones", [])
                    resultado = []
                    for rel in relaciones:
                        origen = _normalize_entity_name(rel.get("origen", ""))
                        destino = _normalize_entity_name(rel.get("destino", ""))
                        if origen and destino:
                            resultado.append((
                                origen,
                                destino,
                                rel.get("relacion", "relacionado_con"),
                                text[:80]
                            ))
                    entidades_normalizadas = []
                    for ent in entidades:
                        nombre = _normalize_entity_name(ent.get("nombre", ""))
                        tipo = ent.get("tipo", "concepto")
                        if nombre:
                            entidades_normalizadas.append({"nombre": nombre, "tipo": tipo})
                    return resultado, entidades_normalizadas
        except Exception:
            pass
        return [], []

    def _get_central_person(self, namespace="default"):
        """Intenta identificar a la persona principal del namespace."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT nombre FROM entities WHERE tipo='persona' ORDER BY id LIMIT 1", )
            row = cursor.fetchone()
            if row:
                return row[0]
            # Si no hay entidades guardadas aún, buscar en los textos de facts
            cursor.execute("SELECT content FROM facts WHERE namespace=? ORDER BY id", (namespace,))
            for (content,) in cursor.fetchall():
                if "Luis Hernandez" in content:
                    return "Luis Hernandez"
        return None

    def build_graph_from_facts(self, namespace="default"):
        """Extrae entidades y relaciones de todos los hechos activos del namespace."""
        # Limpiar tablas previas para evitar duplicados
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM relationships")
            cursor.execute("DELETE FROM entities")
            conn.commit()

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, content FROM facts WHERE namespace=? ORDER BY id", (namespace,))
            facts = cursor.fetchall()

        if not facts:
            return {"entities": [], "relationships": [], "mensaje": "No hay hechos para graficar."}

        all_entities = {}
        all_relationships = []

        central_person = self._get_central_person(namespace)

        for fact_id, content in facts:
            relaciones, entidades = self.extract_graph_entities(content)
            # Registrar entidades
            for ent in entidades:
                nombre = ent.get("nombre", "")
                tipo = ent.get("tipo", "concepto")
                if nombre and nombre not in all_entities:
                    all_entities[nombre] = {"nombre": nombre, "tipo": tipo, "embedding": None}
            # Registrar relaciones del modelo
            for origen, destino, tipo_rel, contexto in relaciones:
                if origen and destino:
                    all_relationships.append({
                        "origen": origen,
                        "destino": destino,
                        "relacion": tipo_rel,
                        "hecho_id": fact_id,
                        "contexto": contexto
                    })

        # Si hay una persona central, asegurar que esté conectada con todo lo demás
        if central_person:
            if central_person not in all_entities:
                all_entities[central_person] = {"nombre": central_person, "tipo": "persona", "embedding": None}
            # Crear relaciones desde la persona central hacia cada otra entidad
            for nombre in all_entities:
                if nombre != central_person:
                    # Verificar si ya existe una relación directa
                    ya_existe = any(
                        r["origen"] == central_person and r["destino"] == nombre
                        for r in all_relationships
                    )
                    if not ya_existe:
                        all_relationships.append({
                            "origen": central_person,
                            "destino": nombre,
                            "relacion": "relacionado_con",
                            "hecho_id": None,
                            "contexto": "conexión implícita desde persona central"
                        })

        # Guardar en BD
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            for nombre, data in all_entities.items():
                cursor.execute("INSERT OR IGNORE INTO entities (nombre, tipo, embedding) VALUES (?, ?, ?)",
                               (nombre, data["tipo"], json.dumps(data["embedding"])))
            for rel in all_relationships:
                cursor.execute("INSERT INTO relationships (entidad_origen, entidad_destino, tipo_relacion, hecho_origen_id, peso) VALUES (?, ?, ?, ?, ?)",
                               (rel["origen"], rel["destino"], rel["relacion"], rel["hecho_id"], 1.0))
            conn.commit()

        return {
            "entities": list(all_entities.values()),
            "relationships": all_relationships,
            "mensaje": f"Grafo construido: {len(all_entities)} entidades, {len(all_relationships)} relaciones."
        }

    def build_graph_from_facts(self, namespace="default"):
        """Extrae entidades y relaciones de todos los hechos activos del namespace."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, content FROM facts WHERE namespace=? ORDER BY id", (namespace,))
            facts = cursor.fetchall()

        if not facts:
            return {"entities": [], "relationships": [], "mensaje": "No hay hechos para graficar."}

        all_entities = {}
        all_relationships = []

        for fact_id, content in facts:
            relaciones, entidades = self.extract_graph_entities(content)
            # Registrar entidades
            for ent in entidades:
                nombre = ent.get("nombre", "")
                tipo = ent.get("tipo", "concepto")
                if nombre and nombre not in all_entities:
                    all_entities[nombre] = {"nombre": nombre, "tipo": tipo, "embedding": None}
            # Registrar relaciones
            for origen, destino, tipo_rel, contexto in relaciones:
                if origen and destino:
                    all_relationships.append({
                        "origen": origen,
                        "destino": destino,
                        "relacion": tipo_rel,
                        "hecho_id": fact_id,
                        "contexto": contexto
                    })

        # Guardar en BD
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            for nombre, data in all_entities.items():
                cursor.execute("INSERT OR IGNORE INTO entities (nombre, tipo, embedding) VALUES (?, ?, ?)",
                               (nombre, data["tipo"], json.dumps(data["embedding"])))
            for rel in all_relationships:
                cursor.execute("INSERT INTO relationships (entidad_origen, entidad_destino, tipo_relacion, hecho_origen_id, peso) VALUES (?, ?, ?, ?, ?)",
                               (rel["origen"], rel["destino"], rel["relacion"], rel["hecho_id"], 1.0))
            conn.commit()

        return {
            "entities": list(all_entities.values()),
            "relationships": all_relationships,
            "mensaje": f"Grafo construido: {len(all_entities)} entidades, {len(all_relationships)} relaciones."
        }

    def generate_graph_html(self, namespace="default"):
        """Genera un archivo HTML con vis-network (CDN) para visualizar el grafo."""
        grafo = self.build_graph_from_facts(namespace)

        entities = grafo.get("entities", [])
        relationships = grafo.get("relationships", [])

        # Construir nodos y aristas para vis-network
        nodos_js = []
        for ent in entities:
            color = self._entity_color(ent.get("tipo", "concepto"))
            nodos_js.append(f"{{id: {len(nodos_js)}, label: {json.dumps(ent['nombre'])}, title: {json.dumps(ent.get('tipo','concepto'))}, color: '{color}'}}")

        aristas_js = []
        for rel in relationships:
            # Buscar índices de nodos
            origen_idx = next((i for i, e in enumerate(entities) if e["nombre"] == rel["origen"]), None)
            destino_idx = next((i for i, e in enumerate(entities) if e["nombre"] == rel["destino"]), None)
            if origen_idx is not None and destino_idx is not None:
                aristas_js.append(f"{{from: {origen_idx}, to: {destino_idx}, label: {json.dumps(rel['relacion'])}, arrows: 'to'}}" )

        html = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<title>MemHolografic - Grafo de Memoria</title>
<script type="text/javascript" src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
<style type="text/css">
  #mynetwork {{ width: 100vw; height: 100vh; position: absolute; top: 0; left: 0; }}
  body {{ margin: 0; overflow: hidden; font-family: sans-serif; }}
  #info {{ position: absolute; top: 10px; left: 10px; z-index: 100; background: rgba(255,255,255,0.9); padding: 10px; border-radius: 8px; max-width: 400px; }}
  h1 {{ margin: 0 0 10px 0; font-size: 16px; color: #333; }}
  p {{ margin: 5px 0; font-size: 13px; color: #555; }}
</style>
</head>
<body>
<div id="info">
  <h1>🧠 MemHolografic - Grafo de Memoria</h1>
  <p><strong>Entidades:</strong> {len(entities)}</p>
  <p><strong>Relaciones:</strong> {len(relationships)}</p>
  <p><strong>Namespace:</strong> {namespace}</p>
  <p><small>Haz clic en los nodos para explorar. Arrastra para mover.</small></p>
</div>
<div id="mynetwork"></div>
<script type="text/javascript">
  var nodos = new vis.DataSet([{", ".join(nodos_js)}]);
  var aristas = new vis.DataSet([{", ".join(aristas_js)}]);
  var container = document.getElementById("mynetwork");
  var data = {{ nodes: nodos, edges: aristas }};
  var opciones = {{
    nodes: {{ shape: 'dot', size: 16, font: {{ size: 14 }}, borderWidth: 2 }},
    edges: {{ font: {{ size: 12, align: 'middle' }}, arrows: {{ to: {{ enabled: true, scaleFactor: 0.5 }} }}, smooth: {{ type: 'continuous' }} }},
    physics: {{ enabled: true, solver: 'forceAtlas2Based', stabilization: {{ iterations: 100 }} }},
    interaction: {{ hover: true, tooltipDelay: 200 }}
  }};
  var red = new vis.Network(container, data, opciones);
  red.on("click", function (props) {{
    if (props.nodes.length > 0) {{
      var nodoId = props.nodes[0];
      var nodo = nodos.get(nodoId);
      console.log("Nodo seleccionado:", nodo.label);
    }}
  }});
</script>
</body>
</html>"""

        output_path = GRAPH_OUTPUT_PATH
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html)

        return {
            "output_path": output_path,
            "entities": len(entities),
            "relationships": len(relationships),
            "mensaje": grafo.get("mensaje", "Grafo generado.")
        }

    def _entity_color(self, tipo):
        colores = {
            "persona": "#ff6b6b",
            "proyecto": "#4ecdc4",
            "tecnologia": "#45b7d1",
            "lugar": "#96ceb4",
            "concepto": "#ffeaa7",
            "habilidad": "#fd79a8",
            "juego": "#a29bfe",
            "otro": "#b2bec3"
        }
        return colores.get(tipo, "#b2bec3")

if __name__ == "__main__":
    print("Motor de Memoria cargado. Usa mem_cli.py para interactuar.")
