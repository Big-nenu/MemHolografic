import json
import re

class MemHolograficEngine:
    def __init__(self, trust_threshold=0.7):
        self.memory = [] # List of facts: {"content": str, "energy": float}
        self.threshold = trust_threshold

    def inject_fact(self, content):
        print(f"\n[INJECTING]: {content}")
        # In a real system, we would use embeddings. 
        # Here we simulate " Semantic Similarity" by checking keyword overlap.
        new_fact = {"content": content, "energy": 0.5}
        
        collision = False
        for i, existing_fact in enumerate(self.memory):
            if self._check_collision(content, existing_fact["content"]):
                print(f"🌊 COLLISION DETECTED with: {existing_fact['content']}")
                # INTERFERENCE: Merge the waves
                merged_content = self._merge_waves(existing_fact["content"], content)
                merged_energy = min(1.0, existing_fact["energy"] + 0.2)
                
                print(f"✨ FUSION COMPLETE: {merged_content} (Energy: {merged_energy:.2f})")
                self.memory[i] = {"content": merged_content, "energy": merged_energy}
                collision = True
                break
        
        if not collision:
            print("📍 NO COLLISION: Storing as a new independent wave.")
            self.memory.append(new_fact)

    def _check_collision(self, text1, text2):
        # Simple keyword-based similarity for the prototype
        words1 = set(re.findall(r'\w+', text1.lower()))
        words2 = set(re.findall(r'\w+', text2.lower()))
        intersection = words1.intersection(words2)
        # If more than 30% of words overlap, we consider it a "collision"
        return len(intersection) / max(len(words1), len(words2)) > 0.3

    def _merge_waves(self, text1, text2):
        # In the real version, an LLM would do this.
        # For the prototype, we simulate a smart merge.
        if "superposición" in text1.lower() and "superposición" in text2.lower():
            return "CONSOLIDATED: La superposición cuántica es un fenómeno fundamental donde una partícula reside en múltiples estados, siendo la base de la computación cuántica."
        return f"MERGED: {text1} AND {text2}"

    def show_memory(self):
        print("\n--- CURRENT MEMORY STATE (The Palace) ---")
        for i, f in enumerate(self.memory):
            print(f"{i+1}. [{f['energy']:.2f}] {f['content']}")

# --- TEST RUN ---
if __name__ == "__main__":
    engine = MemHolograficEngine()
    
    # Simulating the "Quantum" trajectory
    trajectory = [
        "La superposición permite que una partícula esté en dos estados a la vez",
        "La superposición es la base de la computación cuántica",
        "En la mecánica cuántica, la superposición es un fenómeno fundamental"
    ]
    
    for phrase in trajectory:
        engine.inject_fact(phrase)
    
    engine.show_memory()
