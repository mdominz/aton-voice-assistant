# -*- coding: utf-8 -*-
"""
Sons do Aton, sintetizados do zero (sem amostras de terceiros): estilos suaves no lugar do bipe do Windows.
Cada estilo tem 3 versões: ativacao (começou a ouvir), continuar (modo conversa) e lembrete (aviso).
Gerar as amostras:  venv\\Scripts\\python.exe sons.py
"""
import os, sys
import numpy as np
import soundfile as sf

SR = 44100
HERE = os.path.dirname(os.path.abspath(__file__))

def _t(seg): return np.arange(int(SR * seg)) / SR

def _env(n, ataque=0.01, decai=0.2, total=None):
    """Envelope: subida suave (seno) + queda exponencial."""
    t = np.arange(n) / SR
    a = np.clip(t / max(ataque, 1e-4), 0, 1); a = np.sin(a * np.pi / 2) ** 2
    return a * np.exp(-np.maximum(t - ataque, 0) / max(decai, 1e-4))

def _fim(x, ms=25):
    n = int(SR * ms / 1000); x = x.copy(); x[-n:] *= np.linspace(1, 0, n); return x

def _norm(x, pico=0.5):
    return (x / (np.abs(x).max() or 1) * pico).astype(np.float32)

def _reverb(x, mix=0.25):
    y = np.concatenate([x, np.zeros(int(SR * 0.6))])
    for seg, g in ((0.031, .5), (0.047, .42), (0.071, .33), (0.097, .25), (0.137, .17), (0.191, .1)):
        d = int(SR * seg); y[d:d + len(x)] += mix * g * x
    return y

def _seq(*partes, gap=0.0):
    out = []
    for i, p in enumerate(partes):
        out.append(p)
        if gap and i < len(partes) - 1: out.append(np.zeros(int(SR * gap)))
    return np.concatenate(out)

def _mix(*partes):
    n = max(len(p) for p in partes); y = np.zeros(n)
    for p in partes: y[:len(p)] += p
    return y

# ------------------------------------------------------------------ estilos
def gota(f0=880, cai=0.55, dur=0.28):
    """Gota d'água: senoide com o tom caindo rápido e decaimento curto."""
    t = _t(dur); f = f0 * (1 + cai * np.exp(-t / 0.018))
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * _env(len(t), 0.002, 0.06)

def vidro(f0=1320, dur=0.9, forca=1.0):
    """Sino de vidro leve: parciais não harmônicas, ataque macio."""
    t = _t(dur); x = np.zeros_like(t)
    for mult, amp, dec in ((1, 1, .35), (2.76, .35, .18), (5.4, .12, .09)):
        x += amp * np.sin(2 * np.pi * f0 * mult * t) * np.exp(-t / dec)
    return x * _env(len(t), 0.006, 10) * forca

def acorde(notas, dur=0.55, passo=0.07):
    """Notas suaves (seno + harmônico baixo), uma depois da outra, com ataque lento."""
    partes = []
    for i, f in enumerate(notas):
        t = _t(dur); x = (np.sin(2 * np.pi * f * t) + .18 * np.sin(2 * np.pi * 2 * f * t)) * _env(len(t), 0.03, 0.25)
        partes.append(np.concatenate([np.zeros(int(SR * passo * i)), x]))
    return _mix(*partes)

def respiro(dur=0.45, subir=True, cor=1800):
    """Sopro: ruído filtrado que cresce e some, como uma respiração curta."""
    n = int(SR * dur); r = np.random.default_rng(7).standard_normal(n)
    esp = np.fft.rfft(r); f = np.fft.rfftfreq(n, 1 / SR)
    esp *= np.exp(-((f - cor) / (cor * .6)) ** 2)                      # banda em volta de "cor" Hz
    x = np.fft.irfft(esp, n)
    t = np.arange(n) / n
    forma = np.sin(np.pi * (t ** (0.6 if subir else 1.6)))             # sobe rápido (ativação) ou some devagar
    return x * forma

def nucleo(f0=110, dur=0.6, subir=True):
    """Pulso do núcleo: zumbido grave e quente que incha e some (combina com o wallpaper)."""
    t = _t(dur); f = f0 * (1 + (0.25 if subir else -0.15) * t / dur)
    fase = 2 * np.pi * np.cumsum(f) / SR
    x = np.sin(fase) + .5 * np.sin(2 * fase) + .22 * np.sin(3 * fase) + .1 * np.sin(5 * fase)
    return x * np.sin(np.pi * np.clip(t / dur, 0, 1)) ** 1.5

def tique(f0=2400, dur=0.06):
    """Toque de vidro mínimo: um 'tic' curtíssimo e abafado."""
    t = _t(dur)
    return (np.sin(2 * np.pi * f0 * t) + .4 * np.sin(2 * np.pi * f0 * 1.5 * t)) * _env(len(t), 0.001, 0.012)

ESTILOS = {
    "1_gota": {
        "ativacao": lambda: _reverb(_seq(gota(660), gota(990), gap=0.04), .2),
        "continuar": lambda: _reverb(gota(880, dur=0.2), .15) * .7,
        "lembrete": lambda: _reverb(_seq(gota(990), gota(740), gota(990), gap=0.07), .25)},
    "2_vidro": {
        "ativacao": lambda: _reverb(_mix(vidro(1046.5), np.concatenate([np.zeros(int(SR * .08)), vidro(1568, forca=.7)])), .3),
        "continuar": lambda: _reverb(vidro(1318.5, .6, .6), .25),
        "lembrete": lambda: _reverb(_seq(vidro(1568, .5), vidro(1318.5, .5), vidro(1568, .8)), .3)},
    "3_acorde_suave": {
        "ativacao": lambda: _reverb(acorde([523.25, 659.25, 783.99]), .3),           # dó-mi-sol subindo
        "continuar": lambda: _reverb(acorde([659.25, 783.99], .4, .05), .25) * .7,
        "lembrete": lambda: _reverb(_seq(acorde([783.99, 659.25], .45), acorde([783.99, 987.77], .6), gap=.05), .3)},
    "4_respiro": {
        "ativacao": lambda: _reverb(_mix(respiro(.5, True, 1600), .25 * acorde([880], .5)), .2),
        "continuar": lambda: respiro(.3, True, 2200) * .7,
        "lembrete": lambda: _reverb(_seq(respiro(.35, True, 1400), respiro(.45, False, 1900), gap=.05), .2)},
    "5_pulso_do_nucleo": {
        "ativacao": lambda: _reverb(_mix(nucleo(110, .6, True), .3 * acorde([440, 660], .5, .1)), .25),
        "continuar": lambda: _reverb(nucleo(130, .35, True), .2) * .8,
        "lembrete": lambda: _reverb(_seq(nucleo(110, .4), nucleo(147, .55), gap=.05), .25)},
    "6_tique_de_vidro": {
        "ativacao": lambda: _reverb(_seq(tique(2000), tique(2800), gap=.05), .3),
        "continuar": lambda: _reverb(tique(2400), .25) * .7,
        "lembrete": lambda: _reverb(_seq(tique(2800), tique(2000), tique(2800), gap=.09), .3)},
}

def gerar(pasta):
    os.makedirs(pasta, exist_ok=True)
    for estilo, sons in ESTILOS.items():
        for momento, fn in sons.items():
            sf.write(os.path.join(pasta, f"{estilo}_{momento}.wav"), _norm(_fim(fn()), 0.45), SR)

def caminho(estilo, momento):
    return os.path.join(HERE, "sons", f"{estilo}_{momento}.wav")

if __name__ == "__main__":
    destino = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "amostras_sons")
    gerar(destino); print("Amostras em", destino)
