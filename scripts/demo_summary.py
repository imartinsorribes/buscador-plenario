"""Demo rápida del resumen con el LLM local (Qwen3-4B vía Ollama).

Resume un fragmento representativo del Diario para ver la calidad del modelo.
Uso:  python scripts/demo_summary.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.config import load_config  # noqa: E402
from src.diario import extract_text  # noqa: E402
from src.summarize import summarize_text  # noqa: E402

cfg = load_config()
text = extract_text("data/diarios/DSCD-15-PL-109.pdf")
fragmento = text[:8000]
print(f"Resumiendo {len(fragmento)} caracteres con '{cfg.llm.model}'...\n")
print(summarize_text(fragmento, cfg))
