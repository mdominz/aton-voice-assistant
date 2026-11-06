# -*- coding: utf-8 -*-
"""
Monitores do Aton (ideia dos agentes agendados do OpenJarvis): ficam checando em segundo plano e avisam por voz.
- cotacao: dólar, euro ou bitcoin acima/abaixo de um valor (Frankfurter e CoinGecko, as mesmas fontes do wallpaper)
- noticia: avisa quando sair notícia nova sobre um termo (DuckDuckGo Notícias)
- resumo: resumo falado todo dia num horário (data, clima, música, lembretes do dia)
Guardados em monitores.json, valem depois de reiniciar o PC.
"""
import datetime, json, logging, os, threading, time, unicodedata, urllib.request, uuid

log = logging.getLogger("aton")
HERE = os.path.dirname(os.path.abspath(__file__))
ARQ = os.path.join(HERE, "monitores.json")
_LOCK = threading.Lock()
INTERVALO = {"cotacao": 600, "noticia": 1800}     # segundos entre checagens

def _norm(t):
    t = unicodedata.normalize("NFD", (t or "").lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn").strip()

def _ler():
    try:
        with open(ARQ, encoding="utf-8") as f: return json.load(f)
    except (FileNotFoundError, ValueError):
        return []

def _gravar(lst):
    tmp = ARQ + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f: json.dump(lst, f, ensure_ascii=False, indent=1)
    os.replace(tmp, ARQ)

def _jget(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "AI-Core-Assistente"}), timeout=10) as r:
        return json.loads(r.read().decode("utf-8"))

ATIVOS = {"dolar": "USD", "euro": "EUR", "bitcoin": "BTC"}

def cotacao(ativo):
    """Preço em reais. Dólar e euro: Frankfurter (BCE); bitcoin: CoinGecko."""
    a = ATIVOS.get(_norm(ativo).replace(" ", ""))
    if a == "BTC":
        return float(_jget("https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=brl")["bitcoin"]["brl"])
    if a:
        return float(_jget(f"https://api.frankfurter.app/latest?from={a}&to=BRL")["rates"]["BRL"])
    raise ValueError(f"ativo desconhecido: {ativo}")

def criar(tipo, alvo="", condicao="", valor=None, horario=""):
    tipo = _norm(tipo)
    m = {"id": uuid.uuid4().hex[:6], "tipo": tipo, "criado": datetime.datetime.now().isoformat(timespec="seconds"), "ultima": 0}
    if tipo == "cotacao":
        if _norm(alvo).replace(" ", "") not in ATIVOS: return "Só monitoro dólar, euro e bitcoin."
        if _norm(condicao) not in ("acima", "abaixo") or valor in (None, ""): return "Diga se é acima ou abaixo e de qual valor."
        try: atual = cotacao(alvo)
        except Exception as e: return f"Não consegui consultar a cotação agora: {e}"
        m.update(alvo=_norm(alvo), condicao=_norm(condicao), valor=float(valor))
        desc = f"{alvo} {condicao} de R$ {float(valor):.2f} (agora está em R$ {atual:.2f})"
    elif tipo == "noticia":
        if not alvo: return "Diga o assunto das notícias."
        m.update(alvo=alvo, vistos=[])
        try: m["vistos"] = [n["url"] for n in _noticias(alvo)]      # o que já saiu não conta como novidade
        except Exception: pass
        desc = f"notícias novas sobre {alvo} (checo a cada 30 minutos)"
    elif tipo == "resumo":
        try: h, mi = [int(x) for x in str(horario).replace("h", ":").split(":")[:2]] if ":" in str(horario).replace("h", ":") else (int(horario), 0)
        except ValueError: return "Horário inválido; use HH:MM."
        m.update(horario=f"{h % 24:02d}:{mi:02d}", ultimo_dia="")
        desc = f"resumo falado todo dia às {m['horario']}"
    else:
        return "Tipos de monitor: cotacao, noticia ou resumo."
    m["descricao"] = desc
    with _LOCK:
        lst = _ler(); lst.append(m); _gravar(lst)
    return f"Monitor criado: {desc}."

def listar():
    lst = _ler()
    return ("Monitores ativos: " + "; ".join(m["descricao"] for m in lst)) if lst else "Nenhum monitor ativo."

def cancelar(trecho):
    t = _norm(trecho)
    with _LOCK:
        lst = _ler(); resto = [m for m in lst if t not in _norm(m["descricao"])]
        _gravar(resto)
    n = len(lst) - len(resto)
    return f"{n} monitor(es) cancelado(s)." if n else "Não achei monitor com esse texto."

def _noticias(termo, n=5):
    from ddgs import DDGS
    return DDGS(timeout=8).news(termo, region="br-pt", max_results=n) or []

def verificar():
    """Chamada a cada minuto. Devolve (avisos para falar, precisa_resumo)."""
    agora, avisos, resumo = time.time(), [], False
    with _LOCK:
        lst = _ler(); mudou = False
        for m in list(lst):
            try:
                if m["tipo"] == "resumo":
                    dt = datetime.datetime.now()
                    if dt.strftime("%H:%M") >= m["horario"] and m.get("ultimo_dia") != dt.date().isoformat() \
                            and dt.strftime("%H:%M") < (datetime.datetime.strptime(m["horario"], "%H:%M") + datetime.timedelta(minutes=30)).strftime("%H:%M"):
                        m["ultimo_dia"] = dt.date().isoformat(); resumo = True; mudou = True
                    continue
                if agora - m.get("ultima", 0) < INTERVALO[m["tipo"]]: continue
                m["ultima"] = agora; mudou = True
                if m["tipo"] == "cotacao":
                    v = cotacao(m["alvo"])
                    if (m["condicao"] == "acima" and v > m["valor"]) or (m["condicao"] == "abaixo" and v < m["valor"]):
                        nome = {"dolar": "dólar", "euro": "euro", "bitcoin": "bitcoin"}.get(m["alvo"], m["alvo"])
                        avisos.append(f"Atenção: o {nome} está em R$ {v:.2f}, {m['condicao']} de R$ {m['valor']:.2f}.")
                        lst.remove(m)                       # avisa uma vez e encerra
                elif m["tipo"] == "noticia":
                    novas = [x for x in _noticias(m["alvo"]) if x.get("url") not in m["vistos"]]
                    if novas:
                        avisos.append(f"Notícia nova sobre {m['alvo']}: {novas[0].get('title', '').strip()}. Fonte: {novas[0].get('source', 'DuckDuckGo')}.")
                        m["vistos"] = (m["vistos"] + [x.get("url") for x in novas])[-50:]
            except Exception as e:
                log.warning("Monitor %s falhou: %r", m.get("descricao"), e)
        if mudou: _gravar(lst)
    return avisos, resumo
