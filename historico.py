# -*- coding: utf-8 -*-
"""
Histórico pesquisável do Aton: cada pergunta e resposta vai para historico.jsonl (só neste PC, fora do GitHub).
Pedidos sobre e-mail e WhatsApp NÃO são gravados (quem chama decide). Serve para "o que eu te perguntei ontem sobre X?"
e para a tela de histórico do modo pesquisa.
"""
import datetime, json, os, re, threading, unicodedata

ARQ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "historico.jsonl")
_LOCK = threading.Lock()
MAX_LINHAS = 5000


def _n(t):
    t = unicodedata.normalize("NFD", (t or "").lower())
    return re.sub(r"[^a-z0-9 ]+", " ", "".join(c for c in t if unicodedata.category(c) != "Mn"))


def gravar(pergunta, resposta, origem="voz"):
    pergunta, resposta = (pergunta or "").strip(), (resposta or "").strip()
    if len(pergunta) < 3 or len(resposta) < 20: return          # "Pausado.", "Pronto." não interessam
    linha = json.dumps({"t": datetime.datetime.now().isoformat(timespec="seconds"), "p": pergunta[:500], "r": resposta[:3000],
                        "o": origem}, ensure_ascii=False)
    with _LOCK:
        with open(ARQ, "a", encoding="utf-8") as f: f.write(linha + "\n")
        try:
            if os.path.getsize(ARQ) > 6_000_000:               # corta os mais antigos de vez em quando
                with open(ARQ, encoding="utf-8") as f: linhas = f.readlines()[-MAX_LINHAS:]
                with open(ARQ, "w", encoding="utf-8") as f: f.writelines(linhas)
        except OSError:
            pass


def _ler():
    try:
        with _LOCK, open(ARQ, encoding="utf-8") as f: bruto = f.readlines()
    except FileNotFoundError:
        return []
    out = []
    for l in bruto:
        try: out.append(json.loads(l))
        except ValueError: pass
    return out


def recentes(n=30):
    return list(reversed(_ler()[-n:]))


def buscar(termos="", dias=None, n=8):
    """As trocas que mais combinam com os termos (as mais novas primeiro em caso de empate). dias = só os últimos N dias."""
    itens = _ler()
    if dias:
        corte = (datetime.datetime.now() - datetime.timedelta(days=int(dias))).isoformat()
        itens = [x for x in itens if x["t"] >= corte]
    pal = [w for w in _n(termos).split() if len(w) > 2 and w not in ("que", "sobre", "ontem", "hoje", "perguntei", "falei", "disse")]
    if not pal: return list(reversed(itens[-n:]))
    pont = []
    for i, x in enumerate(itens):
        tp, tr = _n(x["p"]), _n(x["r"])
        s = sum(2 if w in tp else 1 if w in tr else 0 for w in pal)
        if s: pont.append((s, i, x))
    pont.sort(key=lambda z: (z[0], z[1]), reverse=True)
    return [x for _, _, x in pont[:n]]


def para_ia(itens):
    if not itens: return "Não achei nada parecido no histórico de conversas."
    return "Do histórico de conversas com o usuário:\n" + "\n".join(
        f"- {x['t'][8:10]}/{x['t'][5:7]} às {x['t'][11:16]} — ele perguntou: \"{x['p'][:160]}\" — você respondeu: \"{x['r'][:260]}\"" for x in itens)
