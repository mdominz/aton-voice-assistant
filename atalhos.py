# -*- coding: utf-8 -*-
"""
Comandos por tecla, com contexto: o jeito "script" de controlar vídeos e o navegador.
Antes de apertar qualquer tecla, olha o que está aberto (janela da frente, site da guia, tela cheia) e só age se fizer
sentido; senão responde o que falta ("O YouTube não está aberto."). Nada passa pela IA: é sempre a mesma tecla.

Pausar/tocar usa o controle de mídia do Windows na sessão do navegador (não alterna por engano: "pausa" nunca dá play).
"""
import asyncio, ctypes, logging, re, time
import ctypes.wintypes as wt

log = logging.getLogger("aton")
u32 = ctypes.windll.user32
u32.GetForegroundWindow.restype = wt.HWND

NAVEGADORES = ("chrome", "msedge", "firefox", "brave", "opera")
# nome falado -> (trecho do título da guia, nome bonito)
SITES = {"youtube": ("youtube", "YouTube"), "netflix": ("netflix", "Netflix"), "hbo": ("max", "HBO Max"),
         "max": ("max", "HBO Max"), "prime": ("prime video", "Prime Video"), "disney": ("disney", "Disney+"),
         "twitch": ("twitch", "Twitch"), "globoplay": ("globoplay", "Globoplay"), "crunchyroll": ("crunchyroll", "Crunchyroll")}
VIDEO = r"(?:o |a |esse |essa |este |esta |do |da |no |na )?(?:video|filme|serie|episodio|youtube|netflix|hbo|max|prime|disney|twitch|globoplay|crunchyroll|live)"

class _RECT(ctypes.Structure):
    _fields_ = [("l", ctypes.c_long), ("t", ctypes.c_long), ("r", ctypes.c_long), ("b", ctypes.c_long)]

class _MONINFO(ctypes.Structure):
    _fields_ = [("cbSize", wt.DWORD), ("rcMonitor", _RECT), ("rcWork", _RECT), ("dwFlags", wt.DWORD)]

# ------------------------------------------------------------------ o que está aberto
def _titulo(h):
    n = u32.GetWindowTextLengthW(h); b = ctypes.create_unicode_buffer(n + 1); u32.GetWindowTextW(h, b, n + 1)
    return b.value

def _exe(h):
    import os, psutil
    pid = wt.DWORD(); u32.GetWindowThreadProcessId(h, ctypes.byref(pid))
    try: return os.path.splitext(psutil.Process(pid.value).name())[0].lower()
    except Exception: return ""

def tela_cheia(h):
    r = _RECT(); u32.GetWindowRect(h, ctypes.byref(r))
    mi = _MONINFO(); mi.cbSize = ctypes.sizeof(mi)
    u32.GetMonitorInfoW(u32.MonitorFromWindow(h, 2), ctypes.byref(mi))
    m = mi.rcMonitor
    return r.l <= m.l and r.t <= m.t and r.r >= m.r and r.b >= m.b

def _site_do_titulo(titulo):
    t = titulo.lower()
    for chave, (trecho, bonito) in SITES.items():
        if trecho in t: return chave, bonito
    return None, None

def contexto():
    """{'janela', 'titulo', 'exe', 'navegador', 'site', 'site_nome', 'tela_cheia'} da janela da frente."""
    h = u32.GetForegroundWindow()
    titulo, exe = _titulo(h), _exe(h)
    nav = exe in NAVEGADORES
    site, nome = _site_do_titulo(titulo) if nav else (None, None)
    return {"janela": h, "titulo": titulo, "exe": exe, "navegador": nav, "site": site, "site_nome": nome,
            "tela_cheia": bool(h) and tela_cheia(h)}

def _janela_video(site=None):
    """Janela do navegador com o site pedido (ou qualquer site de vídeo). Prefere a da frente."""
    ctx = contexto()
    if ctx["navegador"] and (ctx["site"] == site or (site is None and ctx["site"])):
        return ctx["janela"], ctx["site_nome"]
    import extras
    for h, titulo, exe in extras._janelas_app():
        if exe not in NAVEGADORES: continue
        s, nome = _site_do_titulo(titulo)
        if s and (site is None or s == site or SITES[s][0] == SITES[site][0]): return h, nome
    return None, None

def _focar(h):
    import extras
    if u32.GetForegroundWindow() != h:
        extras._focar(h); time.sleep(0.3)

def _tecla(h, teclas, vezes=1):
    import keyboard
    _focar(h)
    for _ in range(vezes):
        keyboard.send(teclas); time.sleep(0.05)

def _site_pedido(t):
    for chave in SITES:
        if re.search(rf"\b{chave}\b", t): return chave
    return None

# ------------------------------------------------------------------ pausar / tocar (controle de mídia do navegador)
def _sessao_navegador():
    from ferramentas import _sessions
    sessions, _ = _sessions()
    return next((s for s in sessions if any(n in s.source_app_user_model_id.lower() for n in NAVEGADORES)), None)

def _midia(acao, site):
    h, nome = _janela_video(site)
    if site and not h:
        return f"O {SITES[site][1]} não está aberto."
    try:
        s = _sessao_navegador()
    except Exception as e:
        log.warning("Controle de mídia indisponível: %r", e); s = None
    if s is not None:
        tocando = s.get_playback_info().playback_status == 4
        if acao == "pausar" and not tocando: return "Já está pausado."
        if acao == "tocar" and tocando: return "Já está tocando."
        async def _aw(x): return await x
        asyncio.run(_aw(s.try_pause_async() if acao == "pausar" else s.try_play_async()))
        return "Pausado." if acao == "pausar" else "Play."
    if not h: return "Não achei nenhum vídeo aberto no navegador."
    _tecla(h, "k" if (site or "") == "youtube" or "youtube" in _titulo(h).lower() else "space")   # plano B: tecla na página
    return "Pausado." if acao == "pausar" else "Play."

# ------------------------------------------------------------------ comandos
def _tela_cheia(entrar, site):
    h, nome = _janela_video(site)
    if not h:
        ctx = contexto()
        if not entrar and ctx["tela_cheia"]:                    # qualquer programa em tela cheia: Esc
            _tecla(ctx["janela"], "esc"); return "Saí da tela cheia."
        return "Não achei nenhum vídeo aberto."
    if entrar == tela_cheia(h): return "Já está em tela cheia." if entrar else "Não está em tela cheia."
    _tecla(h, "f" if entrar else "esc")
    return "Tela cheia." if entrar else "Saí da tela cheia."

def _pular(t, frente, site):
    h, nome = _janela_video(site)
    if not h: return "Não achei nenhum vídeo aberto."
    import navegador
    seg = navegador.segundos(t, 10)
    passo = 10 if nome in ("Netflix", "HBO Max", "Prime Video", "Disney+") else 5   # o que a seta faz em cada site
    _tecla(h, "right" if frente else "left", max(1, round(seg / passo)))
    return f"{'Avancei' if frente else 'Voltei'} {seg} segundos."

def _tecla_video(h_site, tecla, ok, so_youtube=False):
    h, nome = h_site
    if not h: return "Não achei nenhum vídeo aberto."
    if so_youtube and nome != "YouTube": return f"Esse atalho só funciona no YouTube (está aberto: {nome})."
    _tecla(h, tecla); return ok

def _guia(teclas, ok):
    ctx = contexto()
    h = ctx["janela"] if ctx["navegador"] else None
    if not h:
        import extras
        h = next((jh for jh, _, exe in extras._janelas_app() if exe in NAVEGADORES), None)
    if not h: return "O navegador não está aberto."
    _tecla(h, teclas); return ok

def _o_que_esta_aberto():
    ctx = contexto()
    if not ctx["titulo"]: return "Não há nenhuma janela na frente."
    if ctx["navegador"]:
        guia = re.sub(r"\s+-\s+(Google Chrome|Microsoft​? Edge|Mozilla Firefox|Brave|Opera)$", "", ctx["titulo"])
        return f"Na frente está o navegador, na guia {guia}" + (", em tela cheia." if ctx["tela_cheia"] else ".")
    return f"Na frente está {ctx['titulo']}" + (", em tela cheia." if ctx["tela_cheia"] else ".")

def _pip():
    import navegador
    return navegador.chrome("picture_in_picture")

def _abrir_na_pagina(t, site, exige):
    """Clica no vídeo/link da página aberta cujo título mais se parece com o nome falado (mesma guia, sem pesquisar)."""
    ctx = contexto()
    if not (ctx["navegador"] and ctx["site"]):
        return "Não há um site de vídeos aberto na frente." if exige else None
    m = re.search(r"(?:abre|abra|abrir|clica|clique|clicar|assiste|assistir|coloca|poe|bota|toca|tocar|seleciona|escolhe)\s+"
                  r"(?:(?:no|o|em|um|esse|aquele)\s+)?(?:video\s+|clipe\s+)?(?:(?:do|da|de|chamado|que se chama|sobre)\s+)?(.+)$", t)
    nome = m.group(1).strip() if m else ""
    if not nome or nome in SITES: return "Qual vídeo?" if exige else None
    if not exige and len(nome.split()) < 2: return None   # "abre o Spotify": é programa, não vídeo da página
    import navegador
    try:
        r = navegador._pedir("pagina", {"op": "melhor", "texto": nome, "so_ver": True}, timeout=10)
    except Exception as e:
        log.warning("Abrir pelo nome falhou: %r", e)
        return f"Não consegui ler a página ({e})." if exige else None
    p, segundo = r.get("p", 0), r.get("segundo", 0)
    if exige and p < 0.5:
        try:
            lista = navegador._pedir("pagina", {"op": "listar", "max": 25}, timeout=10)
            log.info("Abrir pelo nome: melhor=%r p=%.2f | %s vídeos na página '%s': %s", r.get("texto"), p, r.get("total"),
                     lista.get("titulo"), " ; ".join(r.get("amostra") or []))
        except Exception as e: log.info("Listar falhou: %r", e)
    if p < (0.5 if exige else 0.75):                              # pouco parecido: não arrisca clicar em outra coisa
        return f"Não achei um vídeo parecido com {nome} nesta página." if exige else None
    if p - segundo < 0.01 and p < 1:
        return f"Achei mais de um vídeo parecido com {nome}. Diga mais palavras do título." if exige else None
    navegador._pedir("pagina", {"op": "melhor", "texto": nome}, timeout=10)
    return f"Abrindo {r['texto'][:80]}."

A = r"^(?:aton )?"
REGRAS = [
    # com a palavra "vídeo" e um site de vídeo na frente: sempre clica na própria página (nunca abre guia nova)
    (A + r"(?:abre|abra|abrir|clica|clique|clicar|assiste|assistir|coloca|poe|bota|toca|tocar|seleciona|escolhe)\s+(?:(?:no|o|em|um|esse|aquele)\s+)?video\s+\w",
                                                                                lambda t, s: _abrir_na_pagina(t, s, True)),
    (A + r"(?:pausa\w*|pause|pauso|pare|para)\b " + VIDEO + r"\b",              lambda t, s: _midia("pausar", s)),
    (A + r"(?:continua\w*|despausa\w*|retoma\w*|da (?:o |um )?play|solta|volta a passar|tira do pause|play)\b (?:n?o |no )?" + VIDEO + r"\b",
                                                                                lambda t, s: _midia("tocar", s)),
    (r"\b(?:sai\w*|tira\w*|fecha\w*|desliga\w*) (?:d[ao] )?(?:modo )?tela cheia\b", lambda t, s: _tela_cheia(False, s)),
    (r"\btela cheia\b",                                                          lambda t, s: _tela_cheia(True, s)),
    (r"\bpicture\s*(?:in|em|e|and|n)?\s*picture\b|\bpip\b|janela flutuante",    lambda t, s: _pip()),
    (A + r"(?:avanca|adianta|pula|passa) (?:o video |o filme |a serie )?(?:\d+|um|uma|dois|duas|tres|cinco|dez|quinze|vinte|trinta|quarenta|sessenta|um pouco)",
                                                                                lambda t, s: _pular(t, True, s)),
    (A + r"(?:volta|retrocede|recua) (?:o video |o filme |a serie )?(?:\d+|um|uma|dois|duas|tres|cinco|dez|quinze|vinte|trinta|quarenta|sessenta|um pouco)",
                                                                                lambda t, s: _pular(t, False, s)),
    (r"\b(?:muta|silencia|tira o som|sem som)\b (?:d?[oa] )?" + VIDEO + r"\b",   lambda t, s: _tecla_video(_janela_video(s), "m", "Vídeo sem som.")),
    (r"\b(?:liga|ativa|coloca|poe|bota|desliga|tira|desativa)\b (?:a )?legenda", lambda t, s: _tecla_video(_janela_video(s), "c", "Legenda alterada.", True)),
    (A + r"proximo video\b",                                                     lambda t, s: _tecla_video(_janela_video(s or "youtube"), "shift+n", "Próximo vídeo.", True)),
    (A + r"(?:fecha|fechar) (?:a |essa |esta )?(?:guia|aba)$",                    lambda t, s: _guia("ctrl+w", "Fechei a guia.")),
    (A + r"(?:abre |abra )?(?:uma )?nova (?:guia|aba)$",                          lambda t, s: _guia("ctrl+t", "Nova guia.")),
    (A + r"(?:reabre|reabrir|reabra) (?:a )?(?:guia|aba)",                        lambda t, s: _guia("ctrl+shift+t", "Reabri a guia.")),
    (A + r"(?:proxima|vai pra proxima) (?:guia|aba)$",                            lambda t, s: _guia("ctrl+tab", "Próxima guia.")),
    (A + r"(?:guia|aba) anterior$",                                               lambda t, s: _guia("ctrl+shift+tab", "Guia anterior.")),
    (A + r"(?:recarrega|atualiza) (?:a )?pagina$",                                lambda t, s: _guia("f5", "Recarregando.")),
    (A + r"(?:volta|voltar) (?:pra |para )?(?:a )?pagina anterior$",              lambda t, s: _guia("alt+left", "Voltando.")),
    (r"\bo que (?:esta|ta|tem) (?:aberto|na tela|na frente)\b",                   lambda t, s: _o_que_esta_aberto()),
]
REGRAS = [(re.compile(rx), fn) for rx, fn in REGRAS]

def regra(t):
    """t já normalizado (ferramentas.norm). Devolve a resposta, ou None se não é um destes comandos."""
    if re.search(r"lista de comandos|meus comandos|configurac", t): return None    # não é vídeo nem música
    # Spotify na frente: "abre/toca a música X" toca no Spotify (sem pesquisar no navegador)
    if contexto()["exe"] == "spotify":
        m = re.match(A + r"(?:abre|abra|abrir|toca|tocar|toque|coloca|poe|bota|seleciona|escolhe)\s+(?:a |o |um |uma )?"
                         r"(?:(musica|playlist|album|artista|faixa|cancao)\s+)?(?:(?:do|da|de)\s+)?(.+)$", t)
        if m and m.group(2).strip() not in ("spotify", "musica"):
            import spotify
            tipo = {"playlist": "playlist", "album": "album", "artista": "artista", "musica": "musica", "faixa": "musica",
                    "cancao": "musica"}.get(m.group(1) or "", "auto")
            try: r = spotify.tocar(m.group(2).strip(), tipo)
            except Exception as e: log.warning("Spotify falhou: %r", e); r = f"Não consegui tocar no Spotify: {e}."
            log.info("Atalho (Spotify na frente): %s", r); return r
    # "abre X" com um site de vídeos na frente: se X parece muito um vídeo da página, clica nele (senão segue o normal)
    if re.match(A + r"(?:abre|abra|abrir|clica|clique|assiste|assistir|coloca|poe|bota|toca|seleciona|escolhe)\s", t) and             not re.search(r"video", t):
        try:
            r = _abrir_na_pagina(t, _site_pedido(t), False)
        except Exception as e:
            log.warning("Abrir na página falhou: %r", e); r = None
        if r: log.info("Atalho (vídeo da página): %s", r); return r
    for rx, fn in REGRAS:
        if rx.search(t):
            try:
                r = fn(t, _site_pedido(t))
            except Exception as e:
                log.warning("Atalho falhou (%s): %r", rx.pattern[:30], e); r = "Não consegui fazer isso agora."
            log.info("Atalho (%s): %s", rx.pattern[:40], r)
            return r
    return None
