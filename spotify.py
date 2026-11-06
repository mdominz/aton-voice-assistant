# -*- coding: utf-8 -*-
"""
Spotify pela API oficial (Web API), com login PKCE: sem senha nem segredo no código, só o Client ID público do app
que o usuário criou em developer.spotify.com. A autorização fica em spotify_token.json, só neste PC.
Tocar uma playlist/música específica exige Spotify Premium (regra da API).

Primeira vez:  venv\\Scripts\\python.exe spotify.py login
"""
import base64, hashlib, http.server, json, logging, os, secrets, sys, threading, time, unicodedata, urllib.error, \
    urllib.parse, urllib.request, webbrowser

log = logging.getLogger("aton")
HERE = os.path.dirname(os.path.abspath(__file__))
ARQ_TOKEN = os.path.join(HERE, "spotify_token.json")
REDIRECT = "http://127.0.0.1:8888/callback"
ESCOPOS = ("user-read-playback-state user-modify-playback-state user-read-currently-playing "
           "playlist-read-private playlist-read-collaborative user-library-read user-library-modify")
API = "https://api.spotify.com/v1"

def _cfg():
    try:
        with open(os.path.join(HERE, "config.json"), encoding="utf-8") as f: return json.load(f)
    except (FileNotFoundError, ValueError):
        return {}

def client_id():
    return (_cfg().get("spotify_client_id") or "").strip()

def configurado():
    return bool(client_id()) and os.path.exists(ARQ_TOKEN)

def _norm(t):
    t = unicodedata.normalize("NFD", (t or "").lower())
    return " ".join("".join(c for c in t if unicodedata.category(c) != "Mn" and (c.isalnum() or c == " ")).split())

# ------------------------------------------------------------------ login (uma vez) e tokens
def _post_token(dados):
    req = urllib.request.Request("https://accounts.spotify.com/api/token", data=urllib.parse.urlencode(dados).encode(),
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=15) as r:
        tok = json.loads(r.read())
    tok["expira"] = time.time() + tok.get("expires_in", 3600) - 60
    return tok

def _salvar(tok):
    antigo = {}
    if os.path.exists(ARQ_TOKEN):
        with open(ARQ_TOKEN, encoding="utf-8") as f: antigo = json.load(f)
    tok.setdefault("refresh_token", antigo.get("refresh_token"))      # o Spotify às vezes não manda um novo
    with open(ARQ_TOKEN, "w", encoding="utf-8") as f: json.dump(tok, f)

def login():
    """Abre o navegador para o usuário autorizar o Aton; recebe o código em 127.0.0.1:8888 e guarda o token."""
    cid = client_id()
    if not cid: raise SystemExit("Coloque o Client ID do seu app em config.json, no campo spotify_client_id.")
    verificador = secrets.token_urlsafe(64)
    desafio = base64.urlsafe_b64encode(hashlib.sha256(verificador.encode()).digest()).rstrip(b"=").decode()
    estado = secrets.token_urlsafe(16)
    recebido = {}
    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            if q.get("state", [""])[0] == estado: recebido.update({k: v[0] for k, v in q.items()})
            ok = "code" in recebido
            self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.end_headers()
            self.wfile.write(("<h2>Pronto! O Aton já pode usar o seu Spotify. Pode fechar esta aba.</h2>" if ok
                              else "<h2>Não autorizado.</h2>").encode("utf-8"))
        def log_message(self, *a): pass
    srv = http.server.HTTPServer(("127.0.0.1", 8888), H)
    url = "https://accounts.spotify.com/authorize?" + urllib.parse.urlencode({
        "client_id": cid, "response_type": "code", "redirect_uri": REDIRECT, "scope": ESCOPOS,
        "code_challenge_method": "S256", "code_challenge": desafio, "state": estado})
    print("Abrindo o navegador para você autorizar o Aton no Spotify...")
    webbrowser.open(url)
    srv.timeout = 300
    while "code" not in recebido and "error" not in recebido:
        srv.handle_request()
    srv.server_close()
    if "error" in recebido: raise SystemExit(f"Autorização recusada: {recebido['error']}")
    _salvar(_post_token({"grant_type": "authorization_code", "code": recebido["code"], "redirect_uri": REDIRECT,
                         "client_id": cid, "code_verifier": verificador}))
    print("Autorizado! Token guardado em", ARQ_TOKEN)

_LOCK = threading.Lock()

def _token():
    with _LOCK:
        with open(ARQ_TOKEN, encoding="utf-8") as f: tok = json.load(f)
        if time.time() < tok.get("expira", 0): return tok["access_token"]
        novo = _post_token({"grant_type": "refresh_token", "refresh_token": tok["refresh_token"], "client_id": client_id()})
        _salvar(novo)
        return novo["access_token"]

def _api(metodo, caminho, corpo=None, params=None):
    url = API + caminho + ("?" + urllib.parse.urlencode(params) if params else "")
    req = urllib.request.Request(url, method=metodo, data=json.dumps(corpo).encode() if corpo is not None else
                                 (b"" if metodo in ("PUT", "POST") else None),
                                 headers={"Authorization": "Bearer " + _token(), "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            txt = r.read()
            try: return json.loads(txt) if txt else {}
            except ValueError: return {"resposta": txt.decode("utf-8", "replace")}   # ex.: a fila responde só um id
    except urllib.error.HTTPError as e:
        corpo_erro = e.read().decode("utf-8", "replace")
        raise RuntimeError(f"Spotify {e.code}: {corpo_erro[:200]}")

# ------------------------------------------------------------------ aparelho (o Spotify do PC)
def _aparelho():
    """ID do aparelho para tocar: o ativo; senão o computador; se o app estiver fechado, abre e espera."""
    for tentativa in range(12):
        devs = _api("GET", "/me/player/devices").get("devices", [])
        ativo = next((d for d in devs if d.get("is_active")), None)
        if ativo: return ativo["id"]
        pc = next((d for d in devs if d.get("type") == "Computer"), None) or (devs[0] if devs else None)
        if pc: return pc["id"]
        if tentativa == 0:
            log.info("Spotify fechado: abrindo o app."); os.startfile("spotify:")
        time.sleep(1.5)
    raise RuntimeError("O Spotify não apareceu como aparelho disponível.")

# ------------------------------------------------------------------ ações
def minhas_playlists(limite=50):
    out, url = [], "/me/playlists"
    params = {"limit": 50}
    while url and len(out) < 200:
        r = _api("GET", url, params=params)
        out += [p for p in r.get("items", []) if p]
        nxt = r.get("next"); url = nxt[len(API):] if nxt else None; params = None
    return out

def _melhor(itens, consulta, nome=lambda x: x.get("name", "")):
    q = _norm(consulta)
    if not itens: return None
    def nota(x):
        n = _norm(nome(x))
        return (n == q, q in n or n in q, len(set(q.split()) & set(n.split())))
    m = max(itens, key=nota)
    return m if nota(m) != (False, False, 0) else None

def tocar(busca, tipo="auto"):
    """tipo: playlist, artista, musica, album ou auto. Playlists do usuário têm prioridade."""
    tipo = _norm(tipo or "auto")
    alvo, desc = None, ""
    if tipo in ("playlist", "auto"):
        p = _melhor(minhas_playlists(), busca)
        if p: alvo, desc = {"context_uri": p["uri"]}, f"a sua playlist {p['name']}"
    if not alvo:
        tipos = {"playlist": "playlist", "artista": "artist", "musica": "track", "album": "album"}
        t = tipos.get(tipo, "track,artist,playlist,album")
        r = _api("GET", "/search", params={"q": busca, "type": t, "limit": 5, "market": _cfg().get("spotify_pais", "BR")})
        if tipo in ("artista",) or (tipo == "auto" and r.get("artists", {}).get("items") and
                                    _norm(r["artists"]["items"][0]["name"]) == _norm(busca)):
            a = r["artists"]["items"][0]; alvo, desc = {"context_uri": a["uri"]}, f"{a['name']}"
        elif tipo == "album" and r.get("albums", {}).get("items"):
            a = r["albums"]["items"][0]; alvo, desc = {"context_uri": a["uri"]}, f"o álbum {a['name']}, de {a['artists'][0]['name']}"
        elif tipo == "playlist" and r.get("playlists", {}).get("items"):
            p = next(x for x in r["playlists"]["items"] if x); alvo, desc = {"context_uri": p["uri"]}, f"a playlist {p['name']}"
        elif r.get("tracks", {}).get("items"):
            # música solta ("uris") o app do PC aceita mas ignora; tocar o álbum começando nela funciona
            m = r["tracks"]["items"][0]
            alvo = {"context_uri": m["album"]["uri"], "offset": {"uri": m["uri"]}}
            desc = f"{m['name']}, de {m['artists'][0]['name']}"
    if not alvo: return f"Não encontrei '{busca}' no Spotify."
    _api("PUT", "/me/player/play", alvo, params={"device_id": _aparelho()})
    return f"Tocando {desc} no Spotify."

def fila(busca):
    r = _api("GET", "/search", params={"q": busca, "type": "track", "limit": 1, "market": _cfg().get("spotify_pais", "BR")})
    itens = r.get("tracks", {}).get("items", [])
    if not itens: return f"Não encontrei a música '{busca}'."
    m = itens[0]
    _api("POST", "/me/player/queue", params={"uri": m["uri"], "device_id": _aparelho()})
    return f"{m['name']}, de {m['artists'][0]['name']}, entrou na fila."

def curtir_atual():
    r = _api("GET", "/me/player/currently-playing")
    item = (r or {}).get("item")
    if not item: return "Nada está tocando no Spotify agora."
    _api("PUT", "/me/tracks", params={"ids": item["id"]})
    return f"Curti {item['name']}, de {item['artists'][0]['name']}. Está nas suas músicas curtidas."

def listar_playlists():
    ps = minhas_playlists()
    if not ps: return "Você não tem playlists no Spotify."
    return f"Você tem {len(ps)} playlists. Algumas: " + ", ".join(p["name"] for p in ps[:15]) + "."

def aleatorio(ligar):
    _api("PUT", "/me/player/shuffle", params={"state": "true" if ligar else "false", "device_id": _aparelho()})
    return "Modo aleatório ligado." if ligar else "Modo aleatório desligado."

def volume(acao="", nivel=None, passo=10):
    """Mexe na barra de volume do próprio Spotify (não no mixer do Windows). Devolve o novo valor."""
    p = _api("GET", "/me/player") or {}
    dev = p.get("device") or {}
    if not dev.get("id"): raise RuntimeError("nada tocando no Spotify")
    if not dev.get("supports_volume", True): raise RuntimeError("este aparelho não deixa mudar o volume")
    atual = int(dev.get("volume_percent") or 0)
    novo = int(nivel) if nivel is not None else atual + (passo if acao == "aumentar" else -passo)
    novo = max(0, min(100, novo))
    _api("PUT", "/me/player/volume", params={"volume_percent": novo, "device_id": dev["id"]})
    return novo

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "login":
        logging.basicConfig(level=logging.INFO); login()
    else:
        print(__doc__)
