"""Visor 'acta + vídeo' SINCRONIZADO. Devuelve el HTML como string.

Se sirve por el servidor (origen http://) para que el reproductor de YouTube pueda incrustar
el vídeo — abierto como fichero local (file://) YouTube bloquea la incrustación y da error.
"""
from __future__ import annotations

import json
from pathlib import Path

_TPL = """<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Acta sincronizada con el vídeo</title>
<style>
 :root{ --ink:#1a1a1a; --muted:#6b6b6b; --line:#e2e0db; --paper:#faf9f6; --accent:#7a1f2b; }
 *{box-sizing:border-box} body{margin:0;background:var(--paper);color:var(--ink);
   font-family:ui-sans-serif,system-ui,"Segoe UI",Roboto,sans-serif}
 header{padding:14px 22px;border-bottom:1px solid var(--line)}
 header h1{margin:0;font-size:18px} header p{margin:2px 0 0;color:var(--muted);font-size:13px}
 .wrap{display:grid;grid-template-columns:minmax(380px,46%) 1fr;height:calc(100vh - 64px)}
 .left{padding:18px;border-right:1px solid var(--line)} .vid{position:sticky;top:18px}
 .frame{aspect-ratio:16/9;background:#000;border:1px solid var(--line);overflow:hidden}
 .hint{color:var(--muted);font-size:12px;margin-top:10px}
 .right{overflow-y:auto;padding:8px 22px 60px}
 .seg{padding:9px 12px;border-radius:6px;cursor:pointer;border-left:3px solid transparent}
 .seg:hover{background:#f1efe9}
 .seg.active{background:#f6edda}
 .seg .meta{font-size:11px;color:var(--accent);font-weight:600;font-variant-numeric:tabular-nums}
 .seg .who{font-size:11px;color:var(--muted)}
 .seg .tx{font-size:15px;line-height:1.5;margin-top:2px;color:#26241f}
</style></head><body>
<header><h1>Acta sincronizada con el vídeo</h1>
<p>El vídeo va resaltando lo transcrito. Pulsa cualquier frase para saltar a ese minuto. Las voces son las que separó la diarización.</p></header>
<div class="wrap">
 <div class="left"><div class="vid"><div class="frame"><div id="player"></div></div>
   <p class="hint">Reproduce el vídeo y la transcripción se irá marcando sola.</p></div></div>
 <div class="right" id="list"></div>
</div>
<script>
 var SEGS = __DATA__;
 var VID = "__VID__";
 var hms=function(t){t=Math.floor(t||0);var h=Math.floor(t/3600),m=Math.floor(t%3600/60),s=t%60;
   return (h?h+":":"")+(h?String(m).padStart(2,"0"):m)+":"+String(s).padStart(2,"0");};
 var COLORS=["#7a1f2b","#2f5b8f","#3f6f3a","#9c3a6e","#b08328","#2f8f86","#5f7a2a","#356b4a","#a0522d","#444"];
 var list=document.getElementById("list"), nodes=[];
 SEGS.forEach(function(seg){
   var c=COLORS[(seg.v-1)%COLORS.length];
   var el=document.createElement("div"); el.className="seg"; el.style.borderLeftColor=c;
   var esc=seg.x.replace(/[&<>]/g,function(x){return{"&":"&amp;","<":"&lt;",">":"&gt;"}[x];});
   el.innerHTML='<span class="meta">'+hms(seg.t)+'</span> '+
     '<span class="who"><span style="display:inline-block;width:9px;height:9px;border-radius:2px;background:'+c+';margin-right:5px;vertical-align:middle"></span>Voz '+seg.v+'</span>'+
     '<div class="tx">'+esc+'</div>';
   el.onclick=function(){ if(player&&player.seekTo){player.seekTo(seg.t,true);player.playVideo();} };
   list.appendChild(el); nodes.push(el);
 });
 var player, cur=-1;
 function onYouTubeIframeAPIReady(){
   player=new YT.Player("player",{width:"100%",height:"100%",videoId:VID,
     host:"https://www.youtube-nocookie.com",
     playerVars:{rel:0,modestbranding:1,origin:location.origin}});
 }
 function find(t){ var lo=0,hi=SEGS.length-1,r=-1;
   while(lo<=hi){var m=(lo+hi)>>1; if(SEGS[m].t<=t){r=m;lo=m+1;}else{hi=m-1;}} return r; }
 setInterval(function(){
   if(!player||!player.getCurrentTime)return;
   var i=find(player.getCurrentTime());
   if(i!==cur && i>=0){
     if(nodes[cur])nodes[cur].classList.remove("active");
     nodes[i].classList.add("active");
     nodes[i].scrollIntoView({block:"center",behavior:"smooth"}); cur=i;
   }
 },350);
 var s=document.createElement("script"); s.src="https://www.youtube.com/iframe_api"; document.head.appendChild(s);
</script></body></html>"""


def build_html(transcript_path, video_id: str) -> str:
    d = json.loads(Path(transcript_path).read_text(encoding="utf-8"))
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
    return _TPL.replace("__DATA__", json.dumps(rows, ensure_ascii=False)).replace("__VID__", video_id)
