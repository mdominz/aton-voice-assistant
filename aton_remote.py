"""
ATON Remote v0.3 — ponte entre o Aton (PC), o app do celular e o atalho da Siri.
Roda dentro do Aton (assistente.py chama iniciar() numa thread). Porta 8766: a 8765 é a do wallpaper.
Depois (uma vez):  tailscale serve --bg 8766
"""
import asyncio, base64, logging, os, secrets, time, uuid
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Header, HTTPException
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uvicorn

log = logging.getLogger("aton")
PORTA = 8766
TOKEN_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "aton_token.txt")
if not os.path.exists(TOKEN_FILE):
    open(TOKEN_FILE, "w").write(secrets.token_urlsafe(24))
TOKEN = open(TOKEN_FILE).read().strip()

# ==================================================================
# FUNÇÕES DO ATON: o assistente.py preenche HOOKS ao iniciar (são síncronas; aqui rodam em threads)
# ==================================================================
HOOKS = {}

async def aton_processar(texto: str) -> str:
    if "processar" not in HOOKS: return "O Aton ainda está carregando."
    return await asyncio.to_thread(HOOKS["processar"], texto)

async def aton_stt(audio_bytes: bytes, mime: str) -> str:
    if "stt" not in HOOKS: return ""
    return await asyncio.to_thread(HOOKS["stt"], audio_bytes, mime)

async def aton_tts(texto: str) -> tuple[bytes, str] | None:
    if "tts" not in HOOKS or not texto: return None
    try: return await asyncio.to_thread(HOOKS["tts"], texto)
    except Exception as e:
        log.warning("Voz para o celular falhou: %r", e); return None

def aton_print() -> bytes:
    import io
    from PIL import ImageGrab
    buf = io.BytesIO()
    img = ImageGrab.grab(all_screens=True); img.thumbnail((1600, 1600))
    img.save(buf, "JPEG", quality=70)
    return buf.getvalue()
# ==================================================================

app = FastAPI()
clientes: set[WebSocket] = set()
audios: dict[str, tuple[bytes, str, float]] = {}    # id -> (bytes, mime, criado_em)

def guardar_audio(dados: bytes, mime: str) -> str:
    agora = time.time()
    for k in [k for k, v in audios.items() if agora - v[2] > 300]:
        audios.pop(k, None)                          # limpa áudios com mais de 5 min
    aid = uuid.uuid4().hex
    audios[aid] = (dados, mime, agora)
    return f"/audio/{aid}"

async def gerar_resposta(texto: str) -> dict:
    resposta = await aton_processar(texto)
    tts = await aton_tts(resposta)
    return {"texto": resposta, "audio_url": guardar_audio(*tts) if tts else None}

async def avisar_todos(evento: dict):
    """Chame de qualquer parte do Aton para falar com o celular."""
    for ws in list(clientes):
        try: await ws.send_json(evento)
        except Exception: clientes.discard(ws)

@app.get("/audio/{aid}")
async def servir_audio(aid: str):
    if aid not in audios: raise HTTPException(404)
    dados, mime, _ = audios[aid]
    return Response(dados, media_type=mime)

# ---------- rota para o atalho da Siri ----------
class Comando(BaseModel):
    texto: str

@app.post("/comando")
async def comando(c: Comando, x_aton_token: str = Header(default="")):
    if x_aton_token != TOKEN: raise HTTPException(401, "Token inválido")
    r = await gerar_resposta(c.texto)
    await avisar_todos({"tipo": "notificacao", "texto": f"(Siri) {c.texto} → {r['texto']}"})
    return {"resposta": r["texto"]}

# ---------- WebSocket do app ----------
@app.websocket("/ws")
async def ws_aton(ws: WebSocket):
    await ws.accept()
    try:
        auth = await asyncio.wait_for(ws.receive_json(), timeout=10)
    except Exception:
        await ws.close(code=4001); return
    if auth.get("token") != TOKEN:
        await ws.send_json({"tipo": "erro", "texto": "Token inválido."})
        await ws.close(code=4001); return

    clientes.add(ws)
    await ws.send_json({"tipo": "estado", "estado": "repouso"})
    try:
        while True:
            msg = await ws.receive_json()
            tipo = msg.get("tipo")
            if tipo in ("texto", "audio"):
                if tipo == "audio":
                    await ws.send_json({"tipo": "estado", "estado": "ouvindo"})
                    texto = await aton_stt(base64.b64decode(msg["conteudo"]), msg.get("mime", "audio/m4a"))
                    await ws.send_json({"tipo": "transcricao", "texto": texto})
                else:
                    texto = msg["conteudo"]
                await ws.send_json({"tipo": "estado", "estado": "pensando"})
                await ws.send_json({"tipo": "resposta", **(await gerar_resposta(texto))})
                await ws.send_json({"tipo": "estado", "estado": "repouso"})
            elif tipo == "print":
                img = await asyncio.to_thread(aton_print)
                await ws.send_json({"tipo": "print", "imagem": base64.b64encode(img).decode()})
            elif tipo == "ping":
                await ws.send_json({"tipo": "pong"})
    except WebSocketDisconnect:
        pass
    finally:
        clientes.discard(ws)

# o app do celular (PWA) é servido pelo próprio Aton, no mesmo endereço do Tailscale
PASTA_PWA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pwa")


_IP_TS = {"ip": "", "quando": 0.0}


def _ip_tailscale():
    """IP deste PC na rede do Tailscale, perguntado ao próprio Tailscale na hora (não fica guardado em arquivo)."""
    import shutil, subprocess
    if _IP_TS["ip"] and time.time() - _IP_TS["quando"] < 600: return _IP_TS["ip"]
    exe = shutil.which("tailscale") or r"C:\Program Files\Tailscale\tailscale.exe"
    try:
        r = subprocess.run([exe, "ip", "-4"], capture_output=True, text=True, timeout=5,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        ip = (r.stdout or "").strip().splitlines()[0].strip() if r.stdout.strip() else ""
    except Exception:
        ip = ""
    _IP_TS.update(ip=ip, quando=time.time())
    return ip


def _pagina_pwa():
    """index.html com o endereço do RustDesk (o IP do PC no Tailscale, descoberto na hora; nada fica no código)."""
    from fastapi.responses import HTMLResponse
    with open(os.path.join(PASTA_PWA, "index.html"), encoding="utf-8") as f: html = f.read()
    rid = _ip_tailscale()
    if rid: html = html.replace("__RUSTDESK_ID__", rid)
    return HTMLResponse(html, headers={"Cache-Control": "no-cache"})


@app.get("/", include_in_schema=False)
async def _raiz():
    return _pagina_pwa()


@app.get("/index.html", include_in_schema=False)
async def _index():
    return _pagina_pwa()


app.mount("/", StaticFiles(directory=PASTA_PWA, html=True), name="pwa")

LOOP = None

@app.on_event("startup")
async def _guardar_loop():
    global LOOP
    LOOP = asyncio.get_running_loop()

def notificar(texto: str):
    """Para as threads do Aton (fora do loop do servidor): manda uma notificação ao celular, se houver um conectado."""
    if LOOP and clientes:
        asyncio.run_coroutine_threadsafe(avisar_todos({"tipo": "notificacao", "texto": texto}), LOOP)

def iniciar(porta: int = PORTA):
    uvicorn.run(app, host="127.0.0.1", port=porta, log_level="warning")   # só local: o acesso de fora vem pelo Tailscale

if __name__ == "__main__":
    print(f"ATON Remote em http://127.0.0.1:{PORTA}  |  token em {TOKEN_FILE}")
    iniciar()
