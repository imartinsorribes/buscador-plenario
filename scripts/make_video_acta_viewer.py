"""Genera un visor HTML 'acta + vídeo' SINCRONIZADO (standalone, se abre con doble clic).

El vídeo de YouTube a la izquierda; a la derecha la transcripción: según avanza el vídeo se
resalta la frase actual y se autoscrollea; al pinchar una frase, el vídeo salta a ese minuto.

Uso:  python scripts/make_video_acta_viewer.py <transcript.json> <video_id> [salida.html]
"""
import json
import sys


def hms(t):
    t = int(t or 0)
    return (f"{t//3600}:" if t >= 3600 else "") + f"{(t%3600)//60:02d}:{t%60:02d}"


def build(transcript_path, video_id, out_path):
    d = json.loads(open(transcript_path, encoding="utf-8").read())
    segs = sorted(d["segments"], key=lambda s: s.get("start", 0))
    rows, order = [], {}
    for s in segs:
        txt = (s.get("text") or "").strip()
        if not txt:
            continue
        sp = s.get("speaker") or "?"
        if sp not in order:
            order[sp] = len(order) + 1            # Voz 1, 2, ... por orden de aparición
        rows.append({"t": round(s.get("start", 0), 1), "v": order[sp], "x": txt})
    data = json.dumps(rows, ensure_ascii=False)

    html = """<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Acta sincronizada con el vídeo</title>
<style>
 :root{ --ink:#1a1a1a; --muted:#6b6b6b; --line:#e2e0db; --paper:#faf9f6; --accent:#7a1f2b; }
 *{box-sizing:border-box} body{margin:0;background:var(--paper);color:var(--ink);
   font-family:ui-sans-serif,system-ui,"Segoe UI",Roboto,sans-serif}
 header{padding:14px 22px;border-bottom:1px solid var(--line)}
 header h1{margin:0;font-size:18px} header p{margin:2px 0 0;color:var(--muted);font-size:13px}
 .wrap{display:grid;grid-template-columns:minmax(380px,46%) 1fr;gap:0;height:calc(100vh - 64px)}
 .left{padding:18px;border-right:1px solid var(--line)} .vid{position:sticky;top:18px}
 .frame{aspect-ratio:16/9;background:#000;border:1px solid var(--line);overflow:hidden}
 .hint{color:var(--muted);font-size:12px;margin-top:10px}
 .right{overflow-y:auto;padding:8px 22px 60px}
 .seg{padding:9px 12px;border-radius:6px;cursor:pointer;border-left:3px solid transparent}
 .seg:hover{background:#f1efe9}
 .seg.active{background:#f6edda;border-left-color:var(--accent)}
 .seg .meta{font-size:11px;color:var(--accent);font-weight:600;font-variant-numeric:tabular-nums}
 .seg .who{font-size:11px;color:var(--muted)}
 .seg .tx{font-size:15px;line-height:1.5;margin-top:2px;color:#26241f}
</style></head><body>
<header><h1>Acta sincronizada con el vídeo</h1>
<p>El vídeo va resaltando lo transcrito. Pulsa cualquier frase para saltar a ese minuto. Los nombres son orientativos.</p></header>
<div class="wrap">
 <div class="left"><div class="vid"><div class="frame"><div id="player"></div></div>
   <p class="hint">Reproduce el vídeo y la transcripción se irá marcando sola.</p></div></div>
 <div class="right" id="list"></div>
</div>
<script>
 var SEGS = __DATA__;
 var VID = "__VID__";
 var hms = function(t){t=Math.floor(t||0);var h=Math.floor(t/3600),m=Math.floor(t%3600/60),s=t%60;
   return (h?h+":":"")+(h?String(m).padStart(2,"0"):m)+":"+String(s).padStart(2,"0");};
 var COLORS=["#7a1f2b","#2f5b8f","#3f6f3a","#9c3a6e","#b08328","#2f8f86","#5f7a2a","#356b4a","#a0522d","#444"];
 var list=document.getElementById("list"), nodes=[];
 SEGS.forEach(function(seg,i){
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
     playerVars:{rel:0,modestbranding:1}});
 }
 function find(t){ var lo=0,hi=SEGS.length-1,r=-1;
   while(lo<=hi){var m=(lo+hi)>>1; if(SEGS[m].t<=t){r=m;lo=m+1;}else{hi=m-1;}} return r; }
 setInterval(function(){
   if(!player||!player.getCurrentTime)return;
   var i=find(player.getCurrentTime());
   if(i!==cur && i>=0){
     if(nodes[cur])nodes[cur].classList.remove("active");
     nodes[i].classList.add("active");
     nodes[i].scrollIntoView({block:"center",behavior:"smooth"});
     cur=i;
   }
 },350);
 var s=document.createElement("script"); s.src="https://www.youtube.com/iframe_api"; document.head.appendChild(s);
</script></body></html>"""
    html = html.replace("__DATA__", data).replace("__VID__", video_id)
    open(out_path, "w", encoding="utf-8").write(html)
    print("->", out_path, "·", len(rows), "frases")


if __name__ == "__main__":
    tp = sys.argv[1] if len(sys.argv) > 1 else "data/transcripts/TN_gTdxQXA4.json"
    vid = sys.argv[2] if len(sys.argv) > 2 else "TN_gTdxQXA4"
    out = sys.argv[3] if len(sys.argv) > 3 else "data/processed/chiva_acta_sincronizada.html"
    build(tp, vid, out)
