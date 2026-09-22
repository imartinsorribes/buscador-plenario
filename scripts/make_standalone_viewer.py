"""Visor 'acta + grabación' AUTÓNOMO (funciona offline, sin servidor ni YouTube).

Usa el audio local (<audio>) + la transcripción sincronizada (Voz N). Pensado para ENVIAR:
genera una carpeta con visor.html + grabacion.m4a y un .zip listo para adjuntar.

Uso:  python scripts/make_standalone_viewer.py <transcript.json> <audio.m4a> <out_dir>
"""
import json
import os
import shutil
import sys

TPL = """<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Acta sincronizada — __TITLE__</title>
<style>
 :root{--ink:#1a1a1a;--muted:#6b6b6b;--line:#e2e0db;--paper:#faf9f6;--accent:#7a1f2b}
 *{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);
   font-family:ui-sans-serif,system-ui,"Segoe UI",Roboto,sans-serif}
 .top{position:sticky;top:0;background:var(--paper);border-bottom:1px solid var(--line);
   padding:14px 22px;z-index:5}
 .top h1{margin:0 0 2px;font-size:18px}.top p{margin:0 0 10px;color:var(--muted);font-size:13px}
 audio{width:100%;height:38px}
 .list{max-width:900px;margin:0 auto;padding:14px 22px 80px}
 .seg{padding:9px 12px;border-radius:6px;cursor:pointer;border-left:3px solid transparent}
 .seg:hover{background:#f1efe9}.seg.active{background:#f6edda}
 .seg .meta{font-size:11px;color:var(--accent);font-weight:600;font-variant-numeric:tabular-nums}
 .seg .who{font-size:11px;color:var(--muted)}
 .seg .tx{font-size:15px;line-height:1.5;margin-top:2px;color:#26241f}
</style></head><body>
<div class="top"><h1>__TITLE__</h1>
__PLAYER__</div>
<div class="list" id="list"></div>
<script>
 var SEGS=__DATA__;
 var hms=function(t){t=Math.floor(t||0);var h=Math.floor(t/3600),m=Math.floor(t%3600/60),s=t%60;
   return (h?h+":":"")+(h?String(m).padStart(2,"0"):m)+":"+String(s).padStart(2,"0");};
 var COLORS=["#7a1f2b","#2f5b8f","#3f6f3a","#9c3a6e","#b08328","#2f8f86","#5f7a2a","#356b4a","#a0522d","#444"];
 var aud=document.getElementById("aud"),list=document.getElementById("list"),nodes=[],cur=-1;
 SEGS.forEach(function(seg){
   var c=COLORS[(seg.v-1)%COLORS.length];
   var el=document.createElement("div");el.className="seg";el.style.borderLeftColor=c;
   var esc=seg.x.replace(/[&<>]/g,function(x){return{"&":"&amp;","<":"&lt;",">":"&gt;"}[x];});
   el.innerHTML='<span class="meta">'+hms(seg.t)+'</span> <span class="who">'+
     '<span style="display:inline-block;width:9px;height:9px;border-radius:2px;background:'+c+';margin-right:5px;vertical-align:middle"></span>Voz '+seg.v+'</span>'+
     '<div class="tx">'+esc+'</div>';
   el.onclick=function(){aud.currentTime=seg.t;aud.play();};
   list.appendChild(el);nodes.push(el);
 });
 function find(t){var lo=0,hi=SEGS.length-1,r=-1;while(lo<=hi){var m=(lo+hi)>>1;
   if(SEGS[m].t<=t){r=m;lo=m+1;}else{hi=m-1;}}return r;}
 var lastUser=0, topbar=document.querySelector(".top");
 ["wheel","touchmove","keydown","mousedown"].forEach(function(e){addEventListener(e,function(){lastUser=Date.now();},{passive:true});});
 aud.addEventListener("timeupdate",function(){
   var i=find(aud.currentTime);
   if(i===cur||i<0)return;
   if(nodes[cur])nodes[cur].classList.remove("active");
   nodes[i].classList.add("active"); cur=i;
   if(Date.now()-lastUser<4000)return;                       // respeta el scroll manual
   var hb=topbar?topbar.getBoundingClientRect().bottom:0, r=nodes[i].getBoundingClientRect();
   if(r.top<hb+12 || r.bottom>window.innerHeight-24)          // solo si está tapada o fuera de vista
     window.scrollTo({top:window.scrollY+r.top-hb-28,behavior:"smooth"});
 });
</script></body></html>"""


def build(transcript_path, media_path, out_dir, title="Pleno de Chiva"):
    d = json.loads(open(transcript_path, encoding="utf-8").read())
    segs = sorted(d["segments"], key=lambda s: s.get("start", 0))
    rows, order = [], {}
    for s in segs:
        txt = (s.get("text") or "").strip()
        if not txt:
            continue
        sp = s.get("speaker") or "?"
        if sp not in order:
            order[sp] = len(order) + 1
        rows.append({"t": round(s.get("start", 0), 1), "v": order[sp], "x": txt})
    os.makedirs(out_dir, exist_ok=True)
    ext = os.path.splitext(media_path)[1].lower()
    media_name = "grabacion" + ext
    shutil.copy(media_path, os.path.join(out_dir, media_name))
    if ext in (".mp4", ".webm", ".mov", ".mkv"):
        player = (f'<video id="aud" controls preload="metadata" '
                  f'style="width:100%;max-height:46vh;background:#000;border:1px solid var(--line)">'
                  f'<source src="{media_name}"></video>')
    else:
        player = f'<audio id="aud" controls preload="metadata" style="width:100%"><source src="{media_name}"></audio>'
    html = (TPL.replace("__DATA__", json.dumps(rows, ensure_ascii=False))
            .replace("__PLAYER__", player).replace("__TITLE__", title))
    open(os.path.join(out_dir, "visor.html"), "w", encoding="utf-8").write(html)
    zip_path = shutil.make_archive(out_dir.rstrip("/\\"), "zip", out_dir)
    print(f"-> {out_dir}/visor.html (+ {media_name}, {len(rows)} frases)")
    print(f"-> {zip_path}  ({os.path.getsize(zip_path)//1024//1024} MB)")


if __name__ == "__main__":
    tp = sys.argv[1] if len(sys.argv) > 1 else "data/transcripts/TN_gTdxQXA4.json"
    mp = sys.argv[2] if len(sys.argv) > 2 else "data/raw_audio/TN_gTdxQXA4.m4a"
    od = sys.argv[3] if len(sys.argv) > 3 else "data/processed/visor_chiva"
    build(tp, mp, od)
