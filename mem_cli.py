import sys
from mem_engine import MemHolograficEngine

engine = MemHolograficEngine()

if len(sys.argv) < 2:
    print("Usage: python mem_cli.py [inject|query|dream|reflect] \"text\"")
    sys.exit(1)

cmd = sys.argv[1]

if cmd == "inject":
    if len(sys.argv) < 3:
        print("Usage: python mem_cli.py inject \"text\"")
        sys.exit(1)
    print(engine.inject(sys.argv[2]))
elif cmd == "query":
    if len(sys.argv) < 3:
        print("Usage: python mem_cli.py query \"text\"")
        sys.exit(1)
    res = engine.query(sys.argv[2])
    if isinstance(res, str):
        print(res)
    elif res:
        for sim, fid, energy, content in res:
            print(f"Sim: {sim:.4f} | ID: {fid} | Energy: {energy:.2f} | {content}")
    else:
        print("No related memories found.")
elif cmd == "dream":
    result = engine.dream()
    if result:
        print(result)
elif cmd == "reflect":
    result = engine.reflect()
    if result:
        print(result)
else:
    print("Unknown command. Use: inject, query, dream, or reflect")
