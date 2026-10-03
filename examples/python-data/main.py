from pathlib import Path

print("Preparing binary artifact", flush=True)
Path("output").mkdir(exist_ok=True)
Path("output/result.bin").write_bytes(bytes(range(256)))
print("Done", flush=True)
