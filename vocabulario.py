# -*- coding: utf-8 -*-
"""
Vocabulário do Aton: nomes que o Whisper deve reconhecer de primeira e correções que ele aprende com você.

- hotwords(): os nomes que você mais usa (contatos vistos no WhatsApp, os seus em "vocabulario" no config.json,
  os aprendidos por correção e marcas comuns) viram "dica" para o Whisper.
- corrigir(texto): troca o que ele costuma ouvir errado pelo certo (ex.: "de Biomax" -> "HBO Max").
- correcao(texto) + aprender(anterior, certo): "não, eu falei HBO Max" logo depois de um pedido mal ouvido
  ensina a troca e refaz o pedido corrigido.
Tudo fica só neste PC, em vocabulario_aprendido.json.
"""
import difflib, json, os, re, threading, unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
ARQ = os.path.join(HERE, "vocabulario_aprendido.json")
_LOCK = threading.Lock()
MARCAS = ["HBO Max", "Netflix", "Prime Video", "Disney", "Globoplay", "Crunchyroll", "YouTube", "Spotify", "WhatsApp",
          "Discord", "Chrome", "Steam", "League of Legends", "Valorant", "Battle.net", "Twitch"]
VAZIAS = {"o", "a", "os", "as", "de", "da", "do", "das", "dos", "e", "um", "uma", "no", "na", "pra", "pro", "para", "com", "em",
          "que", "eu", "me", "ai", "aí", "abre", "abra", "abrir", "toca", "manda", "coloca", "aton"}


def _n(t):
    t = unicodedata.normalize("NFD", (t or "").lower())
    return re.sub(r"\s+", " ", re.sub(r"[^\w ]+", " ", "".join(c for c in t if unicodedata.category(c) != "Mn"))).strip()


def _ler():
    try:
        with open(ARQ, encoding="utf-8") as f: d = json.load(f)
    except (OSError, ValueError):
        d = {}
    d.setdefault("correcoes", {}); d.setdefault("nomes", [])
    return d


def _gravar(d):
    tmp = ARQ + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f: json.dump(d, f, ensure_ascii=False, indent=1)
    os.replace(tmp, ARQ)


_CACHE = {"dados": None, "cfg_vocab": []}


def _dados():
    if _CACHE["dados"] is None: _CACHE["dados"] = _ler()
    return _CACHE["dados"]


def configurar(cfg):
    _CACHE["cfg_vocab"] = [str(x) for x in (cfg.get("vocabulario") or [])]


def adicionar_nomes(nomes):
    """Guarda nomes vistos (contatos do WhatsApp etc.): os 40 mais recentes viram dica para o Whisper."""
    nomes = [x.strip() for x in nomes if x and 2 <= len(x.strip()) <= 40 and not x.strip().startswith(("+", "@"))]
    if not nomes: return
    with _LOCK:
        d = _dados()
        lista = [x for x in d["nomes"] if x not in nomes]
        d["nomes"] = (nomes + lista)[:40]
        _gravar(d)


def hotwords(nome="Aton"):
    d = _dados()
    vistos, out = set(), []
    for x in [nome, "Claude"] + _CACHE["cfg_vocab"] + list(d["correcoes"].values()) + d["nomes"][:25] + MARCAS:
        k = _n(x)
        if k and k not in vistos:
            vistos.add(k); out.append(x)
    return " ".join(out[:60])


def corrigir(texto):
    """Aplica as correções aprendidas (palavras inteiras, sem ligar para acento ou maiúscula)."""
    corr = _dados()["correcoes"]
    if not corr or not texto: return texto
    palavras = texto.split()
    norm = [_n(p) for p in palavras]
    for errado, certo in sorted(corr.items(), key=lambda kv: -len(kv[0].split())):
        e = errado.split()
        i = 0
        while i + len(e) <= len(norm):
            if norm[i:i + len(e)] == e:
                pont = re.search(r"[,.!?;:]+$", palavras[i + len(e) - 1])
                palavras[i:i + len(e)] = [certo + (pont.group(0) if pont else "")]
                norm[i:i + len(e)] = [_n(certo)]
                i += 1
            else:
                i += 1
    return " ".join(palavras)


# "não, eu falei HBO Max" / "eu disse HBO Max, não Biomax" / "não é Biomax, é HBO Max" / "errado, é HBO Max"
_PADROES = [
    re.compile(r"^(?:aton )?nao,? (?:eu )?(?:falei|disse|pedi|quis dizer|tinha dito) (?P<certo>.+)$"),
    re.compile(r"^(?:aton )?(?:eu )?(?:falei|disse|quis dizer) (?P<certo>.+?),? (?:e )?nao (?P<errado>.+)$"),
    re.compile(r"^(?:aton )?nao e (?P<errado>.+?),? e (?P<certo>.+)$"),
    re.compile(r"^(?:aton )?(?:errado|esta errado|ta errado|entendeu errado|ouviu errado),? (?:e |eu falei |eu disse )?(?P<certo>.+)$"),
]


def correcao(texto):
    """Se a fala é uma correção, devolve (certo_original, errado_normalizado ou None)."""
    t = _n(texto)
    for p in _PADROES:
        m = p.match(t)
        if m:
            # recupera o "certo" com a grafia original (maiúsculas/acentos) a partir da fala
            certo_n = m.group("certo").strip()
            palavras = texto.split()
            cand = [" ".join(palavras[i:j]) for i in range(len(palavras)) for j in range(i + 1, len(palavras) + 1)]
            certo = next((c.strip(" ,.!?") for c in cand if _n(c) == certo_n), certo_n)
            errado = m.groupdict().get("errado")
            return certo, (errado.strip() if errado else None)
    return None


def aprender(anterior, certo, errado=None):
    """Acha no pedido anterior o trecho que foi ouvido errado (o mais parecido com o certo), guarda a troca e
    devolve (pedido_corrigido, trecho_errado), ou None se não der para saber o que trocar."""
    pal = anterior.split()
    norm = [_n(p) for p in pal]
    alvo = _n(certo).replace(" ", "")
    melhor, ini, fim = 0.0, 0, 0
    if errado:
        e = errado.split()
        for i in range(len(norm) - len(e) + 1):
            if norm[i:i + len(e)] == e: melhor, ini, fim = 1.0, i, i + len(e); break
    if melhor == 0:
        n_cert = max(1, len(certo.split()))
        cands = []
        for tam in range(1, min(len(pal), n_cert + 2) + 1):
            for i in range(len(pal) - tam + 1):
                trecho = norm[i:i + tam]
                if trecho[0] in VAZIAS or trecho[-1] in VAZIAS: continue      # não começa nem termina em "de", "o"...
                cands.append((round(difflib.SequenceMatcher(None, "".join(trecho), alvo).ratio(), 2), -abs(tam - n_cert), i, i + tam))
        if cands:
            melhor, _, ini, fim = max(cands)
    if melhor < 0.6: return None          # pouco parecido: melhor perguntar do que aprender errado
    errado_n = " ".join(norm[ini:fim])
    if errado_n == _n(certo) or len(errado_n.replace(" ", "")) < 3: return None
    corrigido = " ".join(pal[:ini] + [certo] + pal[fim:])
    with _LOCK:
        d = _dados()
        d["correcoes"][errado_n] = certo
        _gravar(d)
    return corrigido, errado_n


def esquecer(trecho):
    t = _n(trecho)
    with _LOCK:
        d = _dados()
        apagar = [k for k, v in d["correcoes"].items() if t and (t in k or t in _n(v))]
        for k in apagar: d["correcoes"].pop(k)
        _gravar(d)
    return len(apagar)


def parecido(nome, opcoes, corte=0.72):
    """O nome de opcoes mais parecido com o falado (para contatos), ou None."""
    n = _n(nome).replace(" ", "")
    if not n or not opcoes: return None
    melhores = sorted(((difflib.SequenceMatcher(None, n, _n(o).replace(" ", "")).ratio(), o) for o in opcoes), reverse=True)
    # também compara com o 1º nome ("Juão" ~ "João Silva")
    primeiro = sorted(((difflib.SequenceMatcher(None, n, _n(o).split()[0] if _n(o) else "").ratio(), o) for o in opcoes), reverse=True)
    s, o = max(melhores[0], primeiro[0])
    return o if s >= corte else None
