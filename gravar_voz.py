# -*- coding: utf-8 -*-
r"""
Grava a sua voz chamando o Aton, para medir e melhorar a ativação. Tudo fica só no PC, em
amostras_ativacao\sessoes\<data>_<voz|tv>. Rode pelo gravar_minha_voz.bat (ou gravar_com_tv.bat).
- Depois de cada gravação, aperte R em até 2 segundos para regravar (se falou errado).
- Se não detectar fala nenhuma, repete sozinho.
- O Aton é pausado durante a gravação (senão ele responderia) e volta sozinho no fim.
Opções: --tv (sessão com a TV ligada), --broadcast (grava do microfone do NVIDIA Broadcast).
"""
import msvcrt, os, subprocess, sys, time, wave
import numpy as np
import sounddevice as sd

HERE = os.path.dirname(os.path.abspath(__file__))
SR = 16000
TV = "--tv" in sys.argv
PASTA = os.path.join(HERE, "amostras_ativacao", "sessoes", time.strftime("%Y%m%d_%H%M") + ("_tv" if TV else "_voz"))

ROTEIRO = (
    [("aton", "Diga só:  ATON   (no seu tom NORMAL)", 2.5)] * 10 +
    [("aton", "Diga só:  ATON   (mais BAIXO, cansado)", 2.5)] * 6 +
    [("aton", "Diga só:  ATON   (RÁPIDO, de passagem)", 2.5)] * 6 +
    [("aton", "Diga só:  ATON   (um pouco mais LONGE do microfone)", 2.5)] * 4 +
    [("aton", "Diga:  EI ATON", 2.5)] * 3 +
    [("aton", "Diga:  ATON? (como pergunta, chamando)", 2.5)] * 3 +
    [("frase", f"Diga:  ATON, {f}", 4.5) for f in [
        "que horas são?", "abre o YouTube", "pausa a música", "aumenta o volume", "como está o clima hoje?",
        "manda mensagem pro João", "abre o HBO Max", "clica em Séries", "próxima música", "quem me mandou mensagem?",
        "toca minha playlist", "abre o Discord"]] +
    [("neg", f"NÃO chame o Aton. Diga:  {f}", 4.0) for f in [
        "até amanhã", "atum com tomate", "a tomada está solta", "Anton é meu amigo", "o átomo é pequeno",
        "vou pegar um copo de água", "atendi o telefone agora", "a tonalidade ficou boa", "ah, tô cansado",
        "a tontura passou", "o ator foi bem", "aguenta aí"]]
)
ROTEIRO_TV = (
    [("tv", "Fique em SILÊNCIO e deixe só a TV falando (volume de costume)", 8.0)] * 6 +
    [("tvaton", "Com a TV ligada, diga:  ATON", 2.5)] * 10 +
    [("tvfrase", f"Com a TV ligada, diga:  ATON, {f}", 4.5) for f in
     ["que horas são?", "pausa a música", "abre o YouTube", "aumenta o volume", "próxima música", "abre o HBO Max"]]
)


def microfone():
    """O mesmo microfone que o Aton usa ("microfone" no config.json); com --broadcast, o do NVIDIA Broadcast."""
    import json
    try: cfg_mic = (json.load(open(os.path.join(HERE, "config.json"), encoding="utf-8")).get("microfone") or "").lower()
    except Exception: cfg_mic = ""
    apis = [a["name"] for a in sd.query_hostapis()]
    nomes = [n for n in (("nvidia broadcast",) if "--broadcast" in sys.argv else ()) + (cfg_mic,) if n]
    for want in nomes:
        for api in ("MME", "Windows DirectSound"):
            for i, d in enumerate(sd.query_devices()):
                if d["max_input_channels"] > 0 and want in d["name"].lower() and apis[d["hostapi"]] == api:
                    return i
    return None


def salvar(caminho, audio):
    with wave.open(caminho, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((np.clip(audio, -1, 1) * 32767).astype("<i2").tobytes())


def teve_fala(a):
    try:
        sys.path.insert(0, HERE)
        from vad import DetectorVoz
        d = DetectorVoz()
        return sum(d(a[i:i + 1600]) > 0.5 for i in range(0, len(a) - 1600, 1600)) >= 2
    except Exception:
        return float(np.abs(a).max()) > 0.02


def apertou_r(segundos=2.0):
    while msvcrt.kbhit(): msvcrt.getch()          # descarta teclas antigas
    fim = time.time() + segundos
    while time.time() < fim:
        if msvcrt.kbhit() and msvcrt.getch().lower() in (b"r",): return True
        time.sleep(0.05)
    return False


def main():
    roteiro = ROTEIRO_TV if TV else ROTEIRO
    os.makedirs(PASTA, exist_ok=True)
    print("=" * 66)
    print(f"  {'GRAVAR COM A TV LIGADA' if TV else 'GRAVAR A SUA VOZ PARA O ATON'}  ({len(roteiro)} gravações, uns {3 if TV else 7} minutos)")
    print("=" * 66)
    if TV:
        print("\n  1) Ligue a TV num programa com gente FALANDO (jornal, série), no volume de costume.")
        print("  2) Microfone na posição de sempre (topo para a sua boca, TV atrás dele).")
        print("  3) Nas primeiras gravações fique quieto: é para medir só a TV.")
    else:
        print("\n  Fale do jeito do dia a dia, no microfone de sempre.")
        print("  Sem TV nesta sessão. Música baixa pode, se você costuma usar assim.")
    print("\n  >>> Depois de cada gravação: aperte R em até 2 s para REGRAVAR. <<<")
    input("\n  Aperte ENTER para começar...")
    subprocess.run(["cmd", "/c", os.path.join(HERE, "3_parar.bat")], capture_output=True)
    dev = microfone()
    print(f"\n  Microfone: {sd.query_devices(dev)['name'] if dev is not None else 'padrão do Windows'}")
    print(f"  Pasta: {PASTA}\n")
    cont = {}
    try:
        i = 0
        while i < len(roteiro):
            tipo, instr, dur = roteiro[i]
            print(f"  [{i + 1:2}/{len(roteiro)}]  {instr}")
            time.sleep(0.8)                                   # tempo para ler
            for s in (3, 2, 1):
                print(f"         ...{s}", end="\r"); time.sleep(0.5)
            print("         >>> FALE AGORA <<<                      ", end="\r")
            audio = sd.rec(int(dur * SR), samplerate=SR, channels=1, dtype="float32", device=dev)
            sd.wait()
            a = audio[:, 0]
            if tipo != "tv" and not teve_fala(a):
                print("         não ouvi nada: vamos de novo.              ")
                time.sleep(0.6); continue
            print("         gravado.  (R = regravar)                    ", end="\r")
            if apertou_r():
                print("         ok, regravando...                         ")
                continue
            cont[tipo] = cont.get(tipo, 0) + 1
            salvar(os.path.join(PASTA, f"{tipo}_{cont[tipo]:02d}.wav"), a)
            print("         gravado.                                  ")
            i += 1
    finally:
        print("\n  Religando o Aton...")
        subprocess.run(["schtasks", "/run", "/tn", "AI Core Aton"], capture_output=True)
    print("\n  Pronto! Pode fechar esta janela e avisar no chat que terminou.")
    input("  (ENTER para fechar)")


if __name__ == "__main__":
    main()
