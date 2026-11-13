# -*- coding: utf-8 -*-
"""Gera LISTA_DE_COMANDOS.html: todos os comandos do Aton + os seus (meus_comandos.txt). Roda sozinho quando você
pergunta "Aton, quais comandos você conhece?" e pode ser rodado à mão: venv\\Scripts\\python.exe gerar_lista.py"""
import html, os, time

HERE = os.path.dirname(os.path.abspath(__file__))
SAIDA = os.path.join(HERE, "LISTA_DE_COMANDOS.html")

# (frase de exemplo, o que faz, fixo?)  fixo=True: comando pré-programado (funciona no modo "só comandos");
# fixo=False: entendido pela IA (não funciona no modo "só comandos")
CATEGORIAS = [
    ("Controle do Aton", [
        ("Aton", "Chama o Aton (o som do PC abaixa enquanto vocês conversam)", True),
        ("Ctrl+Alt+P  ·  botão “Aton - Pausar ou Retomar”", "Pausa: para de escutar e de falar sozinho; de novo, retoma", True),
        ("Ctrl+Alt+Espaço", "Fala com o Aton sem dizer o nome (funciona mesmo pausado)", True),
        ("modo silencioso  /  pode voltar a falar", "Responde só por escrito / volta a falar", True),
        ("modo só comandos  /  modo inteligente", "Só obedece à lista (sem IA) / usa a IA no que não estiver na lista", True),
        ("abre a lista de comandos  /  quais comandos você conhece?", "Abre esta lista", True),
        ("bom dia  /  resumo do dia  /  o que tenho pra hoje?", "Clima, agenda, lembretes, e-mails e manchetes, falado e num cartão (sem IA)", True),
        ("abre a segunda notícia  /  desce  /  volta pras notícias", "No modo pesquisa: lê a notícia na própria tela", True),
        ("modo agente: abre o bloco de notas e escreve uma lista", "Olha a tela e age passo a passo (mouse e teclado); para com Ctrl+Alt+P", False),
        ("resume essa notícia  /  o que isso muda pra mim?", "Com uma notícia aberta no modo pesquisa: a resposta aparece no leitor", False),
        ("abre o histórico  /  o que eu te perguntei ontem sobre vulcões?", "Histórico das conversas (na tela ou por voz)", False),
        ("modo jogo  ·  Ctrl+Win+P", "Pausa o Aton e apaga o painel até você apertar Ctrl+Win+P (o atalho também entra no modo)", True),
        ("modo pesquisa  /  fecha a pesquisa", "Tela grande com a resposta, 6 fotos, 3 vídeos e links", True),
        ("toca o vídeo  /  toca o segundo vídeo  /  fecha o vídeo", "Toca o vídeo dentro do painel, sem abrir o navegador", True),
        ("abre as configurações do Aton", "Abre a tela de configurações (também no app do celular)", True),
        ("abre o YouTube e aumenta o volume", "Vários comandos na mesma frase, em ordem", True),
        ("(ele pergunta) Quer que eu abra a página?  →  sim", "Quando oferece uma alternativa, o “sim” executa", True),
        ("não, eu falei HBO Max", "Logo depois de um erro: aprende a palavra certa e refaz o pedido", True),
        ("aprende a palavra Crunchyroll  /  esquece a correção do Biomax", "Ensina ou apaga palavras do reconhecimento", False),
    ]),
    ("Música e som", [
        ("toca  /  pausa  /  próxima  /  volta a música", "Controla o player que estiver tocando (Spotify primeiro)", True),
        ("que música está tocando?", "Diz a música e o artista", True),
        ("toca a playlist Treino  /  toca Queen  /  curte essa música", "Spotify pelo nome", False),
        ("aumenta  /  abaixa o volume  /  muta", "Volume geral do PC", True),
        ("coloca o volume no 50", "Volume geral num valor exato", True),
        ("aumenta o volume do Spotify  /  volume do Discord no 30", "Volume só de um programa", True),
    ]),
    ("Filmes e vídeos (Chrome: HBO Max, Netflix, YouTube, Prime...)", [
        ("pausa o filme  /  continua o filme", "Pausa ou continua o vídeo da guia aberta", True),
        ("dá play  /  assiste  /  reproduzir", "Na página do filme/série clica em Assistir/Reproduzir (clique real)", True),
        ("volta 10 segundos  /  avança 1 minuto  /  volta um pouco", "Pula no vídeo", True),
        ("pula a abertura  /  pula o anúncio  /  próximo episódio", "Botões do player", True),
        ("tela cheia  /  sai da tela cheia  /  muta o vídeo", "Aperta F / Esc / M, conferindo antes se está em tela cheia", True),
        ("quanto falta pro filme acabar?", "", True),
        ("pausa o YouTube  /  pausa a Netflix", "Só age se esse site estiver aberto; senão avisa", True),
        ("coloca o vídeo em picture in picture", "Janela flutuante por cima de tudo; de novo, volta para a página", True),
        ("abre o vídeo Como Correr", "Clica no vídeo com esse nome NA PÁGINA aberta (mesma guia)", True),
        ("liga a legenda  /  próximo vídeo", "Só no YouTube", True),
        ("mostra imagens de aurora boreal  /  mostra vídeos de Porsche", "Fotos (e um vídeo) da internet no painel e no celular, com links", True),
        ("me mostra um Porsche  /  me mostra a fórmula de Bhaskara", "A IA decide se vale mostrar vídeo junto das fotos", False),
        ("abre o vídeo  /  abre a pesquisa  /  abre mais imagens", "Logo depois de mostrar: abre no navegador", True),
        ("o que está aberto?", "Diz qual janela ou guia está na frente", True),
        ("toca o vídeo de receita de bolo  /  toca lofi no YouTube", "Abre o vídeo direto no YouTube", True),
    ]),
    ("Sites, páginas e guias", [
        ("abre o HBO Max  /  abre o site da Kabum", "Abre o site (os conhecidos direto; os outros pela busca)", True),
        ("pesquisa receita de bolo no YouTube  /  no Google", "Abre já com a busca feita", True),
        ("pesquisa The Last of Us aqui", "Usa a busca do PRÓPRIO site aberto", True),
        ("clica em Séries  /  clica em Continuar assistindo", "Clica no link/botão com esse texto", True),
        ("abre o terceiro vídeo  /  o primeiro resultado  /  o episódio 4", "Escolhe na lista da página", True),
        ("o que dá pra clicar aqui?", "Lê os botões e links da página", True),
        ("desce  /  sobe a página  ·  vai pro topo  /  fim da página", "SEMPRE na guia aberta do Chrome (sem Chrome: janela da frente)", True),
        ("abre uma nova guia  /  fecha essa guia  /  fecha a guia do YouTube", "", True),
        ("fecha as outras guias  /  reabre a guia que fechei", "", True),
        ("vai pra guia do WhatsApp  /  próxima guia  /  recarrega a página  /  volta a página", "", True),
        ("resume essa página  /  quais guias estão abertas?", "Lê a página para a IA", False),
    ]),
    ("Programas e janelas", [
        ("abre o Discord  /  abre o LoL  /  abre a calculadora", "Qualquer programa do Menu Iniciar", True),
        ("coloca o Chrome na esquerda e o Spotify na direita", "Lado a lado", True),
        ("maximiza o Chrome  /  minimiza o Discord", "", True),
        ("minimiza tudo menos o Spotify  /  fecha tudo menos o Chrome", "Fechar pede “sim”", True),
        ("fecha o Discord", "Fecha um programa (pede “sim”)", False),
        ("quais janelas estão abertas?", "", False),
    ]),
    ("Teclado e cliques em qualquer programa (janela da frente)", [
        ("salva  /  salvar como  /  desfaz  /  refaz", "", True),
        ("copia  /  cola  /  recorta  /  seleciona tudo", "", True),
        ("fecha essa janela  /  troca de janela  /  imprime", "", True),
        ("aperta enter  /  aperta F5  /  aperta control shift T  /  aperta seta pra baixo 3 vezes", "Qualquer tecla", True),
        ("clica em Arquivo  →  clica em Salvar como", "Botões e menus de qualquer programa", True),
        ("marca a opção X  /  desmarca X", "Caixas de marcar", True),
        ("digite olá mundo e aperte enter", "Digita na janela da frente", True),
        ("mostra a área de trabalho  /  bloqueia o computador  /  aumenta o zoom", "", True),
    ]),
    ("WhatsApp (aplicativo do PC)", [
        ("tenho mensagens novas no WhatsApp?", "Quem mandou e um trecho (IA local, não sai do PC)", False),
        ("lê as últimas mensagens do João", "", False),
        ("manda pro João que eu já tô chegando", "Diz o contato e o texto e só envia depois do seu “sim”", False),
    ]),
    ("Bluetooth e saída de som", [
        ("liga  /  desliga o Bluetooth  /  o Bluetooth está ligado?", "Desligar pede “sim”", True),
        ("conecta meu fone  /  desconecta o fone", "Aparelhos já pareados", True),
        ("quanto de bateria tem o fone?", "", True),
        ("passa o som pro fone  /  coloca o som no monitor", "Troca a saída de som", True),
    ]),
    ("Agenda, lembretes e e-mail", [
        ("me lembra de ligar pro dentista daqui a 30 minutos  /  às 15h", "", False),
        ("marca na agenda reunião quinta às 10h  /  o que eu tenho amanhã?", "", False),
        ("tenho e-mail novo?  /  tem e-mail do banco?", "Outlook (IA local)", False),
    ]),
    ("Informação e ajudas", [
        ("que horas são?  /  que dia é hoje?  /  como está o clima?", "", True),
        ("o que tem na minha tela?", "Print + Claude (só olha, não clica)", True),
        ("traduz pro inglês o que eu copiei  /  resume o que eu copiei", "Área de transferência", False),
        ("pesquisa os melhores notebooks e me avisa", "Tarefa em segundo plano (relatório na pasta tarefas)", False),
        ("cotação do dólar  /  me avisa se o dólar passar de 6 reais", "", False),
        ("pergunta pro Claude ...", "Manda a pergunta direto para o Claude", False),
    ]),
]


def gerar():
    import scripts_aton
    scripts_aton._CACHE["mtime"] = None
    sc = scripts_aton.carregar()
    meus = {}
    for frase, (nome, passos) in sc.items():
        meus.setdefault(nome, {"frases": [], "passos": passos})["frases"].append(frase)
    e = html.escape
    secoes = []
    for titulo, itens in CATEGORIAS:
        linhas = "".join(
            f'<tr><td class="f">{e(f)}</td><td>{e(o)}</td><td class="t">{"⚡ fixo" if fx else "🧠 IA"}</td></tr>' for f, o, fx in itens)
        secoes.append(f'<section><h2>{e(titulo)}</h2><table>{linhas}</table></section>')
    if meus:
        cards = "".join(
            f'<div class="card"><h3>{e(n)}</h3><p class="fr">{" · ".join(e(x) for x in v["frases"])}</p><ol>'
            + "".join(f"<li><b>{e(a)}</b> {e(arg)}</li>" for a, arg in v["passos"]) + "</ol></div>" for n, v in meus.items())
    else:
        cards = "<p>Nenhum ainda. Abra o meus_comandos.txt e crie o primeiro.</p>"
    pagina = f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Comandos do Aton</title><style>
:root{{--bg:#f6f7f9;--card:#fff;--tx:#1b1f24;--mut:#5b6573;--ln:#e3e6ea;--ac:#1e5bff}}
@media (prefers-color-scheme:dark){{:root{{--bg:#0f1216;--card:#171b21;--tx:#e8ebef;--mut:#9aa4b2;--ln:#262c35;--ac:#6e9bff}}}}
body{{margin:0;background:var(--bg);color:var(--tx);font:15px/1.5 "Segoe UI",system-ui,sans-serif}}
main{{max-width:1000px;margin:0 auto;padding:28px 16px 60px}} h1{{margin:0 0 4px;font-size:26px}}
.sub{{color:var(--mut);margin:0 0 22px}} section{{background:var(--card);border:1px solid var(--ln);border-radius:12px;padding:6px 18px 12px;margin:0 0 16px}}
h2{{font-size:17px;margin:12px 0 8px;color:var(--ac)}} table{{width:100%;border-collapse:collapse}}
td{{padding:7px 8px;border-top:1px solid var(--ln);vertical-align:top}} tr:first-child td{{border-top:0}}
td.f{{width:46%;font-weight:600}} td.t{{width:72px;color:var(--mut);font-size:13px;white-space:nowrap;text-align:right}}
.box{{background:var(--card);border:1px solid var(--ln);border-left:4px solid var(--ac);border-radius:12px;padding:12px 18px;margin:0 0 16px}}
.cards{{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:12px}}
.card{{background:var(--card);border:1px solid var(--ln);border-radius:12px;padding:10px 16px}} .card h3{{margin:6px 0 2px}}
.fr{{color:var(--mut);margin:0 0 6px}} code{{background:var(--ln);padding:1px 5px;border-radius:5px}}
@media (max-width:640px){{td.f{{width:auto}} td.t{{width:auto}}}}
@media print{{body{{background:#fff}} section,.box,.card{{break-inside:avoid}}}}
</style></head><body><main>
<h1>Comandos do Aton</h1><p class="sub">Diga “Aton, …” e o comando. Atualizada em {time.strftime("%d/%m/%Y %H:%M")}.
⚡ fixo = comando pré-programado, sempre igual e instantâneo (funciona no modo “só comandos”). 🧠 IA = entendido pela inteligência artificial.</p>
<div class="box"><b>Meus comandos</b> — você cria no arquivo <code>meus_comandos.txt</code> (pasta do Aton). Salvou, já vale.
Diga “Aton, quais comandos você conhece?” para atualizar esta lista.</div>
<div class="cards">{cards}</div><br>
{"".join(secoes)}
<div class="box"><b>Para preencher depois</b> — ideias de comandos seus: modo trabalho · hora de dormir · modo reunião ·
modo estudo · abrir meu banco · preparar o PC para jogar · abrir os sites do trabalho · ligar a live.<br>
Passos possíveis: <code>abrir</code> <code>site</code> <code>esperar</code> <code>teclas</code> <code>clicar</code> <code>digitar</code>
<code>falar</code> <code>volume</code> <code>musica</code> <code>spotify</code> <code>pausar_escuta</code> <code>comando</code> (o modelo completo está no topo do meus_comandos.txt).</div>
</main></body></html>"""
    with open(SAIDA, "w", encoding="utf-8") as f: f.write(pagina)
    return SAIDA


if __name__ == "__main__":
    print(gerar())
