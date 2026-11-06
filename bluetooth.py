# -*- coding: utf-8 -*-
"""
Bluetooth do Aton: ligar/desligar o rádio, bateria dos aparelhos, conectar/desconectar fones e caixas já pareados
e trocar a saída de som do Windows. Parear um aparelho novo continua sendo pelas Configurações do Windows.

Conectar usa o truque das ferramentas tipo ToothTray: desliga e religa os serviços de áudio (A2DP/mãos-livres)
do aparelho pareado, o que faz o Windows conectar nele. Desconectar desliga esses serviços.
"""
import asyncio, ctypes, json, logging, re, subprocess, time, unicodedata
from ctypes import wintypes

log = logging.getLogger("aton")
SEM_JANELA = getattr(subprocess, "CREATE_NO_WINDOW", 0)

def _norm(t):
    t = unicodedata.normalize("NFD", (t or "").lower())
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", "".join(c for c in t if unicodedata.category(c) != "Mn"))).strip()

# ------------------------------------------------------------------ rádio (liga/desliga)
def _radio():
    from winrt.windows.devices.radios import Radio, RadioKind
    async def f():
        await Radio.request_access_async()
        return next((r for r in await Radio.get_radios_async() if r.kind == RadioKind.BLUETOOTH), None)
    return asyncio.run(f())

def estado():
    from winrt.windows.devices.radios import RadioState
    r = _radio()
    if not r: return "Não achei o adaptador Bluetooth."
    return "O Bluetooth está ligado." if r.state == RadioState.ON else "O Bluetooth está desligado."

def ligar(on=True):
    from winrt.windows.devices.radios import RadioState
    r = _radio()
    if not r: return "Não achei o adaptador Bluetooth."
    async def f(): return await r.set_state_async(RadioState.ON if on else RadioState.OFF)
    res = asyncio.run(f())
    if int(res) != 1: return "O Windows não deixou mudar o Bluetooth."   # 1 = Allowed
    return "Bluetooth ligado." if on else "Bluetooth desligado."

# ------------------------------------------------------------------ bateria (propriedade do Windows para aparelhos BT)
PS_BATERIA = ("Get-PnpDevice -Class Bluetooth -Status OK | % { $b=(Get-PnpDeviceProperty -InstanceId $_.InstanceId "
              "-KeyName '{104EA319-6EE2-4701-BD47-8DDBF425BBE5} 2' -ErrorAction SilentlyContinue).Data; "
              "if($b -ne $null){ [pscustomobject]@{n=$_.FriendlyName;b=$b} } } | ConvertTo-Json -Compress")

def baterias():
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command", PS_BATERIA], capture_output=True, text=True,
                             timeout=20, creationflags=SEM_JANELA).stdout.strip()
        lst = json.loads(out) if out else []
    except Exception as e:
        log.warning("Bateria BT falhou: %r", e); return {}
    if isinstance(lst, dict): lst = [lst]
    res = {}
    for d in lst:   # um aparelho aparece várias vezes (um por serviço); fica o menor valor
        nome = re.sub(r"(Transporte de Avrcp|Avrcp Transport|Hands-Free.*|Mãos Livres.*)$", "", d["n"]).strip()
        res[nome] = min(res.get(nome, 999), int(d["b"]))
    return res

def bateria(nome=""):
    b = baterias()
    if not b: return "Nenhum aparelho Bluetooth conectado informou a bateria."
    if nome:
        achou = {k: v for k, v in b.items() if _norm(nome) in _norm(k) or any(p in _norm(k) for p in _norm(nome).split() if len(p) > 2)}
        if achou: b = achou
    return "; ".join(f"{k}: {v}%" for k, v in b.items()) + "."

# ------------------------------------------------------------------ aparelhos pareados (API clássica do Windows)
class _SYSTEMTIME(ctypes.Structure):
    _fields_ = [(n, wintypes.WORD) for n in ("y", "m", "dw", "d", "h", "mi", "s", "ms")]

class _INFO(ctypes.Structure):
    _fields_ = [("dwSize", wintypes.DWORD), ("Address", ctypes.c_ulonglong), ("ulClassofDevice", wintypes.ULONG),
                ("fConnected", wintypes.BOOL), ("fRemembered", wintypes.BOOL), ("fAuthenticated", wintypes.BOOL),
                ("stLastSeen", _SYSTEMTIME), ("stLastUsed", _SYSTEMTIME), ("szName", wintypes.WCHAR * 248)]

class _BUSCA(ctypes.Structure):
    _fields_ = [("dwSize", wintypes.DWORD), ("fReturnAuthenticated", wintypes.BOOL), ("fReturnRemembered", wintypes.BOOL),
                ("fReturnUnknown", wintypes.BOOL), ("fReturnConnected", wintypes.BOOL), ("fIssueInquiry", wintypes.BOOL),
                ("cTimeoutMultiplier", ctypes.c_ubyte), ("hRadio", wintypes.HANDLE)]

class _GUID(ctypes.Structure):
    _fields_ = [("a", wintypes.DWORD), ("b", wintypes.WORD), ("c", wintypes.WORD), ("d", ctypes.c_ubyte * 8)]

def _guid(curto):
    return _GUID(curto, 0x0000, 0x1000, (ctypes.c_ubyte * 8)(0x80, 0x00, 0x00, 0x80, 0x5F, 0x9B, 0x34, 0xFB))

SERVICOS_AUDIO = (0x110B, 0x111E)   # A2DP (fone/caixa) e mãos-livres

def _bt():
    dll = ctypes.WinDLL("bthprops.cpl")
    dll.BluetoothFindFirstDevice.restype = wintypes.HANDLE
    return dll

def pareados():
    dll, lst = _bt(), []
    p = _BUSCA(ctypes.sizeof(_BUSCA), 1, 1, 0, 1, 0, 0, None)
    i = _INFO(); i.dwSize = ctypes.sizeof(_INFO)
    h = dll.BluetoothFindFirstDevice(ctypes.byref(p), ctypes.byref(i))
    if not h: return lst
    try:
        while True:
            lst.append(dict(nome=i.szName, conectado=bool(i.fConnected), info=_INFO.from_buffer_copy(i)))
            i = _INFO(); i.dwSize = ctypes.sizeof(_INFO)
            if not dll.BluetoothFindNextDevice(wintypes.HANDLE(h), ctypes.byref(i)): break
    finally:
        dll.BluetoothFindDeviceClose(wintypes.HANDLE(h))
    return lst

def _achar(nome):
    lst = pareados(); n = _norm(nome)
    if not lst: return None, lst
    if n in ("fone", "fone de ouvido", "headphone", "caixa", "caixa de som", "meu fone", ""):
        # sem nome: o aparelho de áudio pareado (classe de dispositivo 0x04 = áudio/vídeo)
        audio = [d for d in lst if (d["info"].ulClassofDevice >> 8) & 0x1F == 0x04]
        return (audio[0] if audio else None), lst
    for d in lst:
        if n in _norm(d["nome"]) or any(p in _norm(d["nome"]) for p in n.split() if len(p) > 2): return d, lst
    return None, lst

def _servicos(d, ligar_):
    dll = _bt()
    for s in SERVICOS_AUDIO:
        dll.BluetoothSetServiceState(None, ctypes.byref(d["info"]), ctypes.byref(_guid(s)), 1 if ligar_ else 0)

def conectar(nome=""):
    d, lst = _achar(nome)
    if not d:
        return "Não achei esse aparelho entre os pareados" + (f" ({', '.join(x['nome'] for x in lst)})." if lst else ".")
    _servicos(d, False); time.sleep(1.0); _servicos(d, True)
    for _ in range(12):           # espera a saída de som do aparelho aparecer e passa o som para ela
        time.sleep(1)
        if trocar_saida(d["nome"], silencioso=True, estrito=True): return f"{d['nome']} conectado, som passado para ele."
    return f"Pedi a conexão com {d['nome']}. Se não conectar, ligue o aparelho e peça de novo."

def desconectar(nome=""):
    d, lst = _achar(nome)
    if not d: return "Não achei esse aparelho entre os pareados."
    _servicos(d, False)
    return f"{d['nome']} desconectado."

# ------------------------------------------------------------------ saída de som do Windows
APELIDOS = {"monitor": "ultrawide", "tela": "ultrawide", "lg": "ultrawide", "pc": "high definition", "computador": "high definition"}

def saidas():
    from pycaw.pycaw import AudioUtilities, EDataFlow
    return [d for d in AudioUtilities.GetAllDevices(data_flow=EDataFlow.eRender.value) if "Active" in str(d.state)
            and "steam" not in _norm(d.FriendlyName)]

def trocar_saida(nome, silencioso=False, estrito=False):
    import comtypes
    from pycaw.pycaw import AudioUtilities
    try: comtypes.CoInitialize()
    except OSError: pass
    n = re.sub(r"^(?:o|a|meu|minha) ", "", _norm(nome)); n = APELIDOS.get(n, n)
    if n in ("fone", "fone de ouvido", "fone bluetooth", "headphone", "caixa", "caixa de som"):
        bt = [d["nome"] for d in pareados() if (d["info"].ulClassofDevice >> 8) & 0x1F == 0x04]
        for alvo in bt + ["headphones"]:
            r = trocar_saida(alvo, silencioso=True, estrito=True)
            if r: return r
    for d in saidas():
        fn = _norm(d.FriendlyName)
        if n in fn or (not estrito and any(p in fn for p in n.split() if len(p) > 2)):
            AudioUtilities.SetDefaultDevice(d.id)
            return f"Som saindo em {d.FriendlyName}."
    if silencioso: return None
    return "Não achei essa saída. Tenho: " + ", ".join(d.FriendlyName for d in saidas()) + "."
