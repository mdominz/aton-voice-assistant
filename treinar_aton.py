# -*- coding: utf-8 -*-
r"""
Treina um detector da palavra "Aton" com a SUA voz (openWakeWord: impressões digitais de som + um classificador
pequeno por cima). Usa as gravações em amostras_ativacao\ (sessões gravadas e os "Aton" reais guardados pelo uso).

  python treinar_aton.py --teste   -> treina com tudo MENOS a sessão mais nova e mede nela (medida honesta)
  python treinar_aton.py           -> treina com tudo e salva modelos\aton_detector.pkl
"""
import glob, os, pickle, random, sys, wave
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
A = os.path.join(HERE, "amostras_ativacao")
SR, JAN = 16000, 32000            # janela de 2 s (16 "impressões" de 80 ms)
random.seed(7); np.random.seed(7)


def ler(p):
    with wave.open(p) as w:
        return np.frombuffer(w.readframes(w.getnframes()), "<i2").astype("float32") / 32768


_F = {}
def feats():
    if "f" not in _F:
        from openwakeword import utils
        _F["f"] = utils.AudioFeatures(inference_framework="onnx")
    return _F["f"]


def emb(janelas):
    """janelas float32 (n, 32000) -> (n, 16*96)"""
    x = (np.clip(np.asarray(janelas), -1, 1) * 32767).astype(np.int16)
    e = feats().embed_clips(x, batch_size=64)
    return e[:, -16:, :].reshape(len(x), -1)


def fala_regiao(a):
    """(início, fim) em amostras da primeira fala contínua (Silero), juntando pausas curtas."""
    sys.path.insert(0, HERE)
    from vad import DetectorVoz
    d = DetectorVoz(); ativo = []
    for i in range(0, len(a) - 512, 512):
        ativo.append(d(a[i:i + 512]) > 0.5)
    ini = next((i for i, x in enumerate(ativo) if x), None)
    if ini is None: return None
    fim, buraco = ini, 0
    for i in range(ini, len(ativo)):
        if ativo[i]: fim, buraco = i, 0
        else:
            buraco += 1
            if buraco > 8: break                      # ~0,25 s de silêncio: acabou a palavra
    return ini * 512, (fim + 1) * 512


def janela_terminando(a, fim):
    ini = fim - JAN
    if ini < 0: a = np.concatenate([np.zeros(-ini, "float32"), a]); fim -= ini; ini = 0
    w = a[ini:fim]
    return np.concatenate([w, np.zeros(JAN - len(w), "float32")]) if len(w) < JAN else w


def janelas_deslizantes(a, passo=0.16):
    a = np.concatenate([np.zeros(JAN // 2, "float32"), a, np.zeros(SR // 2, "float32")])
    p = int(passo * SR)
    return [a[i:i + JAN] for i in range(0, len(a) - JAN + 1, p)] or [janela_terminando(a, len(a))]


FRASES_NEG = """até amanhã|até logo|atum com tomate|a tomada está solta|o átomo é pequeno|o ator foi muito bem|atendi o telefone
a tonalidade ficou boa|ah tô cansado|a tontura passou|aguenta aí|tom sobre tom|que tom bonito|o tom da voz|anton chegou
o pato nadou|bato na porta|cato as folhas|o rato correu|o prato está quente|ato de coragem|é um fato|o gato dormiu
tá bom então|ah tá|então tá|tô indo|vamos lá|e aí beleza|olha só isso|não sei não|pode ser|com certeza
hoje vai chover|o jogo começou agora|o time ganhou ontem|a reunião foi adiada|o preço subiu de novo|a notícia saiu hoje
o presidente falou|a previsão do tempo|o trânsito está parado|a polícia chegou|o médico atendeu|a escola fechou
liga a televisão|desliga o rádio|abre a janela|fecha a porta|me passa o sal|cadê o controle|vem jantar
eu acho que sim|eu não concordo|ele disse que vinha|ela foi embora|nós vamos amanhã|vocês viram isso
um dois três quatro|cinco seis sete|segunda terça quarta|janeiro fevereiro março|bom dia boa tarde boa noite
atenção senhores passageiros|atualização disponível|automóvel novo|autor do livro|ataque do time|atrás da casa
a tom jobim|no tom certo|atolado na lama|aton de ouro é diferente|antonio chegou|atona e tônica
estamos ao vivo|voltamos já|fique ligado|daqui a pouco|no próximo bloco|chegou a hora|agora é com você""".replace("\n", "|").split("|")


def negativos_tts():
    """Gera (uma vez) frases faladas por vozes sintéticas como exemplos de 'fala que não é Aton'."""
    pasta = os.path.join(A, "negativos_tts"); os.makedirs(pasta, exist_ok=True)
    feitos = glob.glob(os.path.join(pasta, "*.wav"))
    if len(feitos) >= len(FRASES_NEG) * 2: return feitos
    import asyncio, io, av, edge_tts
    async def falar(t, v):
        b = b""
        async for c in edge_tts.Communicate(t, v).stream():
            if c["type"] == "audio": b += c["data"]
        return b
    vozes = ["pt-BR-AntonioNeural", "pt-BR-FranciscaNeural", "pt-BR-ThalitaMultilingualNeural"]
    for i, frase in enumerate(FRASES_NEG):
        for v in vozes:
            arq = os.path.join(pasta, f"neg_{i:03d}_{v[6:12]}.wav")
            if os.path.exists(arq): continue
            try:
                c = av.open(io.BytesIO(asyncio.run(falar(frase.strip(), v)))); r = av.AudioResampler("s16", "mono", SR)
                pcm = b"".join(bytes(g.planes[0])[: g.samples * 2] for f in c.decode(audio=0) for g in r.resample(f))
                with wave.open(arq, "wb") as w: w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR); w.writeframes(pcm)
            except Exception as e:
                print("  tts falhou:", frase, v, e)
    return glob.glob(os.path.join(pasta, "*.wav"))


def arquivos(sem_sessoes=False):
    """{'pos', 'neg', 'tv', 'frase'} -> caminhos. sem_sessoes: deixa as sessões novas só para o teste."""
    out = {"pos": [], "neg": [], "tv": [], "frase": []}
    pastas = [os.path.join(A, "gravadas"), os.path.join(A, "gravadas_broadcast")]
    if not sem_sessoes: pastas += sorted(glob.glob(os.path.join(A, "sessoes", "*")))
    for d in pastas:
        for p in glob.glob(os.path.join(d, "*.wav")):
            t = os.path.basename(p).split("_")[0]
            if t in ("aton", "tvaton"): out["pos"].append(p)
            elif t == "neg": out["neg"].append(p)
            elif t == "tv": out["tv"].append(p)
            elif t in ("frase", "tvfrase"): out["frase"].append(p)
    out["pos"] += glob.glob(os.path.join(A, "aton_*.wav"))          # "Aton" reais guardados pelo uso
    out["neg"] += negativos_tts()
    return out


def montar(arqs):
    tv = [ler(p) for p in arqs["tv"]]
    X, y = [], []
    for p in arqs["pos"]:
        a = ler(p); r = fala_regiao(a)
        if not r or float(np.abs(a).max()) < 0.01: continue
        for desloc in (0.0, 0.15, 0.3):
            fim = r[1] + int(desloc * SR)
            for ganho in (0.6, 1.4):
                w = janela_terminando(a, fim) * ganho
                X.append(w); y.append(1)
                if tv:                                   # o mesmo "Aton" com a TV por baixo
                    t = random.choice(tv); i = random.randint(0, max(0, len(t) - JAN))
                    ruido = t[i:i + JAN]; ruido = np.pad(ruido, (0, JAN - len(ruido)))
                    X.append(w + ruido * random.uniform(0.5, 1.3)); y.append(1)
        X.append(janela_terminando(a, max(JAN // 4, r[0] - SR // 4))); y.append(0)   # antes de falar: silêncio
    for p in arqs["neg"] + arqs["tv"]:
        a = ler(p)
        if "negativos_tts" in p: a = a * random.uniform(0.15, 0.5)    # voz sintética vem alta: deixa no nível de microfone
        for w in janelas_deslizantes(a, passo=0.2):
            X.append(w); y.append(0)
            X.append(w * random.uniform(0.4, 1.8)); y.append(0)
            if tv and "negativos_tts" in p:                            # fala + TV por baixo
                t = random.choice(tv); i = random.randint(0, max(0, len(t) - JAN))
                X.append(w + np.pad(t[i:i + JAN], (0, max(0, JAN - len(t[i:i + JAN])))) * 0.8); y.append(0)
    for p in arqs["frase"]:                               # o RESTO do pedido (depois do "Aton,") é negativo
        a = ler(p); r = fala_regiao(a)
        if not r: continue
        for w in janelas_deslizantes(a[r[1] + SR // 2:], passo=0.3): X.append(w); y.append(0)
    print(f"  janelas: {sum(y)} positivas, {len(y) - sum(y)} negativas")
    return emb(X), np.array(y)


def treinar(X, y):
    from sklearn.neural_network import MLPClassifier
    from sklearn.preprocessing import StandardScaler
    from sklearn.pipeline import make_pipeline
    m = make_pipeline(StandardScaler(),
                      MLPClassifier(hidden_layer_sizes=(64,), alpha=1e-2, max_iter=400, early_stopping=True, random_state=0))
    m.fit(X, y)
    return m


def pontuar(m, a):
    """Maior nota do detector ao longo de um áudio (como se fosse escutando ao vivo)."""
    return float(m.predict_proba(emb(janelas_deslizantes(a)))[:, 1].max())


def main():
    teste = "--teste" in sys.argv
    print(f"Treinando{' SEM as sessões novas (ficam para o teste)' if teste else ' com tudo'}...")
    X, y = montar(arquivos(sem_sessoes=teste))
    m = treinar(X, y)
    if not teste:
        os.makedirs(os.path.join(HERE, "modelos"), exist_ok=True)
        with open(os.path.join(HERE, "modelos", "aton_detector.pkl"), "wb") as f: pickle.dump(m, f)
        print("Salvo em modelos\\aton_detector.pkl"); return
    # teste honesto: só na(s) pasta(s) da sessão mais nova
    res = {}
    for d in glob.glob(os.path.join(A, "sessoes", "*")):
        for p in sorted(glob.glob(os.path.join(d, "*.wav"))):
            t = os.path.basename(p).split("_")[0]
            res.setdefault(t, []).append((os.path.basename(d)[-3:] + "/" + os.path.basename(p), pontuar(m, ler(p))))
    with open(os.path.join(HERE, "modelos", "aton_teste_notas.pkl"), "wb") as f: pickle.dump(res, f)
    for limiar in (0.3, 0.5, 0.7, 0.8, 0.9, 0.95):
        lin = []
        for t, v in res.items():
            hits = sum(n >= limiar for _, n in v)
            lin.append(f"{t} {'acordou ' if t in ('neg', 'tv') else ''}{hits}/{len(v)}")
        print(f"  limiar {limiar:.2f}: " + " | ".join(lin))


if __name__ == "__main__":
    main()
