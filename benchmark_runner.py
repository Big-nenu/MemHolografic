import json
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
            
            # Clear DB for each case to avoid contamination
            engine._init_db()
            
            # 1. Injection Phase
            for phrase in trajectory:
                engine.inject_fact(phrase)
            
            # 2. Retrieval Phase (Simulate query)
            # We look for the most energetic fact related to the first phrase of trajectory
            final_memory = engine.get_final_state()
            # For simplicity, we take the most "consolidated" (longest/richest) fact
            # In a real system, we'd query using a vector.
            best_fact = max(final_memory, key=len) if final_memory else "No memory"
            
            # 3. Evaluation (Simple overlap for prototype)
            # In real life, we'd use a LLM to grade the similarity
            success = any(word in best_fact.lower() for word in gold.lower().split() if len(word) > 5)
            
            results.append({
                "id": case_id,
                "success": success,
                "result": best_fact,
                "gold": gold
            })

    # Print Final Report
    print("\n=== MEMBENCH FINAL REPORT ===")
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
