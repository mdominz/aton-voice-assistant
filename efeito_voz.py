# -*- coding: utf-8 -*-
"""
Efeito "IA de filme" aplicado por cima da voz (não troca a voz, só o acabamento):
filtro de alto-falante + eco metálico curto + chorus leve + reverb curto de sala.
Tudo em numpy; leva poucos milissegundos por frase.
"""
import numpy as np

NIVEIS = {   # intensidade de cada parte por nível
    "leve":  {"banda": (90, 9000), "eco": ((0.015, 0.18),), "chorus": 0.10, "reverb": 0.08},
    "medio": {"banda": (130, 7500), "eco": ((0.015, 0.25), (0.031, 0.12)), "chorus": 0.18, "reverb": 0.14},
    "forte": {"banda": (180, 6000), "eco": ((0.012, 0.32), (0.024, 0.2), (0.037, 0.1)), "chorus": 0.28, "reverb": 0.2},
}

def _banda(x, sr, lo, hi):
    """Filtro passa-banda suave (FFT): corta graves e agudos extremos, como um alto-falante de painel."""
    n = len(x)
    f = np.fft.rfftfreq(n, 1 / sr)
    g = np.clip((f - lo * 0.6) / (lo * 0.4), 0, 1) * np.clip((hi * 1.3 - f) / (hi * 0.3), 0, 1)
    return np.fft.irfft(np.fft.rfft(x) * g, n)

def _eco(x, sr, taps):
    y = x.copy()
    for seg, ganho in taps:
        d = int(sr * seg)
        y[d:] += ganho * x[:-d]
    return y

def _chorus(x, sr, mix, base=0.008, prof=0.0025, freq=0.8):
    """Cópia com atraso oscilando levemente: dá o brilho "sintético"."""
    t = np.arange(len(x))
    atraso = (base + prof * np.sin(2 * np.pi * freq * t / sr)) * sr
    return x + mix * np.interp(t - atraso, t, x, left=0.0)

def _reverb(x, sr, mix):
    y = x.copy()
    for seg, ganho in ((0.043, 0.5), (0.061, 0.4), (0.079, 0.3), (0.113, 0.2)):
        d = int(sr * seg)
        y[d:] += mix * ganho * x[:-d]
    return y

def aplicar(audio, sr, nivel="medio"):
    p = NIVEIS.get(nivel)
    if not p:
        return audio
    x = audio.astype(np.float64)
    if x.ndim > 1: x = x.mean(axis=1)
    pico = float(np.abs(x).max()) or 1.0
    y = _banda(x, sr, *p["banda"])
    y = _eco(y, sr, p["eco"])
    y = _chorus(y, sr, p["chorus"])
    y = _reverb(y, sr, p["reverb"])
    return (y / (float(np.abs(y).max()) or 1.0) * min(pico, 0.95)).astype(np.float32)   # mesmo volume do original
