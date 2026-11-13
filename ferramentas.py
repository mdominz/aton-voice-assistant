# -*- coding: utf-8 -*-
"""
Ferramentas do assistente: comandos reconhecidos por regras fixas (rápidos e confiáveis),
antes de a frase ir para a IA. executar(texto, cfg) devolve (resposta, depois) ou None.
'depois' é uma função opcional executada depois que a resposta foi falada (ex.: dar play).
"""
import asyncio, datetime, json, os, re, time, unicodedata, urllib.parse, urllib.request, logging
import bracos, monitores, agenda, spotify, email_outlook, bluetooth, extras, navegador, desktop

log = logging.getLogger("aton")

def norm(t):
    t = unicodedata.normalize("NFD", t.lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", t)).strip()

# ------------------------------------------------------------------ hora e data
DIAS = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"]
MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"]

def hora(cfg):
    n = datetime.datetime.now()
    h = "meia-noite" if n.hour == 0 else "meio-dia" if n.hour == 12 else f"{n.hour} hora" + ("s" if n.hour != 1 else "")
    m = "" if n.minute == 0 else f" e {n.minute} minuto" + ("s" if n.minute != 1 else "")
    return f"São {h}{m}, {cfg['tratamento']}." if n.hour not in (0, 1, 12) else f"É {h}{m}, {cfg['tratamento']}."

def data(cfg):
    n = datetime.datetime.now()
    return f"Hoje é {DIAS[n.weekday()]}, {n.day} de {MESES[n.month - 1]} de {n.year}."

# ------------------------------------------------------------------ clima (Open-Meteo, mesma fonte do wallpaper)
WMO = {0: "céu limpo", 1: "predominantemente limpo", 2: "parcialmente nublado", 3: "nublado", 45: "neblina", 48: "neblina",
       51: "garoa fraca", 53: "garoa", 55: "garoa forte", 56: "garoa congelante", 57: "garoa congelante",
       61: "chuva fraca", 63: "chuva", 65: "chuva forte", 66: "chuva congelante", 67: "chuva congelante",
       71: "neve fraca", 73: "neve", 75: "neve forte", 77: "neve", 80: "pancadas de chuva fracas", 81: "pancadas de chuva",
       82: "pancadas de chuva fortes", 85: "neve", 86: "neve", 95: "trovoadas", 96: "trovoadas com granizo", 99: "trovoadas com granizo"}
_WX = {}

def _jget(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "AI-Core-Assistente"}), timeout=8) as r:
        return json.loads(r.read().decode("utf-8"))

def clima(cfg, cidade=None):
    cidade = (cidade or cfg.get("cidade") or "").strip()
    if not cidade:
        return f"Ainda não sei a sua cidade, {cfg['tratamento']}. Coloque-a no campo cidade do config.json."
    hit = _WX.get(cidade.lower())
    if hit and time.time() - hit[0] < 600:
        return hit[1]
    try:
        g = _jget("https://geocoding-api.open-meteo.com/v1/search?count=1&language=pt&name=" + urllib.parse.quote(cidade))
        r = (g.get("results") or [None])[0]
        if not r:
            return f"Não encontrei a cidade {cidade}, {cfg['tratamento']}."
        w = _jget(f"https://api.open-meteo.com/v1/forecast?latitude={r['latitude']}&longitude={r['longitude']}"
                  "&current=temperature_2m,weather_code&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max"
                  "&forecast_days=1&timezone=auto")
        c, d = w["current"], w["daily"]
        chuva = d["precipitation_probability_max"][0]
        txt = (f"Em {r['name']} agora faz {round(c['temperature_2m'])} graus, {WMO.get(c['weather_code'], 'tempo indefinido')}. "
               f"Hoje a máxima é de {round(d['temperature_2m_max'][0])} e a mínima de {round(d['temperature_2m_min'][0])}"
               + (f", com {chuva}% de chance de chuva" if chuva is not None else "") + ". Dados do Open-Meteo.")
        _WX[cidade.lower()] = (time.time(), txt)
        return txt
    except Exception as e:
        log.warning("Clima falhou: %r", e)
        return f"Não consegui consultar o clima agora, {cfg['tratamento']}. O serviço Open-Meteo não respondeu."

# ------------------------------------------------------------------ música (controle de mídia do Windows: Spotify, navegador...)
def _sessions():
    from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionManager as M
    async def _get():
        m = await M.request_async()
        return list(m.get_sessions()), m.get_current_session()
    return asyncio.run(_get())

PLAYING = 4

def _pick(cfg, want_playing=False):
    """Escolhe o player: o preferido (Spotify) se ele estiver tocando; senão quem estiver tocando; senão o preferido."""
    sessions, current = _sessions()
    pref = (cfg.get("player_preferido") or "spotify").lower()
    def playing(s): return s.get_playback_info().playback_status == PLAYING
    fav = next((s for s in sessions if pref in s.source_app_user_model_id.lower()), None)
    if fav and playing(fav): return fav
    tocando = next((s for s in sessions if playing(s)), None)
    if want_playing: return tocando
    return fav or tocando or current

def _nome_app(s):
    a = s.source_app_user_model_id.lower()
    return "Spotify" if "spotify" in a else "Chrome" if "chrome" in a else "Edge" if "edge" in a else "player"

def _midia(cfg, acao):
    try:
        s = _pick(cfg, want_playing=(acao == "pausar"))
    except Exception as e:
        log.warning("Controle de mídia indisponível: %r", e); s = None
    if s is None:
        if acao == "pausar":
            return f"Não há nada tocando, {cfg['tratamento']}.", None
        return None
    def run(op):
        asyncio.run(_aw(getattr(s, op)()))
    async def _aw(x): return await x
    if acao == "pausar":
        run("try_pause_async"); return "Pausado.", None
    if acao == "tocar":
        return f"Tocando no {_nome_app(s)}.", lambda: run("try_play_async")
    if acao == "proxima":
        return "Próxima.", lambda: run("try_skip_next_async")
    if acao == "anterior":
        return "Voltando.", lambda: run("try_skip_previous_async")

def _midia_tecla(acao):
    """Plano B, sem winrt: teclas de mídia do teclado."""
    import keyboard
    tecla = {"pausar": "play/pause media", "tocar": "play/pause media", "proxima": "next track", "anterior": "previous track"}[acao]
    if acao == "pausar":
        keyboard.send(tecla); return "Pausado.", None
    return {"tocar": "Tocando.", "proxima": "Próxima.", "anterior": "Voltando."}[acao], lambda: keyboard.send(tecla)

def musica(cfg, acao):
    return _midia(cfg, acao) or _midia_tecla(acao)

def tocando_agora(cfg):
    try:
        sessions, _ = _sessions()
        pref = (cfg.get("player_preferido") or "spotify").lower()
        com_titulo = []
        for s in sessions:
            p = asyncio.run(_props(s))
            if (p.title or "").strip():
                tocando = s.get_playback_info().playback_status == PLAYING
                com_titulo.append((not tocando, pref not in s.source_app_user_model_id.lower(), s, p))
        if not com_titulo:
            return f"Nada está tocando agora, {cfg['tratamento']}."
        _, _, s, p = min(com_titulo, key=lambda x: (x[0], x[1]))   # tocando antes de pausado; Spotify antes dos outros
        estado = "Está tocando" if s.get_playback_info().playback_status == PLAYING else "Está pausado em"
        return f"{estado} {p.title.strip()}" + (f", de {p.artist.strip()}" if (p.artist or "").strip() else "") + f", no {_nome_app(s)}."
    except Exception as e:
        log.warning("Leitura da mídia falhou: %r", e)
        return f"Não consegui ver o que está tocando, {cfg['tratamento']}."

async def _props(s):
    return await s.try_get_media_properties_async()

# ------------------------------------------------------------------ volume do Windows (teclas de volume: 2% por toque)
def volume(cfg, acao):
    import keyboard
    if acao == "mudo":
        keyboard.send("volume mute"); return "Pronto.", None
    tecla = "volume up" if acao == "aumentar" else "volume down"
    for _ in range(int(cfg.get("passo_volume", 5))):
        keyboard.send(tecla); time.sleep(0.02)
    return ("Volume aumentado." if acao == "aumentar" else "Volume reduzido."), None

NUM_PALAVRA = {"zero": 0, "dez": 10, "vinte": 20, "trinta": 30, "quarenta": 40, "cinquenta": 50, "sessenta": 60,
               "setenta": 70, "oitenta": 80, "noventa": 90, "cem": 100, "metade": 50, "maximo": 100, "minimo": 0}

def volume_nivel(cfg, nivel):
    """Põe o volume do Windows num valor exato (0 a 100)."""
    try:
        nivel = max(0, min(100, int(NUM_PALAVRA.get(norm(str(nivel)), nivel))))
    except (TypeError, ValueError):
        return "Nível inválido; use um número de 0 a 100.", None
    import comtypes
    from pycaw.pycaw import AudioUtilities
    try: comtypes.CoInitialize()
    except OSError: pass
    v = AudioUtilities.GetSpeakers().EndpointVolume
    v.SetMute(0, None); v.SetMasterVolumeLevelScalar(nivel / 100, None)
    return f"Volume em {nivel}.", None

# ------------------------------------------------------------------ volume de um app só (mixer do Windows)
APPS_SOM = {"spotify": "spotify", "musica": "spotify", "discord": "discord", "chrome": "chrome", "navegador": "chrome",
            "edge": "msedge", "youtube": "chrome", "jogo": "league", "league": "league", "lol": "league", "steam": "steam"}

def volume_app(cfg, app, acao="", nivel=None):
    """Muda o volume só de um programa (ex.: o Spotify), sem mexer no volume geral do PC."""
    import comtypes
    from pycaw.pycaw import AudioUtilities
    try: comtypes.CoInitialize()
    except OSError: pass
    chave = APPS_SOM.get(norm(app), norm(app))
    if chave == "spotify" and acao != "mudo" and spotify.configurado():   # a barra de volume do próprio Spotify
        try:
            n = None if nivel is None else int(NUM_PALAVRA.get(norm(str(nivel)), nivel))
            return f"Volume do Spotify em {spotify.volume(acao, n, int(cfg.get('passo_volume_app', 10)))}.", None
        except Exception as e:
            log.warning("Volume pela API do Spotify falhou (%r); usando o mixer do Windows.", e)
    ss =[x for x in AudioUtilities.GetAllSessions() if x.Process and chave in x.Process.name().lower()]
    if not ss: return f"O {app} não está aberto tocando som agora.", None
    v = ss[0].SimpleAudioVolume
    if acao == "mudo":
        m = not v.GetMute()
        for x in ss: x.SimpleAudioVolume.SetMute(m, None)
        return (f"{app.capitalize()} no mudo." if m else f"Som do {app} de volta."), None
    if nivel is not None:
        try: novo = int(NUM_PALAVRA.get(norm(str(nivel)), nivel)) / 100
        except (TypeError, ValueError): return "Nível inválido; use 0 a 100.", None
    else:
        passo = float(cfg.get("passo_volume_app", 10)) / 100
        novo = v.GetMasterVolume() + (passo if acao == "aumentar" else -passo)
    novo = max(0.0, min(1.0, novo))
    for x in ss: x.SimpleAudioVolume.SetMute(0, None); x.SimpleAudioVolume.SetMasterVolume(novo, None)
    return f"Volume do {app} em {round(novo * 100)}.", None

def _volume_app_regra(cfg, t, app):
    if re.search(r"\b(aumenta\w*|sobe|subir|mais alto)\b", t): return volume_app(cfg, app, "aumentar")
    if re.search(r"\b(abaix\w*|diminu\w*|baixa\w*|mais baixo)\b", t): return volume_app(cfg, app, "diminuir")
    if re.search(r"\b(muta\w*|silencia\w*|mudo)\b", t): return volume_app(cfg, app, "mudo")
    n = re.search(r"\b(\d{1,3}|" + "|".join(NUM_PALAVRA) + r")\b", t)
    return volume_app(cfg, app, nivel=n.group(1)) if n else None

# ------------------------------------------------------------------ sites (abre no navegador padrão)
SITES_PADRAO = {
    "youtube": "https://www.youtube.com", "google": "https://www.google.com", "gmail": "https://mail.google.com",
    "outlook": "https://outlook.live.com", "whatsapp": "https://web.whatsapp.com", "netflix": "https://www.netflix.com",
    "github": "https://github.com", "chatgpt": "https://chatgpt.com", "claude": "https://claude.ai",
    "instagram": "https://www.instagram.com", "twitch": "https://www.twitch.tv", "mercado livre": "https://www.mercadolivre.com.br",
    "amazon": "https://www.amazon.com.br", "google maps": "https://maps.google.com", "maps": "https://maps.google.com",
    # streaming
    "hbo max": "https://play.hbomax.com", "max": "https://play.hbomax.com", "hbo": "https://play.hbomax.com",
    "prime video": "https://www.primevideo.com", "amazon prime": "https://www.primevideo.com", "disney": "https://www.disneyplus.com",
    "disney plus": "https://www.disneyplus.com", "globoplay": "https://globoplay.globo.com", "crunchyroll": "https://www.crunchyroll.com",
    "paramount": "https://www.paramountplus.com", "apple tv": "https://tv.apple.com", "youtube music": "https://music.youtube.com",
    "spotify": "https://open.spotify.com", "deezer": "https://www.deezer.com", "pluto tv": "https://pluto.tv", "kick": "https://kick.com",
    # redes e serviços
    "facebook": "https://www.facebook.com", "twitter": "https://x.com", "x": "https://x.com", "tiktok": "https://www.tiktok.com",
    "linkedin": "https://www.linkedin.com", "reddit": "https://www.reddit.com", "pinterest": "https://www.pinterest.com",
    "telegram": "https://web.telegram.org", "discord": "https://discord.com/app", "wikipedia": "https://pt.wikipedia.org",
    "google drive": "https://drive.google.com", "drive": "https://drive.google.com", "google agenda": "https://calendar.google.com",
    "google docs": "https://docs.google.com", "planilhas": "https://sheets.google.com", "google fotos": "https://photos.google.com",
    "tradutor": "https://translate.google.com", "google tradutor": "https://translate.google.com", "gemini": "https://gemini.google.com",
    "shopee": "https://shopee.com.br", "aliexpress": "https://pt.aliexpress.com", "magalu": "https://www.magazineluiza.com.br",
    "ifood": "https://www.ifood.com.br", "uber": "https://m.uber.com", "steam": "https://store.steampowered.com",
    "epic games": "https://store.epicgames.com", "twitch tv": "https://www.twitch.tv", "canva": "https://www.canva.com",
    "notion": "https://www.notion.so", "trello": "https://trello.com", "figma": "https://www.figma.com", "olx": "https://www.olx.com.br",
    "g1": "https://g1.globo.com", "uol": "https://www.uol.com.br", "ge": "https://ge.globo.com", "previsao do tempo": "https://www.climatempo.com.br",
}
BUSCA = {"youtube": "https://www.youtube.com/results?search_query={}", "google": "https://www.google.com/search?q={}",
         "mercado livre": "https://lista.mercadolivre.com.br/{}", "amazon": "https://www.amazon.com.br/s?k={}",
         "maps": "https://www.google.com/maps/search/{}", "google maps": "https://www.google.com/maps/search/{}"}

def _site(cfg, alvo):
    sites = {norm(k): v for k, v in {**SITES_PADRAO, **(cfg.get("sites") or {})}.items()}
    return next((k for k in sorted(sites, key=len, reverse=True) if re.search(r"\b" + re.escape(k) + r"\b", norm(alvo))), None), sites

def _limpa_site(alvo):
    t = norm(alvo)
    t = re.sub(r"^(?:o |a )?(?:site|pagina|portal|app|aplicativo)?\s*(?:d[oae]s? |o |a )?", "", t).strip()
    return re.sub(r"\b(por favor|pra mim|ai|agora|no navegador|no chrome)\b", "", t).strip()

def abrir_site(cfg, alvo, qualquer=False):
    """Site da lista (ou parecido com um da lista: o Whisper ouve "HBO Max" como "de Biomax").
    qualquer=True (a IA pediu, ou o usuário disse "site"): endereço direto ("tal.com") ou o 1º resultado da busca."""
    import webbrowser, difflib
    nome, sites = _site(cfg, alvo)
    if nome: return f"Abrindo {nome}.", lambda: webbrowser.open(sites[nome])
    t = _limpa_site(alvo)
    if not t: return None
    # nome mal ouvido: compara sem espaços com os sites conhecidos ("biomax" ~ "hbomax")
    junto = t.replace(" ", "")
    chaves = {k.replace(" ", ""): k for k in sites if len(k) >= 4}
    parecido = difflib.get_close_matches(junto, list(chaves), n=1, cutoff=0.78)
    if not parecido and len(t.split()) > 1:      # "de biomax": tenta sem a 1ª palavra
        parecido = difflib.get_close_matches("".join(t.split()[1:]), list(chaves), n=1, cutoff=0.8)
    if parecido:
        k = chaves[parecido[0]]
        return f"Abrindo {k}.", lambda: webbrowser.open(sites[k])
    if not qualquer: return None
    if re.fullmatch(r"[\w-]+(\.[\w-]+)+(/\S*)?", junto):            # "abre o hbomax.com"
        return f"Abrindo {junto}.", lambda: webbrowser.open("https://" + junto)
    # qualquer outro: o DuckDuckGo abre direto o 1º resultado da busca ("!ducky")
    url = "https://duckduckgo.com/?q=" + urllib.parse.quote("!ducky " + t + " site oficial")
    return f"Abrindo {t}.", lambda: webbrowser.open(url)

def pesquisar_em(cfg, termo, site="google"):
    """Abre a página de resultados do site (YouTube, Google...) já com a busca feita."""
    import webbrowser
    site = norm(site or "google"); url = BUSCA.get(site, BUSCA["google"])
    termo = termo.strip(" .")
    if not termo: return "O que devo pesquisar?", None
    return f"Pesquisando {termo} no {site}.", lambda: webbrowser.open(url.format(urllib.parse.quote_plus(termo)))

def _bt_desligar():
    bracos.preparar("desligar o Bluetooth (o teclado e o fone Bluetooth desconectam)", lambda: bluetooth.ligar(False))
    return "Desligar o Bluetooth desconecta o teclado e o fone. Confirma?"

ORDINAL = {"primeiro": 1, "segundo": 2, "terceiro": 3, "quarto": 4, "quinto": 5}

def tocar_video(cfg, termo, n=1):
    """Abre direto o n-ésimo vídeo da busca no YouTube (lê a página de resultados, sem chave)."""
    termo = re.sub(r"\b(no|do) youtube\b", "", termo).strip(" .")
    if not termo: return "Qual vídeo?", None
    url = "https://www.youtube.com/results?search_query=" + urllib.parse.quote_plus(termo)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept-Language": "pt-BR"})
        html = urllib.request.urlopen(req, timeout=10).read().decode("utf-8", "replace")
        ids = list(dict.fromkeys(re.findall(r'"videoRenderer":\{"videoId":"([\w-]{11})"', html)))
    except Exception as e:
        log.warning("Busca no YouTube falhou: %r", e); ids = []
    import webbrowser
    if not ids: return f"Não achei o vídeo; abrindo a busca.", lambda: webbrowser.open(url)
    vid = ids[min(max(1, int(n or 1)), len(ids)) - 1]
    return f"Abrindo o vídeo de {termo}.", lambda: webbrowser.open("https://www.youtube.com/watch?v=" + vid)

def _video_regra(cfg, t):
    n = 1
    o = re.match(r"(?:o )?(primeiro|segundo|terceiro|quarto|quinto) (?:video )?(?:d[aoe] |sobre )?(.+)", t)
    if o: n, t = ORDINAL[o.group(1)], o.group(2)
    return tocar_video(cfg, t, n)

# ------------------------------------------------------------------ ver a tela (print + Claude da assinatura)
def ver_tela(cfg, pergunta=""):
    """Tira um print de todas as telas e pergunta ao Claude o que tem nele. Só lê: não clica em nada."""
    import subprocess, shutil
    from PIL import ImageGrab
    pasta = os.path.join(os.path.dirname(os.path.abspath(__file__)), "claude_workdir"); os.makedirs(pasta, exist_ok=True)
    img = ImageGrab.grab(all_screens=True)
    if img.width > 2000: img = img.resize((2000, round(img.height * 2000 / img.width)))
    arq = os.path.join(pasta, "tela.png"); img.save(arq)
    exe = cfg.get("claude_exe") or os.path.expandvars(r"%USERPROFILE%\.local\bin\claude.exe")
    p = (f"Leia o arquivo tela.png: é um print da tela do computador do usuário agora. Pedido dele: \"{pergunta or 'o que tem na minha tela?'}\". "
         f"Responda em português do Brasil, em no máximo 3 frases curtas para serem faladas, sem markdown. "
         f"Se aparecerem senhas ou dados sensíveis, não os repita.")
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
    try:
        r = subprocess.run([exe, "-p", p, "--model", cfg.get("claude_modelo", "sonnet"), "--tools", "Read", "--allowedTools", "Read",
                            "--max-turns", "3", "--no-session-persistence", "--setting-sources", "project", "--strict-mcp-config"],
                           capture_output=True, text=True, encoding="utf-8", cwd=pasta, env=env, timeout=120,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        resp = r.stdout.strip()
    except Exception as e:
        log.warning("Ver tela falhou: %r", e); resp = ""
    finally:
        try: os.remove(arq)
        except OSError: pass
    return (resp or f"Não consegui analisar a tela, {cfg['tratamento']}."), None

def digitar_cmd(texto, enter=False):
    import keyboard
    def f():
        time.sleep(0.4); keyboard.write(texto, delay=0.01)
        if enter: time.sleep(0.1); keyboard.send("enter")
    return "Digitando.", f

# ------------------------------------------------------------------ abrir programas (só os da lista em config.json)
APPS_PADRAO = {
    "spotify": "spotify:", "navegador": "chrome", "chrome": "chrome", "discord": "discord://", "steam": "steam://open/main",
    "calculadora": "calc", "bloco de notas": "notepad", "explorador de arquivos": "explorer", "arquivos": "explorer",
    "configuracoes": "ms-settings:", "gerenciador de tarefas": "taskmgr",
}

def abrir(cfg, alvo):
    apps = {norm(k): v for k, v in (cfg.get("apps") or APPS_PADRAO).items()}
    alvo = norm(alvo)
    nome = next((k for k in sorted(apps, key=len, reverse=True) if re.search(r"\b" + re.escape(k) + r"\b", alvo)), None)
    if not nome and re.search(r"\b(site|pagina|\w+\.(com|br|net|org|tv|io)\b)", alvo):   # pediu site: nem procura programa
        return abrir_site(cfg, alvo, qualquer=True)
    if not nome:
        # qualquer programa do Menu Iniciar: nome idêntico ganha do site ("whatsapp" abre o app instalado);
        # depois um site conhecido ("youtube"); por último o programa de nome parecido ("discórdia" -> Discord)
        try:
            app = extras.achar_app(alvo, so_exato=True) or (None if _site(cfg, alvo)[0] else extras.achar_app(alvo))
        except Exception as e:
            log.warning("Busca de programas falhou: %r", e); app = None
        if app:
            return f"Abrindo {app['nome']}.", lambda a=app: extras.abrir_app(a)
        return abrir_site(cfg, alvo)   # um site conhecido, ou None: deixa a IA responder
    try:
        if str(apps[nome]).lower() in ("chrome", "chrome.exe") and abrir_no_chrome(cfg): pass      # no perfil escolhido
        else: os.startfile(os.path.expandvars(apps[nome]))
        return f"Abrindo {nome}.", None
    except OSError as e:
        log.warning("Falha ao abrir %s: %r", nome, e)
        return f"Não consegui abrir {nome}, {cfg['tratamento']}.", None

def _salvar_opcao(cfg, chave, ligar):
    """Muda uma opção liga/desliga e guarda no config.json (vale depois de reiniciar), sem mexer no resto do arquivo."""
    cfg[chave] = ligar
    try:
        caminho = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
        with open(caminho, encoding="utf-8") as f: texto = f.read()
        valor = "true" if ligar else "false"
        novo = re.sub(rf'"{chave}":\s*(true|false)', f'"{chave}": {valor}', texto)
        if novo == texto: novo = texto.replace("{", f'{{\n  "{chave}": {valor},', 1)
        json.loads(novo)
        with open(caminho, "w", encoding="utf-8") as f: f.write(novo)
    except Exception as e:
        log.warning("Não salvei a opção %s: %r", chave, e)

def _voz_respostas(cfg, ligar):
    _salvar_opcao(cfg, "respostas_por_voz", ligar)
    return "Voz ligada de novo." if ligar else "Modo silencioso: vou responder só por escrito."

def _lista_comandos():
    import scripts_aton
    pasta = os.path.dirname(os.path.abspath(__file__))
    meus = scripts_aton.listar()
    txt = (f"Abri a lista de comandos na tela. Seus comandos: {', '.join(meus)}." if meus else
           "Abri a lista de comandos na tela. Você ainda não criou comandos próprios no arquivo meus comandos.")
    def abrir_lista():
        import gerar_lista
        os.startfile(gerar_lista.gerar())           # gera de novo (inclui os comandos que você criou) e abre
    return txt, abrir_lista

def _so_comandos(cfg, ligar):
    _salvar_opcao(cfg, "so_comandos", ligar)
    return ("Modo só comandos: agora só obedeço aos comandos da lista, sem usar a inteligência artificial." if ligar else
            "Modo inteligente: quando não for um comando da lista, eu uso a inteligência artificial.")

def _atalho_regra(texto):
    t = desktop.atalho_por_nome(norm(texto))
    return (desktop.apertar(t), None) if t else None

VEZES = {"duas": 2, "tres": 3, "quatro": 4, "cinco": 5, "dez": 10}

def _teclas_regra(trecho, vezes):
    t = desktop.teclas_faladas(trecho)
    if not t: return None                  # não é tecla ("aperta Entrar"): a regra de clicar pelo nome tenta
    n = int(vezes) if vezes and vezes.isdigit() else VEZES.get(vezes or "", 1)
    return desktop.apertar(t, n), None

def _trecho_original(trecho_norm):
    """O mesmo trecho com a grafia original da fala (acentos e maiúsculas importam na página e na busca)."""
    pal = ORIGINAL.split()
    for i in range(len(pal)):
        for j in range(len(pal), i, -1):
            if norm(" ".join(pal[i:j])).strip() == trecho_norm.strip():
                return " ".join(pal[i:j]).strip(" ,.!?")
    return trecho_norm

def _janela_regra(acao, nome):
    r = extras.janelas(acao, nome)
    if bracos.tem_pendente():          # "fecha tudo menos X": pergunta antes (o "sim" seguinte executa)
        return f"Posso {bracos.PENDENTE.get('descricao', 'fechar as janelas')}? Confirma?", None
    return r, None

# ------------------------------------------------------------------ roteador
MUS = r"(musica|som|faixa|spotify|video|playlist)"
VID = r"(?:filme|serie|video|episodio|ep|netflix|youtube|desenho|anime|novela|live|prime|disney|max|globoplay|stream)"
R = lambda p: re.compile(p)
# (regex, função, tipo): "pergunta" só informa (o Aton continua ouvindo); "comando" faz algo (o Aton para de ouvir)
REGRAS = [   # a ordem importa: a primeira regra que casar responde
    (R(r"\b(?:desliga\w*|desativ\w*)\b (?:o )?bluetooth\b"), lambda c, m: (_bt_desligar(), None), "comando"),
    (R(r"\b(?:liga|ligar|ligue|ativa|ativar|ative)\b (?:o )?bluetooth\b"), lambda c, m: (bluetooth.ligar(True), None), "comando"),
    (R(r"\bbluetooth\b.*\b(?:ligado|desligado|ativo)\b|\b(?:como|status)\b.*\bbluetooth\b"), lambda c, m: (bluetooth.estado(), None), "pergunta"),
    (R(r"\bbateria\b(?:.*\b(?:d[oae]|meu|minha) (?P<n>.+))?"), lambda c, m: (bluetooth.bateria(m.group("n") or ""), None), "pergunta"),
    (R(r"\bdesconect\w* (?:o |a |meu |minha |do |da )?(?P<n>.*)$"), lambda c, m: (bluetooth.desconectar(m.group("n")), None), "comando"),
    (R(r"\b(?:conect\w*|liga|ligue) (?:o |a |no |na |meu |minha )?(?P<n>fone.*|caixa.*|headphone.*|(?:jbl|sony|aiwa|edifier|philips|samsung|xiaomi|qcy|baseus|lg)\b.*|(?<=conecta ).+|(?<=conecte ).+|(?<=conectar ).+)$"),
     lambda c, m: (bluetooth.conectar(m.group("n")), None), "comando"),
    (R(r"\b(?:passa|passe|muda|mude|troca|troque|coloca|coloque|joga|manda)\b.*\b(?:som|audio|saida)\b.*\b(?:pro|pra|para|no|na|em)\b (?:o |a )?(?P<n>.+)$"),
     lambda c, m: volume_nivel(c, m.group("n")) if re.fullmatch(r"\d{1,3}|" + "|".join(NUM_PALAVRA), m.group("n")) else (bluetooth.trocar_saida(m.group("n")), None), "comando"),
    # janelas: "coloca o chrome na esquerda e o vscode na direita", "fecha tudo menos o spotify", "maximiza o chrome"
    (R(r"\b(?:coloca|coloque|poe|bota|joga|deixa|organiza)\b (?:o |a )?(?P<a>[\w ]+?) (?:na|do lado|pra|para a?) ?esquerd\w* e (?:o |a )?(?P<b>[\w ]+?) (?:na|do lado|pra|para a?) ?direit\w*$"),
     lambda c, m: (extras.janelas("lado_a_lado", m.group("a"), m.group("b")), None), "comando"),
    (R(r"\b(?:coloca|coloque|poe|bota|joga|deixa|organiza)\b (?:o |a )?(?P<b>[\w ]+?) (?:na|do lado|pra|para a?) ?direit\w* e (?:o |a )?(?P<a>[\w ]+?) (?:na|do lado|pra|para a?) ?esquerd\w*$"),
     lambda c, m: (extras.janelas("lado_a_lado", m.group("a"), m.group("b")), None), "comando"),
    (R(r"\b(?P<v>minimiz\w*|fech\w*)\b (?:tudo|todas as janelas|todos os programas) (?:menos|exceto|fora|so deixa) (?:o |a )?(?P<n>.+)$"),
     lambda c, m: _janela_regra("fechar_tudo_menos" if m.group("v").startswith("fech") else "minimizar_tudo_menos", m.group("n")), "comando"),
    (R(r"^(?:aton )?(?P<v>maximiz\w*|minimiz\w*) (?:o |a |a janela d[oa] )?(?P<n>(?!tudo\b)[\w ]+)$"),
     lambda c, m: _janela_regra("maximizar" if m.group("v").startswith("max") else "minimizar", m.group("n")), "comando"),
    # modo agente: olha a tela e age passo a passo (usa o Claude a cada passo)
    (R(r"^(?:aton )?(?:modo agente|agente|faz (?:isso )?(?:pra|para) mim|resolve (?:isso )?(?:pra|para) mim)\b"),
     lambda c, m: _agente_cmd(), "comando"),
    (R(r"^(?:aton )?(?:abre |abra |mostra |mostre |ver |quero ver )?(?:o |meu )?historico(?: (?:de|das|dos) (?:pesquisas?|perguntas?|conversas?))?$"),
     lambda c, m: ((HISTORICO() if HISTORICO else None) or "Histórico na tela.", None), "comando"),
    # resumo do dia (sem IA): clima, agenda, lembretes, e-mails e manchetes, falado e num cartão do painel
    (R(r"^(?:aton )?(?:bom dia|resumo (?:do dia|matinal|da manha|de hoje)|(?:como|qual) (?:esta|ta|e) (?:o )?meu dia|"
       r"o que (?:eu )?tenho (?:pra|para) hoje|me atualiza|me atualize|briefing)(?: aton)?$"),
     lambda c, m: (RESUMO(), None) if RESUMO else None, "comando"),
    (R(r"^(?:aton )?(?:fecha|fechar|tira|some com) (?:o )?resumo$"),
     lambda c, m: ((PAINEL({"resumo": None}) if PAINEL else None) or "Fechei o resumo.", None), "comando"),
    # modos: jogo (pausa tudo até Ctrl+Win+P) e pesquisa (tela grande com resposta, fotos, vídeos e links)
    (R(r"^(?:aton )?(?:(?:ativa|liga|entra no|entrar no|abre|abre o|coloca no) )?(?:o )?modo (?:jogo|game|gamer|jogar)$"),
     lambda c, m: MODO("jogo", True) if MODO else None, "comando"),
    (R(r"^(?:aton )?(?:(?:ativa|liga|entra no|entrar no|abre|abre o|coloca no) )?(?:o )?modo (?:pesquisa|de pesquisa|pesquisar)$"),
     lambda c, m: MODO("pesquisa", True) if MODO else None, "comando"),
    (R(r"^(?:aton )?(?:fecha|fechar|sai|sair|desliga|encerra) (?:a |o |d[ao] )?(?:modo )?(?:de )?pesquisa$"),
     lambda c, m: MODO("pesquisa", False) if MODO else None, "comando"),
    # voz das respostas: "modo silencioso" (só texto) / "pode voltar a falar"
    (R(r"^(?:aton )?(?:modo silencioso|fica em silencio|fique em silencio|para de falar|nao fala mais|responde so por escrito|sem voz)$"),
     lambda c, m: (_voz_respostas(c, False), None), "comando"),
    (R(r"^(?:aton )?(?:pode )?(?:voltar a falar|volta a falar|fala de novo|sai do modo silencioso|desliga o modo silencioso|com voz)$"),
     lambda c, m: (_voz_respostas(c, True), None), "comando"),
    # modo "só comandos" (como a Alexa: sem IA) / modo inteligente
    (R(r"^(?:aton )?(?:(?:ativa|liga|entra no|modo) )?(?:o )?(?:modo )?so (?:comandos|comando)$|^(?:aton )?modo alexa$|^(?:aton )?desliga a (?:ia|inteligencia artificial)$"),
     lambda c, m: (_so_comandos(c, True), None), "comando"),
    (R(r"^(?:aton )?(?:(?:ativa|liga|entra no|volta pro|volta ao) )?(?:o )?modo (?:inteligente|completo|normal)$|^(?:aton )?(?:liga|religa) a (?:ia|inteligencia artificial)$|^(?:aton )?sai do modo so comandos$"),
     lambda c, m: (_so_comandos(c, False), None), "comando"),
    (R(r"\b(?:abre|abra|abrir|mostra|mostre) (?:as |a tela de |o painel de )?configurac\w+\b|^configurac\w+ do aton$"),
     lambda c, m: (_config_abrir(), None), "comando"),
    (R(r"^(?:aton )?(?:me )?(?:mostra|mostre|exibe|exiba|quero ver|procura|busca) (?:umas? |algumas? )?(?:imagens?|fotos?|figuras?) (?:de |do |da |dos |das |sobre )?(.+)$"),
     lambda c, m: ((f"Mostrando imagens de {m.group(1)}. Diga 'abre a pesquisa' para ver no navegador."
                    if MOSTRAR_IMAGENS and MOSTRAR_IMAGENS(m.group(1)) else f"Não achei imagens de {m.group(1)}."), None), "comando"),
    (R(r"^(?:aton )?(?:me )?(?:mostra|mostre|exibe|exiba|procura|busca) (?:uns? |um |alguns? )?(?:videos?|clipes?) (?:de |do |da |dos |das |sobre )?(.+)$"),
     lambda c, m: ((f"Mostrando um vídeo e imagens de {m.group(1)}. Diga 'toca o vídeo' para assistir aqui."
                    if MOSTRAR_IMAGENS and MOSTRAR_IMAGENS(m.group(1), True) else f"Não achei vídeos de {m.group(1)}."), None), "comando"),
    # "quais comandos você conhece?": abre a lista
    (R(r"\b(?:quais|que) comandos\b|\blista de comandos\b|\bo que voce sabe fazer\b|\bmeus comandos\b"),
     lambda c, m: _lista_comandos(), "pergunta"),
    # página aberta no Chrome: escolher o N-ésimo item, clicar pelo nome, pesquisar no próprio site, listar opções
    (R(r"^(?:aton )?(?:abre|abra|abrir|clica no|clique no|toca|toque|coloca|coloque|entra no|entre no|seleciona|assiste|mostra) (?:o |a )?"
       r"(?P<o>\d+|primeir[oa]|segund[oa]|terceir[oa]|quart[oa]|quint[oa]|sext[oa]|setim[oa]|oitav[oa]|non[oa]|decim[oa]|ultim[oa]) ?(?:o |a )?"
       r"(?P<t>video|resultado|link|item|episodio|opcao)s?(?: da (?:lista|pagina))?$"),
     lambda c, m: (navegador.pagina("escolher", n=navegador.numero(m.group("o")),
                                    tipo={"video": "video", "episodio": "episodio"}.get(m.group("t"), "resultado")), None), "comando"),
    (R(r"^(?:aton )?(?:abre|abra|coloca|coloque|toca|toque|vai pro|vai para o|assiste|entra no|ver|bota) (?:o )?(?:episodio|ep) (?P<n>\d+|um|dois|tres|quatro|cinco|seis|sete|oito|nove|dez|onze|doze)$"),
     lambda c, m: (navegador.pagina("escolher", n=navegador.numero(m.group("n")), tipo="episodio"), None), "comando"),
    (R(r"\b(?:o que|onde) (?:da|posso|eu posso|tem|tem pra) (?:pra |para )?clicar\b|\bquais (?:sao )?(?:as )?(?:opcoes|botoes|links)\b.*\b(?:aqui|pagina|site|tela|janela)\b"),
     lambda c, m: (desktop.listar(), None), "pergunta"),
    (R(r"\b(?:pesquis\w*|procur\w*|busc\w*)\b (?:por )?(?P<t>.+?) (?:aqui|nesse site|neste site|nessa pagina|nesta pagina|no site|aqui no site)$"),
     lambda c, m: (navegador.pagina("pesquisar", texto=_trecho_original(m.group("t"))), None), "comando"),
    # teclado: atalhos por nome ("salva", "desfaz", "troca de janela") e teclas ("aperta control shift T", "aperta enter 3 vezes")
    (R(r"^"), lambda c, m: _atalho_regra(m.string), "comando"),
    (R(r"^(?:aton )?(?:aperta|aperte|apertar|pressiona|pressione|da um|tecla)\s+(?P<t>.+?)(?: (?P<v>\d+|duas|tres|quatro|cinco|dez) vezes)?$"),
     lambda c, m: _teclas_regra(m.group("t"), m.group("v")), "comando"),
    (R(r"^(?:aton )?(?P<v>marca|marque|desmarca|desmarque)\b (?:a |o )?(?:opcao |caixa |chave )?(?:d[oae] )?(?P<t>.+)$"),
     lambda c, m: (desktop.marcar(_trecho_original(m.group("t")), not m.group("v").startswith("des")), None), "comando"),
    # clicar pelo nome: no Chrome a extensão clica dentro da página; em qualquer outro programa, a acessibilidade do Windows
    (R(r"^(?:aton )?(?:clica|clique|clicar|aperta|aperte|apertar|seleciona|selecione)\b (?:em |no |na |nos |nas |o |a )?(?:botao |link |opcao |aba |menu )?(?:d[oae] )?(?P<t>.+)$"),
     lambda c, m: (desktop.clicar(_trecho_original(m.group("t"))), None), "comando"),
    # Chrome: vídeos (Netflix, YouTube, Prime...) e guias — navegador.py + extensão do Aton
    (R(r"^(?:aton )?(?:pausa\w*|pause|pauso|pare|para)\b (?:o |a |esse |essa |este |esta )?" + VID + r"\b"),
     lambda c, m: (navegador.chrome("pausar"), None), "comando"),
    (R(r"^(?:aton )?(?:continua\w*|despausa\w*|retoma\w*|da (?:o )?play|solta|volta a passar|tira do pause)\b (?:n?o |a |esse |essa )?" + VID + r"\b"
       r"|^(?:aton )?(?:da (?:o |um )?play|assiste|assistir|assista|reproduz|reproduzir|reproduza|bota pra rodar|comeca o (?:filme|episodio)|"
       r"comeca a serie|aperta o play)(?: (?:ai|agora|nele|nela|esse|essa|esse filme|essa serie|o filme|a serie|o episodio))?$"),
     lambda c, m: (navegador.chrome("tocar"), None), "comando"),
    (R(r"\b(?P<v>volta\w*|volte|retroced\w*|avanc\w*|adiant\w*|pula|pular|pule)\b (?:mais |uns |umas )?(?P<q>(?:\d+|um|uma|dois|duas|tres|cinco|dez|quinze|vinte|"
       r"trinta|quarenta|cinquenta|sessenta|noventa) ?(?:segundos?|seg|minutos?|min)\b(?: e meio)?|um pouco|um pouquinho)"),
     lambda c, m: (navegador.chrome("voltar_tempo" if m.group("v").startswith(("volt", "retroc")) else "avancar_tempo",
                                    valor=navegador.segundos(m.group("q"))), None), "comando"),
    (R(r"\b(?:pula|pular|pule|passa|tira|fecha)\b (?:o |a |essa |esse )?(?:anuncio|propaganda|abertura|intro|introducao|recap|resumo do episodio)\b"),
     lambda c, m: (navegador.chrome("pular_anuncio"), None), "comando"),
    (R(r"\b(?:proximo|outro) (?:episodio|ep|video)\b|\bpassa (?:pro|para o) proximo (?:episodio|video)\b"),
     lambda c, m: (navegador.chrome("proximo_video"), None), "comando"),
    (R(r"\btela cheia\b"), lambda c, m: (navegador.chrome("tela_cheia"), None), "comando"),
    (R(r"\bquanto (?:tempo )?falta\b.*\b(?:filme|episodio|video|serie)\b"), lambda c, m: (navegador.chrome("quanto_falta"), None), "pergunta"),
    (R(r"\b(?:muta|silencia|tira o som d)\w* (?:o |a |esse |essa )?" + VID + r"\b"), lambda c, m: (navegador.chrome("mudo"), None), "comando"),
    (R(r"\bfech\w* (?:as |todas as )?outras (?:guias|abas)\b|\bfech\w* todas as (?:guias|abas) (?:menos|exceto) (?:essa|esta)\b"),
     lambda c, m: (navegador.chrome("fechar_outras"), None), "comando"),
    (R(r"\bfech\w* (?:a |as |essa |esta |todas as )?(?:guias?|abas?)(?: d[oae]s? (?P<b>.+))?$"),
     lambda c, m: (navegador.chrome("fechar", busca=m.group("b") or ""), None), "comando"),
    (R(r"\b(?:abre|abra|abrir|cria|crie)\b (?:uma )?(?:nova (?:guia|aba)|(?:guia|aba) nova)\b"), lambda c, m: (navegador.chrome("nova_aba"), None), "comando"),
    (R(r"\b(?:reabr\w*|abre de novo|desfaz) (?:a )?(?:guia|aba)\b|\b(?:guia|aba) que (?:eu )?fechei\b"),
     lambda c, m: (navegador.chrome("reabrir"), None), "comando"),
    (R(r"\b(?:vai|volta|muda|troca|ir)\b (?:pra|para|pro|na|a)? ?(?:a )?(?:guia|aba) d[oae] (?P<b>.+)$"),
     lambda c, m: (navegador.chrome("ir", busca=m.group("b")), None), "comando"),
    (R(r"\bproxima (?:guia|aba)\b"), lambda c, m: (navegador.chrome("proxima_aba"), None), "comando"),
    (R(r"\b(?:guia|aba) anterior\b"), lambda c, m: (navegador.chrome("aba_anterior"), None), "comando"),
    (R(r"\b(?:recarreg\w*|atualiz\w*) (?:a |essa )?pagina\b"), lambda c, m: (navegador.chrome("recarregar"), None), "comando"),
    (R(r"\b(?:volta|voltar|volte) (?:a |uma )?pagina\b|\bpagina anterior\b"), lambda c, m: (navegador.chrome("voltar"), None), "comando"),
    (R(r"\b(?:vai|volta|leva|rola|sobe)\b (?:pro|para o|ao|pra) (?:topo|inicio|comeco) (?:da pagina|do site)?$|^(?:aton )?topo da pagina$"),
     lambda c, m: (desktop.rolar("topo"), None), "comando"),
    (R(r"\b(?:vai|leva|rola|desce)\b (?:pro|para o|ao|pra) (?:fim|final) (?:da pagina|do site)?$|^(?:aton )?fim da pagina$"),
     lambda c, m: (desktop.rolar("fim"), None), "comando"),
    (R(r"\b(?:rola|desce|descer|role)\b.*\b(?:baixo|pagina|tela)\b|^(?:aton )?(?:desce|rola|desce mais|mais pra baixo)$"), lambda c, m: (desktop.rolar("baixo"), None), "comando"),
    (R(r"\b(?:rola|sobe|subir|role)\b.*\b(?:cima|pagina|tela)\b|^(?:aton )?(?:sobe|sobe mais|mais pra cima)$"), lambda c, m: (desktop.rolar("cima"), None), "comando"),
    (R(r"\b(?:toca|toque|tocar|abre|abra|abrir|coloca|coloque|bota|poe|passa|mostra|mostre)\b (?:o |um |uns )?(?:(?P<o>primeiro|segundo|terceiro|quarto|quinto) )?(?:video|clipe)s? (?:d[aoe] |sobre )?(?P<t>.+)$"
       r"|\b(?:toca|toque|tocar|abre|abra|coloca|coloque|bota|poe)\b (?P<t2>.+) no youtube$"),
     lambda c, m: _video_regra(c, ((m.group("o") or "") + " " + (m.group("t") or m.group("t2"))).strip()), "comando"),
    (R(r"\b(minha tela|na tela|nessa tela|desta tela|dessa tela|da tela|o que (?:eu )?(?:estou|to) vendo)\b"),
     lambda c, m: ver_tela(c, ORIGINAL), "pergunta"),
    (R(r"\b(que|qual) (musica|som|faixa|cancao)\b.*\b(tocando|toca|essa|esta)\b|\b(o )?que (ta|esta) tocando\b|\bquem (canta|e o cantor)\b"),
     lambda c, m: (tocando_agora(c), None), "pergunta"),
    (R(r"^(proxima|pula|avanca)( a)?( musica| faixa)?$|\b(proxima|pula|pular|avanca|passa)( a| essa| esta)? (musica|faixa)\b"),
     lambda c, m: musica(c, "proxima"), "comando"),
    (R(r"^(volta|anterior)$|\b(musica|faixa) anterior\b|\bvolta (a|uma|pra) (musica|faixa)\b"), lambda c, m: musica(c, "anterior"), "comando"),
    # "pauso"/"toco": o Whisper às vezes troca a conjugação
    (R(r"^(pausa|pause|pauso|pausar|para|parar|pare)( a| o)?( " + MUS + r")?( por favor)?$|\b(pausa|pause|pauso|pausar|pare|parar|para)( a| o)? " + MUS + r"\b"),
     lambda c, m: musica(c, "pausar"), "comando"),
    # só pedidos genéricos ("toca", "bota uma música aí"); com nome ("toca a playlist de treino", "toca Queen") vai para a IA,
    # que usa o Spotify de verdade
    (R(r"^(toca|toco|tocar|toque|play|despausa|retoma|continua)( a| o)?( " + MUS + r")?( por favor)?$|\b(toca|toco|tocar|toque|bota|coloca|poe)\b"
       r"( uma| alguma)? (musica|som)( ai| pra mim| por favor)?$|\b(despausa|solta o som|volta a tocar|continua (a musica|tocando))\b"),
     lambda c, m: musica(c, "tocar"), "comando"),
    (R(r"\b(?:volume|som)\b.*\b(?:do|da|no|na) (?P<app>spotify|musica|discord|chrome|navegador|edge|youtube|jogo|league|lol|steam)\b"
       r"|\b(?:aumenta\w*|abaix\w*|diminu\w*|sobe|baixa\w*|muta\w*|silencia\w*) (?:o |a )?(?P<app2>spotify|discord|chrome|navegador)\b"),
     lambda c, m: _volume_app_regra(c, m.string, m.group("app") or m.group("app2")), "comando"),
    (R(r"^(?!.*\b(?:aumenta\w*|abaix\w*|diminu\w*|sobe|subir|baixa\w*)\b).*\b(?:volume|som)\b\D*?\b(?P<n>\d{1,3}|" + "|".join(NUM_PALAVRA) + r")\b"),
     lambda c, m: volume_nivel(c, m.group("n")), "comando"),
    (R(r"\b(?:pesquis\w*|procur\w*|busc\w*)\b (?:por )?(.+?) (?:no|na) (youtube|google maps|google|mercado livre|amazon|maps)$"),
     lambda c, m: pesquisar_em(c, m.group(1), m.group(2)), "comando"),
    (R(r"\b(?:no|na) (youtube|google maps|google|mercado livre|amazon|maps),? (?:pesquis\w*|procur\w*|busc\w*) (?:por )?(.+)$"),
     lambda c, m: pesquisar_em(c, m.group(2), m.group(1)), "comando"),
    (R(r"^(?:aton,? )?(?:digit\w*|escrev\w*) "), lambda c, m: _digitar_original(), "comando"),
    (R(r"\b(aumenta|aumentar|sobe|subir)\b.*\b(volume|som)\b|\bvolume\b.*\b(mais alto|pra cima)\b"), lambda c, m: volume(c, "aumentar"), "comando"),
    (R(r"\b(abaixa|abaixar|diminui|diminuir|baixa|baixar)\b.*\b(volume|som)\b|\bvolume\b.*\b(mais baixo|pra baixo)\b"), lambda c, m: volume(c, "diminuir"), "comando"),
    (R(r"\b(muta|mutar|desmuta|desmutar|silencia|silenciar|tira o som|modo mudo|tira do mudo)\b"), lambda c, m: volume(c, "mudo"), "comando"),
    (R(r"\b(abre|abra|abrir|inicia|iniciar|executa|executar)\b (.+)"), lambda c, m: abrir(c, m.group(2)), "comando"),
    (R(r"\b(clima|previsao do tempo|vai chover|quantos graus|como (esta|ta) o tempo|(ta|esta) (frio|calor|chovendo)|temperatura (agora|hoje|la fora|em|no|na))\b"),
     lambda c, m: (clima(c, _cidade(m.string)), None), "pergunta"),
    (R(r"\b(que horas|que hora e|horas sao|que oracao)\b"), lambda c, m: (hora(c), None), "pergunta"),   # "que oração": como o Whisper às vezes ouve
    (R(r"\b(que dia e hoje|qual e a data|qual a data|que data e hoje|dia e hoje)\b"), lambda c, m: (data(c), None), "pergunta"),
]

def _cidade(t):
    m = re.search(r"\b(?:clima|tempo|chover|graus|temperatura|frio|calor|chovendo) (?:em|no|na|de) ([a-z ]+)$", t)
    return re.sub(r"\b(hoje|agora|amanha|la fora|por favor)\b", "", m.group(1)).strip() or None if m else None

# ------------------------------------------------------------------ pesquisa na web (DuckDuckGo, sem chave)
def pesquisar_web(consulta, n=5):
    from ddgs import DDGS
    r = None
    for backend in ("auto", "bing", "brave", "wikipedia"):    # o DuckDuckGo às vezes volta vazio: tenta outros motores
        try:
            r = DDGS(timeout=5).text(consulta, region="br-pt", max_results=n, backend=backend)
            if r: break
        except Exception as e:
            log.warning("Pesquisa (%s) falhou: %r", backend, e)
    if not r:
        return ("A pesquisa na internet falhou e não trouxe nenhum resultado. Diga ao usuário que não conseguiu confirmar "
                "essa informação agora; não responda com base na memória de treino.")
    return "Resultados do DuckDuckGo:\n" + "\n".join(f"- {x.get('title','')}: {x.get('body','')} ({x.get('href','')})" for x in r)

# ------------------------------------------------------------------ perfil do Chrome
def chrome_exe():
    for p in (r"%ProgramFiles%\Google\Chrome\Application\chrome.exe", r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe",
              r"%LocalAppData%\Google\Chrome\Application\chrome.exe"):
        p = os.path.expandvars(p)
        if os.path.isfile(p): return p
    return None

def abrir_no_chrome(cfg, url=None):
    """Abre o Chrome (ou um endereço nele) no perfil escolhido em "chrome_perfil" (ex.: "Default", "Profile 1")."""
    import subprocess
    exe, perfil = chrome_exe(), (cfg.get("chrome_perfil") or "").strip()
    if not exe or not perfil: return False
    subprocess.Popen([exe, f"--profile-directory={perfil}"] + ([url] if url else []))
    return True

def usar_perfil_chrome(cfg):
    """Com "chrome_perfil" no config, TUDO que o Aton abre na internet vai para esse perfil do Chrome (em vez do
    último perfil usado). Sem a opção, nada muda: vale o navegador padrão do Windows."""
    import webbrowser
    if not (cfg.get("chrome_perfil") or "").strip() or not chrome_exe(): return
    original = webbrowser.open
    def abrir(url, new=0, autoraise=True):
        if str(url).lower().startswith(("http://", "https://")) and abrir_no_chrome(cfg, url): return True
        return original(url, new, autoraise)
    webbrowser.open = abrir
    log.info("Chrome: usando sempre o perfil \"%s\".", cfg["chrome_perfil"])

FONTES_NOTICIAS = [("G1", "https://g1.globo.com/rss/g1/"), ("InfoMoney", "https://www.infomoney.com.br/feed/"),
                   ("CNN Brasil", "https://www.cnnbrasil.com.br/feed/")]
NOTICIAS = {"itens": [], "t": 0.0, "lendo": None, "resultado": False}   # resultado = há uma pesquisa na tela do modo pesquisa

def ultimas_noticias(por_fonte=4):
    """As últimas manchetes do G1, InfoMoney e CNN Brasil (pelos feeds RSS públicos deles), intercaladas:
    [{fonte, titulo, url, img, quando}]. Fica guardado por 5 minutos."""
    import html, email.utils, threading
    if NOTICIAS["itens"] and time.time() - NOTICIAS["t"] < 300: return NOTICIAS["itens"]
    grupos = {}
    def ler(nome, url):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            x = urllib.request.urlopen(req, timeout=8).read().decode("utf-8", "replace")
            out = []
            for it in x.split("<item>")[1:por_fonte + 4]:
                tag = lambda t: (re.search(rf"<{t}[^>]*>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</{t}>", it, re.S) or [None, ""])[1].strip()
                titulo, link = html.unescape(re.sub(r"<[^>]+>", "", tag("title"))), tag("link")
                if not titulo or not link.startswith("https://"): continue
                img = re.search(r'(?:url|src)="(https://[^"]+?\.(?:jpg|jpeg|png|webp)[^"]*)"', it)
                try:
                    dt = email.utils.parsedate_to_datetime(tag("pubDate"))
                    if dt.tzinfo is None: dt = dt.replace(tzinfo=datetime.timezone.utc)     # "-0000" = horário de Greenwich
                    quando = dt.astimezone().strftime("%H:%M")
                except Exception: quando = ""
                out.append({"fonte": nome, "titulo": titulo[:140], "url": link, "img": html.unescape(img.group(1)) if img else "",
                            "quando": quando})
                if len(out) >= por_fonte: break
            grupos[nome] = out
        except Exception as e:
            log.warning("Notícias do %s falharam: %r", nome, e)
    ths = [threading.Thread(target=ler, args=f, daemon=True) for f in FONTES_NOTICIAS]
    for t in ths: t.start()
    for t in ths: t.join(9)
    itens = [g[i] for i in range(por_fonte) for nome, _ in FONTES_NOTICIAS for g in [grupos.get(nome, [])] if i < len(g)]
    if itens: NOTICIAS.update(itens=itens, t=time.time())
    return itens

def ler_noticia(i):
    """Baixa a página da notícia i (da lista na tela) e tira só o texto: {fonte, titulo, url, img, quando, paragrafos}.
    Tudo é feito aqui no PC, sem IA (não gasta tokens)."""
    import html
    n = NOTICIAS["itens"][i]
    req = urllib.request.Request(n["url"], headers={"User-Agent": "Mozilla/5.0", "Accept-Language": "pt-BR"})
    pagina = urllib.request.urlopen(req, timeout=10).read().decode("utf-8", "replace")
    pagina = re.sub(r"<(script|style|noscript|svg|figure|aside|nav|footer|header|form)\b.*?</\1>", " ", pagina, flags=re.S | re.I)
    def paragrafos(trecho):
        out = []
        for bruto in re.findall(r"<(?:p|h2|h3|li)\b[^>]*>(.*?)</(?:p|h2|h3|li)>", trecho, re.S | re.I):
            t = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", bruto))).strip()
            if len(t) < 45 or t in out: continue
            if re.search(r"^(leia (tambem|também|mais)|veja (tambem|também|mais)|siga |assine |compartilhe|publicidade|continua depois|"
                         r"receba |clique aqui|baixe o app|©|todos os direitos)", t, re.I): continue
            out.append(t[:1500])
            if len(out) >= 60: break
        return out
    # 1º o corpo marcado pelo site (G1 usa content-text__container); 2º todos os <article>; por fim a página inteira
    ps = paragrafos(" ".join(re.findall(r'<p[^>]*class="[^"]*content-text__container[^"]*"[^>]*>.*?</p>', pagina, re.S | re.I)))
    if len(ps) < 3: ps = paragrafos(" ".join(re.findall(r"<article\b.*?</article>", pagina, re.S | re.I)))
    if len(ps) < 3: ps = paragrafos(pagina)
    img = n["img"]
    if not img:
        og = re.search(r'<meta[^>]+property="og:image"[^>]+content="(https://[^"]+)"', pagina)
        img = html.unescape(og.group(1)) if og else ""
    if len(ps) >= 2:                                   # só vale como "notícia aberta" se o texto foi lido de verdade
        NOTICIAS["lendo"] = n["url"]
        NOTICIAS["artigo"] = {"fonte": n["fonte"], "titulo": n["titulo"], "texto": "\n".join(ps)[:9000]}
    return {"fonte": n["fonte"], "titulo": n["titulo"], "url": n["url"], "img": img, "quando": n["quando"], "paragrafos": ps, "i": i}

def noticia_no_painel(i):
    """Abre a notícia i no leitor do modo pesquisa (ou no navegador, se não der para ler o texto)."""
    try:
        a = ler_noticia(i)
    except Exception as e:
        log.warning("Não li a notícia: %r", e); a = None
    if a and len(a["paragrafos"]) >= 2 and PAINEL:
        PAINEL({"artigo": a}); log.info("Notícia no leitor: %s (%d parágrafos)", a["fonte"], len(a["paragrafos"]))
        return True
    import webbrowser; webbrowser.open(NOTICIAS["itens"][i]["url"])
    return False

def _agente_cmd():
    """'modo agente: <tarefa>' — tira o comando do texto ORIGINAL (com acentos e pontuação) e roda depois da fala."""
    if not AGENTE: return None
    obj = re.sub(r"(?i)^\W*(?:aton\W+)?(?:modo\s+agente|agente|faz(?:\s+isso)?\s+(?:pra|para)\s+mim|resolve(?:\s+isso)?\s+(?:pra|para)\s+mim)\W*", "", ORIGINAL).strip()
    if len(obj) < 5: return "Qual é a tarefa? Diga, por exemplo: modo agente, abre o bloco de notas e escreve uma lista.", None
    return "Certo, vou fazer passo a passo. Para interromper, aperte Control, Alt, P.", (lambda o=obj: AGENTE(o))

def comando_do_leitor(t):
    """Com uma notícia aberta no leitor: 'desce', 'sobe', 'volta pras notícias', 'abre no navegador'."""
    if not PAINEL: return None
    if NOTICIAS.get("resultado") and not NOTICIAS.get("lendo"):          # resultado de uma pesquisa na tela: "volta" = notícias
        if re.match(r"^(?:aton )?(?:volta|voltar|volte)(?: (?:pra|para|pras|para as|pro|para o|a|as))? ?(?:noticias?|lista|manchetes|inicio|tela inicial)?$", t):
            NOTICIAS["resultado"] = False; PAINEL({"leitor": "fechar"}); return "Voltei para as notícias."
        return None
    if not NOTICIAS.get("lendo"): return None
    if re.match(r"^(?:aton )?(?:desce|descer|rola (?:pra|para) baixo|continua|mais|proxima pagina)(?: (?:a pagina|mais|um pouco))?$", t):
        PAINEL({"leitor": "desce"}); return "Descendo."
    if re.match(r"^(?:aton )?(?:sobe|subir|rola (?:pra|para) cima|volta um pouco)(?: (?:a pagina|mais|um pouco))?$", t):
        PAINEL({"leitor": "sobe"}); return "Subindo."
    if re.match(r"^(?:aton )?(?:volta|voltar|fecha|fechar)(?: (?:pra|para|pras|para as|a|as|essa))? ?(?:noticias?|lista|manchetes)?$", t):
        NOTICIAS["lendo"] = None; PAINEL({"leitor": "fechar"}); return "Voltei para as notícias."
    if re.match(r"^(?:aton )?(?:abre|abra|abrir)(?: (?:isso|essa noticia|a noticia|ela))? no (?:navegador|chrome|site)$", t):
        import webbrowser; webbrowser.open(NOTICIAS["lendo"]); return "Abri a notícia no navegador."
    return None

def abrir_noticia(t):
    """'abre a segunda notícia' / 'abre a notícia 3' com as manchetes na tela (modo pesquisa)."""
    m = re.match(r"^(?:aton )?(?:abre|abra|abrir|le|ler|mostra) (?:a )?(?:(primeira|segunda|terceira|quarta|quinta|sexta|setima|oitava|nona|decima) noticia|noticia (?:numero )?(\d+|um|uma|dois|duas|tres|quatro|cinco|seis|sete|oito|nove|dez))$", t)
    if not m or not NOTICIAS["itens"]: return None
    ords = ["primeira", "segunda", "terceira", "quarta", "quinta", "sexta", "setima", "oitava", "nona", "decima"]
    nums = {"um": 1, "uma": 1, "dois": 2, "duas": 2, "tres": 3, "quatro": 4, "cinco": 5, "seis": 6, "sete": 7, "oito": 8, "nove": 9, "dez": 10}
    i = ords.index(m.group(1)) if m.group(1) else (int(m.group(2)) if m.group(2).isdigit() else nums[m.group(2)]) - 1
    if not 0 <= i < len(NOTICIAS["itens"]): return f"Só há {len(NOTICIAS['itens'])} notícias na tela."
    n = NOTICIAS["itens"][i]
    if PAINEL:                                     # no modo pesquisa: abre no leitor da própria tela
        import threading; threading.Thread(target=noticia_no_painel, args=(i,), daemon=True).start()
        return f"Notícia do {n['fonte']}."
    import webbrowser; webbrowser.open(n["url"])
    return f"Abri a notícia do {n['fonte']}: {n['titulo']}."

def buscar_imagens(consulta, n=3):
    """[{url, titulo}] de fotos da internet (miniaturas do buscador, com filtro de conteúdo adulto ligado)."""
    from ddgs import DDGS
    r = []
    for regiao in ("br-pt", "wt-wt"):
        try:
            r = DDGS(timeout=6).images(consulta, region=regiao, safesearch="on", max_results=n + 3) or []
        except Exception as e:
            log.info("Busca de imagens (%s) vazia: %s", regiao, str(e)[:60])
        if r: break
    out = [{"url": x.get("thumbnail") or x.get("image"), "titulo": (x.get("title") or "")[:80]} for x in r]
    return [x for x in out if str(x["url"]).startswith("https://")][:n]

def buscar_videos(consulta, n=3):
    """Os n melhores vídeos do YouTube sobre o assunto (mesma avaliação do buscar_video)."""
    return buscar_video(consulta, n) or []

def buscar_video(consulta, varios=0):
    """Um vídeo do YouTube sobre o assunto: {url, thumb, titulo, duracao, site}, ou None. Lê a página de resultados do
    YouTube (sem chave), como o tocar_video; pula vídeos curtos demais (Shorts) e os muito longos."""
    url = "https://www.youtube.com/results?search_query=" + urllib.parse.quote_plus(consulta)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept-Language": "pt-BR"})
        html = urllib.request.urlopen(req, timeout=8).read().decode("utf-8", "replace")
    except Exception as e:
        log.warning("Busca no YouTube falhou: %r", e); return None
    achados = []
    for m in re.finditer(r'"videoRenderer":\{"videoId":"([\w-]{11})"', html):
        trecho = html[m.end():m.end() + 6000]
        t = re.search(r'"title":\{"runs":\[\{"text":"((?:[^"\\]|\\.)*)"', trecho)
        d = re.search(r'"lengthText":\{.{0,300}?"simpleText":"([\d:]+)"', trecho)
        if not t or not d: continue                              # sem duração = transmissão ao vivo ou anúncio
        try: titulo = json.loads('"' + t.group(1) + '"')
        except ValueError: titulo = t.group(1)
        p = [int(x) for x in d.group(1).split(":")]
        seg = p[-1] + 60 * (p[-2] if len(p) > 1 else 0) + 3600 * (p[-3] if len(p) > 2 else 0)
        achados.append((m.group(1), titulo[:90], d.group(1), seg))
        if len(achados) >= 8: break
    if not achados: return None
    # avaliação: prefere vídeos de 30 s a 15 min cujo título tem as palavras pedidas
    pal = [w for w in norm(consulta).split() if len(w) > 2]
    def nota(a):
        tn = norm(a[1])
        return (sum(w in tn for w in pal) / max(1, len(pal))) + (0.5 if 30 <= a[3] <= 900 else 0) - (0.3 if a[3] > 3600 else 0)
    item = lambda a: {"url": "https://www.youtube.com/watch?v=" + a[0], "thumb": f"https://i.ytimg.com/vi/{a[0]}/mqdefault.jpg",
                      "titulo": a[1], "duracao": a[2], "site": "YouTube"}
    if varios: return [item(a) for a in sorted(achados, key=nota, reverse=True)[:varios]]
    return item(max(achados, key=nota))

def links_de(consulta, video=None):
    """Links para abrir a mesma busca no navegador."""
    from urllib.parse import quote_plus
    q = quote_plus(consulta)
    ls = [{"rotulo": "Pesquisa no Google", "url": f"https://www.google.com/search?q={q}", "tipo": "pesquisa"},
          {"rotulo": "Mais imagens", "url": f"https://www.google.com/search?tbm=isch&q={q}", "tipo": "imagens"}]
    if video: ls.insert(0, {"rotulo": "Abrir o vídeo", "url": video["url"], "tipo": "video"})
    ls.append({"rotulo": "Vídeos no YouTube", "url": f"https://www.youtube.com/results?search_query={q}", "tipo": "videos"})
    return ls

MOSTRAR_IMAGENS = None     # o assistente.py põe aqui a função que mostra imagens/vídeo/links no painel: f(consulta, video=False)
MIDIA = {"links": [], "t": 0.0, "consulta": "", "video": None, "videos": [], "tocando": False}   # o que está na tela agora
MODO = None                # o assistente.py põe aqui a função dos modos: f(nome, ligar) -> (resposta, ação depois da fala)
AGENTE = None              # idem: função do modo agente: f(objetivo)
HISTORICO = None           # idem: função que mostra o histórico na tela do modo pesquisa: f()
RESUMO = None              # o assistente.py põe aqui a função do resumo do dia: f() -> texto para falar
PAINEL = None              # o assistente.py põe aqui a função que manda um recado ao wallpaper: f(dict)

def fluxo_video(url, altura=480):
    """Endereços diretos do vídeo (VP9) e do áudio (Opus) no YouTube, para o player do painel: o Wallpaper Engine não
    aceita páginas embutidas nem MP4/H.264, mas toca WebM. Os endereços valem por algumas horas e só neste PC."""
    import yt_dlp
    with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True, "skip_download": True, "noplaylist": True}) as y:
        info = y.extract_info(url, download=False)
    fs = [f for f in info.get("formats", []) if f.get("protocol") == "https" and f.get("ext") == "webm" and f.get("url")]
    vs = sorted((f for f in fs if str(f.get("vcodec", "")).startswith("vp") and (f.get("height") or 0) <= altura),
                key=lambda f: f.get("height") or 0)
    aus = sorted((f for f in fs if f.get("vcodec") in (None, "none") and str(f.get("acodec", "")).startswith("opus")),
                 key=lambda f: f.get("abr") or 0)
    if not vs or not aus: raise RuntimeError("este vídeo não tem um formato que o painel consiga tocar")
    return {"v": vs[-1]["url"], "a": aus[-1]["url"], "titulo": (info.get("title") or "")[:90]}

def tocar_no_painel(i=0):
    """Busca os fluxos (leva ~2 s) e manda o painel tocar. Se não der, abre no navegador. i = qual vídeo da lista."""
    vs = MIDIA.get("videos") or []
    v = vs[i] if 0 <= i < len(vs) else MIDIA.get("video")
    if not v or not PAINEL: return
    try:
        fl = fluxo_video(v["url"])
        MIDIA["tocando"] = True
        PAINEL({"cmd": "tocar_video", "v": fl["v"], "a": fl["a"], "titulo": fl["titulo"], "url": v["url"]})
    except Exception as e:
        log.warning("Vídeo no painel falhou (%s): abrindo no navegador.", str(e)[:120])
        MIDIA["tocando"] = False
        import webbrowser; webbrowser.open(v["url"])

def video_no_painel(t):
    """'toca o vídeo' / 'fecha o vídeo': o player fica na janela flutuante do painel, sem abrir o navegador."""
    if not PAINEL: return None
    if MIDIA["tocando"] and re.match(r"^(?:aton )?(?:fecha|fechar|tira|para|pare|encerra|some com)\b (?:o |esse |com o )?(?:video|player)$", t):
        MIDIA["tocando"] = False; PAINEL({"cmd": "fechar_video"}); return "Fechei o vídeo."
    if MIDIA["tocando"] and re.match(r"^(?:aton )?(?:pausa|pause|pausar)\b (?:o |esse )?video$", t):
        PAINEL({"cmd": "pausar_video"}); return "Pausado."
    if MIDIA["tocando"] and re.match(r"^(?:aton )?(?:continua|despausa|da play)\b (?:n?o |esse )?video$", t):
        PAINEL({"cmd": "continuar_video"}); return "Continuando."
    if MIDIA["video"] and time.time() - MIDIA["t"] < 300 and re.match(
            r"^(?:aton )?(?:toca|tocar|toque|reproduz|reproduzir|reproduza|roda|passa|assiste|assistir|da play n?o?|play n?o?|inicia|comeca)\b ?(?:o |esse |no )?"
            r"(?:(primeiro|segundo|terceiro) )?video(?: (um|dois|tres|1|2|3))?(?: aqui| ai| na tela| no painel| no aton)?$", t):
        m = re.search(r"(primeiro|segundo|terceiro) video|video (um|dois|tres|1|2|3)", t)
        i = {"primeiro": 0, "um": 0, "1": 0, "segundo": 1, "dois": 1, "2": 1, "terceiro": 2, "tres": 2, "3": 2}[m.group(1) or m.group(2)] if m else 0
        MIDIA["tocando"] = True; MIDIA["t"] = time.time()
        import threading; threading.Thread(target=tocar_no_painel, args=(i,), daemon=True).start()
        return "Carregando o vídeo no painel. Diga 'fecha o vídeo' quando quiser."
    return None

def abrir_link_da_midia(t):
    """'abre o vídeo / a pesquisa / as imagens / o link' logo depois de o Aton mostrar algo: abre no navegador."""
    if not MIDIA["links"] or time.time() - MIDIA["t"] > 180: return None
    m = re.match(r"^(?:aton )?(?:abre|abra|abrir|mostra|quero ver|pode abrir|sim abre)(?: no navegador)? (?:o |a |os |as |esse |essa |mais )?"
                 r"(video|videos|pesquisa|busca|imagens|fotos|link|links|resultado|resultados)(?: (?:no|do) (?:navegador|google|youtube))?$", t)
    if not m: return None
    quer = {"video": "video", "videos": "videos", "imagens": "imagens", "fotos": "imagens"}.get(m.group(1), "pesquisa")
    alvo = next((l for l in MIDIA["links"] if l["tipo"] == quer), None) or \
           next((l for l in MIDIA["links"] if quer == "video" and l["tipo"] == "videos"), None) or MIDIA["links"][0]
    import webbrowser
    webbrowser.open(alvo["url"])
    return {"video": "Abri o vídeo", "videos": "Abri os vídeos", "imagens": "Abri mais imagens",
            "pesquisa": "Abri a pesquisa"}[alvo["tipo"]] + f" de {MIDIA['consulta']} no navegador."

def _config_abrir():
    import aton_remote, webbrowser
    webbrowser.open(f"http://127.0.0.1:{aton_remote.PORTA}/config.html#t={aton_remote.TOKEN}")
    return "Abri as configurações."

# ------------------------------------------------------------------ ferramentas oferecidas à IA (chamada de funções do Ollama)
# Padrão de "tool calling" adaptado do OrchestratorAgent do OpenJarvis (Apache-2.0).
def _f(nome, desc, props=None, req=()):
    return {"type": "function", "function": {"name": nome, "description": desc, "parameters": {
        "type": "object", "properties": props or {}, "required": list(req)}}}

ESQUEMAS = [
    _f("pesquisar_web", "Pesquisa na internet (DuckDuckGo). Use para fatos atuais, notícias, resultados de jogos, preços, "
       "pessoas e qualquer coisa que você não saiba com certeza.", {"consulta": {"type": "string", "description": "termos da busca"}}, ["consulta"]),
    _f("mostrar_midia", "MOSTRA NA TELA fotos da internet (e opcionalmente um vídeo) sobre algo, com links para abrir no navegador. "
       "Use sempre que o usuário pedir para ver ou mostrar alguma coisa ('me mostra um Porsche', 'quero ver a fórmula de Bhaskara', "
       "'como é um axolote'). Você decide o 'video': true para o que vale ver em movimento (carros, animais, lugares, esportes, "
       "pessoas, jogos, filmes, como fazer algo); false para o que é estático (fórmulas, equações, diagramas, mapas, logotipos, "
       "tabelas, símbolos, textos).",
       {"consulta": {"type": "string", "description": "o que mostrar, em poucas palavras"},
        "video": {"type": "boolean", "description": "true = incluir um vídeo junto das fotos"}}, ["consulta"]),
    _f("buscar_historico", "Procura nas conversas ANTERIORES com o usuário (perguntas que ele fez e o que você respondeu, com data). "
       "Use quando ele perguntar 'o que eu te perguntei sobre X', 'o que você me disse ontem', 'qual era aquele ... que pesquisamos'.",
       {"busca": {"type": "string", "description": "palavras do assunto; vazio = as conversas mais recentes"},
        "dias": {"type": "integer", "description": "só os últimos N dias (1 = hoje e ontem)"}}),
    _f("clima", "Clima atual e previsão de hoje (Open-Meteo).", {"cidade": {"type": "string", "description": "cidade; vazio = cidade do usuário"}}),
    _f("hora_data", "Hora e data atuais do computador."),
    _f("musica", "Controla o player de música do Windows (Spotify) ou diz o que está tocando.",
       {"acao": {"type": "string", "enum": ["tocar", "pausar", "proxima", "anterior", "o_que_toca"]}}, ["acao"]),
    _f("volume", "Muda o volume do Windows.", {"acao": {"type": "string", "enum": ["aumentar", "diminuir", "mudo"]}}, ["acao"]),
    _f("tocar_video", "Abre direto um vídeo do YouTube pela busca.", {"termo": {"type": "string"},
       "posicao": {"type": "integer", "description": "1 = primeiro resultado"}}, ["termo"]),
    _f("ver_tela", "Olha a tela do computador (print) e responde sobre o que aparece nela.", {"pergunta": {"type": "string"}}),
    _f("bluetooth", "Bluetooth e som: ligar/desligar o rádio, estado, bateria dos aparelhos, conectar/desconectar fone ou caixa pareados, trocar a saída de som.",
       {"acao": {"type": "string", "enum": ["ligar", "desligar", "estado", "bateria", "conectar", "desconectar", "trocar_saida"]},
        "aparelho": {"type": "string", "description": "nome do aparelho ou da saída de som; vazio = o fone pareado"}}, ["acao"]),
    _f("volume_app", "Muda o volume SÓ de um programa (ex.: Spotify, Discord, navegador), sem mexer no volume geral do PC.",
       {"app": {"type": "string"}, "acao": {"type": "string", "enum": ["aumentar", "diminuir", "mudo", "definir"]},
        "nivel": {"type": "integer", "description": "0 a 100, quando acao = definir"}}, ["app", "acao"]),
    _f("volume_nivel", "Põe o volume do Windows num valor exato.", {"nivel": {"type": "integer", "description": "0 a 100"}}, ["nivel"]),
    _f("abrir_site", "Abre QUALQUER site no navegador pelo nome ou endereço (HBO Max, Netflix, Prime Video, Gmail, um banco, uma loja...). "
       "Se o nome parecer mal ouvido, passe o que você acha que o usuário quis dizer.", {"nome": {"type": "string"}}, ["nome"]),
    _f("pesquisar_em", "Abre o navegador já com uma busca feita no site.", {"termo": {"type": "string"},
       "site": {"type": "string", "enum": ["youtube", "google", "mercado livre", "amazon", "maps"]}}, ["termo"]),
    _f("abrir_programa", "Abre qualquer programa ou jogo instalado no PC (tudo que aparece no Menu Iniciar: Discord, Spotify, "
       "Steam, League of Legends, Calculadora, Word...), pelo nome.", {"nome": {"type": "string"}}, ["nome"]),
    _f("lembrar", "Guarda um fato na memória permanente quando o usuário pedir para lembrar algo ou contar algo pessoal importante.",
       {"fato": {"type": "string", "description": "o fato, em uma frase curta na 3ª pessoa"}}, ["fato"]),
    _f("esquecer", "Apaga da memória anotações que contenham o trecho dado.", {"trecho": {"type": "string"}}, ["trecho"]),
]

def chamar(nome, args, cfg, memoria):
    """Executa uma ferramenta pedida pela IA. Devolve (texto para a IA, função a rodar depois da fala ou None)."""
    args = args or {}
    if nome == "pesquisar_web": return pesquisar_web(args.get("consulta", "")), None
    if nome == "buscar_historico":
        import historico
        return historico.para_ia(historico.buscar(str(args.get("busca", "")), args.get("dias") or None)), None
    if nome == "mostrar_midia":
        c = str(args.get("consulta", "")).strip()
        if not c: return "Diga o que devo mostrar.", None
        if not MOSTRAR_IMAGENS: return "A tela não está disponível agora.", None
        video = bool(args.get("video")) and not re.search(     # coisas estáticas nunca levam vídeo, mesmo que a IA peça
            r"\b(formula|equac|teorema|diagrama|mapa|logo|logotipo|tabela|simbolo|grafico|bandeira|brasao|planta baixa|organograma)", norm(c))
        r = MOSTRAR_IMAGENS(c, video)
        if not r: return f"Não achei imagens de {c}.", None
        return (f"Coloquei na tela {r} de {c}. Para abrir no navegador, diga "
                + ("'abre a pesquisa'; para assistir aqui mesmo, diga 'toca o vídeo'." if "vídeo" in r else "'abre a pesquisa'.")), None
    if nome == "clima": return clima(cfg, args.get("cidade") or None), None
    if nome == "hora_data": return hora(cfg) + " " + data(cfg), None
    if nome == "musica":
        a = norm(str(args.get("acao", ""))).replace(" ", "_")
        a = {"next": "proxima", "skip": "proxima", "play": "tocar", "resume": "tocar", "continuar": "tocar", "pause": "pausar",
             "previous": "anterior", "voltar": "anterior", "now_playing": "o_que_toca", "qual": "o_que_toca",
             "status": "o_que_toca", "estado": "o_que_toca", "info": "o_que_toca", "atual": "o_que_toca"}.get(a, a)
        if a == "o_que_toca": return tocando_agora(cfg), None
        if a in ("tocar", "pausar", "proxima", "anterior"): return musica(cfg, a)
        return "Ação inválida. Use exatamente uma destas: tocar, pausar, proxima, anterior, o_que_toca.", None
    if nome == "volume" and args.get("acao") not in ("aumentar", "diminuir", "mudo"):
        return "Ação inválida. Use exatamente uma destas: aumentar, diminuir, mudo.", None
    if nome == "volume" and args.get("acao") in ("aumentar", "diminuir", "mudo"): return volume(cfg, args["acao"])
    if nome == "tocar_video": return tocar_video(cfg, args.get("termo", ""), args.get("posicao") or 1)
    if nome == "ver_tela": return ver_tela(cfg, args.get("pergunta", ""))
    if nome == "bluetooth":
        a, ap = args.get("acao"), args.get("aparelho") or ""
        if a == "desligar": return _bt_desligar(), None
        f = {"ligar": lambda: bluetooth.ligar(True), "estado": bluetooth.estado, "bateria": lambda: bluetooth.bateria(ap),
             "conectar": lambda: bluetooth.conectar(ap), "desconectar": lambda: bluetooth.desconectar(ap),
             "trocar_saida": lambda: bluetooth.trocar_saida(ap)}.get(a)
        return (f() if f else "Ação inválida."), None
    if nome == "volume_app":
        return volume_app(cfg, args.get("app", "spotify"), args.get("acao", ""), args.get("nivel") if args.get("acao") == "definir" else None)
    if nome == "volume_nivel": return volume_nivel(cfg, args.get("nivel"))
    if nome == "abrir_site": return abrir_site(cfg, args.get("nome", ""), qualquer=True) or (f"Não abri: '{args.get('nome')}' não parece um site. Não diga que abriu.", None)
    if nome == "pesquisar_em": return pesquisar_em(cfg, args.get("termo", ""), args.get("site") or "google")
    if nome == "abrir_programa":
        r = abrir(cfg, args.get("nome", ""))
        return r if r else (f"Não achei nenhum programa instalado chamado '{args.get('nome')}'. Use listar_programas para ver os nomes.", None)
    if nome == "lembrar": return memoria.lembrar(args.get("fato", "")), None
    if nome == "esquecer": return memoria.esquecer(args.get("trecho", "")), None
    if nome.startswith("spotify_"):
        if not spotify.configurado():
            return "O Spotify ainda não foi conectado ao Aton (falta o login). Diga isso ao usuário.", None
        try:
            if nome == "spotify_tocar": return spotify.tocar(args.get("busca", ""), args.get("tipo", "auto")), None
            if nome == "spotify_fila": return spotify.fila(args.get("busca", "")), None
            if nome == "spotify_curtir": return spotify.curtir_atual(), None
            if nome == "spotify_playlists": return spotify.listar_playlists(), None
            if nome == "spotify_aleatorio": return spotify.aleatorio(bool(args.get("ligar", True))), None
        except Exception as e:
            log.warning("Spotify falhou: %r", e)
            return f"O Spotify recusou: {e}", None
    if nome.startswith("email_"):
        if not email_outlook.configurado():
            return "O e-mail ainda não foi conectado ao Aton (falta o login). Diga isso ao usuário.", None
        try:
            if nome == "email_hoje": return email_outlook.texto_para_ia(email_outlook.de_hoje(), "E-mails de hoje"), None
            if nome == "email_recentes":
                return email_outlook.texto_para_ia(email_outlook.recentes(int(args.get("quantos", 5) or 5), bool(args.get("so_nao_lidos"))),
                                                   "Últimos e-mails"), None
            if nome == "email_buscar":
                return email_outlook.texto_para_ia(email_outlook.buscar(args.get("termo", "")), f"E-mails sobre '{args.get('termo', '')}'"), None
        except Exception as e:
            log.warning("E-mail falhou: %r", e)
            return f"Não consegui ler os e-mails: {e}", None
    if nome == "agendar":
        return agenda.agendar(args.get("titulo", "compromisso"), args.get("data", ""), args.get("horario", ""),
                              args.get("duracao_min", 60), args.get("local", ""), args.get("avisar_antes_min", 15)), None
    if nome == "ver_agenda": return agenda.listar(args.get("data", ""), args.get("dias", 1)), None
    if nome == "desmarcar": return agenda.desmarcar(args.get("trecho", "")), None
    if nome == "remarcar": return agenda.remarcar(args.get("trecho", ""), args.get("data", ""), args.get("horario", "")), None
    if nome == "criar_monitor":
        return monitores.criar(args.get("tipo", ""), args.get("alvo", ""), args.get("condicao", ""), args.get("valor"), args.get("horario", "")), None
    if nome == "listar_monitores": return monitores.listar(), None
    if nome == "cancelar_monitor": return monitores.cancelar(args.get("trecho", "")), None
    if nome == "cotacao":
        try: return f"{args.get('ativo')} agora: R$ {monitores.cotacao(args.get('ativo', '')):.2f} (fonte: Frankfurter/BCE para moedas, CoinGecko para bitcoin).", None
        except Exception as e: return f"Não consegui a cotação: {e}", None
    if nome == "vocabulario":
        import vocabulario
        a = args or {}; acao, p = a.get("acao", ""), (a.get("palavra") or "").strip()
        if acao == "aprender" and p:
            lista = list(cfg.get("vocabulario") or [])
            if p not in lista:
                lista.append(p); cfg["vocabulario"] = lista
                try:
                    caminho = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
                    with open(caminho, encoding="utf-8") as f: c = json.load(f)
                    c["vocabulario"] = lista
                    with open(caminho, "w", encoding="utf-8") as f: json.dump(c, f, ensure_ascii=False, indent=2)
                except Exception as e: log.warning("Não salvei o vocabulário: %r", e)
                vocabulario.configurar(cfg)
            return f"Aprendi a palavra '{p}': vou reconhecê-la melhor.", None
        if acao == "esquecer" and p:
            n = vocabulario.esquecer(p); return (f"Esqueci {n} correção(ões) com '{p}'." if n else f"Não havia correção com '{p}'."), None
        d = vocabulario._dados()
        return ("Correções aprendidas: " + ("; ".join(f"'{k}' vira '{v}'" for k, v in d["correcoes"].items()) or "nenhuma") +
                ". Palavras ensinadas: " + (", ".join(cfg.get("vocabulario") or []) or "nenhuma")), None
    if nome == "whatsapp":
        a = args or {}
        return navegador.whatsapp(a.get("acao", ""), a.get("contato", "") or "", a.get("mensagem", "") or "", a.get("quantas") or 10), None
    if nome == "computador": return desktop.chamar(args or {}), None
    if nome == "pagina":
        a = args or {}
        return navegador.pagina(a.get("acao", ""), a.get("texto", "") or "", a.get("n"), a.get("tipo", "") or ""), None
    if nome == "chrome":
        a = args or {}
        return navegador.chrome(a.get("acao", ""), a.get("busca", "") or "", a.get("url", "") or "", a.get("valor")), None
    r = extras.chamar(nome, args, cfg)
    if r is not None: return r, None
    r = bracos.chamar(nome, args, cfg, lambda n, a: chamar(n, a, cfg, memoria))
    if r is not None:
        texto, deps = r
        return texto, ((lambda: [d() for d in deps]) if deps else None)
    return f"Ferramenta desconhecida: {nome}", None

ESQUEMAS += bracos.ESQUEMAS + extras.ESQUEMAS + [navegador.ESQUEMA, navegador.ESQUEMA_WPP, navegador.ESQUEMA_PAGINA, desktop.ESQUEMA] + [
    _f("vocabulario", "Vocabulário do reconhecimento de voz: aprender (o usuário ensina um nome/palavra para ser reconhecido melhor), "
       "esquecer (apaga correções aprendidas que contenham a palavra), listar (mostra correções e palavras ensinadas).",
       {"acao": {"type": "string", "enum": ["aprender", "esquecer", "listar"]}, "palavra": {"type": "string"}}, ["acao"]),
] + [
    _f("email_hoje", "Lista os e-mails recebidos hoje no Outlook do usuário (remetente, assunto e prévia) para resumir."),
    _f("email_recentes", "Últimos e-mails da caixa de entrada do Outlook.",
       {"quantos": {"type": "integer"}, "so_nao_lidos": {"type": "boolean"}}),
    _f("email_buscar", "Procura e-mails por remetente, assunto ou palavra (ex.: 'tem e-mail do banco?').",
       {"termo": {"type": "string"}}, ["termo"]),
    _f("spotify_tocar", "Toca no Spotify uma playlist (as do usuário têm prioridade), artista, música ou álbum pelo nome. "
       "Use para 'toca minha playlist X', 'toca Queen', 'toca a música Y'.",
       {"busca": {"type": "string", "description": "nome da playlist, artista, música ou álbum"},
        "tipo": {"type": "string", "enum": ["auto", "playlist", "artista", "musica", "album"]}}, ["busca"]),
    _f("spotify_fila", "Coloca uma música na fila do Spotify (toca depois da atual).", {"busca": {"type": "string"}}, ["busca"]),
    _f("spotify_curtir", "Curte (salva nas músicas curtidas) a música que está tocando no Spotify."),
    _f("spotify_playlists", "Lista as playlists do usuário no Spotify."),
    _f("spotify_aleatorio", "Liga ou desliga o modo aleatório do Spotify.", {"ligar": {"type": "boolean"}}, ["ligar"]),
    _f("agendar", "Marca um compromisso na agenda do usuário (com aviso falado antes). Calcule a data a partir de hoje "
       "(ex.: 'quinta' = próxima quinta). Para algo sem hora marcada que é só para lembrar, use criar_lembrete.",
       {"titulo": {"type": "string"}, "data": {"type": "string", "description": "AAAA-MM-DD"}, "horario": {"type": "string", "description": "HH:MM 24h"},
        "duracao_min": {"type": "integer"}, "local": {"type": "string"}, "avisar_antes_min": {"type": "integer", "description": "padrão 15"}},
       ["titulo", "data", "horario"]),
    _f("ver_agenda", "Mostra os compromissos de um dia (data AAAA-MM-DD; vazio = hoje) ou dos próximos N dias (dias=7 para a semana).",
       {"data": {"type": "string"}, "dias": {"type": "integer"}}),
    _f("desmarcar", "Desmarca o próximo compromisso cujo título contenha o trecho.", {"trecho": {"type": "string"}}, ["trecho"]),
    _f("remarcar", "Muda data e/ou horário de um compromisso.", {"trecho": {"type": "string"}, "data": {"type": "string"},
       "horario": {"type": "string"}}, ["trecho"]),
    _f("cotacao", "Cotação atual em reais de dólar, euro ou bitcoin.",
       {"ativo": {"type": "string", "enum": ["dolar", "euro", "bitcoin"]}}, ["ativo"]),
    _f("criar_monitor", "Cria um monitor que fica checando sozinho e avisa por voz: tipo 'cotacao' (alvo dolar/euro/bitcoin, "
       "condicao acima/abaixo, valor em reais), tipo 'noticia' (alvo = assunto; avisa notícia nova) ou tipo 'resumo' "
       "(horario HH:MM; resumo falado todo dia).",
       {"tipo": {"type": "string", "enum": ["cotacao", "noticia", "resumo"]}, "alvo": {"type": "string"},
        "condicao": {"type": "string", "enum": ["acima", "abaixo"]}, "valor": {"type": "number"}, "horario": {"type": "string"}}, ["tipo"]),
    _f("listar_monitores", "Lista os monitores ativos."),
    _f("cancelar_monitor", "Cancela monitores cuja descrição contenha o trecho.", {"trecho": {"type": "string"}}, ["trecho"]),
]

ULTIMO_TIPO = None   # tipo da última regra rápida usada ("pergunta" ou "comando")

ORIGINAL = ""
FIM_DIGITAR = re.compile(r"[\s,]*(?:na (?:barra de )?pesquisa|e (?:aperte|aperta|d[êe]|da) enter|e pesquis[ae]|e envi[ae])[\s.!]*$", re.I)

def _digitar_original():
    """Digita o texto como foi ditado (com acentos e pontuação), sem o 'digite' do começo."""
    t = re.sub(r"^\s*(?:aton[,.]?\s*)?(?:digit\w*|escrev\w*)\s*(?:isso|isto|o seguinte|assim)?\s*[:,]?\s*", "", ORIGINAL, flags=re.I)
    enter = bool(FIM_DIGITAR.search(t)); t = FIM_DIGITAR.sub("", t).strip().rstrip(".")
    return digitar_cmd(t, enter) if t else ("O que devo digitar?", None)

def executar(texto, cfg):
    global ULTIMO_TIPO, ORIGINAL
    if ORIGINAL: navegador.ULTIMAS_FALAS.append(ORIGINAL)   # o WhatsApp confere se o texto da mensagem foi mesmo dito
    ORIGINAL = texto
    import scripts_aton                    # 1º: os seus comandos pré-programados (meus_comandos.txt)
    r = scripts_aton.regra(texto, cfg)
    if r is not None:
        ULTIMO_TIPO = "comando"
        return r
    t = norm(texto)
    r = video_no_painel(t) or abrir_link_da_midia(t) or comando_do_leitor(t) or abrir_noticia(t)   # "toca o vídeo" (no painel) / "abre o vídeo" (no navegador)
    if r is not None:
        ULTIMO_TIPO = "comando"
        return r, None
    import atalhos                         # 2º: comandos por tecla com contexto (vídeo, tela cheia, guias): sempre iguais, sem IA
    r = atalhos.regra(t)
    if r is not None:
        ULTIMO_TIPO = "comando"
        return r, None
    for rx, fn, tp in REGRAS:
        m = rx.search(t)
        if m:
            r = fn(cfg, m)
            if r is not None:
                log.info("Ferramenta (%s): %s", tp, rx.pattern[:40])
                ULTIMO_TIPO = tp
                return r
    return None
