import sys
from mem_engine import MemHolograficEngine

engine = MemHolograficEngine()

if len(sys.argv) < 3:
    print("Usage: python mem_cli.py [inject|query] \"text\"")
    sys.exit(1)

cmd = sys.argv[1]
text = sys.argv[2]

if cmd == "inject":
    print(engine.inject(text))
elif cmd == "query":
    res = engine.query(text)
    if not res:
        print("No related memories found.")
    for sim, fid, energy, content in res:
        print(f"Sim: {sim:.4f} | ID: {fid} | Energy: {energy:.2f} | {content}")
else:
    print("Unknown command")
