"""Registro de voces para el pleno (idea del profesor: pre-registrar a cada concejal con unas
frases para que el pleno ya lo reconozca) + banco de pruebas de la huella de voz.

Usa EXACTAMENTE el mismo ECAPA y umbrales que el pleno (src/voiceid.py) y escribe en la MISMA
base de huellas que usa la app principal (`data/voiceprints/<slug>.json`), eligiendo la entidad
de la lista real (para que el slug coincida con el del pleno). Así lo registrado AQUÍ sale
auto-sugerido al procesar un pleno de esa entidad (vía suggest_from_voiceprints).

AVISO de calidad: la huella mezcla VOZ + CANAL (micro/códec). Hay que registrar con el MISMO
micro que se usará en el pleno, o con un micro de calidad. Un audio de WhatsApp/móvil recomprime
y baja mucho la similitud. La entidad "_test" es un sandbox que NO afecta a ningún pleno.

Arrancar:   .venv\\Scripts\\python.exe tools\\voice_test_app.py
Abrir:      http://localhost:8770
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

import numpy as np
from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src import voiceid  # noqa: E402

THR = 0.55                        # mismo umbral que el pleno (suggest_from_voiceprints)
MARGIN = 0.05                     # mismo margen sobre la 2ª persona

app = FastAPI(title="Registro de voces para el pleno")


def _ent(slug: str) -> str:
    """Saneo del slug de entidad (evita rutas raras); '_test' es el sandbox de pruebas."""
    s = "".join(c for c in (slug or "").strip() if c.isalnum() or c in "-_") or "_test"
    return s


def _webm_to_wav(data: bytes) -> tuple[str, float]:
    """Convierte el blob del micro o un archivo (ffmpeg detecta el formato) a wav mono 16 kHz."""
    tmp = Path(tempfile.gettempdir()) / f"voztest_{uuid.uuid4().hex}"
    src = tmp.with_suffix(".bin")
    dst = tmp.with_suffix(".wav")
    src.write_bytes(data)
    subprocess.run(["ffmpeg", "-y", "-i", str(src), "-ar", "16000", "-ac", "1", str(dst)],
                   check=True, capture_output=True)
    wav = voiceid._load_audio(str(dst))
    return str(dst), wav.shape[1] / 16000.0


def _embed(data: bytes):
    path, dur = _webm_to_wav(data)
    v = voiceid._embed_spans(voiceid._load_audio(path), [(0.0, dur)])
    return v, dur


@app.get("/entidades")
def entidades():
    """Lista de entidades reales (de la BD) + sandbox de pruebas. El slug debe coincidir con el
    que usa el pleno, por eso se elige de aquí en vez de escribirlo."""
    out = [{"slug": "_test", "nombre": "Pruebas (no afecta a ningún pleno)"}]
    try:
        from src import db
        con = db.connect()
        for e in db.list_entidades(con):
            out.append({"slug": e["slug"], "nombre": e["nombre"]})
        con.close()
    except Exception:
        pass
    # nº de personas ya registradas por entidad
    for e in out:
        vps = voiceid.load_voiceprints(e["slug"])
        e["n"] = sum(1 for n in vps if voiceid._vecs_of(vps[n]))
    return {"entidades": out}


@app.post("/enroll")
async def enroll(entidad: str = Form(...), name: str = Form(...), audio: UploadFile = File(...)):
    nm, ent = name.strip(), _ent(entidad)
    if not nm:
        return JSONResponse({"error": "pon el nombre de la persona"}, status_code=400)
    v, dur = _embed(await audio.read())
    if v is None or dur < 1.0:
        return JSONResponse({"error": "frase demasiado corta, di unos 3-4 segundos"}, status_code=400)
    vps = voiceid.load_voiceprints(ent)
    vecs = voiceid._cap(voiceid._vecs_of(vps.get(nm, {})) + [v])   # acumula una huella por frase
    vps[nm] = {"vecs": [x.tolist() for x in vecs], "n": int(vps.get(nm, {}).get("n", 0)) + 1,
               "party": vps.get(nm, {}).get("party", "")}
    voiceid.save_voiceprints(ent, vps)
    return {"name": nm, "n_frases": len(vecs), "dur": round(dur, 1)}


@app.post("/verify")
async def verify(entidad: str = Form(...), audio: UploadFile = File(...)):
    ent = _ent(entidad)
    v, dur = _embed(await audio.read())
    if v is None or dur < 1.0:
        return JSONResponse({"error": "frase demasiado corta, di unos 3-4 segundos"}, status_code=400)
    vps = voiceid.load_voiceprints(ent)
    names = [n for n in vps if voiceid._vecs_of(vps[n])]
    if not names:
        return JSONResponse({"error": "esta entidad aún no tiene voces registradas"}, status_code=400)
    sims = [(n, max(float(np.asarray(x) @ v) for x in voiceid._vecs_of(vps[n]))) for n in names]
    sims.sort(key=lambda x: -x[1])
    best, s1 = sims[0]
    s2 = sims[1][1] if len(sims) > 1 else 0.0
    ok = s1 >= THR and (s1 - s2) >= MARGIN
    return {"match": ok, "best": best, "sim": round(s1, 3), "second": round(s2, 3),
            "dur": round(dur, 1), "thr": THR, "margin": MARGIN,
            "all": [{"name": n, "sim": round(s, 3), "n": int(vps[n].get("n", 1))} for n, s in sims]}


@app.get("/list")
def listing(entidad: str):
    ent = _ent(entidad)
    vps = voiceid.load_voiceprints(ent)
    return {"slug": ent,
            "people": [{"name": n, "n_frases": len(voiceid._vecs_of(vps[n])),
                        "n_plenos": int(vps[n].get("n", 1))}
                       for n in vps if voiceid._vecs_of(vps[n])]}


@app.post("/delete")
def delete(entidad: str = Form(...), name: str = Form(...)):
    ent = _ent(entidad)
    vps = voiceid.load_voiceprints(ent)
    vps.pop(name, None)
    voiceid.save_voiceprints(ent, vps)
    return {"ok": True}


@app.post("/reset")
def reset(entidad: str = Form(...)):
    voiceid.save_voiceprints(_ent(entidad), {})
    return {"ok": True}


@app.get("/", response_class=HTMLResponse)
def index():
    return _HTML


_HTML = r"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Registro de voces para el pleno</title>
<script src="https://cdn.tailwindcss.com"></script></head>
<body class="bg-stone-50 text-stone-800">
<div class="max-w-2xl mx-auto p-6">
  <h1 class="text-2xl font-semibold">Registro de voces para el pleno</h1>
  <p class="text-sm text-stone-500 mt-1">Registra la voz de cada concejal con unas frases; al
  procesar un pleno de esa entidad se sugiere su nombre solo. Mismo motor y umbrales que el pleno.</p>

  <div class="mt-4 p-3 rounded-lg bg-amber-50 border border-amber-300 text-sm text-amber-900">
    <b>Importante — el micrófono cuenta.</b> La huella mezcla la voz con el canal de grabación.
    Registra con el <b>mismo micro que se usará en el pleno</b> (o uno de calidad). Un audio de
    <b>WhatsApp o de móvil</b> recomprime el sonido y baja mucho la fiabilidad. Lo más robusto es
    enrolar desde un <b>clip de un pleno anterior</b> de esa persona.
  </div>

  <!-- ENTIDAD -->
  <div class="mt-4 flex items-center gap-2">
    <label class="text-sm text-stone-600">Entidad:</label>
    <select id="entidad" class="border rounded-lg px-3 py-2 text-sm flex-1"></select>
  </div>

  <!-- ENROLAR -->
  <div class="mt-4 p-4 bg-white rounded-xl border border-stone-200">
    <div class="font-medium">1 · Registrar una voz</div>
    <input id="name" placeholder="Nombre de la persona" class="mt-2 w-full border rounded-lg px-3 py-2">
    <div class="text-sm text-stone-500 mt-3">Lee una frase (3-4 s) y pulsa parar. Repite con
    <b>3 frases distintas</b> para una huella estable. Sugeridas:</div>
    <ul class="text-sm text-stone-600 list-disc ml-5 mt-1">
      <li>Buenos días, muchas gracias por su asistencia a este pleno.</li>
      <li>Procedemos a la votación del primer punto del orden del día.</li>
      <li>Quiero agradecer la presencia de los concejales y vecinos.</li>
    </ul>
    <button id="recEnroll" class="mt-3 px-4 py-2 rounded-lg bg-stone-800 text-white">Grabar frase</button>
    <label class="text-sm text-stone-500 ml-2">o sube un archivo (clip de pleno, nota de voz…):
      <input type="file" id="enrollFile" accept="audio/*" class="text-sm"></label>
    <div id="enrollStatus" class="text-sm mt-2 text-stone-600"></div>
    <ul id="frases" class="text-sm mt-2 text-emerald-700"></ul>
  </div>

  <!-- COMPROBAR -->
  <div class="mt-4 p-4 bg-white rounded-xl border border-stone-200">
    <div class="font-medium">2 · Comprobar</div>
    <div class="text-sm text-stone-500 mt-1">Di cualquier cosa unos segundos (es independiente del
    texto). Prueba el <b>efecto del micro</b>: registra con uno y comprueba con otro.</div>
    <button id="recVerify" class="mt-3 px-4 py-2 rounded-lg bg-emerald-700 text-white">Grabar y comprobar</button>
    <label class="text-sm text-stone-500 ml-2">o sube un archivo:
      <input type="file" id="verifyFile" accept="audio/*" class="text-sm"></label>
    <div id="verifyStatus" class="text-sm mt-2 text-stone-600"></div>
    <div id="result" class="mt-3"></div>
  </div>

  <!-- REGISTRADAS -->
  <div class="mt-4 p-4 bg-white rounded-xl border border-stone-200">
    <div class="flex items-center justify-between">
      <div class="font-medium">Voces registradas <span id="count" class="text-stone-400 text-sm"></span></div>
      <button id="reset" class="text-sm text-rose-700">Borrar todas</button>
    </div>
    <ul id="people" class="text-sm mt-2 divide-y divide-stone-100"></ul>
  </div>

  <p class="mt-3 text-xs text-stone-400">Umbral del pleno: similitud ≥ 0.55 y +0.05 sobre la 2ª persona.
  Nunca se inventa un nombre; por debajo del umbral queda «desconocido».</p>
</div>
<script>
const sel = document.getElementById("entidad");
function ent(){ return sel.value; }
async function loadEnt(){
  const d = await (await fetch("/entidades")).json();
  sel.innerHTML = d.entidades.map(e =>
    "<option value='"+e.slug+"'>"+e.nombre+" — "+e.slug+" ("+e.n+")</option>").join("");
  loadPeople();
}
async function loadPeople(){
  const d = await (await fetch("/list?entidad="+encodeURIComponent(ent()))).json();
  document.getElementById("count").textContent = "· "+d.people.length+" en «"+d.slug+"»";
  document.getElementById("people").innerHTML = d.people.length ? d.people.map(p =>
    "<li class='py-1.5 flex items-center justify-between'><span>"+p.name+
    " <span class='text-stone-400'>("+p.n_frases+" huellas)</span></span>"+
    "<button data-n=\""+p.name.replace(/"/g,'&quot;')+"\" class='del text-rose-600 text-xs'>borrar</button></li>").join("")
    : "<li class='py-2 text-stone-400'>ninguna todavía</li>";
  document.querySelectorAll(".del").forEach(b => b.onclick = async () => {
    const f=new FormData(); f.append("entidad",ent()); f.append("name",b.dataset.n);
    await fetch("/delete",{method:"POST",body:f}); loadPeople();
  });
}
sel.onchange = loadPeople;

let media, chunks, recState=null;
async function rec(btn, label, onDone){
  if(recState===btn){ media.stop(); return; }
  const stream = await navigator.mediaDevices.getUserMedia({audio:true});
  media = new MediaRecorder(stream); chunks=[]; recState=btn;
  btn.textContent = "Parar"; btn.classList.add("animate-pulse");
  media.ondataavailable = e => chunks.push(e.data);
  media.onstop = async () => {
    stream.getTracks().forEach(t=>t.stop());
    btn.textContent = label; btn.classList.remove("animate-pulse"); recState=null;
    await onDone(new Blob(chunks, {type:"audio/webm"}));
  };
  media.start();
}
function fd(blob, extra){ const f=new FormData(); f.append("audio", blob, "a.webm");
  f.append("entidad", ent()); if(extra) for(const k in extra) f.append(k, extra[k]); return f; }

async function sendEnroll(blob){
  const name = document.getElementById("name").value.trim();
  const st = document.getElementById("enrollStatus");
  if(!name){ st.textContent="Pon el nombre primero."; return; }
  st.textContent = "Procesando…";
  const d = await (await fetch("/enroll", {method:"POST", body: fd(blob, {name})})).json();
  if(d.error){ st.textContent = "⚠ "+d.error; return; }
  st.textContent = "";
  const li = document.createElement("li");
  li.textContent = "Frase "+d.n_frases+" guardada ("+d.dur+" s)";
  document.getElementById("frases").appendChild(li);
  loadPeople();
}
async function sendVerify(blob){
  const st = document.getElementById("verifyStatus"); st.textContent="Comparando…";
  const d = await (await fetch("/verify", {method:"POST", body: fd(blob)})).json(); st.textContent="";
  const box = document.getElementById("result");
  if(d.error){ box.innerHTML = "<div class='text-amber-700'>"+d.error+"</div>"; return; }
  // 3 estados: reconocido / posible (es él pero baja la similitud por el canal) / no
  const near = !d.match && d.sim>=0.40 && (d.sim - d.second)>=d.margin;
  const col = d.match ? "emerald" : (near ? "amber" : "rose");
  const head = d.match ? ("Reconocido: "+d.best)
             : near ? ("Posible: "+d.best+" — confianza baja (¿micro/canal distinto?)")
             : "No reconocido con seguridad";
  let rows = d.all.map(p => "<tr><td class='pr-4'>"+p.name+"</td><td class='font-mono'>"+p.sim.toFixed(3)+"</td></tr>").join("");
  box.innerHTML =
    "<div class='p-3 rounded-lg bg-"+col+"-50 border border-"+col+"-200'>"+
    "<div class='font-semibold text-"+col+"-800'>"+head+"</div>"+
    "<div class='text-sm text-stone-600'>similitud "+d.sim.toFixed(3)+
       (d.all.length>1? " · 2ª "+d.second.toFixed(3):"")+" · "+d.dur+" s</div></div>"+
    "<table class='text-sm mt-2'>"+rows+"</table>";
}
document.getElementById("recEnroll").onclick = e => rec(e.target, "Grabar frase", sendEnroll);
document.getElementById("recVerify").onclick = e => rec(e.target, "Grabar y comprobar", sendVerify);
document.getElementById("enrollFile").onchange = e => { if(e.target.files[0]){ sendEnroll(e.target.files[0]); e.target.value=""; } };
document.getElementById("verifyFile").onchange = e => { if(e.target.files[0]){ sendVerify(e.target.files[0]); e.target.value=""; } };
document.getElementById("reset").onclick = async () => {
  if(!confirm("¿Borrar TODAS las voces de «"+ent()+"»?")) return;
  const f=new FormData(); f.append("entidad",ent());
  await fetch("/reset", {method:"POST", body:f});
  document.getElementById("frases").innerHTML="";
  document.getElementById("result").innerHTML="";
  loadPeople();
};
loadEnt();
</script></body></html>"""


def main() -> None:
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8770, reload=False)


if __name__ == "__main__":
    main()
