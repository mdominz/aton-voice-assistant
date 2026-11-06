# -*- coding: utf-8 -*-
"""
Agenda do Aton: compromissos guardados no PC (agenda.json), com aviso falado antes de cada um.
Também monta o "painel" (próximos compromissos e lembretes) que o wallpaper mostra em cartões.
"""
import datetime, json, logging, os, re, threading, unicodedata, uuid

log = logging.getLogger("aton")
HERE = os.path.dirname(os.path.abspath(__file__))
ARQ = os.path.join(HERE, "agenda.json")
_LOCK = threading.Lock()
DIAS = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]

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

def _quando(data, horario):
    dia = datetime.date.fromisoformat(data) if data else datetime.date.today()
    m = re.match(r"(\d{1,2})[:h]?(\d{2})?", str(horario or "").strip())
    if not m: raise ValueError("horário inválido; use HH:MM")
    return datetime.datetime.combine(dia, datetime.time(int(m.group(1)) % 24, int(m.group(2) or 0)))

def falar_quando(dt):
    hoje = datetime.date.today()
    if dt.date() == hoje: d = "hoje"
    elif dt.date() == hoje + datetime.timedelta(days=1): d = "amanhã"
    elif 0 < (dt.date() - hoje).days < 7: d = DIAS[dt.weekday()] + ("-feira" if dt.weekday() < 5 else "")
    else: d = f"dia {dt.day}/{dt.month:02d}"
    return f"{d} às {dt:%H:%M}"

def agendar(titulo, data="", horario="", duracao_min=60, local="", avisar_antes_min=15):
    try: ini = _quando(data, horario)
    except ValueError as e: return f"Não entendi a data ou o horário ({e})."
    if ini < datetime.datetime.now() - datetime.timedelta(minutes=1):
        return f"Esse horário ({falar_quando(ini)}) já passou. Confirme a data."
    ev = {"id": uuid.uuid4().hex[:6], "titulo": titulo.strip(), "inicio": ini.isoformat(timespec="minutes"),
          "duracao_min": int(duracao_min or 60), "local": local or "", "avisar_antes_min": int(avisar_antes_min or 15), "avisado": False}
    with _LOCK:
        lst = _ler()
        conflito = [e for e in lst if abs((datetime.datetime.fromisoformat(e["inicio"]) - ini).total_seconds()) < 60 * max(30, ev["duracao_min"])]
        lst.append(ev); _gravar(lst)
    aviso = f" Atenção: já existe '{conflito[0]['titulo']}' perto desse horário." if conflito else ""
    return f"Marcado: {ev['titulo']} {falar_quando(ini)}" + (f", em {local}" if local else "") + \
           f". Aviso {ev['avisar_antes_min']} minutos antes.{aviso}"

def listar(dia="", dias=1):
    """Compromissos de um dia (AAAA-MM-DD; vazio = hoje) ou dos próximos `dias` dias."""
    ini = datetime.datetime.combine(datetime.date.fromisoformat(dia) if dia else datetime.date.today(), datetime.time())
    fim = ini + datetime.timedelta(days=max(1, int(dias or 1)))
    evs = sorted((e for e in _ler() if ini <= datetime.datetime.fromisoformat(e["inicio"]) < fim), key=lambda e: e["inicio"])
    if not evs: return "Nada marcado nesse período."
    return "; ".join(f"{falar_quando(datetime.datetime.fromisoformat(e['inicio']))}: {e['titulo']}" + (f" ({e['local']})" if e["local"] else "") for e in evs)

def _achar(lst, trecho):
    t = _norm(trecho)
    return [e for e in lst if t and t in _norm(e["titulo"])]

def desmarcar(trecho):
    with _LOCK:
        lst = _ler(); achados = _achar(lst, trecho)
        if not achados: return f"Não achei compromisso com '{trecho}'."
        e = min(achados, key=lambda x: x["inicio"]); lst.remove(e); _gravar(lst)
    return f"Desmarcado: {e['titulo']} de {falar_quando(datetime.datetime.fromisoformat(e['inicio']))}."

def remarcar(trecho, data="", horario=""):
    with _LOCK:
        lst = _ler(); achados = _achar(lst, trecho)
        if not achados: return f"Não achei compromisso com '{trecho}'."
        e = min(achados, key=lambda x: x["inicio"]); antigo = datetime.datetime.fromisoformat(e["inicio"])
        try: novo = _quando(data or antigo.date().isoformat(), horario or antigo.strftime("%H:%M"))
        except ValueError as er: return f"Não entendi o novo horário ({er})."
        e["inicio"], e["avisado"] = novo.isoformat(timespec="minutes"), False; _gravar(lst)
    return f"Remarcado: {e['titulo']} para {falar_quando(novo)}."

def concluir(id_):
    with _LOCK:
        lst = _ler(); resto = [e for e in lst if e["id"] != id_]
        if len(resto) == len(lst): return False
        _gravar(resto)
    return True

def avisos_pendentes():
    """Compromissos que entraram na janela de aviso (ex.: 15 min antes). Marca como avisados."""
    agora, out = datetime.datetime.now(), []
    with _LOCK:
        lst = _ler(); mudou = False
        for e in lst:
            ini = datetime.datetime.fromisoformat(e["inicio"])
            if not e.get("avisado") and ini - datetime.timedelta(minutes=e.get("avisar_antes_min", 15)) <= agora <= ini + datetime.timedelta(minutes=5):
                e["avisado"] = True; mudou = True
                faltam = max(0, round((ini - agora).total_seconds() / 60))
                out.append(f"{e['titulo']} " + (f"daqui a {faltam} minutos" if faltam else "agora") + (f", em {e['local']}" if e["local"] else "") + ".")
        # compromissos que já terminaram há mais de um dia saem da agenda
        velhos = [e for e in lst if datetime.datetime.fromisoformat(e["inicio"]) + datetime.timedelta(minutes=e.get("duracao_min", 60)) < agora - datetime.timedelta(days=1)]
        for e in velhos: lst.remove(e); mudou = True
        if mudou: _gravar(lst)
    return out

def painel(lembretes, n=8):
    """Próximos itens para os cartões do wallpaper: compromissos (até 1 h depois de começar) e lembretes."""
    agora = datetime.datetime.now()
    itens = [{"id": e["id"], "tipo": "agenda", "titulo": e["titulo"], "quando": e["inicio"], "local": e.get("local", "")}
             for e in _ler() if datetime.datetime.fromisoformat(e["inicio"]) + datetime.timedelta(minutes=60) >= agora]
    itens += [{"id": l["id"], "tipo": "lembrete", "titulo": l["texto"], "quando": l["quando"][:16], "local": ""} for l in lembretes]
    return sorted(itens, key=lambda x: x["quando"])[:n]
