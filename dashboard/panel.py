"""Panel web de chats (aparte de WAHA).

Read-only. Lee las conversaciones activas de Redis y las muestra en una página
tipo WhatsApp, con auto-refresco. Protegido por un token simple (?token=...).

Rutas:
  GET /panel?token=...            -> página HTML
  GET /panel/api/chats?token=...  -> JSON con las conversaciones
"""
import os

from fastapi import APIRouter, Query
from fastapi.responses import HTMLResponse, JSONResponse

from orchestrator import context
from shared import auth

router_panel = APIRouter()

PANEL_TOKEN = os.getenv("PANEL_TOKEN", "catu2026")


def _vendedor(numero: str) -> str:
    perfil = auth._MOCK_ASESORES.get(numero)
    return perfil.get("nombre", "") if perfil else ""


@router_panel.get("/panel/api/chats")
async def api_chats(token: str = Query("")):
    if token != PANEL_TOKEN:
        return JSONResponse({"error": "token inválido"}, status_code=403)
    chats = await context.list_conversations()
    for c in chats:
        c["vendedor"] = _vendedor(c["numero"])
        c["n"] = len(c.get("mensajes", []))
    # más mensajes primero (proxy de actividad reciente)
    chats.sort(key=lambda c: c["n"], reverse=True)
    return JSONResponse({"chats": chats, "total": len(chats)})


@router_panel.get("/panel", response_class=HTMLResponse)
async def panel(token: str = Query("")):
    if token != PANEL_TOKEN:
        return HTMLResponse(
            "<body style='font-family:sans-serif;padding:40px'>"
            "<h3>🔒 Token inválido</h3><p>Usá <code>/panel?token=TU_TOKEN</code></p></body>",
            status_code=403,
        )
    return HTMLResponse(_HTML.replace("__TOKEN__", token))


_HTML = """<!doctype html>
<html lang="es"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Catu · Panel de chats</title>
<style>
  * { box-sizing: border-box; }
  body { margin:0; font-family: -apple-system, Segoe UI, Roboto, sans-serif; background:#0b141a; color:#e9edef; }
  header { background:#202c33; padding:12px 18px; display:flex; align-items:center; gap:12px; position:sticky; top:0; z-index:5; }
  header h1 { font-size:16px; margin:0; font-weight:600; }
  header .meta { color:#8696a0; font-size:13px; margin-left:auto; }
  .wrap { display:flex; height:calc(100vh - 46px); }
  .list { width:320px; border-right:1px solid #222d34; overflow-y:auto; flex-shrink:0; }
  .item { padding:12px 16px; border-bottom:1px solid #182229; cursor:pointer; }
  .item:hover, .item.sel { background:#202c33; }
  .item .n { font-weight:600; font-size:14px; }
  .item .v { color:#8696a0; font-size:12px; margin-top:2px; }
  .item .c { color:#667781; font-size:12px; margin-top:4px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
  .chat { flex:1; overflow-y:auto; padding:18px 8%; background-image:linear-gradient(#0b141a,#0b141a); }
  .empty { color:#8696a0; text-align:center; margin-top:60px; }
  .msg { max-width:70%; padding:8px 11px; border-radius:8px; margin:6px 0; font-size:14px; line-height:1.35; white-space:pre-wrap; word-wrap:break-word; }
  .user { background:#202c33; margin-right:auto; border-top-left-radius:0; }
  .assistant { background:#005c4b; margin-left:auto; border-top-right-radius:0; }
  .role { font-size:10px; text-transform:uppercase; letter-spacing:.5px; color:#8696a0; margin-bottom:2px; }
  .chat h2 { font-size:15px; color:#e9edef; position:sticky; top:0; background:#111b21; padding:10px 14px; border-radius:8px; margin:0 0 10px; }
</style></head>
<body>
<header>
  <h1>💬 Catu · Panel de chats</h1>
  <span class="meta" id="meta">cargando…</span>
</header>
<div class="wrap">
  <div class="list" id="list"></div>
  <div class="chat" id="chat"><div class="empty">Elegí una conversación de la izquierda</div></div>
</div>
<script>
const TOKEN = "__TOKEN__";
let data = [], sel = null;

function pintarLista() {
  const list = document.getElementById('list');
  list.innerHTML = data.map((c,i) => {
    const last = c.mensajes.length ? c.mensajes[c.mensajes.length-1].content : '';
    return `<div class="item ${sel===c.numero?'sel':''}" onclick="elegir('${c.numero}')">
      <div class="n">${c.vendedor || c.numero}</div>
      <div class="v">${c.vendedor ? c.numero : 'sin identificar'} · ${c.n} msgs</div>
      <div class="c">${escapeHtml(last).slice(0,60)}</div>
    </div>`;
  }).join('') || '<div class="empty" style="padding:20px">Sin chats activos</div>';
}

function pintarChat() {
  const chat = document.getElementById('chat');
  const c = data.find(x => x.numero === sel);
  if (!c) { chat.innerHTML = '<div class="empty">Elegí una conversación</div>'; return; }
  chat.innerHTML = `<h2>${c.vendedor || c.numero} <span style="color:#8696a0;font-weight:400">· ${c.numero}</span></h2>` +
    c.mensajes.map(m => `<div class="msg ${m.role}">
      <div class="role">${m.role==='user'?'cliente':'Catu'}</div>${escapeHtml(m.content)}</div>`).join('');
  chat.scrollTop = chat.scrollHeight;
}

function elegir(num) { sel = num; pintarLista(); pintarChat(); }
function escapeHtml(s){ return (s||'').replace(/[&<>]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[c])); }

async function cargar() {
  try {
    const r = await fetch('/panel/api/chats?token=' + encodeURIComponent(TOKEN));
    const j = await r.json();
    data = j.chats || [];
    document.getElementById('meta').textContent = j.total + ' chats · actualiza cada 5s';
    if (!sel && data.length) sel = data[0].numero;
    pintarLista(); pintarChat();
  } catch(e) { document.getElementById('meta').textContent = 'error al cargar'; }
}
cargar(); setInterval(cargar, 5000);
</script>
</body></html>"""
