# -*- coding: utf-8 -*-
"""
WhatsApp pelo APLICATIVO do Windows (whatsapp.root), lido pela acessibilidade do Windows (UI Automation) — o mesmo
caminho que os leitores de tela usam. Nada de senha, nada de API não oficial.

- O app só mostra a árvore de acessibilidade com a janela restaurada: se estiver minimizada, ela é restaurada POR
  TRÁS das outras janelas (sem tirar o foco) e minimizada de novo no fim.
- Enviar traz o WhatsApp para a frente, cola o texto e aperta Enter, só depois de conferir que a caixa de
  mensagem diz "Digite uma mensagem para <contato certo>". Quem decide enviar é o usuário (confirmação por voz).
"""
import contextlib, ctypes, logging, re, threading, time, unicodedata

import extras

log = logging.getLogger("aton")
u32 = ctypes.windll.user32
_LOCK = threading.Lock()


def _n(t):
    t = unicodedata.normalize("NFD", (t or "").lower())
    return re.sub(r"\s+", " ", "".join(c for c in t if unicodedata.category(c) != "Mn")).strip()


HORA = re.compile(r"^(\d{1,2}:\d{2}|ontem|hoje|segunda|terca|terça|quarta|quinta|sexta|sabado|sábado|domingo|\d{1,2}/\d{1,2}/\d{2,4})", re.I)
NAO_LIDAS = re.compile(r"^(\d+) mensage(m|ns) n[aã]o lidas?", re.I)


class SemApp(RuntimeError):
    pass


def _hwnd(abrir=True):
    j = extras._achar("whatsapp")
    if j: return j[0]
    if not abrir: raise SemApp("o aplicativo do WhatsApp não está aberto")
    app = extras.achar_app("whatsapp", so_exato=True)
    if not app: raise SemApp("o aplicativo do WhatsApp não está instalado")
    extras.abrir_app(app)
    for _ in range(40):
        time.sleep(0.5)
        j = extras._achar("whatsapp")
        if j:
            u32.ShowWindow(j[0], 7)          # abriu na frente: minimiza sem foco (a leitura restaura por trás)
            time.sleep(4)                    # carregar as conversas
            return j[0]
    raise SemApp("o WhatsApp não abriu")


@contextlib.contextmanager
def _aberto(focar=False):
    """Deixa a janela legível pela acessibilidade enquanto o bloco roda."""
    import uiautomation as ua
    with _LOCK, ua.UIAutomationInitializerInThread():
        h = _hwnd()
        minimizada = bool(u32.IsIconic(h))
        if focar:
            extras._focar(h); u32.ShowWindow(h, 9)
        elif minimizada:
            u32.ShowWindow(h, 4)                                     # SW_SHOWNOACTIVATE
            u32.SetWindowPos(h, 1, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010)   # HWND_BOTTOM, sem mexer no tamanho nem no foco
        try:
            doc = None
            for i in range(20):                                      # a árvore aparece alguns instantes depois de restaurar
                time.sleep(0.25)
                w = ua.ControlFromHandle(h)
                doc = w.DocumentControl(searchDepth=12)
                if doc.Exists(0, 0) and _busca(doc):
                    b = _busca(doc)
                    try: sobrou = (b.GetValuePattern().Value or "").strip()
                    except Exception: sobrou = ""
                    if sobrou: _pesquisar(doc, "")                    # busca esquecida de antes: limpa
                    if _cabecalhos(doc): break
            else:
                raise SemApp("não consegui ler a janela do WhatsApp (ele está conectado?)")
            yield doc
        finally:
            if minimizada and not focar: u32.ShowWindow(h, 7)        # SW_SHOWMINNOACTIVE


def _grade(doc):
    import uiautomation as ua
    g = doc.DataGridControl(searchDepth=40)
    return g if g.Exists(0, 0) else None


def _cabecalhos(doc):
    """Os "cabeçalhos" das conversas (nome + hora) do painel da esquerda: servem tanto para a lista normal
    (uma grade) quanto para os resultados da busca (grupos soltos)."""
    import uiautomation as ua
    main = doc.GroupControl(searchDepth=40, AutomationId="main")
    limite = main.BoundingRectangle.left if main.Exists(0, 0) else 10 ** 9
    itens = [c for c, d in ua.WalkControl(doc, maxDepth=60) if c.ControlTypeName == "DataItemControl"
             and c.Name and not c.Name.startswith("Conversa") and c.BoundingRectangle.left < limite]
    # fica com os mais internos (a linha da grade também é um DataItem e contém o cabeçalho)
    internos = []
    for c in itens:
        if not any(x.ControlTypeName == "DataItemControl" and x.Name and not x.Name.startswith("Conversa")
                   for x, _ in ua.WalkControl(c, maxDepth=8)):
            internos.append(c)
    return internos


def _linhas(doc):
    """[{nome, nao_lidas, previa, item}] das conversas visíveis na lista (ou nos resultados da busca)."""
    import uiautomation as ua
    out = []
    for cab in _cabecalhos(doc):
        textos = [t.Name.strip() for t in cab.GetChildren() if t.ControlTypeName == "TextControl" and (t.Name or "").strip()]
        textos += [t.Name.strip() for g2 in cab.GetChildren() if g2.ControlTypeName == "GroupControl"
                   for t in g2.GetChildren() if t.ControlTypeName == "TextControl" and (t.Name or "").strip()]
        nl = next((int(NAO_LIDAS.match(t).group(1)) for t in textos if NAO_LIDAS.match(t)), 0)
        nome = next((t for t in textos if not NAO_LIDAS.match(t) and not HORA.match(t) and t != "(você)"), "")
        prev = cab.GetNextSiblingControl()
        previa = " ".join(t.Name.strip() for t, _ in ua.WalkControl(prev, maxDepth=4)
                          if t.ControlTypeName == "TextControl" and (t.Name or "").strip()) if prev else ""
        if nome: out.append({"nome": nome, "nao_lidas": nl, "previa": previa, "item": cab})   # "ação padrão" do cabeçalho abre a conversa
    return out


def _caixa(doc):
    """Caixa de digitar a mensagem da conversa aberta e o nome que ela mostra."""
    import uiautomation as ua
    for c, d in ua.WalkControl(doc, maxDepth=60):
        if c.ControlTypeName == "EditControl" and (c.Name or "").startswith("Digite uma mensagem"):
            return c, re.sub(r"^Digite uma mensagem para\s*", "", c.Name).strip()
    return None, ""


def _busca(doc):
    """Caixa de busca: a outra caixa de texto que não é a de mensagem (o nome dela some quando tem texto)."""
    import uiautomation as ua
    for c, d in ua.WalkControl(doc, maxDepth=60):
        if c.ControlTypeName == "EditControl" and not (c.Name or "").startswith("Digite uma mensagem"):
            return c
    return None


def _pesquisar(doc, texto):
    import uiautomation as ua
    b = _busca(doc)
    if not b: return False
    try:
        b.GetValuePattern().SetValue(texto)
    except Exception as e:
        log.warning("WhatsApp: busca falhou: %r", e); return False
    time.sleep(1.3 if texto else 0.4)
    if not texto:                       # garante que limpou: o "x" da busca também apaga
        try:
            if (b.GetValuePattern().Value or "").strip():
                x = next((c for c, d in ua.WalkControl(doc, maxDepth=60) if c.ControlTypeName == "ButtonControl"
                          and c.Name in ("End icon button", "Limpar pesquisa", "Cancelar pesquisa")), None)
                if x: x.GetLegacyIAccessiblePattern().DoDefaultAction(); time.sleep(0.4)
        except Exception:
            pass
    return True


def _procurar(doc, nome):
    """Nomes de conversas/contatos parecidos com o falado (sem abrir nenhuma)."""
    n = _n(nome)
    achados = [l for l in _linhas(doc) if n in _n(l["nome"])]
    if not achados and _pesquisar(doc, nome):
        # resultados da busca do próprio WhatsApp: precisam conter o nome falado (ou todas as palavras dele)
        achados = [l for l in _linhas(doc) if n in _n(l["nome"]) or all(p in _n(l["nome"]) for p in n.split())]
    vistos, out = set(), []
    for l in achados:
        if l["nome"] not in vistos: vistos.add(l["nome"]); out.append(l)
    return out


def _abrir(doc, nome):
    _, atual = _caixa(doc)
    if _n(atual) == _n(nome): return True
    alvo = next((l for l in _procurar(doc, nome) if _n(l["nome"]) == _n(nome)), None)
    if not alvo: raise RuntimeError(f"não achei a conversa '{nome}'")
    item = alvo["item"]
    for tentativa in range(3):              # às vezes o primeiro "clique" pela acessibilidade se perde
        try:
            if tentativa < 2: item.GetLegacyIAccessiblePattern().DoDefaultAction()
            else: item.GetSelectionItemPattern().Select()
        except Exception:
            pass
        for _ in range(25):                 # com a janela atrás das outras o WhatsApp responde mais devagar
            time.sleep(0.2)
            _, atual = _caixa(doc)
            if _n(atual) == _n(nome):
                _pesquisar(doc, ""); return True
        alvo = next((l for l in _procurar(doc, nome) if _n(l["nome"]) == _n(nome)), alvo)   # a lista pode ter mudado
        item = alvo["item"]
    _pesquisar(doc, "")
    raise RuntimeError(f"a conversa '{nome}' não abriu")


STATUS = re.compile(r"\b(lida|entregue|enviada|pendente|read|delivered|sent)\b", re.I)
HORA_SO = re.compile(r"^\d{1,2}:\d{2}$")

def _mensagens(doc, n, contato=""):
    """Últimas n mensagens da conversa aberta: [(quem, texto, hora)].
    Cada mensagem tem a hora; as minhas têm o status (Lida/Entregue/Enviada); a 1ª de uma sequência traz "Fulano:"."""
    import uiautomation as ua
    main = doc.GroupControl(searchDepth=40, AutomationId="main")
    if not main.Exists(0, 0): return []
    eh_hora = lambda c: c.ControlTypeName in ("TextControl", "ButtonControl") and re.match(r"^\d{1,2}:\d{2}", c.Name or "")
    def n_horas(c):        # horários distintos (o botão "02:25 Lida" e o texto "02:25" dentro dele contam 1)
        return len({g.Name[:5] for g, _ in ua.WalkControl(c, maxDepth=14, includeTop=True) if eh_hora(g)})
    # cada mensagem tem um horário; mensagens seguidas ficam agrupadas em blocos, então a unidade de cada
    # mensagem é o maior grupo acima do horário que não contém nenhum outro horário
    marcas = [c for c, d in ua.WalkControl(main, maxDepth=22) if eh_hora(c)][-(n + 2):]
    unidades = []
    for t in marcas:
        a = t
        while True:
            p = a.GetParentControl()
            if p is None or p.AutomationId == "main" or n_horas(p) != 1: break
            a = p
        if not unidades or not ua.ControlsAreSame(unidades[-1], a): unidades.append(a)
    out, ultimo = [], ""
    for filho in unidades:
        quem, hora, partes, minha = "", "", [], False
        for c, d in ua.WalkControl(filho, maxDepth=14):
            nm = (c.Name or "").strip()
            if not nm: continue
            m = re.match(r"^([^:\n]{1,60}):\s*(.*)$", nm, re.S)
            if c.ControlTypeName == "GroupControl" and m and not quem:
                quem = m.group(1).strip()
                if m.group(2).strip() and not partes: partes.append(m.group(2).strip())
                continue
            if c.ControlTypeName == "ButtonControl" and STATUS.search(nm): minha = True
            if not hora and re.match(r"^\d{1,2}:\d{2}", nm): hora = nm[:5]
            if c.ControlTypeName == "TextControl" and not HORA_SO.match(nm) and not (len(partes) == 1 and partes[0].startswith(nm)):
                partes.append(nm)
        if not hora: continue                                   # separador de data ou aviso
        if minha or quem.lower().startswith("voc"): quem = "Você"
        quem = quem or ultimo or contato
        ultimo = quem
        texto = " ".join(dict.fromkeys(partes)) or "(mídia: foto, áudio, figurinha ou documento)"
        out.append((quem, texto, hora))
    return out[-n:]


# ------------------------------------------------------------------ API usada pelo Aton
def nao_lidas():
    with _aberto() as doc:
        return [{k: v for k, v in l.items() if k != "item"} for l in _linhas(doc) if l["nao_lidas"] > 0]


def recentes(n=10):
    with _aberto() as doc:
        return [{k: v for k, v in l.items() if k != "item"} for l in _linhas(doc)[:n]]


def buscar(nome):
    with _aberto() as doc:
        try:
            return [l["nome"] for l in _procurar(doc, nome)]
        finally:
            _pesquisar(doc, "")


def ler(nome, n=10):
    with _aberto() as doc:
        _abrir(doc, nome)
        time.sleep(0.8)
        conversa = _caixa(doc)[1]
        return conversa, _mensagens(doc, n, conversa)


def _frente_e_whatsapp(h):
    """A janela da frente é o WhatsApp (a moldura do app ou a parte web dele, msedgewebview2 filho do app)?"""
    import ctypes.wintypes as wt, psutil
    f = u32.GetForegroundWindow()
    if f == h: return True
    pid, wpid = wt.DWORD(), wt.DWORD()
    u32.GetWindowThreadProcessId(f, ctypes.byref(pid)); u32.GetWindowThreadProcessId(h, ctypes.byref(wpid))
    try:
        p = psutil.Process(pid.value)
        return p.name().lower() == "msedgewebview2.exe" and any(a.pid == wpid.value for a in p.parents())
    except Exception:
        return False


def _botao_enviar(doc):
    import uiautomation as ua
    return next((c for c, d in ua.WalkControl(doc, maxDepth=60) if c.ControlTypeName == "ButtonControl" and c.Name in ("Enviar", "Send")), None)


def enviar(nome, texto):
    """Abre a conversa, confere o destinatário, clica na caixa, cola o texto e clica em Enviar.
    Cada tecla só sai com o WhatsApp na frente; qualquer dúvida cancela sem enviar. Devolve (conversa, enviada)."""
    import keyboard, uiautomation as ua
    anterior = u32.GetForegroundWindow()
    h = _hwnd()
    minimizada = bool(u32.IsIconic(h))
    with _aberto(focar=True) as doc:
        for _ in range(20):
            if u32.GetForegroundWindow() == h: break
            extras._focar(h); time.sleep(0.1)
        _abrir(doc, nome)
        caixa, atual = _caixa(doc)
        if not caixa or _n(atual) != _n(nome):
            raise RuntimeError("a conversa aberta não é a certa; nada foi enviado")
        antes_clip, mouse = extras.ler_clipboard(), ua.GetCursorPos()
        try:
            caixa.Click(simulateMove=False); ua.SetCursorPos(*mouse); time.sleep(0.35)   # clique real: o teclado vai para a caixa
            if not _frente_e_whatsapp(h): raise RuntimeError("o WhatsApp não ficou na frente; nada foi enviado")
            extras.copiar(texto); time.sleep(0.1)
            keyboard.send("ctrl+v"); time.sleep(0.6)
            btn = _botao_enviar(doc)
            if not btn or _n(_caixa(doc)[1]) != _n(nome):
                if _frente_e_whatsapp(h): keyboard.send("ctrl+a"); keyboard.send("backspace")
                raise RuntimeError("o texto não entrou na caixa da conversa certa; nada foi enviado")
            try: btn.GetLegacyIAccessiblePattern().DoDefaultAction()
            except Exception: pass
            enviada = False
            for i in range(20):                                # enviada = a caixa esvaziou (o botão Enviar some)
                time.sleep(0.2)
                if not _botao_enviar(doc): enviada = True; break
                if i == 5:                                     # o clique pela acessibilidade não foi: Enter na caixa
                    if not _frente_e_whatsapp(h) or _n(_caixa(doc)[1]) != _n(nome):
                        raise RuntimeError("o WhatsApp saiu da frente; a mensagem ficou escrita na caixa, sem enviar")
                    keyboard.send("enter")
        finally:
            extras.copiar(antes_clip or "")
    if minimizada: u32.ShowWindow(h, 6)                        # devolve tudo como estava
    if anterior and anterior != h:
        try: extras._focar(anterior)
        except Exception: pass
    log.info("WhatsApp: mensagem para %s %s", atual, "enviada" if enviada else "SEM confirmação")
    return atual, enviada
