# -*- coding: utf-8 -*-
"""
Servidor MCP do Aton: deixa o Claude Code (ou qualquer cliente MCP) usar as MESMAS ferramentas do Aton
— volume, Spotify, Bluetooth, janelas, área de transferência, agenda, lembretes, arquivos... — sem reescrever nada.

Registrado no Claude Code com:
    claude mcp add aton --scope user -- "<pasta>\\venv\\Scripts\\python.exe" "<pasta>\\aton_mcp.py"
Remover:  claude mcp remove aton --scope user

Roda só quando o cliente abre (stdio, sem porta de rede). Ações perigosas (fechar programas, desligar o PC,
organizar pastas) continuam pedindo confirmação: a ferramenta devolve "AÇÃO PREPARADA" e só roda depois de
aton_confirmar.
"""
import json, logging, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE); sys.path.insert(0, HERE)
# o protocolo MCP usa a saída padrão: todo log vai para o arquivo, nunca para o stdout
logging.basicConfig(filename=os.path.join(HERE, "aton_mcp.log"), level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s", encoding="utf-8")
_stdout, sys.stdout = sys.stdout, sys.stderr          # nenhum print dos módulos do Aton pode sujar o protocolo
import ferramentas, memoria, bracos                   # noqa: E402
sys.stdout = _stdout

from mcp.server.mcpserver import MCPServer           # noqa: E402

CFG = json.load(open(os.path.join(HERE, "config.json"), encoding="utf-8"))
MEM = memoria.Memoria(HERE)
# ferramentas que só fazem sentido dentro do Aton falando (ou que ele mesmo dispara)
FORA = {"tarefa_segundo_plano"}

mcp = MCPServer("aton", instructions=(
    "Ferramentas do assistente Aton no PC Windows do usuário (som, Spotify, Bluetooth, janelas, área de transferência, "
    "agenda, lembretes, arquivos, YouTube). Use aton_ferramentas para ver a lista e os parâmetros, e aton_usar para "
    "executar. Se a resposta disser 'AÇÃO PREPARADA', confirme com o usuário antes de chamar aton_confirmar."))


def _lista():
    out = []
    for e in ferramentas.ESQUEMAS:
        f = e["function"]
        if f["name"] in FORA: continue
        out.append({"nome": f["name"], "descricao": f["description"], "parametros": f["parameters"].get("properties", {}),
                    "obrigatorios": f["parameters"].get("required", [])})
    return out


@mcp.tool()
def aton_ferramentas() -> str:
    """Lista as ferramentas do Aton com descrição e parâmetros (JSON)."""
    return json.dumps(_lista(), ensure_ascii=False, indent=1)


@mcp.tool()
def aton_usar(ferramenta: str, argumentos: dict | None = None) -> str:
    """Executa uma ferramenta do Aton pelo nome (veja aton_ferramentas), com os argumentos em JSON."""
    nomes = {f["nome"] for f in _lista()}
    if ferramenta not in nomes:
        return f"Ferramenta desconhecida: {ferramenta}. Disponíveis: {', '.join(sorted(nomes))}"
    logging.info("MCP usar %s %s", ferramenta, argumentos)
    texto, depois = ferramentas.chamar(ferramenta, argumentos or {}, CFG, MEM)
    if depois:                                         # ações que o Aton faria depois de falar (ex.: dar play, digitar)
        try: depois()
        except Exception as e: texto += f" (a ação final falhou: {e})"
    return texto


@mcp.tool()
def aton_confirmar(confirmar: bool = True) -> str:
    """Confirma (ou cancela, com confirmar=false) a ação perigosa que uma ferramenta deixou preparada."""
    return bracos.confirmar() if confirmar else bracos.cancelar()


if __name__ == "__main__":
    mcp.run("stdio")
