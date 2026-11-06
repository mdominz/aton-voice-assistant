# -*- coding: utf-8 -*-
"""
"Braços" do Aton: ações no PC, no estilo dos App Intents da Siri / Skills da Alexa — cada ação é declarada,
com parâmetros, e as que alteram algo pedem confirmação falada antes de executar.

Confirmação: a ação perigosa não roda na hora; fica em PENDENTE e a IA pede "confirma?". A próxima fala
do usuário ("sim", "confirmo") executa; qualquer outra coisa cancela. Nada aqui apaga arquivos.
"""
import datetime, json, logging, os, re, shutil, subprocess, threading, time, uuid, winreg

log = logging.getLogger("aton")
HERE = os.path.dirname(os.path.abspath(__file__))
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# ------------------------------------------------------------------ confirmação falada
PENDENTE = {}          # {"descricao", "fazer", "ate"}
_LOCK = threading.Lock()

def preparar(descricao, fazer, validade=45):
    with _LOCK:
        PENDENTE.clear(); PENDENTE.update(descricao=descricao, fazer=fazer, ate=time.time() + validade)
    log.info("Ação aguardando confirmação: %s", descricao)
    return (f"AÇÃO PREPARADA, AINDA NÃO EXECUTADA: {descricao}. Diga isso ao usuário em uma frase e pergunte se ele confirma "
            f"(ele deve responder 'sim' ou 'confirmo'). Não diga que já foi feito.")

def tem_pendente():
    with _LOCK:
        if PENDENTE and time.time() > PENDENTE["ate"]: PENDENTE.clear()
        return bool(PENDENTE)

def confirmar():
    with _LOCK:
        acao = dict(PENDENTE); PENDENTE.clear()
    if not acao or time.time() > acao["ate"]:
        return "Não há nada esperando confirmação."
    log.info("Confirmado: %s", acao["descricao"])
    try: return acao["fazer"]()
    except Exception as e:
        log.exception("Falha ao executar ação confirmada")
        return f"Não consegui concluir: {e}"

def cancelar():
    with _LOCK:
        tinha = bool(PENDENTE); PENDENTE.clear()
    return "Cancelado." if tinha else "Não havia nada para cancelar."

# ------------------------------------------------------------------ pastas do usuário (podem estar no OneDrive)
_SHELL = {"documentos": "Personal", "imagens": "My Pictures", "musicas": "My Music", "videos": "My Video",
          "area de trabalho": "Desktop", "downloads": "{374DE290-123F-4565-9164-39C4925E467B}"}

def pastas():
    out = {}
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders") as k:
            for nome, valor in _SHELL.items():
                try: out[nome] = os.path.expandvars(winreg.QueryValueEx(k, valor)[0])
                except OSError: pass
    except OSError:
        pass
    out.setdefault("downloads", os.path.join(os.path.expanduser("~"), "Downloads"))
    return {k: v for k, v in out.items() if os.path.isdir(v)}

def _norm(t):
    import unicodedata
    t = unicodedata.normalize("NFD", (t or "").lower())
    return re.sub(r"\s+", " ", "".join(c for c in t if unicodedata.category(c) != "Mn")).strip()

def _pasta(nome):
    p = pastas()
    n = _norm(nome).replace("desktop", "area de trabalho").replace("musica", "musicas").replace("video", "videos")
    n = n.replace("musicass", "musicas").replace("videoss", "videos")
    return p.get(n) or next((v for k, v in p.items() if k in n or n in k), None) if n else None

# ------------------------------------------------------------------ arquivos
_ACHADOS = []          # últimos resultados de procurar_arquivo (para "abre o primeiro")

def procurar_arquivo(termo, pasta=""):
    raizes = [_pasta(pasta)] if pasta and _pasta(pasta) else list(pastas().values())
    termo_n = _norm(termo)
    palavras = [w for w in termo_n.split() if len(w) > 1]
    achados, t0 = [], time.time()
    for raiz in raizes:
        for dirpath, dirs, files in os.walk(raiz):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d.lower() not in ("node_modules", "venv", "__pycache__", "appdata")]
            if dirpath.count(os.sep) - raiz.count(os.sep) > 4: dirs[:] = []
            for f in files:
                fn = _norm(f)
                if all(w in fn for w in palavras):
                    p = os.path.join(dirpath, f)
                    try: achados.append((os.path.getmtime(p), p))
                    except OSError: pass
            if time.time() - t0 > 4: break         # busca rápida: não varre o disco inteiro
    achados.sort(reverse=True)
    _ACHADOS[:] = [p for _, p in achados[:5]]
    if not _ACHADOS:
        return f"Nenhum arquivo com '{termo}' nas pastas do usuário."
    return "Arquivos encontrados (mais recentes primeiro; número = posição):\n" + "\n".join(
        f"{i+1}. {os.path.basename(p)} (em {os.path.basename(os.path.dirname(p))}, "
        f"{datetime.datetime.fromtimestamp(os.path.getmtime(p)):%d/%m/%Y})" for i, p in enumerate(_ACHADOS))

def abrir_pasta(pasta):
    p = _pasta(pasta)
    if not p: return f"Não conheço a pasta '{pasta}'. Pastas: {', '.join(pastas())}."
    os.startfile(p); return f"Pasta {pasta} aberta."

def abrir_arquivo(posicao=1):
    if not _ACHADOS: return "Primeiro procure o arquivo com procurar_arquivo."
    i = max(1, int(posicao or 1)) - 1
    if i >= len(_ACHADOS): return f"Só há {len(_ACHADOS)} resultado(s)."
    os.startfile(_ACHADOS[i]); return f"Abrindo {os.path.basename(_ACHADOS[i])}."

def _texto_do_arquivo(p, limite):
    ext = os.path.splitext(p)[1].lower()
    if ext == ".pdf":
        from pypdf import PdfReader
        r = PdfReader(p); partes, total = [], 0
        for pg in r.pages:
            t = pg.extract_text() or ""
            partes.append(t); total += len(t)
            if total > limite: break
        return "\n".join(partes), len(r.pages)
    if ext == ".docx":
        import zipfile
        with zipfile.ZipFile(p) as z: xml = z.read("word/document.xml").decode("utf-8", "replace")
        xml = re.sub(r"</w:p>", "\n", xml)
        return re.sub(r"<[^>]+>", "", xml), None
    if ext in (".txt", ".md", ".csv", ".log", ".json", ".html", ".htm"):
        with open(p, encoding="utf-8", errors="replace") as f: return f.read(limite + 1), None
    return None, None

def ler_documento(posicao=1, limite=12000):
    """Lê o texto de um arquivo achado por procurar_arquivo para a IA responder sobre ele (não abre na tela)."""
    if not _ACHADOS: return "Primeiro procure o arquivo com procurar_arquivo."
    i = max(1, int(posicao or 1)) - 1
    if i >= len(_ACHADOS): return f"Só há {len(_ACHADOS)} resultado(s)."
    p = _ACHADOS[i]
    try:
        texto, paginas = _texto_do_arquivo(p, limite)
    except Exception as e:
        log.warning("Falha ao ler %s: %r", p, e)
        return f"Não consegui ler {os.path.basename(p)}: {e}"
    if texto is None: return f"Não sei ler arquivos {os.path.splitext(p)[1]}; leio PDF, Word (.docx) e texto."
    texto = re.sub(r"[ \t]+", " ", texto).strip()
    if not texto: return f"{os.path.basename(p)} não tem texto legível (talvez seja um PDF escaneado, só imagem)."
    cortado = len(texto) > limite
    return (f"Conteúdo de '{os.path.basename(p)}'" + (f" ({paginas} páginas)" if paginas else "") +
            (f", só o começo ({limite} caracteres)" if cortado else "") + ":\n" + texto[:limite])

TIPOS = {"Imagens": ".jpg .jpeg .png .gif .webp .bmp .heic .svg", "Videos": ".mp4 .mkv .mov .avi .webm",
         "Audios": ".mp3 .wav .flac .m4a .ogg", "Documentos": ".pdf .doc .docx .xls .xlsx .ppt .pptx .txt .csv .odt",
         "Compactados": ".zip .rar .7z .tar .gz", "Instaladores": ".exe .msi"}
_DESFAZER = os.path.join(HERE, "ultima_organizacao.json")

def organizar_downloads():
    base = pastas()["downloads"]
    plano = []
    for f in os.listdir(base):
        p = os.path.join(base, f)
        if not os.path.isfile(p) or f.lower().endswith((".crdownload", ".part", ".tmp")): continue
        ext = os.path.splitext(f)[1].lower()
        destino = next((k for k, v in TIPOS.items() if ext in v.split()), "Outros")
        plano.append((p, os.path.join(base, destino, f)))
    if not plano: return "A pasta Downloads já está organizada (não há arquivos soltos)."
    contagem = {}
    for _, d in plano: contagem[os.path.basename(os.path.dirname(d))] = contagem.get(os.path.basename(os.path.dirname(d)), 0) + 1
    resumo = ", ".join(f"{n} em {k}" for k, n in sorted(contagem.items(), key=lambda x: -x[1]))
    def fazer():
        feitos = []
        for o, d in plano:
            if not os.path.exists(o): continue
            os.makedirs(os.path.dirname(d), exist_ok=True)
            if os.path.exists(d):
                r, e = os.path.splitext(d); d = f"{r} ({uuid.uuid4().hex[:4]}){e}"
            shutil.move(o, d); feitos.append([o, d])
        with open(_DESFAZER, "w", encoding="utf-8") as f: json.dump(feitos, f, ensure_ascii=False)
        return f"Pronto: {len(feitos)} arquivos organizados em subpastas de Downloads. Dá para desfazer."
    return preparar(f"mover {len(plano)} arquivos soltos de Downloads para subpastas por tipo ({resumo})", fazer)

def desfazer_organizacao():
    try:
        with open(_DESFAZER, encoding="utf-8") as f: feitos = json.load(f)
    except (FileNotFoundError, ValueError):
        return "Não há organização para desfazer."
    def fazer():
        n = 0
        for o, d in reversed(feitos):
            if os.path.exists(d) and not os.path.exists(o): shutil.move(d, o); n += 1
        os.remove(_DESFAZER)
        return f"Desfeito: {n} arquivos voltaram para Downloads."
    return preparar(f"devolver {len(feitos)} arquivos para a raiz de Downloads", fazer)

# ------------------------------------------------------------------ janelas e teclado
def minimizar_tudo():
    import keyboard; keyboard.send("windows+d"); return "Área de trabalho à vista."

def captura_de_tela():
    import keyboard; keyboard.send("windows+print screen")
    return f"Print salvo em Imagens, pasta Capturas de tela."

def digitar(texto):
    import keyboard
    time.sleep(0.3); keyboard.write(texto, delay=0.005)
    return "Texto digitado na janela ativa."

APELIDOS = {"vscode": "code", "visualstudiocode": "code", "navegador": "chrome", "googlechrome": "chrome",
            "blocodenotas": "notepad", "calculadora": "calculatorapp", "explorador": "explorer", "word": "winword",
            "excel": "excel", "powerpoint": "powerpnt", "whatsapp": "whatsapp", "edge": "msedge"}
PROTEGIDOS = ("python.exe", "pythonw.exe", "explorer.exe", "wallpaper32.exe", "wallpaper64.exe", "webwallpaper64.exe", "ollama.exe")

def _janelas():
    """[(hwnd, título, pid)] das janelas visíveis com título."""
    import ctypes, ctypes.wintypes as wt
    u = ctypes.windll.user32; out = []
    @ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    def cb(h, _):
        n = u.GetWindowTextLengthW(h)
        if n and u.IsWindowVisible(h):
            b = ctypes.create_unicode_buffer(n + 1); u.GetWindowTextW(h, b, n + 1)
            pid = wt.DWORD(); u.GetWindowThreadProcessId(h, ctypes.byref(pid))
            out.append((h, b.value, pid.value))
        return True
    u.EnumWindows(cb, 0)
    return out

def fechar_programa(nome):
    import psutil
    n = _norm(nome).replace(" ", "").replace(".exe", "")
    n = APELIDOS.get(n, n)
    procs = {}
    for p in psutil.process_iter(["name"]):
        nm = (p.info["name"] or "")
        if n and n in _norm(nm).replace(" ", "") and nm.lower() not in PROTEGIDOS:
            procs.setdefault(nm, []).append(p.pid)
    if procs:
        base = lambda k: _norm(os.path.splitext(k)[0])
        # nome exato > começa com o nome > o que tem mais processos ("steam" -> steam.exe, não steamwebhelper.exe)
        exe = min(procs, key=lambda k: (base(k) != n, not base(k).startswith(n), -len(procs[k])))
        def fazer():
            # sem /F: o programa recebe o pedido de fechar e pode perguntar se você quer salvar
            subprocess.run(["taskkill", "/IM", exe], capture_output=True, creationflags=NO_WINDOW)
            return f"Pedi para o {exe} fechar."
        return preparar(f"fechar o programa {exe} (o que não estiver salvo pode ser perdido)", fazer)
    # não é nome de programa: procura pelo título da janela (ex.: "README.md - Visual Studio Code")
    alvo = _norm(nome)
    jan = [(h, t) for h, t, pid in _janelas() if alvo and alvo in _norm(t) and pid != os.getpid()]
    if not jan: return f"Não encontrei nenhum programa nem janela aberta chamada '{nome}'."
    h, titulo = jan[0]
    def fazer_janela():
        import ctypes; ctypes.windll.user32.PostMessageW(h, 0x0010, 0, 0)   # WM_CLOSE: como clicar no X
        return f"Pedi para a janela '{titulo}' fechar."
    return preparar(f"fechar a janela '{titulo}'", fazer_janela)

# ------------------------------------------------------------------ sistema
def status_pc():
    import psutil
    cpu = psutil.cpu_percent(interval=0.5)
    mem = psutil.virtual_memory()
    for p in psutil.process_iter():
        try: p.cpu_percent(None)
        except Exception: pass
    time.sleep(0.5)
    top = []
    for p in psutil.process_iter(["name"]):
        try: top.append((p.cpu_percent(None) / psutil.cpu_count(), p.info["name"]))
        except Exception: pass
    top = [f"{n} ({c:.0f}%)" for c, n in sorted(t for t in top if t[1] not in ("System Idle Process", "System", "Idle"))[::-1][:3] if c >= 1]
    gpu = ""
    try:
        r = subprocess.run(["nvidia-smi", "--query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu",
                            "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=5, creationflags=NO_WINDOW)
        u, mu, mt, tp = [x.strip() for x in r.stdout.split(",")]
        gpu = f" Placa de vídeo: {u}% de uso, {int(mu)/1024:.1f} de {int(mt)/1024:.0f} GB de memória, {tp} graus."
    except Exception:
        pass
    return (f"Processador em {cpu:.0f}%, memória RAM em {mem.percent:.0f}% ({mem.used/2**30:.1f} de {mem.total/2**30:.0f} GB).{gpu}"
            + (f" O que mais pesa agora: {', '.join(top)}." if top else ""))

def energia(acao):
    if acao == "cancelar":
        r = subprocess.run(["shutdown", "/a"], capture_output=True, creationflags=NO_WINDOW)
        return "Desligamento cancelado." if r.returncode == 0 else "Não havia desligamento agendado."
    flag = {"desligar": "/s", "reiniciar": "/r"}.get(acao)
    if not flag: return "Ação de energia inválida: use desligar, reiniciar ou cancelar."
    def fazer():
        subprocess.run(["shutdown", flag, "/t", "60"], capture_output=True, creationflags=NO_WINDOW)
        return f"O computador vai {acao} em 60 segundos. Para cancelar, diga 'Aton, cancela o desligamento'."
    return preparar(f"{acao} o computador (com 60 segundos para cancelar)", fazer)

# ------------------------------------------------------------------ lembretes e timers (persistem entre reinícios)
_ARQ_LEMB = os.path.join(HERE, "lembretes.json")

def _ler():
    try:
        with open(_ARQ_LEMB, encoding="utf-8") as f: return json.load(f)
    except (FileNotFoundError, ValueError):
        return []

def _gravar(lst):
    with open(_ARQ_LEMB, "w", encoding="utf-8") as f: json.dump(lst, f, ensure_ascii=False, indent=1)

def criar_lembrete(texto, em_minutos=None, horario="", data=""):
    agora = datetime.datetime.now()
    if em_minutos not in (None, "", 0, "0"):
        quando = agora + datetime.timedelta(minutes=float(em_minutos))
    elif horario:
        m = re.match(r"(\d{1,2})[:h]?(\d{2})?", str(horario).strip())
        if not m: return "Horário inválido; use HH:MM."
        dia = datetime.date.fromisoformat(data) if data else agora.date()
        quando = datetime.datetime.combine(dia, datetime.time(int(m.group(1)) % 24, int(m.group(2) or 0)))
        if not data and quando <= agora: quando += datetime.timedelta(days=1)
    else:
        return "Diga quando: em quantos minutos ou a que horas."
    with _LOCK:
        lst = _ler(); lst.append({"id": uuid.uuid4().hex[:6], "texto": texto, "quando": quando.isoformat(timespec="seconds")})
        _gravar(lst)
    dia = "hoje" if quando.date() == agora.date() else "amanhã" if quando.date() == agora.date() + datetime.timedelta(days=1) else f"em {quando:%d/%m}"
    return f"Lembrete criado para {dia} às {quando:%H:%M}: {texto}."

def listar_lembretes():
    lst = sorted(_ler(), key=lambda x: x["quando"])
    if not lst: return "Nenhum lembrete agendado."
    return "Lembretes: " + "; ".join(f"{datetime.datetime.fromisoformat(l['quando']):%d/%m %H:%M} — {l['texto']}" for l in lst)

def cancelar_lembrete(trecho):
    with _LOCK:
        lst = _ler(); t = _norm(trecho)
        resto = [l for l in lst if t not in _norm(l["texto"])]
        _gravar(resto)
    n = len(lst) - len(resto)
    return f"{n} lembrete(s) cancelado(s)." if n else "Não achei lembrete com esse texto."

def lembretes_futuros():
    return sorted(_ler(), key=lambda x: x["quando"])

def concluir_lembrete(id_):
    with _LOCK:
        lst = _ler(); resto = [l for l in lst if l["id"] != id_]
        if len(resto) == len(lst): return False
        _gravar(resto)
    return True

def lembretes_vencidos():
    """Tira da lista e devolve os lembretes cujo horário já passou."""
    agora = datetime.datetime.now()
    with _LOCK:
        lst = _ler()
        venc = [l for l in lst if datetime.datetime.fromisoformat(l["quando"]) <= agora]
        if venc: _gravar([l for l in lst if l not in venc])
    return venc

# ------------------------------------------------------------------ rotinas (definidas em config.json)
def executar_rotina(nome, cfg, chamar):
    rotinas = cfg.get("rotinas") or {}
    n = _norm(nome)
    chave = next((k for k in rotinas if _norm(k) == n), None) or next((k for k in rotinas if _norm(k) in n or n in _norm(k)), None)
    if not chave: return f"Não existe a rotina '{nome}'. Rotinas: {', '.join(rotinas) or 'nenhuma'}.", []
    feitos, depois = [], []
    for passo in rotinas[chave]:
        ferramenta, args = passo[0], (passo[1] if len(passo) > 1 else {})
        res, dep = chamar(ferramenta, args)
        if dep: depois.append(dep)
        feitos.append(f"{ferramenta}: {res}")
    return f"Rotina '{chave}' executada. " + " | ".join(feitos), depois

# ------------------------------------------------------------------ esquemas para a IA
def _f(nome, desc, props=None, req=()):
    return {"type": "function", "function": {"name": nome, "description": desc, "parameters": {
        "type": "object", "properties": props or {}, "required": list(req)}}}

ESQUEMAS = [
    _f("procurar_arquivo", "Procura arquivos pelo nome nas pastas do usuário (Downloads, Documentos, Imagens, Área de Trabalho, Músicas, Vídeos).",
       {"termo": {"type": "string", "description": "palavras do nome do arquivo"}, "pasta": {"type": "string", "description": "opcional: uma dessas pastas"}}, ["termo"]),
    _f("abrir_arquivo", "Abre um dos arquivos achados por procurar_arquivo, pela posição na lista (1 = o primeiro).",
       {"posicao": {"type": "integer"}}),
    _f("abrir_pasta", "Abre uma pasta do usuário no Explorer (downloads, documentos, imagens, area de trabalho, musicas, videos).",
       {"pasta": {"type": "string"}}, ["pasta"]),
    _f("ler_documento", "Lê o texto de um arquivo achado por procurar_arquivo (PDF, Word, texto) para responder perguntas sobre ele. "
       "Use quando o usuário perguntar o que diz, resumir ou buscar algo dentro de um documento. Não abre na tela.",
       {"posicao": {"type": "integer", "description": "posição na lista de procurar_arquivo (1 = o primeiro)"}}),
    _f("organizar_downloads", "Move os arquivos soltos da pasta Downloads para subpastas por tipo (pede confirmação, não apaga nada)."),
    _f("desfazer_organizacao", "Desfaz a última organização da pasta Downloads (pede confirmação)."),
    _f("minimizar_tudo", "Minimiza todas as janelas e mostra a área de trabalho."),
    _f("captura_de_tela", "Tira um print da tela inteira e salva em Imagens."),
    _f("digitar", "Digita um texto ditado pelo usuário na janela ativa.", {"texto": {"type": "string"}}, ["texto"]),
    _f("fechar_programa", "Fecha um programa aberto pelo nome (pede confirmação).", {"nome": {"type": "string", "description": "ex.: chrome, discord, spotify"}}, ["nome"]),
    _f("status_pc", "Uso atual de processador, memória e placa de vídeo, e os programas que mais pesam."),
    _f("energia", "Desliga ou reinicia o computador (pede confirmação, espera 60 s) ou cancela um desligamento agendado.",
       {"acao": {"type": "string", "enum": ["desligar", "reiniciar", "cancelar"]}}, ["acao"]),
    _f("criar_lembrete", "Cria um lembrete ou timer: o Aton avisa em voz alta na hora. Use em_minutos para 'daqui a X minutos' "
       "ou horario (HH:MM, 24h) e data opcional (AAAA-MM-DD).",
       {"texto": {"type": "string"}, "em_minutos": {"type": "number"}, "horario": {"type": "string"}, "data": {"type": "string"}}, ["texto"]),
    _f("listar_lembretes", "Lista os lembretes agendados."),
    _f("cancelar_lembrete", "Cancela lembretes que contenham o trecho.", {"trecho": {"type": "string"}}, ["trecho"]),
    _f("executar_rotina", "Executa uma rotina do usuário (sequência de ações definida por ele, ex.: 'modo trabalho').",
       {"nome": {"type": "string"}}, ["nome"]),
]

def chamar(nome, args, cfg, chamar_ferramenta):
    """Executa um braço. Devolve (texto para a IA, [ações depois da fala]) ou None se o nome não for daqui."""
    a = args or {}
    simples = {
        "procurar_arquivo": lambda: procurar_arquivo(a.get("termo", ""), a.get("pasta", "")),
        "abrir_arquivo": lambda: abrir_arquivo(a.get("posicao", 1)), "ler_documento": lambda: ler_documento(a.get("posicao", 1)), "abrir_pasta": lambda: abrir_pasta(a.get("pasta", "")),
        "organizar_downloads": organizar_downloads, "desfazer_organizacao": desfazer_organizacao,
        "minimizar_tudo": minimizar_tudo, "captura_de_tela": captura_de_tela,
        "digitar": lambda: digitar(a.get("texto", "")), "fechar_programa": lambda: fechar_programa(a.get("nome", "")),
        "status_pc": status_pc, "energia": lambda: energia(a.get("acao", "")),
        "criar_lembrete": lambda: criar_lembrete(a.get("texto", "lembrete"), a.get("em_minutos"), a.get("horario", ""), a.get("data", "")),
        "listar_lembretes": listar_lembretes, "cancelar_lembrete": lambda: cancelar_lembrete(a.get("trecho", "")),
    }
    if nome in simples: return simples[nome](), []
    if nome == "executar_rotina": return executar_rotina(a.get("nome", ""), cfg, chamar_ferramenta)
    return None
