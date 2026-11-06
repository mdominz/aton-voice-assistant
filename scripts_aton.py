# -*- coding: utf-8 -*-
r"""
Seus comandos pré-programados (como as Rotinas da Alexa / Atalhos da Siri), escritos em meus_comandos.txt:

    [modo cinema]
    frases: modo cinema; hora do filme
    abrir HBO Max
    esperar 3
    teclas F11
    volume 40
    falar Bom filme, senhor.

Cada linha depois de "frases:" é um passo, executado em ordem. Passos possíveis (veja LISTA_DE_COMANDOS.html):
  abrir <programa ou site>   site <nome ou endereço>   esperar <segundos>   teclas <combinação>
  clicar <texto do botão>    digitar <texto>           falar <texto>        volume <0-100>
  volume <app> <0-100>       musica <tocar|pausar|proxima|anterior>         spotify <playlist/artista/música>
  pausar_escuta              comando <qualquer frase que o Aton entende, ex.: comando fecha a guia>
O arquivo é relido sozinho quando você salva (não precisa reiniciar o Aton).
"""
import logging, os, re, threading, time, unicodedata

log = logging.getLogger("aton")
HERE = os.path.dirname(os.path.abspath(__file__))
ARQ = os.path.join(HERE, "meus_comandos.txt")
_CACHE = {"mtime": None, "scripts": {}, "erros": []}
FALAR = [None]          # o assistente põe aqui a função de falar


def _n(t):
    t = unicodedata.normalize("NFD", (t or "").lower())
    return re.sub(r"\s+", " ", re.sub(r"[^\w ]+", " ", "".join(c for c in t if unicodedata.category(c) != "Mn"))).strip()


def carregar():
    """{frase normalizada: (nome, [passos])}. Relê o arquivo quando ele muda."""
    try: mt = os.path.getmtime(ARQ)
    except OSError: return {}
    if mt == _CACHE["mtime"]: return _CACHE["scripts"]
    scripts, erros, nome, frases, passos = {}, [], None, [], []
    def fechar():
        if nome:
            for f in (frases or [nome]):
                if _n(f): scripts[_n(f)] = (nome, list(passos))
    with open(ARQ, encoding="utf-8-sig") as f:
        for i, linha in enumerate(f, 1):
            l = linha.strip()
            if not l or l.startswith("#"): continue
            m = re.match(r"^\[(.+)\]$", l)
            if m:
                fechar(); nome, frases, passos = m.group(1).strip(), [], []; continue
            if nome is None: continue
            if l.lower().startswith("frases:"):
                frases = [x.strip() for x in l.split(":", 1)[1].split(";") if x.strip()]; continue
            l = re.sub(r"^\d+[.)-]\s*", "", l)                     # aceita "1. abrir ..." numerado
            acao, _, arg = l.partition(" ")
            acao = _n(acao)
            if acao not in PASSOS: erros.append(f"linha {i}: passo desconhecido '{acao}'"); continue
            passos.append((acao, arg.strip()))
    fechar()
    _CACHE.update(mtime=mt, scripts=scripts, erros=erros)
    if erros: log.warning("meus_comandos.txt: %s", "; ".join(erros))
    log.info("Comandos pré-programados carregados: %d frases.", len(scripts))
    return scripts


def achar(texto):
    """O script cuja frase é exatamente o que foi dito (sem "Aton", "por favor"...), ou None."""
    t = _n(texto)
    t = re.sub(r"^(?:aton|ei aton|oi aton)\s+", "", t)
    t = re.sub(r"\s+(?:por favor|agora|ai)$", "", t).strip()
    return carregar().get(t)


# ------------------------------------------------------------------ passos
def _p_abrir(cfg, a):
    import ferramentas
    r = ferramentas.abrir(cfg, a)
    if r and r[1]: r[1]()
    return bool(r)

def _p_site(cfg, a):
    import ferramentas
    r = ferramentas.abrir_site(cfg, a, qualquer=True)
    if r and r[1]: r[1]()
    return bool(r)

def _p_esperar(cfg, a):
    try: time.sleep(min(60.0, float(a.replace(",", ".") or 1)))
    except ValueError: time.sleep(1)
    return True

def _p_teclas(cfg, a):
    import desktop
    t = desktop.teclas_faladas(_n(a)) or a.lower().replace(" ", "")
    desktop.apertar(t); return True

def _p_clicar(cfg, a):
    import desktop
    return not desktop.clicar(a).startswith(("Não", "O botão"))   # botão perigoso não é clicado por script

def _p_digitar(cfg, a):
    import keyboard
    time.sleep(0.2); keyboard.write(a, delay=0.01); return True

def _p_falar(cfg, a):
    if FALAR[0]: FALAR[0](a)
    return True

def _p_volume(cfg, a):
    import ferramentas
    m = re.match(r"^(.*?)\s*(\d{1,3})$", a.strip())
    if not m: return False
    app, n = m.group(1).strip(), int(m.group(2))
    if app: ferramentas.volume_app(cfg, app, "definir", n)
    else: ferramentas.volume_nivel(cfg, n)
    return True

def _p_musica(cfg, a):
    import ferramentas
    r = ferramentas.musica(cfg, _n(a) or "tocar")
    if r and r[1]: r[1]()
    return True

def _p_spotify(cfg, a):
    import spotify
    spotify.tocar(a, "auto"); return True

def _p_pausar_escuta(cfg, a):
    open(os.path.join(HERE, "pausado.flag"), "w").write("script"); return True

def _p_comando(cfg, a):
    import ferramentas
    r = ferramentas.executar(a, cfg)
    if r and r[1]: r[1]()
    return r is not None

PASSOS = {"abrir": _p_abrir, "site": _p_site, "esperar": _p_esperar, "teclas": _p_teclas, "clicar": _p_clicar,
          "digitar": _p_digitar, "falar": _p_falar, "volume": _p_volume, "musica": _p_musica, "spotify": _p_spotify,
          "pausar_escuta": _p_pausar_escuta, "pausar": _p_pausar_escuta, "comando": _p_comando}


def executar(nome, passos, cfg):
    """Roda os passos em ordem; um passo que falha não para os outros (fica no log)."""
    log.info("Comando pré-programado: %s (%d passos)", nome, len(passos))
    for acao, arg in passos:
        try:
            ok = PASSOS[acao](cfg, arg)
            if not ok: log.warning("  passo '%s %s' não deu certo", acao, arg)
        except Exception as e:
            log.warning("  passo '%s %s' falhou: %r", acao, arg, e)
        time.sleep(0.15)


def regra(texto, cfg):
    """Para o roteador do Aton: (resposta, ação depois da fala) ou None."""
    s = achar(texto)
    if not s: return None
    nome, passos = s
    if passos and passos[0][0] == "falar":          # a 1ª fala do script vira a resposta (sem falar duas vezes)
        resposta, passos = passos[0][1], passos[1:]
    else:
        resposta = f"{nome[:1].upper() + nome[1:]}."
    return resposta, ((lambda: executar(nome, passos, cfg)) if passos else None)


def listar():
    sc = carregar()
    nomes = sorted({n for n, _ in sc.values()})
    return nomes
