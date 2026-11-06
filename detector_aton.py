# -*- coding: utf-8 -*-
"""
Detector do "Aton" treinado com a sua voz (treinar_aton.py -> modelos\aton_detector.pkl).
Roda ao vivo junto com a escuta: a cada pedaço do microfone dá uma nota de 0 a 1 ("isto soa como o seu Aton?").
Sozinho ele não ativa nada: o Aton só aceita a nota alta se o Whisper também ouviu algo compatível
(1-2 palavras curtas, como "Ah", "Ata", "Pato", ou "aton" logo no começo). Medido em 2026-11-04 com
sessões que o detector nunca ouviu: o "Aton" sozinho foi de 72% para 94%, sem ativar com a TV.
"""
import logging, os, pickle
import numpy as np

log = logging.getLogger("aton")
HERE = os.path.dirname(os.path.abspath(__file__))
ARQ = os.path.join(HERE, "modelos", "aton_detector.pkl")


class Detector:
    def __init__(self):
        from openwakeword import utils
        with open(ARQ, "rb") as f: self.clf = pickle.load(f)
        self.f = utils.AudioFeatures(inference_framework="onnx")

    def zerar(self):
        self.f.reset()

    def ouvir(self, x):
        """x: bloco float32 de 16 kHz. Devolve a nota do "Aton" (0 a 1) dos últimos 2 s."""
        self.f((np.clip(x, -1, 1) * 32767).astype(np.int16))
        e = self.f.get_features(16)
        if e.shape[1] < 16: return 0.0
        return float(self.clf.predict_proba(e.reshape(1, -1))[0, 1])


def carregar():
    if not os.path.exists(ARQ): return None
    try:
        d = Detector()
        log.info("Detector do \"Aton\" com a sua voz carregado.")
        return d
    except Exception as e:
        log.warning("Detector do Aton não carregou (%r); só o Whisper confere.", e)
        return None
