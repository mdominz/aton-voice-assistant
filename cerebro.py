# -*- coding: utf-8 -*-
"""
Cérebro do Aton: conversa com o Ollama em streaming, deixa a IA chamar ferramentas e entrega a resposta
frase por frase (para a voz começar antes de a resposta terminar).

Rota "auto": usa o modelo da nuvem do Ollama (mais esperto e rápido) e cai para o modelo local quando a nuvem
recusa (limite do plano, sem internet, demora). Laço de ferramentas adaptado do OrchestratorAgent do
OpenJarvis (Apache-2.0).
"""
import datetime, json, logging, os, re, subprocess, time, unicodedata, urllib.error, urllib.request

import ferramentas

log = logging.getLogger("aton")
DIAS = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"]
FIM_FRASE = re.compile(r"[.!?…:;](\s+)")      # pontuação seguida de espaço: "3.5" e "R$ 1.000" não cortam

def eh_reenvio(pedaco, conteudo):
    """Pedaços normais do streaming têm poucos caracteres; um bloco grande igual ao começo do que já chegou é repetição."""
    p, c = pedaco.strip(), conteudo.strip()
    return len(p) >= 30 and len(c) >= 30 and (p in c or p[:30] == c[:30])

def cortar_frase(buf, minimo=12):
    """Primeira frase completa com pelo menos `minimo` letras (frases curtas como "Sim." juntam com a próxima)."""
    for m in FIM_FRASE.finditer(buf):
        antes = buf[:m.start()].split()[-1:] or [""]
        if buf[m.start()] == "." and (len(antes[0]) <= 2 and antes[0][:1].isupper() or antes[0].lower() in ("sr", "sra", "dr", "dra", "prof")):
            continue                                   # abreviações: "Donald J. Trump", "Dr. Silva"
        if m.start() + 1 >= minimo:
            return buf[:m.start() + 1], buf[m.end():]
    return None, buf

# Perguntas sobre e-mail ficam no modelo local (o conteúdo dos e-mails não sai do PC)
EMAIL_RX = re.compile(r"\b(e ?mails?|e-mails?|caixa de entrada|correio eletronico|outlook|hotmail)\b")
# WhatsApp também: o conteúdo das conversas só é lido pelo modelo local ("whatsapp_local": false libera a nuvem)
WPP_RX = re.compile(r"\b(whatsapp|whats|wpp|zap|zapzap)\b|\bmensage(m|ns)\b")

class PrecisaLocal(Exception):
    """A nuvem pediu uma ferramenta de e-mail: refaz a pergunta no modelo local antes de buscar os e-mails."""

class NuvemIndisponivel(Exception):
    pass

def limpar(t):
    """Tira markdown e símbolos que a voz leria em voz alta."""
    t = re.sub(r"https?://\S+", "", t)
    t = re.sub(r"[*_#`|>]+", "", t)
    t = re.sub(r"^\s*[-•]\s+", "", t, flags=re.M)
    return re.sub(r"\s+", " ", t).strip()

def falavel(frase):
    """Descarta rascunhos que o modelo às vezes solta antes de chamar ferramentas ('“ ....” (c nome ?')."""
    f = frase.lstrip(" .…")
    letras = sum(c.isalnum() for c in f)
    return bool(f) and letras >= 0.6 * len(f.replace(" ", "")) and not re.search(r"\.{4,}|…\s*…|[“\"]\s*[.…]", f)

class Cerebro:
    def __init__(self, cfg, memoria):
        self.cfg, self.mem = cfg, memoria
        self.nuvem_off_ate = 0.0
        self.uso_claude = {"dia": "", "pedidos": 0, "tokens": 0, "custo": 0.0}   # soma de hoje (só informativo)
        self.ultimo_uso = None
        self._uso_arq = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uso_claude.json")
        try:                                  # o total do dia sobrevive a reinícios do Aton
            with open(self._uso_arq, encoding="utf-8") as f: g = json.load(f)
            if g.get("soma", {}).get("dia") == time.strftime("%Y-%m-%d"): self.uso_claude, self.ultimo_uso = g["soma"], g.get("ultimo")
        except (OSError, ValueError): pass
        self.contexto = None         # função que devolve um contexto extra para o pedido (ex.: a notícia aberta na tela)
        self.ao_aviso = None         # idem, para avisos curtos no console do painel
        self.ao_uso = None           # o assistente.py põe aqui a função que mostra o uso no painel
        self.privado = False    # a última resposta envolveu e-mails e ficou só no modelo local
        self.usadas = []        # ferramentas que a IA chamou na última resposta (o modo conversa usa isso)

    # ---------------------------------------------------------------- prompt
    def system_prompt(self):
        c = self.cfg
        n = datetime.datetime.now()
        fatos = self.mem.texto_fatos()
        return (f"Você é {c['nome']}, o assistente de voz de um wallpaper futurista, ao estilo de um mordomo digital elegante e discreto. "
                f"{self.identidade()}"
                f"Responda sempre em português do Brasil, curto (1 a 3 frases), natural para ser falado em voz alta: "
                f"sem markdown, listas, tabelas, emojis, links ou símbolos. Trate o usuário por '{c['tratamento']}', mas "
                f"com moderação: no máximo uma vez por resposta e nem em toda resposta (respostas curtas e diretas soam melhor sem). "
                f"Agora é {DIAS[n.weekday()]}, {n:%d/%m/%Y}, {n:%H:%M}. Cidade do usuário: {c.get('cidade') or 'não informada'}. "
                f"Seu conhecimento de treino é antigo e pode estar desatualizado em relação à data de hoje: para qualquer coisa que "
                f"possa ter mudado (resultados, campeões, 'último', 'atual', notícias, preços, cargos, lançamentos, eventos) "
                f"chame pesquisar_web antes de responder e mencione isso de forma natural (ex.: 'Segundo uma pesquisa, ...'). "
                f"Na busca, nunca suponha o ano pelo que você lembra: para 'último', 'atual' ou 'mais recente', inclua o ano de hoje "
                f"({n.year}) ou nenhum ano, e confie nos resultados da pesquisa mais do que na sua memória. "
                f"Outras ferramentas: clima, música, volume, abrir programas, memória, arquivos, janelas, lembretes e timers, "
                f"estado do PC, desligar/reiniciar e rotinas. Ações que alteram algo (organizar arquivos, fechar programa, "
                f"desligar) voltam como 'AÇÃO PREPARADA': nesse caso explique o que vai acontecer e pergunte se o usuário confirma; "
                f"nunca diga que fez antes da confirmação. Não peça confirmação por conta própria antes de chamar a ferramenta: "
                f"chame direto, o sistema cuida de perguntar. Procurar não é abrir: só abra arquivos se o usuário pedir. "
                f"Não escreva nada antes de chamar uma ferramenta; fale só depois de ter o resultado, e então confirme em uma "
                f"frase o que foi feito (ex.: 'Marquei o dentista para quinta às 14h'). "
                f"Nunca finja ter feito uma ação sem chamar a ferramenta; para tocar playlist, artista ou música pelo nome use sempre spotify_tocar (nunca pesquisar_web para isso); os nomes podem vir com erro de transcrição, então use a grafia mais provável (ex.: 'e e si de si' = AC/DC); você não controla luzes. "
                f"Responda exatamente ao que foi dito, sem puxar assunto novo. "
                f"O texto vem de um microfone ligado o tempo todo: às vezes é o usuário falando com outra pessoa, falando SOBRE você "
                f"(ex.: 'ele não entende', 'às vezes eu peço e ele não faz') ou uma frase cortada sem sentido. Nesses casos não chame "
                f"nenhuma ferramenta e responda apenas a palavra IGNORAR. Só execute uma ação quando ela foi pedida claramente nesta "
                f"frase; nunca execute algo de pedidos anteriores da conversa por conta própria. Chame cada ferramenta no máximo uma "
                f"vez por pedido: se ela falhar, não tente de novo nem tente outra parecida, apenas diga o que aconteceu. "
                f"Se o pedido for ambíguo, pergunte em vez de agir. "
                f"Quando não conseguir fazer exatamente o pedido, mas houver uma alternativa que você pode executar com as "
                f"ferramentas (ex.: abrir a página normal, pesquisar, abrir o programa), não a execute por conta própria nem "
                f"diga só 'posso fazer X': termine a resposta com a pergunta 'Quer que eu ...?' (ex.: 'Quer que eu abra a "
                f"página normal?') e espere o usuário responder. Se não houver alternativa concreta, não termine com pergunta "
                f"genérica como 'Quer ajuda com outra coisa?'."
                + (f"\nO que você sabe sobre o usuário (memória):\n{fatos}" if fatos else ""))

    def identidade(self):
        n = self.cfg["nome"]
        return (f"Só existe UM {n}: você. É você quem ouve o microfone, fala, controla este PC e mostra imagens e vídeos na tela "
                f"(o painel do wallpaper e o app do celular são a SUA tela). Nunca diga ao usuário para 'pedir ao {n}', nunca fale "
                f"de 'outro {n}' ou '{n} de tela', e nunca diga que só responde por voz: quando ele pedir para ver, abrir, tocar ou "
                f"controlar algo, use a ferramenta e faça. Quando o usuário diz '{n}', está chamando você. ")

    # ---------------------------------------------------------------- rota
    def modelos(self):
        c = self.cfg
        rota, nuvem, local = c.get("rota", "auto"), c.get("modelo_nuvem"), c["ollama_modelo"]
        reserva_claude = ["claude"] if c.get("claude_reserva", True) and self.claude_exe() and time.time() >= self.claude_off_ate else []
        if rota == "claude":                 # só o Claude (assinatura do Claude Code); o modelo local fica de reserva
            return reserva_claude + [local]
        if rota == "local" or not nuvem: return [local]
        if rota == "nuvem": return [nuvem]
        return ([nuvem] if time.time() >= self.nuvem_off_ate else []) + reserva_claude + [local]

    # ---------------------------------------------------------------- Claude pela assinatura (Claude Code, sem API)
    claude_off_ate = 0.0

    def claude_exe(self):
        exe = self.cfg.get("claude_exe") or os.path.expandvars(r"%USERPROFILE%\.local\bin\claude.exe")
        return exe if os.path.isfile(exe) else None

    @staticmethod
    def pedido_claude(texto):
        """'Aton, pergunta pro Claude qual...' -> 'qual...'; devolve None se o usuário não pediu o Claude."""
        t = unicodedata.normalize("NFD", texto.lower())
        t = "".join(ch for ch in t if unicodedata.category(ch) != "Mn")
        # o Whisper costuma escrever "Claude" como "Cloud"/"Claud"; "cloud" sozinho no começo não vale ("cloud computing")
        m = re.match(r"^\W*(?:(?:pergunta|pergunte|pede|peca|consulta|chama|usa|use)\s+(?:pro|pra|para o|para|ao|o|a)?\s*"
                     r"(?:claude|cloud|claud|clode|clod|claudi)|claude|claud|clode)\b[\s,:.!?]*(?:(?:se|que)\s+)?", t)
        return texto[m.end():].strip(" ,.:") if m else None

    def _registrar_uso(self, d, segundos):
        """Guarda o uso de um pedido ao Claude (modelo real, esforço, tokens) e avisa o painel."""
        try:
            u = d.get("usage") or {}
            entrada = u.get("input_tokens", 0) + u.get("cache_read_input_tokens", 0) + u.get("cache_creation_input_tokens", 0)
            saida = u.get("output_tokens", 0)
            # o modelo que RESPONDE é o do config; a pesquisa na web usa um modelo menor (Haiku) só para ler as páginas
            mu, quer = d.get("modelUsage") or {"?": {}}, str(self.cfg.get("claude_modelo", "sonnet")).replace("claude-", "")
            modelo = next((k for k in mu if quer.split("-")[0] in k), None) or max(mu.items(), key=lambda kv: kv[1].get("outputTokens", 0))[0]
            hoje = time.strftime("%Y-%m-%d")
            if self.uso_claude["dia"] != hoje: self.uso_claude.update(dia=hoje, pedidos=0, tokens=0, custo=0.0)
            self.uso_claude["pedidos"] += 1; self.uso_claude["tokens"] += entrada + saida
            self.uso_claude["custo"] += float(d.get("total_cost_usd") or 0)
            uso = {"modelo": modelo.replace("claude-", ""), "esforco": self.cfg.get("claude_esforco", "low"), "entrada": entrada,
                   "saida": saida, "segundos": round(segundos, 1), "pesquisas": (u.get("server_tool_use") or {}).get("web_search_requests", 0),
                   "pedidos_hoje": self.uso_claude["pedidos"], "tokens_hoje": self.uso_claude["tokens"],
                   "custo_hoje": round(self.uso_claude["custo"], 2)}
            log.info("Uso do Claude: %s, esforço %s, %d tokens de entrada, %d de saída, %.1f s (hoje: %d pedidos, %d tokens)",
                     uso["modelo"], uso["esforco"], entrada, saida, segundos, uso["pedidos_hoje"], uso["tokens_hoje"])
            self.ultimo_uso = uso
            try:
                with open(self._uso_arq, "w", encoding="utf-8") as f: json.dump({"soma": self.uso_claude, "ultimo": uso}, f)
            except OSError: pass
            if self.ao_uso: self.ao_uso(uso)
        except Exception as e:
            log.warning("Não registrei o uso do Claude: %r", e)

    def _catalogo(self):
        """Lista compacta das ferramentas para o Claude de reserva (as de e-mail e WhatsApp ficam só no modelo local)."""
        linhas = []
        for e in ferramentas.ESQUEMAS:
            f = e["function"]
            if f["name"].startswith("email_") or f["name"] in ("whatsapp", "pesquisar_web", "tarefa_segundo_plano", "ver_tela"): continue
            props = f["parameters"].get("properties", {})
            args = ", ".join(k + ("=" + "|".join(map(str, v["enum"])) if v.get("enum") else "") for k, v in props.items())
            linhas.append(f"- {f['name']}({args}): {f['description'] if f['name'] == 'mostrar_midia' else f['description'][:260]}")
        return "\n".join(linhas)

    def _acoes_claude(self, resposta, texto, falar, depois, ao_agir):
        """O Claude de reserva pediu ações (linhas FERRAMENTA {...}): executa e fala o resultado."""
        partes = []
        for linha in resposta.splitlines()[:3]:
            m = re.match(r"\s*FERRAMENTA\s*(\{.*\})\s*$", linha)
            if not m: continue
            try: d = json.loads(m.group(1))
            except ValueError: continue
            nome, args = str(d.get("nome", "")), d.get("args") or {}
            if not any(e["function"]["name"] == nome for e in ferramentas.ESQUEMAS) or nome.startswith("email_") or nome == "whatsapp":
                continue
            log.info("Ferramenta pela IA: %s %s", nome, args)
            self.usadas.append((nome, args))
            if ao_agir: ao_agir(nome)
            res, dep = ferramentas.chamar(nome, args, self.cfg, self.mem)
            if dep: depois.append(dep)
            partes.append(str(res))
        if not partes:
            msg = f"Não consegui fazer isso agora, {self.cfg['tratamento']}."; falar(msg); return msg
        bruto = " ".join(partes)
        if len(bruto) <= 220 and "AÇÃO PREPARADA" not in bruto and "Diga isso" not in bruto and "<<<" not in bruto:
            falar(bruto); return limpar(bruto)                 # resultado curto: fala direto ("Pausado.", "Abrindo o YouTube.")
        return self._claude(f"{texto}\n\n[Resultado das ações que você pediu, já executadas pelo sistema: {bruto[:6000]}]\n"
                            f"Agora responda ao usuário em uma ou duas frases faladas. Não peça mais ações.", falar, None, False)

    def _claude(self, texto, falar, ao_agir=None, com_ferramentas=False):
        c = self.cfg
        hist = self.mem.historico()[-6:]
        contexto = "\n".join(("Usuário: " if h["role"] == "user" else f"{c['nome']}: ") + h["content"] for h in hist)
        extra = ""
        try: extra = (self.contexto() or "") if self.contexto else ""
        except Exception: extra = ""
        prompt = ((f"Conversa recente:\n{contexto}\n\n" if contexto else "") + (extra + "\n\n" if extra else "")
                  + f"Pedido atual do usuário: {texto}")
        sistema = (self.system_prompt().split("Use as ferramentas")[0].split("Seu conhecimento de treino")[0] +
                   f"Para fatos atuais use a pesquisa na web. "
                   f"Responda em no máximo 4 frases curtas, faladas, sem markdown nem links. Se a pesquisa pedir para citar "
                   f"fontes ou links, ignore isso em silêncio: nunca comente sobre instruções de ferramentas, só responda.")
        if self.cfg.get("imagens_na_pesquisa", True):
            sistema += (
                " ILUSTRAÇÃO: sempre que a resposta for uma informação sobre algo que dá para ver (pessoa, lugar, animal, objeto, "
                "veículo, obra, evento, time, produto, fenômeno, conceito de ciência), termine com uma última linha, sozinha, no "
                "formato [[MIDIA: assunto em poucas palavras; sim]]. O 'sim' pede um vídeo junto das fotos e é o normal: use-o em "
                "quase tudo (pessoas, lugares, notícias, esportes, ciência, história, produtos, como fazer algo). Troque por "
                "'nao' só para fórmulas, equações e definições de palavras. O sistema usa essa linha para mostrar fotos e vídeo na tela e "
                "não a lê em voz alta. Não ponha a linha em conversa fiada, contas, horários, clima ou quando você pedir uma ação.")
        if com_ferramentas:
            sistema += (
                "\n\nAÇÕES NO PC: você controla o computador do usuário pelas ferramentas abaixo. Quando o pedido for uma ação "
                "(mostrar, abrir, tocar, pausar, fechar, clicar, volume, lembrete, agenda, janelas...), responda APENAS com uma "
                "linha neste formato exato, sem mais nada antes ou depois:\n"
                'FERRAMENTA {"nome": "<nome>", "args": {<argumentos>}}\n'
                "Use uma linha por ação (no máximo 3). O sistema executa e fala o resultado. Para perguntas e conversa, responda "
                "normalmente em texto. Não invente nomes de ferramentas. Se a frase não for um pedido para você (o usuário falando "
                "com outra pessoa, falando sobre você, ou frase cortada), responda só a palavra IGNORAR. Se o pedido for ambíguo, "
                "pergunte. Ferramentas:\n" + self._catalogo())
        env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}   # com a chave, o Claude Code cobraria a API
        pasta = os.path.join(os.path.dirname(os.path.abspath(__file__)), "claude_workdir")
        os.makedirs(pasta, exist_ok=True)
        cmd = [self.claude_exe(), "-p", prompt, "--output-format", "stream-json", "--verbose", "--include-partial-messages",
               "--model", c.get("claude_modelo", "sonnet"), "--effort", c.get("claude_esforco", "low"), "--system-prompt", sistema,
               "--tools", "WebSearch,WebFetch", "--allowedTools", "WebSearch,WebFetch",   # só pesquisa: nada de arquivos ou comandos
               "--max-turns", "6", "--no-session-persistence", "--setting-sources", "project", "--strict-mcp-config"]
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=pasta, env=env,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        buf, tudo, guardada, final, erro = "", "", None, None, None
        marca = []
        def _falar(f):
            if tudo.lstrip().upper().startswith(("FERRAMENTA", "IGNORAR")): return   # pedido de ação: não é para falar
            if marca: return                                    # já entrou na linha [[MIDIA: ...]]: não é para falar
            if "[[" in f: marca.append(1); f = f.split("[[")[0]
            f = limpar(f)
            if f and falavel(f): falar(f.lstrip(" .…"))
        t0 = time.time()
        for linha in p.stdout:
            try: d = json.loads(linha)
            except ValueError: continue
            ev = d.get("event") or {}
            if d.get("type") == "stream_event" and ev.get("type") == "content_block_delta" and ev.get("delta", {}).get("type") == "text_delta":
                pedaco = ev["delta"]["text"]; tudo += pedaco; buf += pedaco
                while True:
                    frase, buf = cortar_frase(buf)
                    if frase is None: break
                    if guardada: _falar(guardada)
                    guardada = frase
            elif d.get("type") == "stream_event" and ev.get("type") == "content_block_start" and \
                    (ev.get("content_block") or {}).get("type") in ("tool_use", "server_tool_use"):
                guardada, buf = None, ""               # texto antes de pesquisar era rascunho
                if ao_agir: ao_agir("pesquisar_web")
            elif d.get("type") == "stream_event" and ev.get("type") == "message_start":
                tudo = ""                              # cada rodada (antes/depois da pesquisa) recomeça o texto
            elif d.get("type") == "result":
                final = d.get("result"); erro = d.get("is_error") and (d.get("result") or d.get("subtype"))
                self._registrar_uso(d, time.time() - t0)
            if time.time() - t0 > c.get("timeout_claude", 60):
                p.kill(); erro = "demorou demais"; break
        p.wait(timeout=10)
        if erro or p.returncode not in (0, None):
            msg = erro or p.stderr.read().decode("utf-8", "replace")[:200]
            if re.search(r"limit|login|logged|auth|usage", str(msg), re.I):
                self.claude_off_ate = time.time() + 1800
                if self.ao_aviso:            # limite da assinatura ou login: avisa no painel que o modelo local assumiu
                    m = re.search(r"resets\s+([\d:]+\s*[ap]m)", str(msg), re.I)
                    self.ao_aviso("> claude no limite da assinatura" + (f" (volta {m.group(1)})" if m else "") + ": usando o modelo local"
                                  if re.search(r"limit|usage", str(msg), re.I) else "> claude sem login: usando o modelo local")
            raise NuvemIndisponivel(f"Claude: {msg}")
        if guardada: _falar(guardada)
        _falar(buf)
        bruto = (final or tudo).strip()
        m = re.search(r"\[\[\s*MIDIA\s*:\s*([^;\]]{2,80})(?:;\s*(\w+))?\s*\]\]", bruto, re.I)
        if m:                                                    # assunto para ilustrar com fotos/vídeo (assistente.py mostra)
            self.usadas.append(("pesquisar_web", {"consulta": m.group(1).strip(), "video": (m.group(2) or "").lower().startswith("s")}))
        bruto = re.sub(r"\s*\[\[.*?(\]\]|$)", "", bruto, flags=re.S).strip()
        if bruto.upper().startswith("FERRAMENTA"): return bruto      # quem chamou executa as ações
        return limpar(bruto)

    def responder_claude(self, texto, falar, ao_agir=None):
        t0 = time.time()
        try:
            resposta = self._claude(texto, falar, ao_agir)
        except (NuvemIndisponivel, OSError) as e:
            log.warning("Claude indisponível: %s", e)
            resposta = f"Não consegui falar com o Claude agora, {self.cfg['tratamento']}. Verifique o login do Claude Code."
            falar(resposta)
            return resposta, []
        log.info("IA (claude, %.1fs): %s", time.time() - t0, resposta)
        self.mem.adicionar_troca(texto, resposta)
        return resposta, []

    def usando_local(self):
        return self.modelos()[0] == self.cfg["ollama_modelo"]

    # ---------------------------------------------------------------- resposta
    def responder(self, texto, falar, ao_agir=None):
        """Gera a resposta chamando falar(frase) para cada frase pronta. Devolve (texto completo, [ações para depois])."""
        self.usadas = []
        pedido = self.pedido_claude(texto)
        if pedido is not None and self.claude_exe():          # "Aton, pergunta pro Claude ..."
            if not pedido:
                msg = f"O que deseja perguntar ao Claude, {self.cfg['tratamento']}?"; falar(msg); return msg, []
            return self.responder_claude(pedido, falar, ao_agir)
        msgs = [{"role": "system", "content": self.system_prompt()}] + self.mem.historico() + [{"role": "user", "content": texto}]
        try:
            extra = (self.contexto() or "") if self.contexto else ""
            if extra: msgs.insert(1, {"role": "system", "content": extra})
        except Exception: pass
        depois, ultimo_erro = [], None
        tnorm = unicodedata.normalize("NFD", texto.lower()); tnorm = "".join(c for c in tnorm if unicodedata.category(c) != "Mn")
        self.privado = bool((self.cfg.get("email_local", True) and EMAIL_RX.search(tnorm)) or
                            (self.cfg.get("whatsapp_local", True) and WPP_RX.search(tnorm)))
        modelos = [self.cfg["ollama_modelo"]] if self.privado else self.modelos()
        if self.privado: log.info("Pergunta sobre e-mail/WhatsApp: usando só o modelo local.")
        for modelo in modelos:
            falou = []
            def _falar(f):
                falou.append(f); falar(f)
            try:
                t0 = time.time()
                if modelo == "claude":           # reserva quando a nuvem do Ollama cai: age pelas mesmas ferramentas
                    resposta = self._claude(texto, _falar, ao_agir, True)
                    if resposta.lstrip().upper().startswith("FERRAMENTA"):
                        resposta = self._acoes_claude(resposta, texto, _falar, depois, ao_agir)
                else:
                    resposta = self._laco(modelo, list(msgs), _falar, depois, ao_agir)
                log.info("IA (%s, %.1fs): %s", modelo, time.time() - t0, resposta)
                self.mem.adicionar_troca(texto, resposta)
                return resposta, depois
            except PrecisaLocal:
                log.info("A nuvem pediu os e-mails: refazendo a pergunta no modelo local.")
                self.privado, self.usadas = True, []
                local = self.cfg["ollama_modelo"]
                resposta = self._laco(local, list(msgs), _falar, depois, ao_agir)
                log.info("IA (%s, %.1fs): %s", local, time.time() - t0, resposta)
                self.mem.adicionar_troca(texto, resposta)
                return resposta, depois
            except NuvemIndisponivel as e:
                ultimo_erro = e
                if falou: break          # já começou a falar: não repete com o outro modelo
                log.warning("Nuvem indisponível (%s); usando o modelo local.", e)
        msg = f"Desculpe, {self.cfg['tratamento']}, não consegui pensar numa resposta agora."
        log.error("Sem resposta da IA: %r", ultimo_erro)
        falar(msg)
        return msg, depois

    def _laco(self, modelo, msgs, falar, depois, ao_agir):
        tudo, feitas = "", {}
        for _ in range(4):                       # no máximo 3 rodadas de ferramentas
            conteudo, chamadas = self._stream(modelo, msgs, falar)
            tudo += (" " if tudo and conteudo else "") + conteudo
            if not chamadas:
                if not limpar(tudo):
                    tudo = "Pronto."; falar(tudo)
                return limpar(tudo)
            msgs.append({"role": "assistant", "content": conteudo, "tool_calls": chamadas})
            for ch in chamadas:
                fn = ch.get("function", {})
                nome, args = fn.get("name", ""), fn.get("arguments") or {}
                if isinstance(args, str):
                    try: args = json.loads(args)
                    except ValueError: args = {}
                if modelo.endswith("cloud") and ((nome.startswith("email_") and self.cfg.get("email_local", True)) or
                                                 (nome == "whatsapp" and self.cfg.get("whatsapp_local", True))):
                    raise PrecisaLocal()
                chave = nome + json.dumps(args, sort_keys=True, ensure_ascii=False)
                if chave in feitas:          # uma tentativa por ação: repetir a mesma chamada não muda o resultado
                    log.info("Ferramenta repetida (%s): não executo de novo.", nome)
                    msgs.append({"role": "tool", "tool_name": nome, "content":
                                 "Essa ação já foi executada neste pedido (resultado: " + feitas[chave][:200] + "). NÃO repita. "
                                 "Responda agora ao usuário, em uma frase, o que aconteceu."})
                    continue
                log.info("Ferramenta pela IA: %s %s", nome, args)
                self.usadas.append((nome, args))
                if ao_agir: ao_agir(nome)
                res, dep = ferramentas.chamar(nome, args, self.cfg, self.mem)
                feitas[chave] = str(res)
                if dep: depois.append(dep)
                msgs.append({"role": "tool", "content": res, "tool_name": nome})
        if not limpar(tudo):                     # esgotou as rodadas sem dizer nada: não pode ficar mudo
            tudo = f"Desculpe, {self.cfg['tratamento']}, não consegui concluir isso."
            falar(tudo)
        return limpar(tudo)

    # ---------------------------------------------------------------- memória automática (em segundo plano)
    def extrair_fatos(self, pergunta, resposta):
        """Depois da resposta já falada, procura fatos duradouros sobre o usuário na troca e guarda na memória.
        Ideia do serviço de memória do OpenJarvis. Só usa a nuvem: não vale carregar o modelo local só para isso."""
        nuvem = self.cfg.get("modelo_nuvem")
        if not nuvem or self.cfg.get("rota") in ("local", "claude") or time.time() < self.nuvem_off_ate or len(pergunta.split()) < 4:
            return
        msgs = [{"role": "system", "content":
                 "Você extrai fatos duradouros sobre o USUÁRIO a partir de uma troca com o assistente: preferências, gostos, "
                 "pessoas próximas, trabalho, rotina, objetivos, coisas que ele possui. Ignore perguntas passageiras, curiosidades "
                 "gerais, compromissos e eventos pontuais (reunião hoje, viagem amanhã: isso é lembrete, não memória), "
                 "o que o assistente disse sobre si mesmo e qualquer dado sensível (senhas, documentos, saúde, finanças "
                 "pessoais detalhadas). Cada fato: uma frase curta em português, na 3ª pessoa ('O usuário ...'). "
                 "Não repita fatos já conhecidos. Responda só JSON: {\"fatos\": [..]} (lista vazia se nada)."},
                {"role": "user", "content": f"Fatos já conhecidos:\n{self.mem.texto_fatos() or '(nenhum)'}\n\n"
                                            f"Usuário: {pergunta}\nAssistente: {resposta}"}]
        body = {"model": nuvem, "stream": False, "format": "json", "think": "low", "messages": msgs, "options": {"temperature": 0.1}}
        try:
            req = urllib.request.Request(self.cfg["ollama_url"] + "/api/chat", data=json.dumps(body).encode("utf-8"),
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=20) as r:
                fatos = json.loads(json.loads(r.read())["message"]["content"]).get("fatos", [])
        except Exception as e:
            log.info("Memória automática pulada: %r", e); return
        for f in fatos[:3]:
            if isinstance(f, str) and 8 < len(f) < 200:
                log.info("Memória automática: %s -> %s", f, self.mem.lembrar(f))

    # ---------------------------------------------------------------- saudação de abertura
    def saudar(self, dados, falar):
        """Saudação curta a partir de dados já coletados (receita do morning_digest do OpenJarvis).
        Só usa a nuvem: no boot o modelo local levaria segundos para carregar; sem nuvem, devolve None."""
        c = self.cfg
        msgs = [{"role": "system", "content":
                 f"Você é {c['nome']}, o assistente de voz do usuário, um mordomo digital elegante. Gere a saudação falada de quando "
                 f"o computador liga: 2 ou 3 frases curtas em português do Brasil, sem markdown, listas ou símbolos. Comece "
                 f"exatamente com o 'cumprimento obrigatorio' dos dados (já calculado pelo relógio; não troque) e trate o usuário "
                 f"por '{c['tratamento']}'. Use SOMENTE os dados "
                 f"fornecidos, não invente nada, e não leia todos os itens se ficar longo: escolha o mais útil."},
                {"role": "user", "content": dados}]
        nuvem = c.get("modelo_nuvem")
        if not nuvem or c.get("rota") in ("local", "claude") or time.time() < self.nuvem_off_ate:
            return None
        try:
            texto, _ = self._stream(nuvem, msgs, falar, com_ferramentas=False)
            return limpar(texto) or None
        except NuvemIndisponivel as e:
            log.warning("Saudação sem nuvem (%s); usando o texto pronto.", e)
            return None

    def _stream(self, modelo, msgs, falar, com_ferramentas=True):
        nuvem = modelo.endswith("cloud")
        body = {"model": modelo, "stream": True, "messages": msgs, "options": {"temperature": 0.6, "num_predict": 400}}
        if com_ferramentas:
            # pergunta de e-mail no modelo local: só as ferramentas de e-mail e hora (o modelo pequeno erra menos)
            body["tools"] = ([e for e in ferramentas.ESQUEMAS if e["function"]["name"].startswith("email_") or e["function"]["name"] in ("hora_data", "whatsapp")]
                             if self.privado and not nuvem else ferramentas.ESQUEMAS)
        if nuvem: body["think"] = "low"
        else:
            body["keep_alive"] = self.cfg["manter_carregado"]
            # modelos locais que "pensam" antes de responder (Qwen 3.x) ficam lentos demais para voz: pensamento desligado
            if modelo.startswith(("qwen3", "gemma4")) and not self.cfg.get("pensar_local", False): body["think"] = False
        req = urllib.request.Request(self.cfg["ollama_url"] + "/api/chat", data=json.dumps(body).encode("utf-8"),
                                     headers={"Content-Type": "application/json"})
        buf, conteudo, chamadas, guardada = "", "", [], None
        def _falar(f):
            f = limpar(f)
            if f and falavel(f): falar(f.lstrip(" .…"))
        try:
            # Timeout por leitura: a nuvem tem que começar rápido; o local pode precisar carregar o modelo.
            with urllib.request.urlopen(req, timeout=self.cfg.get("timeout_nuvem", 8) if nuvem else 120) as r:
                for linha in r:
                    d = json.loads(linha)
                    if d.get("error"): raise NuvemIndisponivel(d["error"])
                    m = d.get("message") or {}
                    if m.get("tool_calls"): chamadas += m["tool_calls"]
                    pedaco = m.get("content") or ""
                    if not pedaco: continue
                    if eh_reenvio(pedaco, conteudo): continue   # a nuvem às vezes reenvia a resposta inteira num bloco só
                    conteudo += pedaco; buf += pedaco
                    if conteudo.lstrip().startswith("{"): continue   # o modelo local às vezes escreve a chamada de ferramenta como texto
                    while True:
                        frase, buf = cortar_frase(buf)
                        if frase is None: break
                        # cada frase só vai para a voz quando a seguinte começa: se a rodada terminar chamando uma
                        # ferramenta, a última frase guardada era rascunho ("Abrindo o arquivo...") e é descartada
                        if guardada: _falar(guardada)
                        guardada = frase
        except urllib.error.HTTPError as e:
            if nuvem:
                self.nuvem_off_ate = time.time() + (1800 if e.code in (401, 402, 403, 429) else 300)
                raise NuvemIndisponivel(f"HTTP {e.code}")
            raise
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            if nuvem:
                self.nuvem_off_ate = time.time() + 300
                raise NuvemIndisponivel(repr(e))
            raise
        if not chamadas and conteudo.lstrip().startswith("{"):
            try:
                j = json.loads(conteudo)
                chamadas = [{"function": {"name": j.get("name", ""), "arguments": j.get("parameters") or j.get("arguments") or {}}}]
                return "", chamadas
            except ValueError:
                pass
        if chamadas:
            return "", chamadas            # texto escrito junto com a chamada de ferramenta é rascunho
        if guardada: _falar(guardada)
        _falar(buf)
        return conteudo, chamadas
