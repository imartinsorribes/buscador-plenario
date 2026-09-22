"""Convierte el pytorch_model.bin de un modelo HF (ya en caché) a model.safetensors.

Sirve para esquivar la restricción de transformers (con torch < 2.6 no puede usar
torch.load por la CVE-2025-32434). Al haber un model.safetensors, transformers lo
carga sin torch.load. No descarga nada: reusa el .bin ya bajado.

Uso:  python scripts/bin_to_safetensors.py BAAI/bge-m3
"""
import sys
from pathlib import Path

import torch
from safetensors.torch import save_file

model_id = sys.argv[1] if len(sys.argv) > 1 else "BAAI/bge-m3"
cache = (Path.home() / ".cache" / "huggingface" / "hub"
         / ("models--" + model_id.replace("/", "--")) / "snapshots")
snap = sorted(cache.glob("*"))[-1]
bin_path = snap / "pytorch_model.bin"
out_path = snap / "model.safetensors"

if out_path.exists():
    print("Ya existe:", out_path)
    sys.exit(0)

print("Cargando", bin_path, "...")
state = torch.load(str(bin_path), map_location="cpu", weights_only=True)
state = {k: v.contiguous() for k, v in state.items() if isinstance(v, torch.Tensor)}
save_file(state, str(out_path), metadata={"format": "pt"})
print(f"Guardado {out_path}  ({out_path.stat().st_size / 1e9:.2f} GB)")
