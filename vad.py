"""
Detector de voz (Silero VAD) em tempo real: diz se cada pedaço do microfone é fala humana ou não.
Usa o modelo que já vem com o faster-whisper (sem baixar nada). Roda no processador (~0,1 ms por pedaço).

Uso:  d = DetectorVoz();  prob = d(bloco_float32_16khz)   # 0..1, a maior probabilidade do bloco
O estado (memória do modelo) passa de um bloco para o outro; chame d.zerar() ao abrir um microfone novo.
"""
import os
import numpy as np

JANELA, CONTEXTO = 512, 64          # 32 ms a 16 kHz (o que o modelo espera) + 4 ms do pedaço anterior


class DetectorVoz:
    def __init__(self):
        import onnxruntime
        import faster_whisper.vad as fv
        caminho = os.path.join(os.path.dirname(fv.__file__), "assets", "silero_vad_v6.onnx")
        op = onnxruntime.SessionOptions()
        op.inter_op_num_threads = op.intra_op_num_threads = 1
        op.log_severity_level = 4
        self.s = onnxruntime.InferenceSession(caminho, providers=["CPUExecutionProvider"], sess_options=op)
        self.zerar()

    def zerar(self):
        self.h = np.zeros((1, 1, 128), "float32")
        self.c = np.zeros((1, 1, 128), "float32")
        self.ctx = np.zeros(CONTEXTO, "float32")
        self.resto = np.zeros(0, "float32")

    def __call__(self, x):
        """Probabilidade de fala (0..1) do bloco. Sobras menores que 32 ms ficam para o próximo bloco."""
        x = np.concatenate([self.resto, np.asarray(x, "float32").ravel()])
        n = len(x) // JANELA
        self.resto = x[n * JANELA:]
        melhor = 0.0
        for i in range(n):
            j = x[i * JANELA:(i + 1) * JANELA]
            entrada = np.concatenate([self.ctx, j])[None, :]
            p, self.h, self.c = self.s.run(None, {"input": entrada, "h": self.h, "c": self.c})
            self.ctx = j[-CONTEXTO:]
            melhor = max(melhor, float(np.ravel(p)[0]))
        return melhor
