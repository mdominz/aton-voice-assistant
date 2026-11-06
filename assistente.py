# -*- coding: utf-8 -*-
"""
AI Core - Assistente de voz para o wallpaper.
"Aton" (ou o atalho) -> escuta -> transcreve -> comandos rápidos ou IA (nuvem do Ollama, com o local de reserva) -> fala.
Avisa o wallpaper (ws://127.0.0.1:8765) em cada etapa para o núcleo reagir.
Uso:  python assistente.py                   (normal)
      python assistente.py --demo            (só testa a ligação com o wallpaper, sem microfone nem IA)
      python assistente.py --frase "texto"   (pula o microfone: pergunta, fala e sai)
      python assistente.py --arquivo a.mp3   (transcreve um áudio no lugar do microfone e sai)
      python assistente.py --ativacao a.mp3  (só diz se o áudio começa com a palavra de ativação e sai)
      python assistente.py --saudacao        (faz a saudação de abertura e sai)
"""
import asyncio, json, os, sys, threading, time, tempfile, datetime, logging, re, socket, subprocess, unicodedata, shutil
import urllib.request, itertools, queue
from collections import deque
from logging.handlers import RotatingFileHandler

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
HERE = os.path.dirname(os.path.abspath(__file__))
CFG = {
    "hotkey": "ctrl+alt+space",
    "rota": "auto",                       # "auto" (nuvem do Ollama, com o local de reserva), "nuvem" ou "local"
    "modelo_nuvem": "gpt-oss:120b-cloud",  # modelo na nuvem do Ollama (precisa estar logado no Ollama)
    "timeout_nuvem": 8,                   # segundos sem resposta da nuvem antes de usar o modelo local
    "ollama_url": "http://127.0.0.1:11434",
    "ollama_modelo": "llama3.1:8b",
    "manter_carregado": "30m",            # quanto tempo o Ollama mantém o modelo na placa de vídeo
    "nome": "Aton",
    "tratamento": "senhor",
    "voz": "pt-BR-AntonioNeural",
    "velocidade_voz": "+0%",
    "whisper_modelo": "small",
    "ativacao_por_voz": True,             # escuta o tempo todo esperando a palavra de ativação
    "palavra_ativacao": ["aton", "atom", "a tom"],   # variantes de como o Whisper escreve "Aton"
    "modelo_ativacao": "tiny",            # modelo leve só para reconhecer a palavra
    "microfone": None,                   # None = padrão do Windows; ou parte do nome, ex.: "USB"
    "porta": 8765,
    "max_segundos": 15,
}
try:
    # utf-8-sig: aceita o config.json salvo pelo Bloco de Notas com "BOM"
    with open(os.path.join(HERE, "config.json"), encoding="utf-8-sig") as f:
        CFG.update(json.load(f))
except FileNotFoundError:
    pass
except ValueError as e:                   # vírgula ou aspas faltando: mensagem clara em vez de um erro genérico
    msg = f"O config.json tem um erro de digitação (linha {getattr(e, 'lineno', '?')}): {e}. Corrija e inicie de novo."
    try:
        import ctypes; ctypes.windll.user32.MessageBoxW(None, msg, "Aton", 0x10)
    except Exception:
        pass
    sys.exit(msg)
ARGS = sys.argv[1:]
DEMO = "--demo" in ARGS
def _arg(name):
    return ARGS[ARGS.index(name) + 1] if name in ARGS and ARGS.index(name) + 1 < len(ARGS) else None
FRASE, ARQUIVO, ATIVACAO = _arg("--frase"), _arg("--arquivo"), _arg("--ativacao")

# ------------------------------------------------------------------ log (arquivo + console, se houver)
log = logging.getLogger("aton")
log.setLevel(logging.INFO)
_fh = RotatingFileHandler(os.path.join(HERE, "assistente.log"), maxBytes=1_000_000, backupCount=2, encoding="utf-8")
_fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%Y-%m-%d %H:%M:%S"))
log.addHandler(_fh)
if sys.stdout is not None:
    log.addHandler(logging.StreamHandler(sys.stdout))
else:                                     # pythonw: sem console; bibliotecas que escrevem em stdout/stderr não podem quebrar
    sys.stdout = sys.stderr = open(os.devnull, "w", encoding="utf-8")
sys.excepthook = lambda t, v, tb: log.critical("Erro fatal", exc_info=(t, v, tb))

# ------------------------------------------------------------------ servidor websocket
def _porta_livre(p):
    with socket.socket() as s:
        try: s.bind(("127.0.0.1", p)); return True
        except OSError: return False
if not ATIVACAO and not _porta_livre(CFG["porta"]):
    log.error("A porta %s já está em uso (outro assistente aberto?). Encerrando.", CFG["porta"])
    sys.exit(1)

import websockets
LOOP = asyncio.new_event_loop()
CLIENTS = set()
INTRO = threading.Event()        # o wallpaper abriu e pediu a saudação (pode chegar antes de o resto carregar)

EMAILS = {"lista": []}             # últimos e-mails (atualizados 1x por minuto em segundo plano)

def atualizar_emails():
    try:
        import email_outlook
        if email_outlook.configurado() and CFG.get("emails_no_wallpaper", True):
            EMAILS["lista"] = email_outlook.painel(8)
    except Exception as e:
        log.warning("E-mails para o wallpaper falharam: %r", e)

def _painel_json():
    try:
        import agenda, bracos
        return json.dumps({"agenda": agenda.painel(bracos.lembretes_futuros()), "emails": EMAILS["lista"]}, ensure_ascii=False)
    except Exception as e:
        log.warning("Painel da agenda falhou: %r", e); return None

def enviar_json(obj):
    data = json.dumps(obj, ensure_ascii=False)
    async def _b():
        for ws in list(CLIENTS):
            try: await ws.send(data)
            except Exception: CLIENTS.discard(ws)
    asyncio.run_coroutine_threadsafe(_b(), LOOP)

def enviar_painel():
    """Manda ao wallpaper os próximos compromissos e lembretes (cartões do canto direito)."""
    data = _painel_json()
    if not data: return
    async def _b():
        for ws in list(CLIENTS):
            try: await ws.send(data)
            except Exception: CLIENTS.discard(ws)
    asyncio.run_coroutine_threadsafe(_b(), LOOP)

def _concluir(id_):
    import agenda, bracos
    if agenda.concluir(id_) or bracos.concluir_lembrete(id_):
        log.info("Item %s concluído pelo wallpaper", id_)
    enviar_painel()

async def _handler(ws):
    CLIENTS.add(ws)
    log.info("Wallpaper conectado (%d)", len(CLIENTS))
    try:
        if time.time() - REINICIO_AUDIO[0] < 20:      # recarregou só por causa da troca de som: sem animação de início
            await ws.send(json.dumps({"cmd": "semintro"}))
        data = _painel_json()
        if data: await ws.send(data)
        async for msg in ws:
            try:
                m = json.loads(msg)
                if m.get("event") == "intro": INTRO.set()
                elif m.get("event") == "concluir" and m.get("id"):
                    threading.Thread(target=_concluir, args=(str(m["id"]),), daemon=True).start()
            except (ValueError, AttributeError):
                pass
    finally:
        CLIENTS.discard(ws)

async def _serve():
    async with websockets.serve(_handler, "127.0.0.1", CFG["porta"]):
        await asyncio.Future()

def _run_loop():
    asyncio.set_event_loop(LOOP)
    LOOP.run_until_complete(_serve())

def send(state=None, user=None, reply=None):
    msg = {}
    if state is not None: msg["state"] = state
    if user is not None: msg["user"] = user
    if reply is not None: msg["reply"] = reply
    data = json.dumps(msg, ensure_ascii=False)
    async def _b():
        for ws in list(CLIENTS):
            try: await ws.send(data)
            except Exception: CLIENTS.discard(ws)
    asyncio.run_coroutine_threadsafe(_b(), LOOP)

if not ATIVACAO:
    threading.Thread(target=_run_loop, daemon=True).start()

# ------------------------------------------------------------------ demo
if DEMO:
    log.info("Modo demonstração: enviando estados ao wallpaper. Ctrl+C para sair.")
    time.sleep(1)
    while True:
        send("listening"); time.sleep(3)
        send("thinking", user="Que horas são?"); time.sleep(2.5)
        send("speaking", reply="São " + datetime.datetime.now().strftime("%H:%M") + ", " + CFG["tratamento"] + ". Posso ajudar em mais alguma coisa?"); time.sleep(5)
        send("idle"); time.sleep(6)

# ------------------------------------------------------------------ dependências pesadas
import glob
# Bibliotecas CUDA (pip nvidia-cublas-cu12 / nvidia-cudnn-cu12) para o Whisper rodar na placa de vídeo.
for _d in glob.glob(os.path.join(sys.prefix, "Lib", "site-packages", "nvidia", "*", "bin")):
    os.add_dll_directory(_d); os.environ["PATH"] = _d + os.pathsep + os.environ["PATH"]
import numpy as np
import sounddevice as sd
import edge_tts
import pygame
from faster_whisper import WhisperModel
import ferramentas, memoria, cerebro, bracos, monitores, agenda, extras, vocabulario, fundo
vocabulario.configurar(CFG)
threading.Thread(target=fundo.restaurar_se_ficou, daemon=True).start()   # o Aton caiu com o som abaixado? devolve
# confirma se COMEÇA com uma palavra de "sim" e não tem "não" ("Sim, sim, pode fechar." / "Pode sim, Aton")
# verbos ("fecha", "faz") só contam em respostas curtas: "Fecha a sala da área de trabalho" é outro pedido
CONFIRMA = re.compile(r"^(?!.*\bnao\b)((sim|confirmo|confirma|confirmado|pode|claro|isso|positivo|ok|com certeza|certo|aham|uhum|"
                      r"por favor)\b|(manda|faz|faca|fecha|desliga|reinicia|organiza|vai)( \w+){0,2}$)")
NEGA = re.compile(r"^(nao|cancela|cancelar|deixa|deixa pra la|esquece|negativo|nao precisa|nao obrigad[oa])\b")

pygame.mixer.init()
_SAIDA = [None]

def saida_atual():
    """Id da saída de som padrão do Windows (o pygame não acompanha a troca sozinho)."""
    try:
        import comtypes
        from pycaw.pycaw import AudioUtilities
        try: comtypes.CoInitialize()
        except OSError: pass
        return AudioUtilities.GetSpeakers().id
    except Exception:
        return None

def mixer_na_saida_atual():
    """Se a saída padrão mudou (ex.: passou para o fone), reabre o mixer nela."""
    sid = saida_atual()
    if _SAIDA[0] is None: _SAIDA[0] = sid
    elif sid and sid != _SAIDA[0]:
        log.info("Saída de som mudou; reabrindo o áudio do Aton nela.")
        pygame.mixer.quit(); pygame.mixer.init(); _SAIDA[0] = sid

mixer_na_saida_atual()
MEM = memoria.Memoria(HERE)
CER = cerebro.Cerebro(CFG, MEM)
STT = {"m": None, "wake": None}
BUSY = threading.Lock()
STOP = threading.Event()
FALANDO = threading.Event()          # está respondendo numa conversa: dizer "Aton" interrompe
INTERRUPCAO = {"pedido": None}       # None = sem interrupção; "" = só "Aton"; texto = pedido já falado junto

# ------------------------------------------------------------------ PC bloqueado = Aton dormente
# Com a Inicialização Rápida, o Windows abre a sessão e fica na tela de senha: o Aton carrega, mas não escuta,
# não fala e não aceita o atalho até você desbloquear (ninguém dá comandos com o PC bloqueado).
TRAVADO = threading.Event()
SAUDOU = threading.Event()

def _bloqueado():
    import psutil
    return any((p.info["name"] or "").lower() == "logonui.exe" for p in psutil.process_iter(["name"]))

def vigia_bloqueio():
    if _bloqueado(): TRAVADO.set(); log.info("PC bloqueado: Aton dormente até o desbloqueio.")
    while True:
        time.sleep(2)
        try: b = _bloqueado()
        except Exception: continue
        if b and not TRAVADO.is_set():
            TRAVADO.set(); STOP.set(); log.info("PC bloqueado: Aton dormente.")
        elif not b and TRAVADO.is_set():
            TRAVADO.clear(); log.info("PC desbloqueado: Aton ativo.")
            if not SAUDOU.is_set() and CFG.get("saudar_ao_desbloquear", True):
                # primeira vez nesta sessão: o wallpaper repete a abertura (animação + som) e, no ponto da voz,
                # pede a saudação; sem wallpaper (ou com a abertura desligada), saúda direto depois de 8 s
                if CLIENTS: enviar_json({"cmd": "intro"}); log.info("Pedindo ao wallpaper para repetir a abertura.")
                threading.Timer(0 if not CLIENTS else 8, lambda: None if SAUDOU.is_set() else INTRO.set()).start()

def esperar_desbloqueio():
    while TRAVADO.is_set(): time.sleep(0.5)

def whisper(nome):
    """Carrega um modelo Whisper na placa de vídeo (10x mais rápido); se não der, no processador."""
    if CFG.get("whisper_gpu", True):
        try:
            m = WhisperModel(nome, device="cuda", compute_type="float16", download_root=os.path.join(HERE, "modelos"))
            log.info("Whisper '%s' na placa de vídeo.", nome)
            return m
        except Exception as e:
            log.warning("Whisper '%s' não carregou na placa de vídeo (%r); usando o processador.", nome, e)
    return WhisperModel(nome, device="cpu", compute_type="int8", download_root=os.path.join(HERE, "modelos"))

def load_stt():
    log.info("Carregando modelo de transcrição '%s' (na primeira vez baixa ~500 MB)...", CFG["whisper_modelo"])
    STT["m"] = whisper(CFG["whisper_modelo"])
    if CFG["ativacao_por_voz"]:
        STT["wake"] = whisper(CFG["modelo_ativacao"])
        log.info("Pronto. Diga \"%s\" ou pressione %s para falar.", CFG["nome"], CFG["hotkey"])
    else:
        log.info("Pronto. Pressione %s para falar.", CFG["hotkey"])

class SemMicrofone(Exception):
    pass

# O botão de mudo de muitos microfones USB não avisa o Windows: o microfone passa a entregar silêncio digital
# (pico de 0,00003, só 0 e ±1 bit). Desmutado, a sala mais silenciosa medida teve pico de 0,00024.
MUDO_PICO = 1e-4
MUTED = threading.Event()

def recarregar_audio():
    """Relê a lista de dispositivos de áudio do Windows (o PortAudio guarda a lista do momento em que abriu)."""
    try: sd._terminate(); sd._initialize()
    except Exception as e: log.warning("Não consegui recarregar os dispositivos de áudio: %r", e)

def mic_device():
    """Índice do microfone escolhido. Com "microfone_obrigatorio", não usa outro se ele sumir."""
    want = CFG.get("microfone")
    if want is None or isinstance(want, int): return want
    if not str(want).strip(): return None             # vazio = microfone padrão do Windows
    reserva = CFG.get("microfone_reserva")
    if reserva:                                   # ex.: microfone virtual de um filtro fechado -> o microfone físico
        for nome in (want, reserva):
            try: return _mic_por_nome(nome)
            except SemMicrofone: continue
        raise SemMicrofone(want)
    return _mic_por_nome(want)

MIC_ATUAL = {"nome": ""}

def mudo_confiavel():
    """O "mudo" do microfone é detectado pelo silêncio digital. Com um filtro de remoção de ruído (ex.: NVIDIA Broadcast) a sala
    quieta também vira silêncio digital, então nesse caso a detecção fica desligada."""
    return CFG.get("detectar_mudo", True) and "broadcast" not in MIC_ATUAL["nome"].lower()

def _mic_por_nome(want):
    # Ordem das interfaces de áudio: MME e DirectSound aceitam 16 kHz e gravação "bloqueante"; WASAPI exige a taxa
    # nativa (48 kHz) e WDM-KS não grava assim ("Blocking API not supported"). No boot um microfone USB pode aparecer só no
    # WDM-KS por alguns segundos: nesse caso é melhor esperar do que pegar a interface errada.
    PREFERENCIA = ("MME", "Windows DirectSound")
    for tentativa in range(2):
        apis = [a["name"] for a in sd.query_hostapis()]
        achados = [(i, apis[d["hostapi"]]) for i, d in enumerate(sd.query_devices())
                   if d["max_input_channels"] > 0 and str(want).lower() in d["name"].lower()]
        for api in PREFERENCIA:
            for i, nome_api in achados:
                if nome_api == api:
                    MIC_ATUAL["nome"] = sd.query_devices(i)["name"]
                    return i
        if tentativa == 0:                             # pode ter sido (re)conectado: recarrega a lista de dispositivos
            recarregar_audio()
    if CFG.get("microfone_obrigatorio", True):
        raise SemMicrofone(want)
    log.warning("Microfone '%s' não encontrado; usando o padrão do Windows.", want)
    return None

def beep(freq=900, ms=70):
    try:
        import winsound; winsound.Beep(freq, ms)
    except Exception:
        pass

def som(momento, esperar=True):
    """Toca o som do Aton (sons.py: ativacao, continuar ou lembrete) até o fim, antes de o microfone abrir.
    Os arquivos são gerados na primeira vez em sons\\; sem eles, cai para o bipe do Windows."""
    estilo = CFG.get("estilo_som") or ""
    if not estilo:
        return beep(*{"ativacao": (900, 70), "continuar": (1300, 40), "lembrete": (1100, 120)}.get(momento, (900, 70)))
    try:
        import sons, winsound
        path = sons.caminho(estilo, momento)
        if not os.path.exists(path): sons.gerar(os.path.dirname(path))
        if momento == "lembrete":                      # aviso: toca inteiro antes da fala
            winsound.PlaySound(path, winsound.SND_FILENAME)
        else:                                          # ativação/continuar: o microfone abre enquanto a cauda do som termina
            winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC)
            if esperar: time.sleep(0.25)
    except Exception as e:
        log.warning("Som '%s' falhou (%r); usando o bipe.", momento, e); beep()

_VAD = {}

def detector_voz(qual):
    """Um Silero VAD por escuta (cada um guarda a própria memória). None se não carregar: volta ao volume do som."""
    if qual not in _VAD:
        try:
            import vad; _VAD[qual] = vad.DetectorVoz()
        except Exception as e:
            log.warning("Detector de voz (Silero) não carregou (%r); usando o volume do som.", e); _VAD[qual] = None
    d = _VAD[qual]
    if d: d.zerar()
    return d

def record(espera=6, som_inicio=None):
    """Grava até você parar de falar (ou max_segundos); sem fala em `espera` s devolve None ("mudo" se mutado).
    O fim da fala é decidido pelo Silero VAD (fala humana x ruído/música); sem ele, pelo volume.
    som_inicio: toca o som de ativação JÁ com o microfone aberto (o que você falar junto com o som não se perde)."""
    sr, block = 16000, 1600
    frames, speech, quiet, noise, pico, falou = [], False, 0, None, 0.0, 0
    det = detector_voz("pedido") if CFG.get("detector_voz", True) else None
    fim = max(3, round(CFG.get("fim_fala", 0.7) * 10)) if det else 8
    if som_inicio and not det: som(som_inicio); som_inicio = None    # sem o Silero, o som atrapalharia a medida de ruído
    t0 = time.time()
    with sd.InputStream(samplerate=sr, channels=1, dtype="float32", blocksize=block, device=mic_device()) as st:
        if som_inicio: som(som_inicio, esperar=False)
        while time.time() - t0 < CFG["max_segundos"] and not STOP.is_set():
            data, _ = st.read(block)
            x = data[:, 0].copy(); frames.append(x)
            pico = max(pico, float(np.abs(x).max()))
            if det:
                p = det(x)
                if speech and p > 0.5 and float(np.sqrt(np.mean(x ** 2))) < CFG.get("volume_fala_continua", 0.016):
                    p = 0.0                                  # fala baixa (TV ao fundo) depois que você começou: é pausa
                if p > 0.5:
                    falou += 1; quiet = 0
                    if falou >= 2: speech = True        # 2 pedaços seguidos: não é um estalo
                elif p < 0.35:
                    falou = 0
                    if speech: quiet += 1
            else:
                rms = float(np.sqrt(np.mean(x ** 2)))
                if noise is None: noise = rms
                if len(frames) < 4: noise = min(noise, rms) if rms else noise; continue
                thr = max(noise * 3, 0.012)
                if rms > thr: speech, quiet = True, 0
                elif speech: quiet += 1
            if speech and quiet >= fim: break        # ~0,7 s sem fala
            if not speech and time.time() - t0 > espera:          # ninguém falou (só silêncio digital = mutado)
                return "mudo" if pico < MUDO_PICO and espera >= 6 and mudo_confiavel() else None
    return np.concatenate(frames) if speech else None

def transcribe(audio, model="m", rapido=False):
    # modelo principal: recebe o vocabulário (contatos, programas, correções aprendidas) como dica e aplica as
    # correções; o modelo da palavra de ativação só precisa do nome
    dica = vocabulario.hotwords(CFG["nome"]) if model == "m" else CFG["nome"]
    extra = {}
    if rapido:          # conferência do "Aton": uma tentativa só (sem repetir com "temperatura" quando o áudio é ruim)
        extra = dict(temperature=0.0, condition_on_previous_text=False, without_timestamps=True)
    segs, _ = STT[model].transcribe(audio, language="pt", vad_filter=True, beam_size=1, hotwords=dica, **extra)
    texto = " ".join(s.text.strip() for s in segs).strip()
    return vocabulario.corrigir(texto) if model == "m" else texto

# ------------------------------------------------------------------ palavra de ativação
SAUDACOES = {"ei", "oi", "ola", "e", "hey", "ok", "fala", "ow", "o", "a", "ah"}
SO_NO_INICIO = {"atom"}      # "Atom, aumenta o volume" vale; "o Atom é pequeno" não

def _norm(word):
    w = unicodedata.normalize("NFD", word.lower())
    return re.sub(r"[^a-z0-9]+", "", "".join(c for c in w if unicodedata.category(c) != "Mn"))

def wake_split(text):
    """Se a frase começa com a palavra de ativação (talvez depois de "ei"/"oi"), devolve o resto; senão None."""
    toks = [(t, _norm(t)) for t in text.split()]
    toks = [t for t in toks if t[1]]
    norms = [n for _, n in toks]
    for var in CFG["palavra_ativacao"]:
        v = [_norm(p) for p in var.split()]
        for i in (0, 1):
            if i == 1 and (not norms or norms[0] not in SAUDACOES or _norm(var) in SO_NO_INICIO): break
            if norms[i:i + len(v)] == v:
                return " ".join(t for t, _ in toks[i + len(v):]).strip(" ,.!?;:-")
    return None

def guardar_amostra_ativacao(audio):
    """Guarda (só no PC) os "Aton" confirmados, com a sua voz de verdade: servem para treinar um detector de
    palavra de ativação próprio (openWakeWord) depois. Fica nas últimas 300 amostras; desligue com
    "coletar_amostras_ativacao": false."""
    if not CFG.get("coletar_amostras_ativacao", True): return
    try:
        import wave
        pasta = os.path.join(HERE, "amostras_ativacao"); os.makedirs(pasta, exist_ok=True)
        with wave.open(os.path.join(pasta, time.strftime("aton_%Y%m%d_%H%M%S.wav")), "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000)
            w.writeframes((np.clip(audio, -1, 1) * 32767).astype("<i2").tobytes())
        velhas = sorted(glob.glob(os.path.join(pasta, "aton_*.wav")))[:-300]
        for v in velhas: os.remove(v)
    except Exception as e:
        log.warning("Não guardei a amostra de ativação: %r", e)

def _duvida_ativacao(text):
    """O início soa parecido com "Aton"? (medido com as gravações do usuário em 2026-11-04: o modelo leve escreve
    "Bato", "Cato", "Ato", "Ah, tô"; nesses casos vale conferir com o modelo melhor, ~150 ms)"""
    import difflib
    w = [_norm(x) for x in text.split()][:2]
    alvo = _norm(CFG["nome"])
    return any(x and difflib.SequenceMatcher(None, x, alvo).ratio() >= 0.6 for x in w) or bool(w and w[0] in ("ah", "a", "o", "ei"))

_DET_ATON = {}

def detector_aton():
    """Detector do "Aton" treinado com a sua voz (None se ainda não foi treinado)."""
    if "d" not in _DET_ATON:
        _DET_ATON["d"] = None
        if CFG.get("detector_aton", True):
            import detector_aton as da
            _DET_ATON["d"] = da.carregar()
    return _DET_ATON["d"]

def check_wake(audio, nota=0.0):
    # o "Aton" vem no começo: para conferir bastam os primeiros 2,5 s (trechos longos de TV não travam a escuta)
    inicio = audio[:int(16000 * CFG.get("segundos_conferencia", 2.5))]
    text = transcribe(inicio, "wake", rapido=True)
    rest = wake_split(text)
    if rest is None and _duvida_ativacao(text):
        text = transcribe(inicio, rapido=True)   # o modelo leve ficou em dúvida ("Ato", "Tato", "Ah, tô"...): confere com o melhor
        rest = wake_split(text)
    if rest is None and nota >= CFG.get("limiar_detector", 0.97):
        # o detector treinado com a sua voz só AJUDA quando o Whisper ouviu algo QUASE igual a "Aton" ("Ato", "Ata",
        # "At", "Que é a aton"). Em 2026-11-06 a regra antiga (qualquer palavra curta) ativava com "YouTube", "Um",
        # "Beleza", "de"... no dia a dia: o detector dá nota alta para muita fala comum.
        pal = [_norm(w) for w in text.split() if _norm(w)]
        # "quase Aton": começa com "at" e é curta (Ato, Ata, At, Atom); "até" e "atum" são palavras comuns: não valem
        parecido = lambda w: w.startswith("at") and len(w) <= 5 and w not in ("ate", "atum", "atual", "atras")
        if pal and len(pal) <= 2 and parecido(pal[-1] if pal[0] in SAUDACOES and len(pal) == 2 else pal[0]):
            rest = ""
        elif any(w in ("aton", "atom") for w in pal[:4]):
            i = next(i for i, w in enumerate(pal[:4]) if w in ("aton", "atom"))
            rest = " ".join(text.split()[i + 1:]).strip(" ,.!?;:-")
        if rest is not None: log.info("Ativação pelo detector da sua voz (nota %.2f; o Whisper ouviu \"%s\")", nota, text)
    if rest is None:
        if CFG.get("log_ativacao"): log.info("Ignorado: \"%s\"%s", text, f" (detector {nota:.2f})" if nota else "")
        return
    log.info("Ativação por voz: \"%s\"", text)
    if not rest: guardar_amostra_ativacao(audio)
    interrompendo = FALANDO.is_set() and CFG.get("interromper_por_voz", True)
    if rest or len(audio) > len(inicio):   # falou junto ("Aton, que horas são?"): transcreve tudo com o modelo melhor
        full = transcribe(audio)
        better = wake_split(full)
        if better is None:         # escreveu o nome de outro jeito; o início já foi confirmado, então só tira a 1ª palavra
            w = full.split()
            if w and _norm(w[0]) in SAUDACOES: w = w[1:]
            better = " ".join(w[1:]).strip(" ,.!?;:-")
        rest = better or rest
    if interrompendo:              # ele estava falando: corta a fala e a conversa atende o novo pedido
        INTERRUPCAO["pedido"] = rest or ""; STOP.set()
        log.info("Interrompido por voz%s", f": {rest}" if rest else ".")
        return
    start_session(rest or None)

def wake_listener():
    """Escuta o microfone o tempo todo; cada trecho de fala é testado com o modelo leve."""
    sr, block = 16000, 1600
    noise, ausente = 0.003, False
    while True:
        if STT["wake"] is None or (BUSY.locked() and not FALANDO.is_set()) or TRAVADO.is_set() or pausado():
            time.sleep(0.5); continue
        try:
            with sd.InputStream(samplerate=sr, channels=1, dtype="float32", blocksize=block, device=mic_device()) as st:
                if ausente: log.info("Microfone %s conectado de novo.", CFG["microfone"]); ausente = False
                pre, seg, quiet, mudo, falas = deque(maxlen=3), [], 0, 0, 0
                det = detector_voz("ativacao") if CFG.get("detector_voz", True) else None
                daton = detector_aton()
                if daton: daton.zerar()
                notas, nota_seg = deque(maxlen=6), 0.0
                while (not BUSY.locked() or FALANDO.is_set()) and not TRAVADO.is_set() and not pausado():
                    x = st.read(block)[0][:, 0].copy()
                    if daton:                                    # nota do "Aton" (sua voz) a cada 0,1 s
                        try: notas.append(daton.ouvir(x))
                        except Exception: notas.append(0.0)
                        if seg: nota_seg = max(nota_seg, notas[-1])
                    mudo = mudo + 1 if float(np.abs(x).max()) < MUDO_PICO and mudo_confiavel() else 0
                    if mudo >= 15 and not MUTED.is_set():        # 1,5 s de silêncio digital: mutado
                        MUTED.set(); seg = []; log.info("Microfone mudo: assistente em pausa.")
                    elif mudo == 0 and MUTED.is_set():
                        MUTED.clear(); log.info("Microfone ligado: escutando \"%s\" de novo.", CFG["nome"])
                    if MUTED.is_set(): continue
                    if det:
                        # Silero: só fala humana abre um trecho (música e barulho não acordam o Whisper).
                        # Depois de aberto, só fala ALTA o mantém: a TV ao fundo (mais baixa) conta como pausa e não
                        # se cola antes nem depois do "Aton" (medido com gravações da TV em 2026-11-04)
                        p = det(x)
                        fala, calado = p > 0.5, p < 0.35
                        if seg and fala and float(np.sqrt(np.mean(x ** 2))) < CFG.get("volume_fala_continua", 0.016):
                            fala, calado = False, True
                    else:
                        rms = float(np.sqrt(np.mean(x ** 2)))
                        thr = max(noise * 3.5, 0.01)
                        fala, calado = rms > thr, rms <= thr
                        if not seg and not fala: noise = noise * 0.95 + rms * 0.05
                    if not seg:
                        if fala: seg, quiet, falas, nota_seg = list(pre) + [x], 0, 1, max(notas, default=0.0)
                        else: pre.append(x)
                        continue
                    seg.append(x)
                    if fala: falas += 1
                    quiet = quiet + 1 if calado else (0 if fala else quiet)
                    # trecho curto (só "Aton", ~0,5 s) termina com 0,3 s de pausa; frase longa espera mais (pausas entre palavras)
                    curto = det is not None and falas <= CFG.get("ativacao_curta_blocos", 9)
                    fim = CFG.get("fim_fala_ativacao_curta", 4) if curto else CFG.get("fim_fala_ativacao", 6)
                    if quiet >= fim or len(seg) >= 100:              # pausa ou 10 s de fala
                        audio, seg = np.concatenate(seg), []
                        pre.clear()
                        if len(audio) >= sr * 0.4 and (det is None or falas >= 2):
                            t0 = time.time()
                            check_wake(audio, nota_seg)
                            if CFG.get("log_ativacao"): log.info("Conferência levou %.2f s.", time.time() - t0)
        except SemMicrofone:
            if not ausente: log.warning("Microfone %s não encontrado: assistente desligado até ele voltar.", CFG["microfone"])
            ausente = True; MUTED.clear()
            time.sleep(5)
        except Exception as e:                           # ex.: desconectado no meio da escuta, ou lista desatualizada
            log.warning("Erro na escuta da palavra de ativação (%r); recarregando os dispositivos de áudio.", e)
            time.sleep(5)
            if not BUSY.locked(): recarregar_audio()

def _ollama(path, body, timeout=180):
    req = urllib.request.Request(CFG["ollama_url"] + path, data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))

OLLAMA_LOCK = threading.Lock()

def ensure_ollama():
    """Se o servidor do Ollama não estiver no ar (ele não inicia sozinho com o Windows), sobe 'ollama serve' escondido."""
    with OLLAMA_LOCK:
        try:
            urllib.request.urlopen(CFG["ollama_url"] + "/api/version", timeout=2).close(); return True
        except Exception:
            pass
        exe = shutil.which("ollama") or os.path.expandvars(r"%LOCALAPPDATA%\Programs\Ollama\ollama.exe")
        log.info("Ollama fora do ar; iniciando %s serve", exe)
        try:
            # CREATE_NO_WINDOW (sem DETACHED_PROCESS): o servidor ganha um console oculto, herdado pelos "runners"
            # que ele cria ao carregar o modelo; sem isso cada runner abre uma janela de terminal que pisca.
            subprocess.Popen([exe, "serve"], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
        except OSError as e:
            log.error("Não foi possível iniciar o Ollama: %r", e); return False
        for _ in range(60):
            time.sleep(0.5)
            try:
                urllib.request.urlopen(CFG["ollama_url"] + "/api/version", timeout=2).close(); return True
            except Exception:
                pass
        log.error("O Ollama não respondeu em 30 s."); return False

def warm_up():
    """Garante o Ollama no ar; carrega o modelo local na placa de vídeo só quando ele vai ser usado."""
    def _w():
        try:
            if ensure_ollama() and CER.usando_local():
                _ollama("/api/generate", {"model": CFG["ollama_modelo"], "keep_alive": CFG["manter_carregado"]})
        except Exception as e: log.warning("Ollama não respondeu ao pré-carregamento: %r", e)
    threading.Thread(target=_w, daemon=True).start()

# ------------------------------------------------------------------ voz (frase por frase)
def _tts_offline(text, path):
    """Voz do Windows (Maria), usada quando o edge-tts (online) falha."""
    ps = ("Add-Type -AssemblyName System.Speech;$s=New-Object System.Speech.Synthesis.SpeechSynthesizer;"
          "try{$s.SelectVoiceByHints('NotSet','NotSet',0,[Globalization.CultureInfo]'pt-BR')}catch{};"
          f"$s.SetOutputToWaveFile('{path}');$s.Speak([Console]::In.ReadToEnd());$s.Dispose()")
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], input=text.encode("utf-8"),
                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), check=True, timeout=60)

_N_FALA = itertools.count()

def _para_voz(texto):
    """Ajustes só para a fala: a vírgula antes do tratamento ("Pronto, senhor.") vira uma pausa artificial na voz."""
    t = CFG.get("tratamento", "senhor")
    return re.sub(rf",\s*({re.escape(t)})\b", r" \1", texto, flags=re.I) if t else texto

def _sintetizar(texto):
    texto = _para_voz(texto)
    path = os.path.join(tempfile.gettempdir(), f"aton_fala_{next(_N_FALA)}.mp3")
    # respostas sobre e-mail/WhatsApp: com "voz_offline_privado", fala com a voz do Windows (sem internet), para o
    # conteúdo não ir ao serviço online de voz
    if CFG.get("voz_offline_privado", False) and getattr(globals().get("CER"), "privado", False):
        path = path[:-4] + ".wav"; _tts_offline(texto, path)
        return _com_efeito(path)
    try:
        asyncio.run(edge_tts.Communicate(texto, CFG["voz"], rate=CFG["velocidade_voz"], pitch=CFG.get("tom_voz", "+0Hz")).save(path))
    except Exception as e:
        log.warning("edge-tts falhou (%r); usando a voz offline do Windows.", e)
        path = path[:-4] + ".wav"
        _tts_offline(texto, path)
    return _com_efeito(path)

def _com_efeito(path):
    """Aplica o efeito "IA de filme" (efeito_voz: leve, medio, forte); vazio = voz pura. Leva ~70 ms."""
    nivel = CFG.get("efeito_voz") or ""
    if not nivel: return path
    try:
        import soundfile as sf, efeito_voz
        x, sr = sf.read(path, dtype="float32")
        saida = os.path.splitext(path)[0] + "_fx.wav"
        sf.write(saida, efeito_voz.aplicar(x, sr, nivel), sr)
        try: os.remove(path)
        except OSError: pass
        return saida
    except Exception as e:
        log.warning("Efeito de voz falhou (%r); usando a voz pura.", e)
        return path

class Falante:
    """Fala frase por frase: enquanto uma frase toca, a próxima já está sendo gerada."""
    def __init__(self, interrompivel=False):
        self.textos, self.audios, self.dito, self.n_trat = queue.Queue(), queue.Queue(), [], 0
        if interrompivel and CFG.get("interromper_por_voz", True) and CFG["ativacao_por_voz"]: FALANDO.set()
        self.t1 = threading.Thread(target=self._gerar, daemon=True); self.t1.start()
        self.t2 = threading.Thread(target=self._tocar, daemon=True); self.t2.start()

    def dizer(self, frase):
        self.textos.put(frase)

    def _limitar(self, f):
        """No máximo um "senhor" por resposta: as repetições ("..., senhor." / "Senhor, ...") são tiradas."""
        t = CFG.get("tratamento")
        if not t: return f
        def tirar(m):
            self.n_trat += 1
            return m.group(0) if self.n_trat == 1 else ""
        f = re.sub(rf"(,\s*{re.escape(t)}\b|^\s*{re.escape(t)}\s*,\s*)", tirar, f, flags=re.I).strip()
        return f[:1].upper() + f[1:]

    def _gerar(self):
        while True:
            f = self.textos.get()
            if f is None:
                self.audios.put(None); return
            if STOP.is_set(): continue
            f = self._limitar(f)
            if not CFG.get("respostas_por_voz", True):       # modo silencioso: a resposta só aparece escrita
                self.audios.put((f, None)); continue
            try: self.audios.put((f, _sintetizar(f)))
            except Exception: log.exception("Falha ao gerar a voz")

    def _tocar(self):
        while True:
            item = self.audios.get()
            if item is None: return
            f, path = item
            if path is None:                                  # modo silencioso: só mostra o texto
                if not STOP.is_set():
                    self.dito.append(f); send("speaking", reply=" ".join(self.dito)); time.sleep(0.3)
                continue
            if not STOP.is_set():
                self.dito.append(f)
                send("speaking", reply=" ".join(self.dito))
                mixer_na_saida_atual()
                pygame.mixer.music.load(path); pygame.mixer.music.play()
                while pygame.mixer.music.get_busy() and not STOP.is_set():
                    time.sleep(0.03)
                pygame.mixer.music.stop(); pygame.mixer.music.unload()
            try: os.remove(path)
            except OSError: pass

    def terminar(self):
        self.textos.put(None); self.t1.join(); self.t2.join()
        FALANDO.clear()

def speak(text, interrompivel=False):
    f = Falante(interrompivel); f.dizer(text); f.terminar()

# Ferramentas que FAZEM algo (comando): depois delas o Aton para de ouvir. As demais só informam (pergunta).
ACOES = {"musica", "volume", "volume_app", "bluetooth", "tocar_video", "volume_nivel", "abrir_site", "pesquisar_em", "abrir_programa", "spotify_tocar", "spotify_fila", "spotify_curtir", "spotify_aleatorio",
         "agendar", "desmarcar", "remarcar", "criar_lembrete", "cancelar_lembrete", "criar_monitor", "cancelar_monitor",
         "minimizar_tudo", "captura_de_tela", "digitar", "abrir_arquivo", "abrir_pasta",
         "executar_rotina", "janelas", "tarefa_segundo_plano", "abrir_relatorio", "chrome", "pagina", "computador"}

def _foi_comando(usadas):
    return any(n in ACOES and not (n == "musica" and str(a.get("acao", "")).startswith("o_que"))
               and not (n == "chrome" and a.get("acao") in ("abas", "ler_pagina", "quanto_falta"))
               and not (n in ("pagina", "computador") and a.get("acao") == "listar") for n, a in usadas)

ULTIMO_PEDIDO = {"texto": "", "t": 0.0}

def answer(text, fim=True):
    """Responde. Devolve True se foi um COMANDO (o modo conversa encerra) e False se foi uma PERGUNTA (continua ouvindo)."""
    log.info("Você: %s", text)
    send("thinking", user=text); t0 = time.time()
    # "não, eu falei HBO Max": aprende a troca e refaz o pedido anterior já corrigido
    corr = vocabulario.correcao(text) if ULTIMO_PEDIDO["texto"] and time.time() - ULTIMO_PEDIDO["t"] < 180 else None
    if corr:
        certo, errado = corr
        r = vocabulario.aprender(ULTIMO_PEDIDO["texto"], certo, errado)
        bracos.cancelar()                                  # um envio/ação preparado com o nome errado não vale mais
        if r:
            novo, trecho = r
            log.info("Correção aprendida: \"%s\" -> \"%s\". Refazendo: %s", trecho, certo, novo)
            speak(f"Entendi, {certo}. Vou lembrar.")
            ULTIMO_PEDIDO["texto"] = ""                    # não corrige a correção
            return answer(novo, fim)
        speak(f"Não sei qual palavra eu ouvi errado. Pode repetir o pedido inteiro, {CFG['tratamento']}?")
        if fim: send("idle")
        return False
    ULTIMO_PEDIDO.update(texto=text, t=time.time())
    if bracos.tem_pendente():      # havia uma ação esperando "confirma?": sim executa, qualquer outra coisa cancela
        t = ferramentas.norm(text)
        if CONFIRMA.match(t) or NEGA.match(t):
            reply = bracos.confirmar() if CONFIRMA.match(t) else bracos.cancelar()
            log.info("Resposta: %s", reply); MEM.adicionar_troca(text, reply); speak(reply)
            enviar_painel()
            if fim: send("idle")
            return True                # confirmou ou cancelou: a ação terminou
        bracos.cancelar(); log.info("Ação pendente cancelada (o usuário falou outra coisa).")
    pediu_claude = CER.pedido_claude(text) is not None    # "pergunta pro Claude se vai chover" vai para o Claude, não para o clima
    tool = ferramentas.executar(text, CFG) if CFG.get("ferramentas", True) and not pediu_claude else None
    if tool:                       # comando reconhecido (música, clima, apps...): responde na hora, sem passar pela IA
        reply, dep = tool
        MEM.adicionar_troca(text, reply)
        log.info("Resposta: %s", reply)
        speak(reply, interrompivel=True)
        depois = [dep] if dep else []
        comando = ferramentas.ULTIMO_TIPO == "comando"
    elif CFG.get("so_comandos") and not pediu_claude:
        # modo só comandos (como a Alexa): nada de IA; o que não está na lista não é entendido
        reply = f"Não conheço esse comando, {CFG['tratamento']}. Diga 'quais comandos você conhece' para ver a lista."
        log.info("Só comandos: não reconheci \"%s\"", text)
        MEM.adicionar_troca(text, reply); speak(reply)
        depois, comando = [], True
    else:
        ensure_ollama()
        fal, avisou = Falante(interrompivel=True), []
        def ao_agir(nome):         # pesquisa demora alguns segundos: avisa na hora, como a Siri
            if nome == "pesquisar_web" and not avisou:
                avisou.append(1); fal.dizer("Só um instante, vou pesquisar.")
        reply, depois = CER.responder(text, fal.dizer, ao_agir)
        fal.terminar()
        comando = _foi_comando(CER.usadas)
        if CFG.get("memoria_automatica", True) and not CER.privado:   # depois de falar, em segundo plano (e-mail: nunca)
            threading.Thread(target=CER.extrair_fatos, args=(text, reply), daemon=True).start()
    if INTERRUPCAO["pedido"] is not None: depois = []   # interrompido: não executa o que viria depois da fala
    for d in depois: d()           # ex.: dar play só depois de falar, para a voz não brigar com a música
    enviar_painel()                # a resposta pode ter marcado/desmarcado algo: atualiza os cartões
    if fim: send("idle")
    if time.time() - t0 > 20:      # tarefa longa (ex.: Claude Code): avisa no celular também
        notificar_celular(f"Terminei: {reply[:160]}")
    if bracos.tem_pendente(): return False             # perguntou "confirma?": continua ouvindo para o "sim"
    if reply and reply.rstrip(" .…\"'").endswith("?"):
        log.info("O Aton fez uma pergunta: continua ouvindo."); return False
    if CFG.get("ouvir_apos_comando", False): return bool(depois)
    if comando or depois: log.info("Comando executado: encerrando a escuta.")
    return comando or bool(depois)

# ------------------------------------------------------------------ modo conversa
# Depois de responder, o Aton escuta mais alguns segundos sem precisar dizer "Aton" de novo.
DESPEDIDA = re.compile(r"^(e )?(obrigad[oa]|muito obrigad[oa]|valeu|so isso|e so isso|era so isso|pode parar|pode encerrar|encerra|"
                       r"tchau|ate mais|ate logo|nada|nao|nao obrigad[oa]|ta bom|ta bom obrigad[oa]|beleza|ok obrigad[oa]|"
                       r"nao preciso de mais nada|mais nada|por enquanto e so)( (aton|obrigad[oa]))*$")
ALUCINACOES = ("amara org", "inscreva se", "legendas pela", "legenda adriana")   # o Whisper "ouve" isso em ruído

def conversa(foi_comando):
    if INTERRUPCAO["pedido"] is None and (not CFG.get("modo_conversa", True) or foi_comando):
        send("idle"); return                      # comando executado: para de ouvir (pergunta: continua)
    for _ in range(CFG.get("max_turnos", 10)):
        pedido = INTERRUPCAO["pedido"]
        if pedido is not None:                    # você disse "Aton" enquanto ele falava
            INTERRUPCAO["pedido"] = None; STOP.clear()
            if pedido:                            # "Aton, na verdade toca Queen": atende direto
                r = answer(pedido, fim=False)
                if INTERRUPCAO["pedido"] is None and r: break
                continue
            som("ativacao")                       # só "Aton": ouve o novo pedido
        else:
            if STOP.is_set(): break
            if CFG.get("bipe_continuar", True): som("continuar")
        send("listening")
        audio = record(espera=CFG.get("espera_continuar", 5))
        if audio is None or isinstance(audio, str) or STOP.is_set(): break
        send("thinking", user="...")
        text = transcribe(audio)
        t = ferramentas.norm(text)
        if not t or any(a in t for a in ALUCINACOES): break
        resto = wake_split(text)                 # falou "Aton, ..." de novo: tira o nome
        if resto: text = resto
        if DESPEDIDA.match(ferramentas.norm(text)) and not bracos.tem_pendente():   # "não" com ação pendente = cancelar
            log.info("Você: %s (encerrou a conversa)", text)
            send("thinking", user=text); speak(f"Às ordens, {CFG['tratamento']}."); break
        r = answer(text, fim=False)
        if INTERRUPCAO["pedido"] is None and r: break
    INTERRUPCAO["pedido"] = None
    send("idle")

def avisar(texto):
    """Aviso curto sem passar pela IA (ex.: microfone mudo)."""
    log.info("Aviso: %s", texto)
    if texto.startswith("Lembrete") or pausado(): notificar_celular(texto)
    send("idle", user="", reply=texto)
    if pausado(): return              # pausado: o aviso aparece escrito (wallpaper e celular), sem voz
    speak(texto)

# ------------------------------------------------------------------ saudação de abertura (pedida pelo wallpaper)
def saudar():
    n = datetime.datetime.now()
    cumprimento = "Bom dia" if 5 <= n.hour < 12 else "Boa tarde" if 12 <= n.hour < 18 else "Boa noite"
    # "São 2 horas" é ambíguo para a IA (14h?); o cumprimento vai pronto, calculado pelo relógio (24h)
    dados = {"cumprimento obrigatorio": cumprimento, "agora": f"{n:%H:%M} (formato 24h). " + ferramentas.data(CFG)}
    for nome, fn in (("clima", lambda: ferramentas.clima(CFG)), ("musica", lambda: ferramentas.tocando_agora(CFG))):
        try: dados[nome] = fn()
        except Exception as e: log.warning("Saudação: %s falhou (%r)", nome, e)
    fatos = MEM.texto_fatos()
    if fatos: dados["anotacoes do usuario"] = fatos
    try: dados["agenda de hoje"] = agenda.listar()
    except Exception as e: log.warning("Saudação: agenda falhou (%r)", e)
    log.info("Saudação de abertura")
    send("thinking", user="")
    fal = Falante()
    texto = CER.saudar("\n".join(f"{k}: {v}" for k, v in dados.items()), fal.dizer) if CFG.get("saudacao_ia", True) else None
    if not texto:                  # sem nuvem: texto pronto, só com dados locais e o clima
        texto = f"{cumprimento}, {CFG['tratamento']}. {dados['agora']}" + (f" {dados['clima']}" if "clima" in dados else "")
        fal.dizer(texto)
    fal.terminar()
    log.info("Saudação: %s", texto)
    send("idle")

def _rodar_rotina(nome):
    res, depois = bracos.executar_rotina(nome, CFG, lambda n, a: ferramentas.chamar(n, a, CFG, MEM))
    for d in depois:
        try: d()
        except Exception: log.exception("Rotina: passo falhou")
    return f"Rotina {nome} ativada." if not res.startswith("Não existe") else res

def lembretes_loop():
    """Avisa lembretes na hora e checa os monitores a cada minuto (espera o Aton terminar o que estiver fazendo)."""
    proximo_monitor = 0.0
    while True:
        time.sleep(5)
        if TRAVADO.is_set(): continue       # bloqueado: lembretes esperam (não se perdem) e saem depois da senha
        try:
            for l in bracos.lembretes_vencidos():
                with BUSY:
                    STOP.clear(); som("lembrete")
                    avisar(f"Lembrete, {CFG['tratamento']}: {l['texto']}")
            if time.time() >= proximo_monitor:
                proximo_monitor = time.time() + 60
                for a in agenda.avisos_pendentes():        # compromisso chegando (ex.: 15 min antes)
                    with BUSY:
                        STOP.clear(); som("lembrete")
                        avisar(f"Compromisso: {a}")
                atualizar_emails()                         # e-mails novos para os cartões (rede, fora do BUSY)
                enviar_painel()                            # tira dos cartões o que já passou
                avisos, resumo = monitores.verificar()     # rede (cotações/notícias): fora do BUSY
                for a in avisos:
                    with BUSY:
                        STOP.clear(); som("lembrete"); avisar(a)
                if resumo:
                    with BUSY:
                        STOP.clear(); saudar()
                for texto, rotina in ([] if pausado() else extras.checar_proatividade(CFG, CFG["tratamento"])):
                    with BUSY:
                        STOP.clear(); som("lembrete")
                        if rotina and rotina.startswith("!"):          # rotina marcada para rodar sem perguntar
                            avisar(texto); _rodar_rotina(rotina[1:])
                        elif rotina:                                   # pergunta e escuta o "sim"
                            bracos.preparar(f"ativar a rotina {rotina}", lambda r=rotina: _rodar_rotina(r))
                            avisar(texto); conversa(False)
                        else:
                            avisar(texto)
            for texto, arq in extras.tarefas_prontas():                # tarefa em segundo plano terminou
                notificar_celular(texto)
                with BUSY:
                    STOP.clear(); som("lembrete"); avisar(texto)
        except Exception:
            log.exception("Erro nos lembretes/monitores")

def saudacao_loop():
    ultima = 0.0
    while True:
        INTRO.wait(); INTRO.clear()
        if TRAVADO.is_set() and SAUDOU.is_set():      # Win+L depois de já ter saudado: abertura descartada
            esperar_desbloqueio(); continue           # (ao ligar o PC ele saúda mesmo na tela de senha)
        if time.time() - ultima < 90: continue        # dois wallpapers (ou recarga rápida) não saúdam duas vezes
        if pausado(): log.info("Saudação pulada: Aton pausado."); continue
        if not BUSY.acquire(blocking=False): continue
        ultima = time.time(); STOP.clear(); SAUDOU.set()
        try: saudar()
        except Exception: log.exception("Erro na saudação")
        finally: BUSY.release()

def session(cmd=None):
    if CFG.get("abaixar_fundo", True):      # Spotify/YouTube/jogos descem enquanto você fala com o Aton
        try: fundo.abaixar(CFG.get("nivel_fundo", 0.25))
        except Exception: log.exception("Abaixar o som de fundo")
    try:
        # MUTED não é consultado aqui: ainda não foi confirmado se sala muito quieta também gera silêncio digital,
        # então o atalho sempre escuta e record() só declara "mudo" depois de 6 s sem nenhum sinal.
        warm_up()
        if cmd:                    # "Aton, <pergunta>" numa frase só: responde direto
            conversa(answer(cmd, fim=False)); return
        if STT["m"] is None:
            send("thinking", user="", reply="Carregando o modelo de voz, aguarde...")
            while STT["m"] is None: time.sleep(0.3)
        send("listening")
        audio = record(som_inicio="ativacao")
        if isinstance(audio, str):
            avisar(f"Microfone mudo, {CFG['tratamento']}."); return
        if audio is None:
            log.info("Nada foi ouvido.")
            send("idle", reply="Não ouvi nada."); return
        send("thinking", user="...")
        text = transcribe(audio)
        if not text:
            send("idle", reply="Não consegui entender."); return
        conversa(answer(text, fim=False))
    except SemMicrofone:
        avisar(f"O microfone {CFG['microfone']} não está conectado, {CFG['tratamento']}.")
    except Exception as e:
        log.exception("Erro na sessão")
        send("idle", reply="Ocorreu um erro: " + str(e)[:80])
    finally:
        try: fundo.restaurar()
        except Exception: log.exception("Restaurar o som de fundo")
        BUSY.release()

def start_session(cmd=None):
    if not BUSY.acquire(blocking=False): return False
    STOP.clear(); INTERRUPCAO["pedido"] = None
    threading.Thread(target=session, args=(cmd,), daemon=True).start()
    return True

# ------------------------------------------------------------------ pausar / retomar (sem fechar o Aton)
# O estado fica num arquivo: o atalho Ctrl+Alt+P, o botão "Aton - Pausar ou Retomar" da área de trabalho e o
# celular mexem no mesmo lugar, e a pausa continua valendo se o PC reiniciar. Pausado: não escuta "Aton",
# não fala avisos sozinho. O atalho de falar (Ctrl+Alt+Espaço) continua funcionando, porque é pedido seu.
PAUSA_ARQ = os.path.join(HERE, "pausado.flag")

def pausado():
    return os.path.exists(PAUSA_ARQ)

def alternar_pausa():
    if pausado():
        try: os.remove(PAUSA_ARQ)
        except OSError: pass
        log.info("Aton retomado: escutando de novo."); beep(880, 80); beep(1320, 80)
        send("idle", user="", reply="Escutando de novo.")
    else:
        open(PAUSA_ARQ, "w").write(time.strftime("%Y-%m-%d %H:%M"))
        STOP.set()                                  # corta o que ele estiver falando
        log.info("Aton pausado: não escuta nem fala sozinho."); beep(1320, 80); beep(660, 120)
        send("idle", user="", reply="Pausado. Ctrl+Alt+P para retomar.")

def vigia_pausa():
    """Avisa no log quando a pausa muda por fora (botão da área de trabalho)."""
    antes = pausado()
    if antes: log.info("Aton iniciou PAUSADO (botão de pausa ligado).")
    while True:
        time.sleep(1)
        agora = pausado()
        if agora != antes:
            log.info("Pausa %s pelo botão.", "ligada" if agora else "desligada")
            if agora: STOP.set(); beep(1320, 80); beep(660, 120)
            else: beep(880, 80); beep(1320, 80)
            send("idle", user="", reply="Pausado." if agora else "Escutando de novo.")
            antes = agora

def on_hotkey():
    if TRAVADO.is_set(): return         # PC bloqueado: atalho ignorado
    if not start_session():
        STOP.set()      # apertar de novo interrompe a fala

# ------------------------------------------------------------------ testes sem microfone
if ATIVACAO:
    STT["wake"] = whisper(CFG["modelo_ativacao"])
    text = transcribe(ATIVACAO, "wake")
    rest = wake_split(text)
    log.info("[ativação] %-45s -> %s", text, "NÃO" if rest is None else "SIM, comando: " + repr(rest))
    sys.exit(0)
if "--saudacao" in ARGS:
    time.sleep(1.5); saudar(); sys.exit(0)
if FRASE or ARQUIVO:
    time.sleep(1.5)     # dá tempo do wallpaper reconectar
    warm_up()
    try:
        if ARQUIVO:
            load_stt(); send("thinking", user="...")
            FRASE = transcribe(ARQUIVO)
        answer(FRASE)
    except Exception:
        log.exception("Erro no teste")
        sys.exit(1)
    sys.exit(0)

import keyboard
try:                               # prioridade acima do normal: escuta e fala sem engasgar com jogos/compilações abertos
    import psutil; psutil.Process().nice(psutil.ABOVE_NORMAL_PRIORITY_CLASS)
except Exception: pass
threading.Thread(target=load_stt, daemon=True).start()
threading.Thread(target=ensure_ollama, daemon=True).start()
threading.Thread(target=saudacao_loop, daemon=True).start()
threading.Thread(target=lembretes_loop, daemon=True).start()
REINICIO_AUDIO = [0.0]

def vigia_saida():
    """O Wallpaper Engine não acompanha a troca da saída de som (ex.: para o fone Bluetooth) e as ondas param.
    Quando a saída padrão muda, para e retoma o wallpaper, o que faz ele voltar a ouvir a música."""
    exe = CFG.get("wallpaper_exe") or r"C:\Program Files (x86)\Steam\steamapps\common\wallpaper_engine\wallpaper64.exe"
    if not CFG.get("reiniciar_wallpaper", True): return      # só faz sentido com o wallpaper do Aton
    ultima = saida_atual()
    while True:
        time.sleep(3)
        sid = saida_atual()
        if not sid or sid == ultima: continue
        ultima = sid; time.sleep(2)                      # deixa o Windows terminar de trocar
        if not os.path.isfile(exe): continue
        log.info("Saída de som mudou; reiniciando o áudio do wallpaper.")
        REINICIO_AUDIO[0] = time.time()
        for c in ("stop", "play"):
            subprocess.run([exe, "-control", c], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)); time.sleep(1.5)

threading.Thread(target=vigia_bloqueio, daemon=True).start()
threading.Thread(target=vigia_saida, daemon=True).start()

def saudacao_inicial():
    """Ao ligar o PC: se o wallpaper já desistiu de esperar o Aton (ele subiu depois), pede a abertura de novo
    e, sem wallpaper, saúda direto. Assim o Aton sempre fala quando o computador liga."""
    time.sleep(CFG.get("espera_saudacao_inicial", 2))
    if SAUDOU.is_set() or not CFG.get("saudar_ao_iniciar", True): return
    try:                                   # só logo depois de entrar no Windows (reiniciar só o Aton não saúda)
        import psutil
        ex = [p.info["create_time"] for p in psutil.process_iter(["name", "create_time"]) if (p.info["name"] or "").lower() == "explorer.exe"]
        if ex and time.time() - min(ex) > 300: return
    except Exception: pass
    # a abertura do wallpaper já rodou quando o Windows abriu: saúda direto (repetir a abertura deixava ela 2x)
    log.info("Saudação inicial."); INTRO.set()

threading.Thread(target=saudacao_inicial, daemon=True).start()
# ------------------------------------------------------------------ app do celular (aton_remote.py, via Tailscale)
def notificar_celular(texto):
    try:
        import aton_remote; aton_remote.notificar(texto)
    except Exception: pass

def remoto_processar(texto):
    """Pedido digitado ou falado no celular: o mesmo caminho da voz no PC, mas a resposta volta em texto."""
    if not BUSY.acquire(timeout=120): return "Estou ocupado com outro pedido no PC; tente de novo em instantes."
    t0 = time.time()
    try:
        log.info("Celular: %s", texto)
        send("thinking", user=texto)
        if bracos.tem_pendente():
            t = ferramentas.norm(texto)
            if CONFIRMA.match(t) or NEGA.match(t):
                reply = bracos.confirmar() if CONFIRMA.match(t) else bracos.cancelar()
                MEM.adicionar_troca(texto, reply); enviar_painel(); return reply
            bracos.cancelar()
        pediu_claude = CER.pedido_claude(texto) is not None
        tool = ferramentas.executar(texto, CFG) if CFG.get("ferramentas", True) and not pediu_claude else None
        if tool:
            reply, dep = tool; depois = [dep] if dep else []
        elif CFG.get("so_comandos") and not pediu_claude:
            reply, depois = "Não conheço esse comando (modo só comandos).", []
        else:
            ensure_ollama()
            reply, depois = CER.responder(texto, lambda f: None)
            if CFG.get("memoria_automatica", True) and not CER.privado:
                threading.Thread(target=CER.extrair_fatos, args=(texto, reply), daemon=True).start()
        MEM.adicionar_troca(texto, reply)
        for d in depois: d()
        enviar_painel()
        log.info("Resposta (celular): %s", reply)
        return reply
    except Exception as e:
        log.exception("Erro no pedido do celular"); return f"Não consegui concluir: {e}"
    finally:
        send("idle"); BUSY.release()
        if time.time() - t0 > 20: notificar_celular("Pronto: terminei o pedido \"" + texto[:60] + "\".")

def remoto_stt(dados, mime):
    """Áudio do iPhone (m4a/mp4) -> texto, com o mesmo Whisper do Aton (o PyAV decodifica, sem ffmpeg)."""
    import io, av
    with av.open(io.BytesIO(dados)) as c:
        r = av.AudioResampler(format="flt", layout="mono", rate=16000)
        partes = [f.to_ndarray().ravel() for p in c.decode(audio=0) for f in r.resample(p)]
        partes += [f.to_ndarray().ravel() for f in r.resample(None)]
    audio = np.concatenate(partes).astype(np.float32) if partes else np.zeros(0, np.float32)
    if len(audio) < 1600 or STT.get("m") is None: return ""
    texto = transcribe(audio)
    log.info("Celular (voz): %s", texto)
    return texto

def remoto_tts(texto):
    path = _sintetizar(texto)
    try:
        with open(path, "rb") as f: dados = f.read()
    finally:
        try: os.remove(path)
        except OSError: pass
    return dados, ("audio/wav" if path.endswith(".wav") else "audio/mpeg")

def iniciar_remoto():
    try:
        import aton_remote
        aton_remote.HOOKS.update(processar=remoto_processar, stt=remoto_stt, tts=remoto_tts)
        log.info("App do celular em http://127.0.0.1:%d", aton_remote.PORTA)
        aton_remote.iniciar()
    except Exception:
        log.exception("Servidor do app do celular não iniciou")

if CFG.get("app_celular", True):
    threading.Thread(target=iniciar_remoto, daemon=True).start()

if CFG.get("ponte_chrome", True):          # extensão do Aton no Chrome (ws://127.0.0.1:8767)
    import chrome_ponte; chrome_ponte.iniciar()
import navegador; navegador.VIA["via"] = CFG.get("whatsapp_via", "app")   # WhatsApp: "app" (aplicativo) ou "web" (Chrome)

if CFG["ativacao_por_voz"]:
    threading.Thread(target=wake_listener, daemon=True).start()
import scripts_aton; scripts_aton.FALAR[0] = speak          # o passo "falar" dos seus comandos usa a voz do Aton
keyboard.add_hotkey(CFG["hotkey"], on_hotkey)
keyboard.add_hotkey(CFG.get("hotkey_pausa", "ctrl+alt+p"), alternar_pausa)
threading.Thread(target=vigia_pausa, daemon=True).start()
log.info("Assistente ativo (IA: %s). Atalho: %s", " -> ".join(CER.modelos()), CFG["hotkey"])
keyboard.wait()
