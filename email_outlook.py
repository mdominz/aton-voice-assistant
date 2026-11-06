# -*- coding: utf-8 -*-
"""
E-mails do Outlook/Hotmail pela API oficial da Microsoft (Graph), só LEITURA (Mail.Read).
Login por código (device code): sem senha no código; a autorização fica em outlook_token.json, só neste PC.
Precisa do "outlook_client_id" (app registrado no portal do Azure) em config.json.

Primeira vez:  venv\\Scripts\\python.exe email_outlook.py login
"""
import datetime, json, logging, os, sys, threading, time, urllib.error, urllib.parse, urllib.request, webbrowser

log = logging.getLogger("aton")
HERE = os.path.dirname(os.path.abspath(__file__))
ARQ_TOKEN = os.path.join(HERE, "outlook_token.json")
AUTORIDADE = "https://login.microsoftonline.com/consumers/oauth2/v2.0"   # contas pessoais (Outlook/Hotmail)
ESCOPOS = "Mail.Read User.Read offline_access"
GRAPH = "https://graph.microsoft.com/v1.0"
_LOCK = threading.Lock()

def _cfg():
    try:
        with open(os.path.join(HERE, "config.json"), encoding="utf-8") as f: return json.load(f)
    except (FileNotFoundError, ValueError):
        return {}

def client_id(): return (_cfg().get("outlook_client_id") or "").strip()
def configurado(): return bool(client_id()) and os.path.exists(ARQ_TOKEN)

def _post(url, dados):
    req = urllib.request.Request(url, data=urllib.parse.urlencode(dados).encode(),
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r: return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return json.loads(e.read() or b"{}")

def _salvar(tok):
    tok["expira"] = time.time() + int(tok.get("expires_in", 3600)) - 60
    with open(ARQ_TOKEN, "w", encoding="utf-8") as f: json.dump(tok, f)

def login():
    cid = client_id()
    if not cid: raise SystemExit("Coloque o Client ID do app em config.json, no campo outlook_client_id.")
    d = _post(AUTORIDADE + "/devicecode", {"client_id": cid, "scope": ESCOPOS})
    if "user_code" not in d: raise SystemExit(f"Erro ao pedir o código: {d}")
    print(f"\nAbra {d['verification_uri']} e digite o código:  {d['user_code']}\n", flush=True)
    webbrowser.open(d["verification_uri"])
    fim = time.time() + int(d.get("expires_in", 900))
    while time.time() < fim:
        time.sleep(int(d.get("interval", 5)))
        t = _post(AUTORIDADE + "/token", {"grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                                          "client_id": cid, "device_code": d["device_code"]})
        if "access_token" in t:
            _salvar(t); print("Autorizado! Token guardado em", ARQ_TOKEN); return
        if t.get("error") not in ("authorization_pending", "slow_down"):
            raise SystemExit(f"Autorização falhou: {t.get('error_description', t)}")
    raise SystemExit("O código expirou; rode de novo.")

def _token():
    with _LOCK:
        with open(ARQ_TOKEN, encoding="utf-8") as f: tok = json.load(f)
        if time.time() < tok.get("expira", 0): return tok["access_token"]
        novo = _post(AUTORIDADE + "/token", {"grant_type": "refresh_token", "client_id": client_id(),
                                             "refresh_token": tok["refresh_token"], "scope": ESCOPOS})
        if "access_token" not in novo: raise RuntimeError(f"Login do Outlook expirou: {novo.get('error_description', '')[:120]}")
        novo.setdefault("refresh_token", tok["refresh_token"]); _salvar(novo)
        return novo["access_token"]

def _get(caminho, params=None, texto=False):
    url = GRAPH + caminho + ("?" + urllib.parse.urlencode(params, quote_via=urllib.parse.quote) if params else "")
    h = {"Authorization": "Bearer " + _token()}
    if texto: h["Prefer"] = 'outlook.body-content-type="text"'
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=15) as r: return json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Outlook {e.code}: {e.read().decode('utf-8', 'replace')[:200]}")

CAMPOS = "id,from,subject,receivedDateTime,isRead,bodyPreview"

def _resumo(m):
    de = ((m.get("from") or {}).get("emailAddress") or {})
    quando = datetime.datetime.fromisoformat(m["receivedDateTime"].replace("Z", "+00:00")).astimezone()
    return {"id": m["id"], "de": de.get("name") or de.get("address") or "?", "endereco": de.get("address", ""),
            "assunto": m.get("subject") or "(sem assunto)", "quando": quando.strftime("%Y-%m-%dT%H:%M"),
            "lido": bool(m.get("isRead")), "previa": (m.get("bodyPreview") or "")[:300]}

def recentes(n=5, so_nao_lidos=False):
    p = {"$top": n, "$select": CAMPOS, "$orderby": "receivedDateTime desc"}
    if so_nao_lidos: p["$filter"] = "isRead eq false"
    return [_resumo(m) for m in _get("/me/mailFolders/inbox/messages", p).get("value", [])]

def de_hoje(n=25):
    ini = datetime.datetime.combine(datetime.date.today(), datetime.time()).astimezone().astimezone(datetime.timezone.utc)
    p = {"$top": n, "$select": CAMPOS, "$orderby": "receivedDateTime desc",
         "$filter": f"receivedDateTime ge {ini.strftime('%Y-%m-%dT%H:%M:%SZ')}"}
    return [_resumo(m) for m in _get("/me/mailFolders/inbox/messages", p).get("value", [])]

def buscar(termo, n=8):
    return [_resumo(m) for m in _get("/me/messages", {"$search": f'"{termo}"', "$top": n, "$select": CAMPOS}).get("value", [])]

def texto_para_ia(lista, titulo):
    if not lista: return f"{titulo}: nenhum e-mail."
    return (f"{titulo} ({len(lista)}). Ao responder, diga de quem são e sobre o que tratam os mais importantes "
            f"(não diga só a quantidade):\n") + "\n".join(
        f"- [{'lido' if e['lido'] else 'NÃO LIDO'}] {e['quando'][11:16]} de {e['de']}: {e['assunto']} — {e['previa'][:200]}" for e in lista)

def painel(n=3):
    """Últimos e-mails para os cartões do wallpaper (sem o texto, só remetente e assunto)."""
    return [{k: e[k] for k in ("id", "de", "assunto", "quando", "lido")} for e in recentes(n)]

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "login": login()
    else: print(__doc__)
