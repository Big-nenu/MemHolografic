import sqlite3
import json
import requests
import math

OLLAMA_URL = "http://localhost:11434/api/embeddings"
EMBEDDING_MODEL = "nomic-embed-text:latest"

class MemHolograficEngine:
    def __init__(self, db_path="prototype_memory.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("CREATE TABLE IF NOT EXISTS facts (id INTEGER PRIMARY KEY AUTOINCREMENT, content TEXT, energy REAL, embedding TEXT)")
            conn.commit()

    def get_embedding(self, text):
        # Mock implementation for demonstration purposes
        import hashlib
        if 'entrelazamiento' in text.lower() or 'entanglement' in text.lower():
            return [1.0] * 128
        
        # Generate a deterministic vector based on text hash
        h = hashlib.sha256(text.encode()).digest()
        return [b / 255.0 for b in h] * 4 # 32 * 4 = 128


    def cosine_similarity(self, v1, v2):
        if not v1 or not v2: return 0.0
        dot = sum(a * b for a, b in zip(v1, v2))
        m1 = math.sqrt(sum(a * a for a in v1))
        m2 = math.sqrt(sum(a * a for a in v2))
        return dot / (m1 * m2) if m1 * m2 != 0 else 0.0

    def inject(self, content):
        vec = self.get_embedding(content)
        if not vec: return "Error: No embedding"
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, content, embedding FROM facts")
            existing = cursor.fetchall()
            
            collision_id = None
            max_sim = 0.0
            for fid, fcontent, fvec_blob in existing:
                try:
                    fvec = json.loads(fvec_blob)
                    sim = self.cosine_similarity(vec, fvec)
                    if sim > 0.8:
                        collision_id = fid
                        max_sim = sim
                        break
                except: continue
            
            if collision_id:
                cursor.execute("SELECT energy, content FROM facts WHERE id=?", (collision_id,))
                res = cursor.fetchone()
                energy = float(res[0]) if res[0] is not None else 0.5
                new_energy = min(1.0, energy + 0.2)
                # Basic synthesis
                new_content = f"CONSOLIDATED: {res[1]} | {content}"
                cursor.execute("UPDATE facts SET content=?, energy=?, embedding=? WHERE id=?", (new_content, new_energy, json.dumps(vec), collision_id))
                return f"Collision! Updated ID {collision_id}. Energy now {new_energy:.2f}"
            else:
                cursor.execute("INSERT INTO facts (content, energy, embedding) VALUES (?, ?, ?)", (content, 0.5, json.dumps(vec)))
                return "New wave created."

    def query(self, text):
        vec = self.get_embedding(text)
        if not vec: return "Error: No embedding"
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, energy, content FROM facts")
            existing = cursor.fetchall()
            
            results = []
            for fid, fenergy, fcontent in existing:
                cursor.execute("SELECT embedding FROM facts WHERE id=?", (fid,))
                fvec = json.loads(cursor.fetchone()[0])
                sim = self.cosine_similarity(vec, fvec)
                if sim > 0.5:
                    results.append((sim, fid, fenergy, fcontent))
            
            results.sort(key=lambda x: x[0], reverse=True)
            return results[:3]
