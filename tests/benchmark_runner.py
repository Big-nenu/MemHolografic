import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import time
from mem_engine import MemHolograficEngine

def run_benchmark():
    dataset_path = "tests/dataset.jsonl"
    # FIX: Usar base de datos aislada para pruebas
    engine = MemHolograficEngine(db_path="tests/bench.db")
    
    results = []
    
    with open(dataset_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip(): continue
            case = json.loads(line)
            case_id = case["id"]
            trajectory = case["trajectory"]
            gold = case["gold_answer"]
            
            engine.clear_db()
            
            # 1. Injection Phase
            for phrase in trajectory:
                engine.inject(phrase)
                time.sleep(0.1)
            
            # 2. Dreaming Phase (FIX: Ahora es parte obligatoria del proceso)
            print(f"Dreaming for case {case_id}...")
            engine.dream()
            
            # 3. Retrieval Phase
            final_memory = engine.get_all_facts()
            best_fact = max(final_memory, key=len) if final_memory else "No memory"
            
            gold_words = [w.lower() for w in gold.split() if len(w) > 5]
            matches = sum(1 for w in gold_words if w in best_fact.lower())
            success = (matches / len(gold_words) >= 0.3) if gold_words else False
            
            results.append({
                "id": case_id,
                "success": success,
                "result": best_fact,
                "gold": gold
            })

    print("\n=== MEMBENCH FINAL REPORT (Professional Version) ===")
    print(f"Total Cases: {len(results)}")
    successes = sum(1 for r in results if r["success"])
    print(f"Successful Unifications: {successes}")
    print(f"Accuracy: {(successes/len(results)*100):.2f}%")
    print("\n--- Detailed Failures ---")
    for r in results:
        if not r["success"]:
            print(f"ID {r['id']}: Expected {r['gold'][:50]}... | Got {r['result'][:50]}...")

if __name__ == "__main__":
    run_benchmark()
