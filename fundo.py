# -*- coding: utf-8 -*-
"""
"Ducking": quando você chama o Aton, o som dos outros programas (Spotify, Chrome/YouTube, jogos, Discord...)
desce para uma fração do volume e volta ao fim da conversa — como a Alexa e a Siri fazem.

- Mexe só no volume de cada programa no mixer do Windows (nunca no volume geral nem no do próprio Aton).
- Se durante a conversa o volume de um programa for mudado (por você ou por um comando), ele não é desfeito.
- Os volumes originais ficam num arquivo: se o Aton cair com o som abaixado, ele devolve ao iniciar de novo.
"""
import json, logging, os, threading, time

log = logging.getLogger("aton")
HERE = os.path.dirname(os.path.abspath(__file__))
ARQ = os.path.join(HERE, "volumes_antes_do_aton.json")
_LOCK = threading.Lock()
_ESTADO = {"abaixado": {}}           # chave do programa -> (volume original, volume que o Aton pôs)


def _sessoes():
    import comtypes
    from pycaw.pycaw import AudioUtilities
    try: comtypes.CoInitialize()
    except OSError: pass
    meu = os.getpid()
    out = []
    for s in AudioUtilities.GetAllSessions():
        p = s.Process
        if p is None or p.pid == meu: continue                    # sem processo = sons do sistema
        try:
            if any(a.pid == meu for a in p.parents()): continue   # o próprio Aton (e os filhos dele)
        except Exception:
            pass
        nome = p.name().lower()
        if nome.startswith(("python", "pythonw")): continue
        out.append((f"{nome}:{p.pid}", s.SimpleAudioVolume))
    return out


def _salvar():
    try:
        with open(ARQ, "w", encoding="utf-8") as f:
            json.dump({k: v[0] for k, v in _ESTADO["abaixado"].items()}, f)
    except OSError:
        pass


def abaixar(fracao=0.25, passos=4):
    """Desce o volume de cada programa que está tocando para `fracao` do atual, numa rampa curta."""
    with _LOCK:
        if _ESTADO["abaixado"]: return                               # já está abaixado (conversa em andamento)
        try: sess = _sessoes()
        except Exception as e:
            log.warning("Abaixar o som de fundo falhou: %r", e); return
        alvo = {}
        for chave, vol in sess:
            try:
                atual = vol.GetMasterVolume()
                if atual <= 0.02 or vol.GetMute(): continue
                alvo[chave] = (vol, atual, atual * fracao)
            except Exception:
                continue
        if not alvo: return
        for i in range(1, passos + 1):                              # rampa: não dá "tranco" na música
            for chave, (vol, ini, fim) in alvo.items():
                try: vol.SetMasterVolume(ini + (fim - ini) * i / passos, None)
                except Exception: pass
            time.sleep(0.03)
        _ESTADO["abaixado"] = {k: (ini, fim) for k, (vol, ini, fim) in alvo.items()}
        _salvar()
        log.info("Som de fundo abaixado (%d programa(s)).", len(alvo))


def restaurar(passos=6):
    """Devolve cada programa ao volume de antes (se ninguém mexeu nele durante a conversa)."""
    with _LOCK:
        guardado = dict(_ESTADO["abaixado"])
        _ESTADO["abaixado"] = {}
        if not guardado: return
        try: sess = dict(_sessoes())
        except Exception as e:
            log.warning("Restaurar o som de fundo falhou: %r", e); return
        volta = {}
        for chave, (ini, posto) in guardado.items():
            vol = sess.get(chave)
            if not vol: continue                                     # o programa fechou
            try:
                agora = vol.GetMasterVolume()
                if abs(agora - posto) > 0.03: continue               # mudaram o volume dele durante a conversa: respeita
                volta[chave] = (vol, agora, ini)
            except Exception:
                continue
        for i in range(1, passos + 1):
            for chave, (vol, de, para) in volta.items():
                try: vol.SetMasterVolume(de + (para - de) * i / passos, None)
                except Exception: pass
            time.sleep(0.04)
        try: os.remove(ARQ)
        except OSError: pass


def restaurar_se_ficou():
    """Ao iniciar: se o Aton caiu com o som abaixado, devolve os volumes guardados no arquivo."""
    if not os.path.exists(ARQ): return
    try:
        with open(ARQ, encoding="utf-8") as f: antes = json.load(f)
        sess = dict(_sessoes())
        n = 0
        for chave, ini in antes.items():
            if chave in sess:
                sess[chave].SetMasterVolume(float(ini), None); n += 1
        log.info("Volumes restaurados depois de uma queda do Aton (%d programa(s)).", n)
    except Exception as e:
        log.warning("Não restaurei os volumes guardados: %r", e)
    finally:
        try: os.remove(ARQ)
        except OSError: pass
