# -*- coding: utf-8 -*-
"""
Ponte Aton <-> Chrome. A extensão (pasta extensao_chrome) conecta em ws://127.0.0.1:8767; o Aton manda comandos
(abas, vídeos, página) e espera a resposta. Só aceita conexões vindas de uma extensão do Chrome (cabeçalho Origin
chrome-extension://), então nenhum site aberto consegue se passar por ela.
"""
import asyncio, itertools, json, logging, threading

log = logging.getLogger("aton")
PORTA = 8767
_LOOP = None
_EXT = {"ws": None}
_ESPERA = {}
_IDS = itertools.count(1)


class SemExtensao(RuntimeError):
    pass


async def _handler(ws):
    origem = (ws.request.headers.get("Origin") or "") if getattr(ws, "request", None) else ""
    if not origem.startswith("chrome-extension://"):
        log.warning("Ponte do Chrome: conexão recusada (origem %r)", origem)
        await ws.close(1008, "origem não permitida"); return
    _EXT["ws"] = ws
    log.info("Extensão do Chrome conectada.")
    asyncio.get_running_loop().create_task(_atualizar_se_velha())
    try:
        async for msg in ws:
            try: m = json.loads(msg)
            except ValueError: continue
            f = _ESPERA.pop(m.get("id"), None)
            if f and not f.done(): f.set_result(m)
    except Exception:
        pass
    finally:
        if _EXT["ws"] is ws:
            _EXT["ws"] = None; log.info("Extensão do Chrome desconectada.")


async def _atualizar_se_velha():
    """Se a extensão carregada no Chrome é mais velha que a da pasta, manda ela se recarregar (sem o usuário mexer)."""
    import os
    try:
        await asyncio.sleep(1)
        man = os.path.join(os.path.dirname(os.path.abspath(__file__)), "extensao_chrome", "manifest.json")
        na_pasta = json.load(open(man, encoding="utf-8"))["version"]
        no_chrome = await _pedir("versao", {}, 5)
        log.info("Extensão do Chrome: versão %s (pasta: %s).", no_chrome, na_pasta)
        if no_chrome != na_pasta:
            log.info("Extensão do Chrome %s -> %s: recarregando.", no_chrome, na_pasta)
            await _pedir("recarregar_extensao", {}, 5)
    except Exception as e:
        log.warning("Não conferi a versão da extensão: %r", e)


async def _servir():
    from websockets.asyncio.server import serve
    async with serve(_handler, "127.0.0.1", PORTA, ping_interval=20):
        await asyncio.Future()


def iniciar():
    def _rodar():
        global _LOOP
        _LOOP = asyncio.new_event_loop()
        asyncio.set_event_loop(_LOOP)
        try: _LOOP.run_until_complete(_servir())
        except Exception as e: log.warning("Ponte do Chrome não iniciou: %r", e)
    threading.Thread(target=_rodar, daemon=True).start()


def conectada():
    return _EXT["ws"] is not None


async def _pedir(cmd, args, timeout):
    ws = _EXT["ws"]
    if ws is None: raise SemExtensao("a extensão do Aton no Chrome não está conectada")
    i = next(_IDS)
    f = asyncio.get_running_loop().create_future()
    _ESPERA[i] = f
    await ws.send(json.dumps({"id": i, "cmd": cmd, "args": args or {}}))
    try: m = await asyncio.wait_for(f, timeout)
    finally: _ESPERA.pop(i, None)
    if not m.get("ok"): raise RuntimeError(m.get("erro") or "falhou")
    return m.get("res")


def pedir(cmd, args=None, timeout=8):
    """Manda um comando para a extensão e devolve a resposta (síncrono, para as threads do Aton)."""
    if _LOOP is None or _EXT["ws"] is None:
        raise SemExtensao("a extensão do Aton no Chrome não está conectada")
    return asyncio.run_coroutine_threadsafe(_pedir(cmd, args, timeout), _LOOP).result(timeout + 1)
