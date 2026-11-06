# -*- coding: utf-8 -*-
"""
Memória persistente do Aton: fatos que o usuário pediu para lembrar e o histórico recente da conversa.
Ideia inspirada na memória de fatos do OpenJarvis (Apache-2.0), simplificada para um arquivo JSON.
"""
import datetime, json, os, threading

class Memoria:
    def __init__(self, pasta, max_fatos=200, max_hist=16):
        self.arq = os.path.join(pasta, "memoria.json")
        self.max_fatos, self.max_hist = max_fatos, max_hist
        self.lock = threading.Lock()
        self.fatos, self.hist = [], []
        try:
            with open(self.arq, encoding="utf-8") as f:
                d = json.load(f)
            self.fatos, self.hist = d.get("fatos", []), d.get("historico", [])
        except (FileNotFoundError, ValueError):
            pass

    def _salvar(self):
        tmp = self.arq + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"fatos": self.fatos, "historico": self.hist}, f, ensure_ascii=False, indent=1)
        os.replace(tmp, self.arq)

    def lembrar(self, fato):
        fato = fato.strip().rstrip(".")
        with self.lock:
            if any(f["texto"].lower() == fato.lower() for f in self.fatos):
                return "Isso eu já sabia."
            self.fatos.append({"texto": fato, "quando": datetime.date.today().isoformat()})
            del self.fatos[:-self.max_fatos]
            self._salvar()
        return "Anotado: " + fato

    def esquecer(self, trecho):
        t = trecho.lower().strip()
        with self.lock:
            antes = len(self.fatos)
            self.fatos = [f for f in self.fatos if t not in f["texto"].lower()]
            n = antes - len(self.fatos)
            if n: self._salvar()
        return f"Esqueci {n} anotação(ões)." if n else "Não encontrei nada parecido nas anotações."

    def texto_fatos(self):
        with self.lock:
            return "\n".join(f"- {f['texto']} (anotado em {f['quando']})" for f in self.fatos)

    def adicionar_troca(self, usuario, resposta):
        with self.lock:
            self.hist += [{"role": "user", "content": usuario}, {"role": "assistant", "content": resposta}]
            del self.hist[:-self.max_hist]
            self._salvar()

    def historico(self):
        with self.lock:
            return list(self.hist)
