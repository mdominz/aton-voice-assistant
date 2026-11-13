# -*- coding: utf-8 -*-
"""
Tela de configurações do Aton (pwa/config.html) e notificações push do app do celular.
As rotas entram no mesmo servidor do app (aton_remote.py, só 127.0.0.1 + Tailscale) e exigem o token do aton_token.txt.
Só os campos listados em CAMPOS podem ser lidos ou alterados: chaves de API, IDs e tokens nunca passam por aqui.
"""
import json, logging, os, shutil, subprocess, threading

log = logging.getLogger("aton")
HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.join(HERE, "config.json")

def _c(chave, rotulo, tipo, grupo, ajuda="", opcoes=None, minimo=None, maximo=None, reinicia=False):
    return {"chave": chave, "rotulo": rotulo, "tipo": tipo, "grupo": grupo, "ajuda": ajuda, "opcoes": opcoes,
            "min": minimo, "max": maximo, "reinicia": reinicia}

CAMPOS = [
    _c("tratamento", "Como o Aton te chama", "texto", "Geral", "Ex.: senhor, chefe. Vazio = não usa."),
    _c("cidade", "Cidade (clima)", "texto", "Geral"),
    _c("microfone", "Microfone", "microfone", "Geral", "Vazio = o padrão do Windows.", reinicia=True),
    _c("respostas_por_voz", "Responder por voz", "sim_nao", "Voz", "Desligado: responde só por escrito."),
    _c("voz", "Voz", "lista", "Voz", opcoes=["pt-BR-AntonioNeural", "pt-BR-FranciscaNeural", "pt-BR-ThalitaNeural"]),
    _c("velocidade_voz", "Velocidade da voz", "lista", "Voz", opcoes=["-10%", "+0%", "+10%", "+20%", "+30%"]),
    _c("efeito_voz", "Efeito de voz", "lista", "Voz", opcoes=["", "leve", "medio", "forte"]),
    _c("voz_offline_privado", "Voz offline para e-mail e WhatsApp", "sim_nao", "Voz", "Esse conteúdo não vai para a voz online."),
    _c("so_comandos", "Modo só comandos (sem IA)", "sim_nao", "Inteligência", "Só obedece à lista de comandos."),
    _c("rota", "Onde a IA roda", "lista", "Inteligência",
       "claude = Claude (sua assinatura), com o modelo local de reserva; local = só no PC; auto = nuvem do Ollama primeiro.",
       opcoes=["claude", "local", "auto"]),
    _c("claude_modelo", "Modelo do Claude", "lista", "Inteligência", "claude-sonnet-5-5 = travado nessa versão; sonnet/haiku/opus = sempre a versão mais nova de cada um.",
       opcoes=["claude-sonnet-5-5", "haiku", "sonnet", "opus"]),
    _c("claude_esforco", "Esforço do Claude", "lista", "Inteligência", "low = respostas mais rápidas; high = pensa mais antes de responder.",
       opcoes=["low", "medium", "high"]),
    _c("claude_reserva", "Permitir o uso do Claude", "sim_nao", "Inteligência"),
    _c("memoria_automatica", "Lembrar fatos das conversas", "sim_nao", "Inteligência"),
    _c("ativacao_por_voz", "Acordar dizendo \"Aton\"", "sim_nao", "Escuta", "Desligado: só o atalho do teclado.", reinicia=True),
    _c("modo_conversa", "Continuar ouvindo depois de responder", "sim_nao", "Escuta"),
    _c("fim_fala", "Pausa que encerra a sua fala (segundos)", "numero", "Escuta",
       "Maior = ele espera mais antes de achar que você terminou (bom para quem pensa no meio da frase).", minimo=0.5, maximo=3),
    _c("espera_continuar", "Segundos esperando a próxima fala", "numero", "Escuta", minimo=3, maximo=20),
    _c("interromper_por_voz", "Interromper a fala dizendo \"Aton\"", "sim_nao", "Escuta"),
    _c("abaixar_fundo", "Abaixar o som dos outros programas", "sim_nao", "Escuta"),
    _c("nivel_fundo", "Volume dos outros programas enquanto fala (0 a 1)", "numero", "Escuta", minimo=0, maximo=1),
    _c("limiar_detector", "Rigor do detector da sua voz (0.9 a 0.999)", "numero", "Escuta",
       "Mais alto = menos ativações por engano.", minimo=0.9, maximo=0.999),
    _c("log_ativacao", "Registrar no log o que foi ignorado", "sim_nao", "Escuta"),
    _c("coletar_amostras_ativacao", "Guardar gravações do \"Aton\" para treino", "sim_nao", "Escuta"),
    _c("chrome_perfil", "Perfil do Chrome", "perfil_chrome", "Recursos", "Onde o Aton abre sites e vídeos. Vazio = o último perfil usado.",
       reinicia=True),
    _c("resumo_matinal", "Resumo do dia na primeira saudação da manhã", "sim_nao", "Recursos",
       "Clima, agenda, lembretes, e-mails e manchetes, uma vez por dia entre 5h e 12h."),
    _c("imagens_na_pesquisa", "Mostrar imagens da internet nas pesquisas", "sim_nao", "Recursos"),
    _c("notificacoes_celular", "Notificações no celular", "sim_nao", "Recursos"),
    _c("app_celular", "App do celular", "sim_nao", "Recursos", reinicia=True),
    _c("ponte_chrome", "Controle do Chrome (extensão)", "sim_nao", "Recursos", reinicia=True),
    _c("reiniciar_wallpaper", "Reiniciar o wallpaper ao trocar a saída de som", "sim_nao", "Recursos"),
]
PADRAO = {"respostas_por_voz": True, "voz_offline_privado": False, "so_comandos": False, "rota": "auto", "claude_reserva": True,
          "memoria_automatica": True, "ativacao_por_voz": True, "modo_conversa": True, "espera_continuar": 5,
          "interromper_por_voz": True, "abaixar_fundo": True, "nivel_fundo": 0.25, "limiar_detector": 0.97, "log_ativacao": False,
          "coletar_amostras_ativacao": True, "imagens_na_pesquisa": True, "resumo_matinal": True, "notificacoes_celular": True, "app_celular": True,
          "ponte_chrome": True, "reiniciar_wallpaper": True, "tratamento": "senhor", "cidade": "", "microfone": "",
          "claude_modelo": "sonnet", "claude_esforco": "low", "chrome_perfil": "", "voz": "pt-BR-AntonioNeural", "velocidade_voz": "+0%", "efeito_voz": ""}

def _ler():
    try:
        with open(CONFIG, encoding="utf-8-sig") as f: return json.load(f)
    except FileNotFoundError:
        return {}

def _microfones():
    try:
        import sounddevice as sd
        apis = [a["name"] for a in sd.query_hostapis()]
        return sorted({d["name"] for d in sd.query_devices() if d["max_input_channels"] > 0 and apis[d["hostapi"]] == "MME"
                       and "mapeador" not in d["name"].lower() and "mapper" not in d["name"].lower()})
    except Exception:
        return []

def _perfis_chrome():
    """[{pasta, nome}] dos perfis do Chrome deste PC (só o nome que aparece no Chrome; nada de e-mail)."""
    try:
        with open(os.path.expandvars(r"%LocalAppData%\Google\Chrome\User Data\Local State"), encoding="utf-8") as f:
            info = json.load(f)["profile"]["info_cache"]
        return [{"pasta": k, "nome": v.get("name") or k} for k, v in sorted(info.items())]
    except Exception:
        return []

def estado():
    cfg = _ler()
    campos = []
    for c in CAMPOS:
        c = dict(c)
        if c["tipo"] == "lista" and cfg.get(c["chave"]) not in (None, *c["opcoes"]): c["opcoes"] = c["opcoes"] + [cfg[c["chave"]]]
        campos.append(c)
    return {"campos": campos, "valores": {c["chave"]: cfg.get(c["chave"], PADRAO.get(c["chave"])) for c in CAMPOS},
            "microfones": _microfones(), "perfis_chrome": _perfis_chrome()}

def _validar(c, v):
    if c["tipo"] == "sim_nao":
        if not isinstance(v, bool): raise ValueError(f"{c['rotulo']}: esperava ligado/desligado")
        return v
    if c["tipo"] == "numero":
        if isinstance(v, bool) or not isinstance(v, (int, float)): raise ValueError(f"{c['rotulo']}: esperava um número")
        if (c["min"] is not None and v < c["min"]) or (c["max"] is not None and v > c["max"]):
            raise ValueError(f"{c['rotulo']}: fica entre {c['min']} e {c['max']}")
        return v
    if not isinstance(v, str) or len(v) > 80 or any(ch in v for ch in "\r\n\0"):
        raise ValueError(f"{c['rotulo']}: texto inválido")
    if c["tipo"] == "perfil_chrome" and v and v not in [p["pasta"] for p in _perfis_chrome()]:
        raise ValueError(f"{c['rotulo']}: perfil desconhecido")
    if c["tipo"] == "lista" and v not in c["opcoes"] and v != _ler().get(c["chave"]):
        raise ValueError(f"{c['rotulo']}: opção desconhecida")
    return v.strip()

def salvar(valores, aplicar=None):
    """Grava só as chaves conhecidas (as outras do config.json ficam como estão). Devolve {mudou, reiniciar}."""
    por_chave = {c["chave"]: c for c in CAMPOS}
    cfg, mudou, reiniciar = _ler(), {}, False
    for k, v in (valores or {}).items():
        if k not in por_chave: raise ValueError(f"Campo não permitido: {k}")
        v = _validar(por_chave[k], v)
        if cfg.get(k, PADRAO.get(k)) != v:
            mudou[k] = v; reiniciar = reiniciar or por_chave[k]["reinicia"]
    if mudou:
        if os.path.exists(CONFIG): shutil.copyfile(CONFIG, CONFIG + ".bak")
        cfg.update(mudou)
        tmp = CONFIG + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f: json.dump(cfg, f, ensure_ascii=False, indent=2)
        os.replace(tmp, CONFIG)
        log.info("Configurações alteradas pela tela: %s", ", ".join(mudou))
        if aplicar: aplicar(mudou)                    # vale na hora para o que não precisa reiniciar
    return {"mudou": sorted(mudou), "reiniciar": reiniciar}

def reiniciar_aton():
    """Fecha este Aton e liga de novo (aton_ligar.bat), sem janela."""
    def _r():
        subprocess.Popen(["cmd", "/c", os.path.join(HERE, "aton_ligar.bat")], cwd=HERE,
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
    threading.Timer(1.0, _r).start()

# ------------------------------------------------------------------ notificações push (Web Push)
# A chave fica só no PC (vapid_private.pem). O texto viaja cifrado de ponta a ponta até o celular; o serviço de push da
# Apple/Google só entrega, não consegue ler.
VAPID = os.path.join(HERE, "vapid_private.pem")
INSCRICOES = os.path.join(HERE, "push_inscricoes.json")
_trava = threading.Lock()

def _vapid():
    from py_vapid import Vapid
    if not os.path.exists(VAPID):
        v = Vapid(); v.generate_keys(); v.save_key(VAPID)
    return Vapid.from_file(VAPID)

def chave_publica():
    import base64
    from cryptography.hazmat.primitives import serialization
    pub = _vapid().public_key.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    return base64.urlsafe_b64encode(pub).rstrip(b"=").decode()

def _inscricoes():
    try:
        with open(INSCRICOES, encoding="utf-8") as f: return json.load(f)
    except (FileNotFoundError, ValueError):
        return []

def inscrever(sub):
    if not isinstance(sub, dict) or not str(sub.get("endpoint", "")).startswith("https://") or "keys" not in sub:
        raise ValueError("inscrição inválida")
    with _trava:
        subs = [s for s in _inscricoes() if s.get("endpoint") != sub["endpoint"]] + [sub]
        with open(INSCRICOES, "w", encoding="utf-8") as f: json.dump(subs[-10:], f)
    log.info("Celular inscrito para notificações (%d aparelho(s)).", len(subs))
    return len(subs)

def enviar_push(texto, titulo="Aton"):
    """Manda a notificação para os celulares inscritos. Devolve quantos receberam."""
    subs = _inscricoes()
    if not subs or not _ler().get("notificacoes_celular", True): return 0
    from pywebpush import webpush, WebPushException
    contato = _ler().get("push_contato") or "mailto:aton@example.com"
    ok, vivos = 0, []
    for s in subs:
        try:
            webpush(s, json.dumps({"titulo": titulo, "texto": texto[:300]}, ensure_ascii=False), vapid_private_key=VAPID,
                    vapid_claims={"sub": contato}, ttl=3600, timeout=10)
            ok += 1; vivos.append(s)
        except WebPushException as e:
            cod = getattr(e.response, "status_code", None)
            if cod in (404, 410): log.info("Inscrição de push expirada: removida.")
            else: vivos.append(s); log.warning("Push falhou (%s): %s", cod, str(e)[:160])
        except Exception as e:
            vivos.append(s); log.warning("Push falhou: %r", e)
    if len(vivos) != len(subs):
        with _trava:
            with open(INSCRICOES, "w", encoding="utf-8") as f: json.dump(vivos, f)
    return ok
