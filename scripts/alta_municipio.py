"""Alta de un municipio nuevo en 5 minutos (demuestra la escalabilidad Chiva -> cualquiera).

Hace de una tacada todo lo que un ayuntamiento nuevo necesita:
  1. crea la ENTIDAD en la BD (slug corto estable, el mismo que usará todo),
  2. descarga su ESCUDO de Wikimedia Commons (membrete del acta),
  3. crea su GLOSARIO de términos locales (plantilla comentada para lexfix),
  4. imprime los pasos siguientes (registro de voces, primer pleno).

Uso:  python scripts/alta_municipio.py "Ayuntamiento de Buñol"
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.server import _slug  # noqa: E402  (misma regla de slug que el producto)
from src import db  # noqa: E402
from src.config import resolve_path  # noqa: E402
from src.escudo import ensure_escudo  # noqa: E402

_PLANTILLA = """# Términos locales de {nombre} — corrección léxica del ASR (src/lexfix.py).
# UNO por línea. Añade aquí nombres de parajes, pedanías, mancomunidades, siglas locales…
# que el reconocedor de voz suela escribir mal. También alias exactos 'MAL=BIEN'.
# OJO: no añadas palabras que colisionen con vocabulario común (ver memoria del proyecto).
mancomunidad
"""


def main() -> None:
    nombre = " ".join(sys.argv[1:]).strip()
    if not nombre:
        sys.exit('Uso:  python scripts/alta_municipio.py "Ayuntamiento de X"')
    slug = _slug(nombre)
    print(f"Alta de «{nombre}»  (slug: {slug})\n")

    con = db.connect()
    eid = db.upsert_entidad(con, slug, nombre, "ayuntamiento")
    con.close()
    print(f"  [1/3] entidad en BD (id {eid})")

    esc = ensure_escudo(slug, nombre)
    print(f"  [2/3] escudo: {esc or 'no encontrado en Commons (puedes dejar data/ref/escudo_' + slug + '.png a mano)'}")

    terms = resolve_path(f"data/ref/terms_{slug}.txt")
    if not terms.exists():
        terms.write_text(_PLANTILLA.format(nombre=nombre), encoding="utf-8")
        print(f"  [3/3] glosario plantilla: {terms}")
    else:
        print(f"  [3/3] glosario ya existía: {terms}")

    print(f"""
Listo. Pasos siguientes:
  · Registro de voces:  pestaña «Registro de voces» -> entidad «{nombre}»
    (con el MISMO micro del salón de plenos; 3-5 frases por concejal)
  · Primer pleno:       pestaña «Generar acta» -> pega el YouTube y escribe «{nombre}»
  · Términos locales:   edita {terms.name} con parajes/siglas que el ASR falle
""")


if __name__ == "__main__":
    main()
