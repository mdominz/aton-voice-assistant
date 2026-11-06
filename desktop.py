# -*- coding: utf-8 -*-
"""
Controle do PC como uma pessoa no mouse e no teclado, na janela que está na frente:

1) Teclado: atalhos por nome ("salva", "desfaz", "seleciona tudo", "troca de janela") e qualquer tecla ou
   combinação ("aperta enter", "aperta control shift T", "aperta F5"), rolar a tela e zoom.
2) Clicar pelo nome em qualquer programa, pela acessibilidade do Windows (UI Automation): botões, menus, abas,
   caixas de marcar, itens de lista... Funciona também nos menus que abrem por cima ("clica em Arquivo" e
   depois "clica em Salvar como"). No Chrome, quem clica é a extensão do Aton (dentro da página).

Travas: botões de comprar/pagar/enviar/excluir/desinstalar pedem "sim"; nada é digitado em campo de senha;
Alt+F4 com a área de trabalho na frente não roda (abriria o "Desligar o Windows").
"""
import ctypes, ctypes.wintypes as wt, difflib, logging, re, time, unicodedata

log = logging.getLogger("aton")
u32 = ctypes.windll.user32
u32.GetForegroundWindow.restype = wt.HWND


def _n(t):
    t = unicodedata.normalize("NFD", (t or "").lower())
    return re.sub(r"\s+", " ", re.sub(r"[^\w+ ]+", " ", "".join(c for c in t if unicodedata.category(c) != "Mn"))).strip()


# ================================================================== janela da frente
def _frente():
    """(hwnd, nome do processo, título, classe) da janela da frente."""
    import psutil
    h = u32.GetForegroundWindow()
    if not h: return None, "", "", ""
    pid = wt.DWORD(); u32.GetWindowThreadProcessId(h, ctypes.byref(pid))
    t = ctypes.create_unicode_buffer(256); u32.GetWindowTextW(h, t, 256)
    c = ctypes.create_unicode_buffer(128); u32.GetClassNameW(h, c, 128)
    try: exe = psutil.Process(pid.value).name().lower()
    except Exception: exe = ""
    return h, exe, t.value, c.value


def _na_area_de_trabalho(classe):
    return classe in ("Progman", "WorkerW", "Shell_TrayWnd", "")


# ================================================================== 1) teclado
TECLAS = {
    "control": "ctrl", "controle": "ctrl", "ctrl": "ctrl", "contrau": "ctrl", "shift": "shift", "chifte": "shift", "alt": "alt",
    "windows": "windows", "win": "windows", "tecla windows": "windows", "enter": "enter", "entra": "enter", "esc": "esc",
    "escape": "esc", "esqueipe": "esc", "tab": "tab", "espaco": "space", "barra de espaco": "space", "backspace": "backspace",
    "apagar": "backspace", "apaga": "backspace", "delete": "delete", "deletar": "delete", "del": "delete", "home": "home",
    "inicio": "home", "end": "end", "fim": "end", "page up": "page up", "page down": "page down", "pagina para cima": "page up",
    "pagina para baixo": "page down", "seta para cima": "up", "seta pra cima": "up", "pra cima": "up", "cima": "up",
    "seta para baixo": "down", "seta pra baixo": "down", "pra baixo": "down", "baixo": "down", "seta para esquerda": "left",
    "seta pra esquerda": "left", "esquerda": "left", "seta para direita": "right", "seta pra direita": "right", "direita": "right",
    "print screen": "print screen", "print": "print screen", "insert": "insert",
}
# atalhos por nome (a frase inteira, normalizada) -> teclas
ATALHOS = {
    r"salva|salvar|salve|salva isso|salva o arquivo": "ctrl+s",
    r"salvar como|salva como": "ctrl+shift+s",
    r"desfaz|desfazer|desfaca|volta o que eu fiz": "ctrl+z",
    r"refaz|refazer|refaca": "ctrl+y",
    r"copia|copiar|copie|copia isso": "ctrl+c",
    r"cola|colar|cole|cola aqui|cola isso": "ctrl+v",
    r"recorta|recortar|recorte": "ctrl+x",
    r"seleciona tudo|selecionar tudo|selecione tudo|marca tudo": "ctrl+a",
    r"fecha essa janela|fecha esta janela|fechar janela|fecha a janela": "alt+f4",
    r"troca de janela|muda de janela|alterna janela|alt tab|proxima janela": "alt+tab",
    r"imprime|imprimir|imprima": "ctrl+p",
    r"procura na pagina|localiza|procurar na pagina|buscar na pagina": "ctrl+f",
    r"aumenta o zoom|mais zoom|zoom mais|aproxima": "ctrl+=",
    r"diminui o zoom|menos zoom|zoom menos|afasta": "ctrl+-",
    r"zoom normal|volta o zoom": "ctrl+0",
    r"tela cheia do programa|maximiza tudo": "f11",
    r"mostra a area de trabalho|area de trabalho": "windows+d",
    r"abre o menu iniciar|menu iniciar": "windows",
    r"abre a central de notificacoes|notificacoes": "windows+n",
    r"bloqueia o computador|bloqueia o pc|bloquear tela": "windows+l",
    r"captura de tela de uma parte|recorte de tela": "windows+shift+s",
    r"abre o explorador|meu computador": "windows+e",
    r"emoji|abre os emojis": "windows+.",
    r"historico da area de transferencia": "windows+v",
}
_ATALHOS_RX = [(re.compile(r"^(?:aton )?(?:" + k + r")(?: por favor)?$"), v) for k, v in ATALHOS.items()]


def atalho_por_nome(texto_norm):
    for rx, teclas in _ATALHOS_RX:
        if rx.match(texto_norm): return teclas
    return None


def teclas_faladas(texto_norm):
    """'control shift t' -> 'ctrl+shift+t'; 'f5' -> 'f5'; 'enter' -> 'enter'. None se não entender."""
    t = re.sub(r"^(?:a tecla|tecla|o botao|o|a)\s+", "", texto_norm.strip())       # "aperta a tecla F5"
    t = re.sub(r"\s+(?:mais|com|junto com|e)\s+", " ", " " + t + " ").strip()        # "control mais shift mais T"
    t = re.sub(r"\s+(?:de novo|por favor|agora)$", "", t)
    partes, i, pal = [], 0, t.split()
    while i < len(pal):
        for tam in (3, 2, 1):                       # "seta pra cima" antes de "cima"
            k = " ".join(pal[i:i + tam])
            if k in TECLAS:
                partes.append(TECLAS[k]); i += tam; break
        else:
            w = pal[i]
            if re.fullmatch(r"f(1[0-2]|[1-9])", w) or re.fullmatch(r"[a-z0-9]", w): partes.append(w)
            else: return None
            i += 1
    return "+".join(partes) if partes else None


def apertar(teclas, vezes=1):
    import keyboard
    h, exe, titulo, classe = _frente()
    if teclas == "alt+f4" and _na_area_de_trabalho(classe):
        return "Não há janela na frente para fechar."
    for _ in range(max(1, min(int(vezes or 1), 20))):
        keyboard.send(teclas); time.sleep(0.05)
    return "Pronto."


def rolar(direcao="baixo", vezes=3):
    """Regra fixa: rola SEMPRE a guia aberta do Chrome (pela extensão, sem mexer no mouse nem na janela da frente).
    Sem Chrome/extensão: rola a janela da frente com a rodinha do mouse (o cursor vai ao meio dela e volta)."""
    import uiautomation as ua, navegador
    try:
        acao = {"baixo": "rolar_baixo", "cima": "rolar_cima", "topo": "topo", "fim": "fim"}[direcao]
        for _ in range(max(1, min(int(vezes or 1), 10)) if direcao in ("baixo", "cima") else 1):
            navegador._pedir("rolar", {"direcao": {"rolar_baixo": "baixo", "rolar_cima": "cima"}.get(acao, acao)})
        return "Pronto."
    except Exception:
        pass                                                 # sem Chrome aberto: rodinha na janela da frente
    if direcao in ("topo", "fim"): direcao = "cima" if direcao == "topo" else "baixo"; vezes = 15
    h, exe, titulo, classe = _alvo()
    if not h: return "Não há janela na frente."
    if _frente()[0] != h:                                   # era a área de trabalho: traz o Chrome para frente
        import extras; extras._focar(h); time.sleep(0.2)
    r = wt.RECT(); u32.GetWindowRect(h, ctypes.byref(r))
    pos = ua.GetCursorPos()
    ua.SetCursorPos((r.left + r.right) // 2, (r.top + r.bottom) // 2)
    for _ in range(max(1, min(int(vezes or 3), 20))):
        (ua.WheelDown if direcao == "baixo" else ua.WheelUp)(wheelTimes=3, interval=0.02, waitTime=0)
    ua.SetCursorPos(*pos)
    return "Pronto."


# ================================================================== 2) clicar pelo nome (UI Automation)
CLICAVEIS = {"ButtonControl", "MenuItemControl", "HyperlinkControl", "TabItemControl", "ListItemControl", "TreeItemControl",
             "CheckBoxControl", "RadioButtonControl", "ComboBoxControl", "SplitButtonControl", "DataItemControl",
             "EditControl", "MenuBarControl", "ImageControl", "TextControl", "HeaderItemControl", "DocumentControl"}
PRIORIDADE = {"ButtonControl": 0, "MenuItemControl": 0, "CheckBoxControl": 0, "RadioButtonControl": 0, "TabItemControl": 0,
              "HyperlinkControl": 1, "SplitButtonControl": 1, "ListItemControl": 1, "TreeItemControl": 1, "ComboBoxControl": 1,
              "DataItemControl": 2, "EditControl": 2, "HeaderItemControl": 2, "TextControl": 3, "ImageControl": 3}


def _janelas_do_app(h):
    """A janela da frente e as outras janelas do mesmo programa (menus e caixas que abrem por cima)."""
    import uiautomation as ua
    pid = wt.DWORD(); u32.GetWindowThreadProcessId(h, ctypes.byref(pid))
    out = [ua.ControlFromHandle(h)]
    for c in ua.GetRootControl().GetChildren():
        try:
            if c.ProcessId == pid.value and c.NativeWindowHandle != h: out.insert(0, c)   # menus por cima primeiro
        except Exception:
            pass
    return out


def _elementos(h, limite=2500, tempo=4.0):
    import uiautomation as ua
    t0, out = time.time(), []
    for raiz in _janelas_do_app(h):
        for c, d in ua.WalkControl(raiz, maxDepth=30):
            if len(out) >= limite or time.time() - t0 > tempo: return out
            try:
                if c.ControlTypeName not in CLICAVEIS or not (c.Name or "").strip() or c.IsOffscreen or not c.IsEnabled: continue
            except Exception:
                continue
            out.append(c)
    return out


def _achar(h, texto, n=1):
    alvo = _n(texto)
    pont = []
    for c in _elementos(h):
        nome = _n(c.Name)
        if not nome: continue
        if nome == alvo: s = 4
        elif nome.startswith(alvo + " ") or nome.startswith(alvo): s = 3
        elif re.search(r"\b" + re.escape(alvo) + r"\b", nome): s = 2
        elif alvo in nome: s = 1
        else:
            r = difflib.SequenceMatcher(None, alvo, nome).ratio()
            if r < 0.78: continue
            s = r                                           # "configuraçoes" ~ "configurações"
        pont.append((s, -PRIORIDADE.get(c.ControlTypeName, 3), -len(nome), c))
    if not pont: return None
    pont.sort(key=lambda x: (x[0], x[1], x[2]), reverse=True)
    return pont[min(n - 1, len(pont) - 1)][3]


def _acionar(c):
    """Usa a ação de acessibilidade certa para o tipo de controle; sem nenhuma, um clique real (o mouse volta)."""
    import uiautomation as ua
    tipo = c.ControlTypeName
    tentativas = []
    if tipo in ("CheckBoxControl",): tentativas.append(lambda: c.GetTogglePattern().Toggle())
    if tipo in ("RadioButtonControl", "ListItemControl", "TabItemControl", "DataItemControl", "TreeItemControl"):
        tentativas.append(lambda: c.GetSelectionItemPattern().Select())
    if tipo in ("MenuItemControl", "SplitButtonControl", "ComboBoxControl"):
        tentativas.append(lambda: c.GetExpandCollapsePattern().Expand())
    tentativas += [lambda: c.GetInvokePattern().Invoke(), lambda: c.GetLegacyIAccessiblePattern().DoDefaultAction()]
    for f in tentativas:
        try:
            f(); return "acessibilidade"
        except Exception:
            continue
    pos = ua.GetCursorPos()
    try: c.Click(simulateMove=False)
    finally: ua.SetCursorPos(*pos)
    return "clique"


def _perigoso(t):
    import navegador
    return bool(navegador.PERIGOSO.search(_n(t)) or re.search(r"\b(desinstal\w*|formatar|redefinir|restaurar padr\w*|uninstall|format)\b", _n(t)))


def _alvo():
    """Janela da frente; se a frente for a área de trabalho (ou nada, ex.: pedido pelo celular), o Chrome."""
    h, exe, titulo, classe = _frente()
    if h and not _na_area_de_trabalho(classe): return h, exe, titulo, classe
    import extras
    j = extras._achar("chrome")
    if not j: return None, "", "", classe
    return j[0], "chrome.exe", j[1], "Chrome_WidgetWin_1"


def _area_da_pagina(h):
    """Retângulo (tela, pixels reais) onde a página aparece no Chrome — via acessibilidade."""
    import uiautomation as ua
    for c, d in ua.WalkControl(ua.ControlFromHandle(h), maxDepth=12):
        if c.ControlTypeName == "DocumentControl":
            r = c.BoundingRectangle
            if r.width() > 200 and r.height() > 150: return r
    return None


def clique_real_chrome(h, fx, fy):
    """Clique de verdade (mouse) num ponto da página: conta como gesto do usuário para o Chrome."""
    import extras, uiautomation as ua
    with ua.UIAutomationInitializerInThread():
        extras._focar(h); time.sleep(0.25)
        r = _area_da_pagina(h)
        if not r: return False
        x, y = int(r.left + fx * r.width()), int(r.top + fy * r.height())
        if not (r.left <= x <= r.right and r.top <= y <= r.bottom): return False
        # trava: o ponto precisa ser do Chrome (outra janela por cima receberia o clique)
        u32.WindowFromPoint.restype = wt.HWND; u32.WindowFromPoint.argtypes = [wt.POINT]
        u32.GetAncestor.restype = wt.HWND
        embaixo = u32.WindowFromPoint(wt.POINT(x, y))
        if not embaixo or u32.GetAncestor(embaixo, 2) != h:          # GA_ROOT
            log.info("Clique real cancelado: outra janela cobre o Chrome nesse ponto.")
            return False
        pos = ua.GetCursorPos()
        try: ua.Click(x, y, waitTime=0.05)
        finally: ua.SetCursorPos(*pos)
        return True


def _clicar_no_chrome(h, texto, n=1, confirmado=False):
    """Acha pela extensão e clica com o mouse de verdade; se não der, clique da extensão. None = não achou."""
    import bracos, navegador
    try:
        ver = navegador._pedir("pagina", {"op": "clicar", "texto": texto, "n": n, "so_ver": True}, timeout=10)
    except navegador.SemExtensao:
        return None
    except Exception:
        return None
    achado = ver.get("texto", texto)
    if not confirmado and (_perigoso(achado) or _perigoso(texto)):
        bracos.preparar(f"clicar em '{achado[:60]}' na página {ver.get('guia', '')[:50]}",
                        lambda: _clicar_no_chrome(h, texto, n, confirmado=True) or "Não consegui clicar.")
        return f"O botão '{achado[:60]}' pode comprar, enviar ou apagar algo. Confirma?"
    if ver.get("visivel") and clique_real_chrome(h, ver["fx"], ver["fy"]):
        log.info("Clique real no Chrome: '%s'", achado[:60])
        return f"Cliquei em {achado[:60]}."
    r = navegador._pedir("pagina", {"op": "clicar", "texto": texto, "n": n}, timeout=10)
    return f"Cliquei em {r.get('texto', achado)[:60]}."


BOTOES_PLAY = ["Assistir", "Reproduzir", "Play", "Continuar assistindo", "Assistir agora", "Começar a assistir",
               "Assistir de novo", "Assistir do início", "Iniciar", "Watch", "Resume", "Continuar"]


def clicar_play():
    """'Dá play' numa página de filme/série (HBO Max, Netflix, Prime...): clica no botão de assistir com clique real."""
    h, exe, titulo, classe = _alvo()
    if exe != "chrome.exe": return None
    for nome in BOTOES_PLAY:
        r = _clicar_no_chrome(h, nome)
        if r: return "Dando play." if r.startswith("Cliquei") else r
    return None


def clicar(texto, n=1):
    import bracos, uiautomation as ua
    h, exe, titulo, classe = _alvo()
    if not h: return "Não há nenhuma janela na frente para eu clicar."
    if exe == "chrome.exe":                                  # dentro da página: acha pela extensão e clica com o mouse
        r = _clicar_no_chrome(h, texto, n)
        if r: return r
    with ua.UIAutomationInitializerInThread():
        c = _achar(h, texto, n)
        if not c: return f"Não achei '{texto}' na janela {titulo[:50] or exe}."
        nome, tipo = c.Name.strip()[:60], c.ControlTypeName
        if tipo == "EditControl" and ("senha" in _n(nome) or "password" in _n(nome)):
            return "Esse é um campo de senha: digite você mesmo."
        if _perigoso(nome) or _perigoso(texto):
            def fazer(t=texto, nn=n, hh=h):
                with ua.UIAutomationInitializerInThread():
                    cc = _achar(hh, t, nn)
                    if not cc: return "O botão sumiu da tela; não cliquei."
                    _acionar(cc); return f"Cliquei em {cc.Name.strip()[:60]}."
            bracos.preparar(f"clicar em '{nome}' no {titulo[:40] or exe}", fazer)
            return f"O botão '{nome}' pode apagar, enviar ou comprar algo. Confirma?"
        modo = _acionar(c)
        log.info("Clique por voz: '%s' (%s, via %s) em %s", nome, tipo, modo, exe)
        return f"Cliquei em {nome}."


def marcar(texto, ligar=True):
    """Marca/desmarca uma caixa ou chave ("ativa o modo escuro", "desmarca lembrar senha")."""
    import uiautomation as ua
    h, exe, titulo, classe = _frente()
    if not h or _na_area_de_trabalho(classe): return "Não há nenhuma janela na frente."
    with ua.UIAutomationInitializerInThread():
        c = _achar(h, texto)
        if not c: return f"Não achei '{texto}' na janela."
        try:
            tp = c.GetTogglePattern()
            if (tp.ToggleState == 1) != ligar: tp.Toggle()
            return f"{'Marquei' if ligar else 'Desmarquei'} {c.Name.strip()[:60]}."
        except Exception:
            _acionar(c); return f"Cliquei em {c.Name.strip()[:60]}."


def listar():
    import uiautomation as ua
    h, exe, titulo, classe = _alvo()
    if not h: return "Não há nenhuma janela na frente."
    if exe == "chrome.exe":
        import navegador
        r = navegador.pagina("listar")
        if not r.startswith(("Não consegui", "Para isso")): return r
    with ua.UIAutomationInitializerInThread():
        els = sorted(_elementos(h), key=lambda c: PRIORIDADE.get(c.ControlTypeName, 3))
        lixo = re.compile(r"^(uma (linha|pagina) (acima|abaixo)|line (up|down)|page (up|down)|[A-Z][a-z]+([A-Z][a-z]+)+)$")
        nomes = list(dict.fromkeys(c.Name.strip()[:50] for c in els if PRIORIDADE.get(c.ControlTypeName, 3) <= 1
                                   and not lixo.match(_n(c.Name) if " " in c.Name else c.Name.strip())))[:40]
    return f"Na janela {titulo[:50] or exe} dá para clicar em: " + "; ".join(nomes) if nomes else "Não achei botões nesta janela."


def digitar_em(campo, texto):
    """'escreve João no campo Nome': clica no campo e digita (nunca em campo de senha)."""
    import keyboard, uiautomation as ua
    h, exe, titulo, classe = _frente()
    if not h or _na_area_de_trabalho(classe): return "Não há nenhuma janela na frente."
    with ua.UIAutomationInitializerInThread():
        c = _achar(h, campo)
        if not c: return f"Não achei o campo '{campo}'."
        if "senha" in _n(c.Name) or "password" in _n(c.Name): return "Esse é um campo de senha: digite você mesmo."
        try: c.SetFocus()
        except Exception: _acionar(c)
        time.sleep(0.2)
        keyboard.write(texto, delay=0.01)
        return f"Escrevi em {c.Name.strip()[:40]}."


# ================================================================== esquema para a IA
ESQUEMA = {"type": "function", "function": {"name": "computador", "description": (
    "Controla a JANELA DA FRENTE como uma pessoa no mouse e teclado (qualquer programa do Windows): clicar (texto = o que está "
    "escrito no botão/menu/aba; serve para menus: 'Arquivo' e depois 'Salvar como'), marcar/desmarcar (caixas e chaves), "
    "listar (o que dá para clicar), teclas (teclas = combinação, ex.: 'ctrl+s', 'alt+tab', 'enter', 'f5'; vezes = repetições), "
    "rolar (direcao baixo/cima), digitar_em (campo + texto). Comprar/excluir/enviar/desinstalar pedem confirmação. Nunca senhas."),
    "parameters": {"type": "object", "properties": {
        "acao": {"type": "string", "enum": ["clicar", "marcar", "desmarcar", "listar", "teclas", "rolar", "digitar_em"]},
        "texto": {"type": "string"}, "teclas": {"type": "string"}, "vezes": {"type": "integer"},
        "direcao": {"type": "string", "enum": ["baixo", "cima"]}, "campo": {"type": "string"}, "n": {"type": "integer"}},
        "required": ["acao"]}}}


def chamar(a):
    acao = a.get("acao", "")
    try:
        if acao == "clicar": return clicar(a.get("texto", ""), int(a.get("n") or 1))
        if acao in ("marcar", "desmarcar"): return marcar(a.get("texto", ""), acao == "marcar")
        if acao == "listar": return listar()
        if acao == "teclas":
            t = (a.get("teclas") or "").lower().replace(" ", "").replace("control", "ctrl").replace("win+", "windows+")
            if re.search(r"ctrl\+alt\+(del|delete)", t): return "Ctrl+Alt+Del eu não aperto."
            return apertar(t, a.get("vezes") or 1)
        if acao == "rolar": return rolar(a.get("direcao") or "baixo", a.get("vezes") or 3)
        if acao == "digitar_em": return digitar_em(a.get("campo", ""), a.get("texto", ""))
    except Exception as e:
        log.warning("Computador (%s) falhou: %r", acao, e)
        return f"Não consegui: {e}"
    return "Ação desconhecida."
