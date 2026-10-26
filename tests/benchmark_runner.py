import json
import time
from mem_engine import MemHolograficEngine

def run_benchmark():
    dataset_path = "tests/dataset.jsonl"
    engine = MemHolograficEngine()
    
    results = []
    
    with open(dataset_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip(): continue
            case = json.loads(line)
            case_id = case["id"]
            trajectory = case["trajectory"]
            gold = case["gold_answer"]
            
            # Reset DB for each case to avoid contamination
            engine._init_db()
            
            # 1. Injection Phase with pauses
            for phrase in trajectory:
                engine.inject_fact(phrase)
                time.sleep(0.1) # Stability pause
            
            # 2. Retrieval Phase
            final_memory = engine.get_final_state()
            best_fact = max(final_memory, key=len) if final_memory else "No memory"
            
            # 3. Evaluation (Overlap based)
            success = any(word in best_fact.lower() for word in gold.lower().split() if len(word) > 5)
            
            results.append({
                "id": case_id,
                "success": success,
                "result": best_fact,
                "gold": gold
            })

    # Final Report
    print("\n=== MEMBENCH FINAL REPORT (Lighweight Version) ===")
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
