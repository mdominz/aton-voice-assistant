# Instalação e configuração do Aton

🇺🇸 [English version](SETUP.md)

Tudo que é pessoal (contas, chaves, endereços) é criado por você e fica só no seu PC, no `config.json` e em arquivos
de token que **nunca** vão para o GitHub.

---

## 1. Requisitos

- Windows 10 ou 11, uns **4 GB** livres no disco e internet.
- **[Python 3.13](https://www.python.org/downloads/windows/)** — use o **3.13** mais recente, não o 3.14 (algumas
  bibliotecas ainda não existem para ele). Marque **"Add python.exe to PATH"** na instalação.
- **[Microsoft Visual C++ Redistributable (x64)](https://aka.ms/vs/17/release/vc_redist.x64.exe)** — muitos PCs já
  têm; sem ele as bibliotecas de voz falham com "DLL load failed".
- [Git](https://git-scm.com) (opcional, para clonar) e **Google Chrome** (para o controle de páginas e vídeos).
- Um microfone. Placa **NVIDIA com o driver atualizado** é recomendada (o reconhecimento de voz fica bem mais rápido);
  sem ela, o Aton usa o processador.

## 2. Instalar o Aton

1. Baixe o repositório: `git clone https://github.com/mdominz/aton-voice-assistant.git`, ou *Code → Download ZIP*.
   Se usar o ZIP, clique com o botão direito nele → **Propriedades → Desbloquear** antes de extrair (senão o Windows
   SmartScreen bloqueia os `.bat`).
2. Dê dois cliques em **`1_instalar.bat`**. Leva **5 a 15 minutos** e baixa cerca de **2,5 GB** na primeira vez (a
   maior parte são as bibliotecas CUDA da NVIDIA, para a placa de vídeo). Ele:
   - cria o ambiente Python 3.13 (`venv`) e instala as bibliotecas;
   - baixa os modelos de base do detector da palavra "Aton";
   - cria o seu **`config.json`** a partir do `config.exemplo.json`.
   Se algum passo falhar, ele para e mostra o erro.
3. Na **primeira vez que liga**, o Aton baixa os modelos de reconhecimento de voz (uns **600 MB**, ficam em
   `modelos\`). Ele só responde depois que o log mostra `Pronto. Diga "Aton"...`.

## 3. Configurar o básico e testar

Abra o `config.json` no Bloco de Notas. Estes são os campos que a maioria das pessoas muda:

| Campo | O que faz |
|---|---|
| `cidade` | Sua cidade, para o clima (ex.: `"Curitiba"`). |
| `microfone` | Parte do nome do seu microfone como aparece no Windows (ex.: `"USB"`); vazio = o padrão do Windows. |
| `tratamento` | Como o Aton te chama (`"senhor"`, `"chefe"` ou vazio). |
| `voz` | Voz online, ex.: `"pt-BR-AntonioNeural"` ou `"pt-BR-FranciscaNeural"`. |
| `hotkey` / `hotkey_pausa` | Falar sem dizer "Aton" (`ctrl+alt+space`) / pausar a escuta (`ctrl+alt+p`). |
| `rota` | `"local"` = só a IA local (padrão); `"auto"` = nuvem do Ollama primeiro, a local como reserva. |
| `so_comandos` | `true` = "só comandos": nada de IA, apenas os comandos fixos e os seus. |
| `respostas_por_voz` | `false` = o Aton responde só em texto (no painel/celular), sem voz. |
| `palavra_ativacao` | Formas como a palavra de ativação pode ser transcrita (`"aton"`, `"a tom"`...). |
| `ativacao_por_voz` | `false` = só o atalho chama o Aton (o microfone não fica escutando o tempo todo). |
| `whisper_modelo` / `modelo_ativacao` | Modelos de voz (`small` / `base`); maior = mais preciso e mais lento. |
| `abaixar_fundo` / `nivel_fundo` | Abaixa o som dos outros programas enquanto você fala com o Aton (para 25%). |
| `coletar_amostras_ativacao` | `true` guarda até 300 trechos curtos de você dizendo "Aton" em `amostras_ativacao\` (só no seu PC), para treinar o detector. Desligado por padrão. |
| `log_ativacao` | `true` escreve no log o que o microfone ouviu quando não era a palavra de ativação (para depuração). Desligado por padrão. |
| `app_celular` / `ponte_chrome` | Liga/desliga o servidor do app do celular e a ponte com a extensão do Chrome. |
| `reiniciar_wallpaper` | Só para o painel opcional do Wallpaper Engine: reinicia o wallpaper quando a saída de áudio muda. |
| `rotinas`, `rotinas_horario`, `apps`, `sites`, `vocabulario` | Rotinas, rotinas com horário, programas e sites extras e palavras para o reconhecimento de voz. |

> Dica: o `config.json` é JSON — mantenha as aspas e as vírgulas. Se houver erro de digitação, o Aton mostra uma
> mensagem com o número da linha.

**Teste rápido (sem microfone):** dê dois cliques em **`teste_sem_microfone.bat`**, ou rode
`venv\Scripts\python.exe assistente.py --frase "que horas são"`. O Aton deve responder a hora.

Depois, ligue com **`2_iniciar.bat`** e diga "Aton, que horas são?".

## 4. IA local (Ollama)

O Aton responde os comandos fixos sem IA. Para perguntas livres e para ler e-mail/WhatsApp, ele usa um modelo de IA:

1. Instale o [Ollama](https://ollama.com/download).
2. Num terminal, baixe um modelo pequeno (cabe em placas de 8 GB):
   ```
   ollama pull qwen3.5:4b
   ```
3. O exemplo já usa esse modelo: `"ollama_modelo": "qwen3.5:4b"` com `"rota": "local"` — nada sai do seu PC.
4. (Opcional) Nuvem do Ollama: entre com `ollama signin` e use `"rota": "auto"` e `"modelo_nuvem"` com um modelo
   `...-cloud`. O Aton tenta a nuvem primeiro e usa o modelo local como reserva.
5. (Opcional) Claude: se você usa o [Claude Code](https://claude.com/claude-code) logado na sua assinatura, coloque
   `"claude_reserva": true`; o Aton pode repassar perguntas ("pergunta pro Claude ...") e analisar a tela.

**O que vai para a internet:** o reconhecimento de voz e a IA local rodam no seu PC. A **voz** falada usa o serviço
online da Microsoft (edge-tts), então o texto de cada resposta é enviado a ele. Pedidos sobre e-mail e WhatsApp usam só
o modelo local (`email_local`, `whatsapp_local`) e, com `"voz_offline_privado": true` (padrão), são falados com a voz
offline do Windows — esse conteúdo nunca sai do PC. `"respostas_por_voz": false` desliga a voz por completo.
A voz offline é a voz **Português (Brasil)** do Windows; se o seu Windows estiver em outro idioma, adicione-a em
*Configurações → Hora e idioma → Fala → Adicionar vozes*.

## 5. E-mail (Outlook / Hotmail)

O Aton lê a sua caixa de entrada (somente leitura) por um "app" que **você mesmo registra** na Microsoft:

1. Entre em [portal.azure.com](https://portal.azure.com) com a sua conta Microsoft → **Registros de aplicativo** →
   **Novo registro**. (Se o portal pedir para criar um diretório/locatário antes, crie o gratuito que ele oferece.)
2. Nome: qualquer um (ex.: `Aton`). Tipos de conta: **"Somente contas Microsoft pessoais"**.
3. Depois de criar, em **Autenticação**, ative **"Permitir fluxos de clientes públicos"** → Salvar.
4. Copie o **ID do aplicativo (cliente)** e cole no `config.json` em `"outlook_client_id"`.
5. Num terminal, na pasta do Aton:
   ```
   venv\Scripts\python.exe email_outlook.py login
   ```
   Ele mostra um endereço e um código: abra, digite o código e autorize. O login fica salvo no seu PC
   (`outlook_token.json`, que nunca vai para o GitHub).
6. Teste: "Aton, tenho e-mail novo?".

## 6. Spotify (opcional)

1. Em [developer.spotify.com/dashboard](https://developer.spotify.com/dashboard), crie um app.
2. Em *Redirect URIs*, adicione exatamente: `http://127.0.0.1:8888/callback`. Marque **Web API**.
3. Copie o **Client ID** para `"spotify_client_id"` no `config.json`.
4. Num terminal: `venv\Scripts\python.exe spotify.py login` → autorize no navegador.
5. Teste: "Aton, toca a playlist ...". Controlar a reprodução exige Spotify Premium.

## 7. Chrome (vídeos, guias e cliques nas páginas)

1. No Chrome, abra `chrome://extensions` e ative o **Modo do desenvolvedor** (canto superior direito).
2. **Carregar sem compactação** → escolha a pasta `extensao_chrome` do Aton.
3. A extensão só conversa com o Aton no próprio PC. Teste com um vídeo aberto: "Aton, pausa o vídeo".

## 8. App do celular e conexão pela VPN (Tailscale)

O servidor do app só aceita conexões do próprio PC. O celular chega até ele por uma **VPN privada do Tailscale**, onde
só os seus aparelhos entram — você não precisa saber nem digitar nenhum IP.

**No PC (uma vez):**
1. Instale o [Tailscale](https://tailscale.com/download) e entre com a sua conta.
2. No painel do Tailscale (*admin console → DNS*), ative **MagicDNS** e **HTTPS Certificates**.
3. Num terminal, publique o Aton **só dentro da sua VPN**:
   ```
   tailscale serve --bg 8766
   ```
   O comando mostra o endereço do seu PC, no formato `https://NOME-DO-PC.SUA-REDE.ts.net`.
4. Com o Aton ligado, abra o arquivo `aton_token.txt` (criado sozinho na pasta do Aton): é a senha do app.

**No celular (uma vez):**
1. Instale o app do Tailscale, entre com a **mesma conta** e deixe a VPN ligada.
2. Abra o endereço do passo 3 no navegador (no iPhone, Safari).
3. Toque em **"SISTEMA OFFLINE"** e cole o conteúdo do `aton_token.txt`.
4. *Compartilhar → Adicionar à Tela de Início*.

> Segurança: não abra portas no roteador e não use `tailscale funnel` (isso publicaria na internet).

## 9. Controle remoto do PC pelo celular (RustDesk, opcional)

1. Instale o [RustDesk](https://rustdesk.com) no PC. Em *Configurações → Segurança*, ative **"Acesso direto por IP"**
   e defina uma **senha permanente**.
2. Instale o app RustDesk no celular.
3. No app do Aton, abra o print da tela e toque em **"CONTROLAR AO VIVO"**. O Aton descobre sozinho o endereço do PC
   na sua VPN (perguntando ao Tailscale); nenhum IP fica gravado. Sem o Tailscale, o botão não aparece.

## 10. WhatsApp do PC (opcional)

Instale o **WhatsApp para Windows** (Microsoft Store) e entre na sua conta. O Aton lê a janela do app pela
acessibilidade do Windows (o app pode ficar minimizado). Enviar mensagem **sempre** pede o seu "sim".

## 11. Ligar junto com o Windows, desligar, pausar

- Crie uma tarefa agendada (Agendador de Tarefas → *Criar tarefa*):
  - **Nome: exatamente `AI Core Aton`** (os scripts de apoio usam esse nome);
  - Disparador: *Ao fazer logon* do seu usuário;
  - Ação: Programa `<pasta do Aton>\venv\Scripts\pythonw.exe`, Argumentos `assistente.py`,
    Iniciar em `<pasta do Aton>` (`pythonw` = sem janela de console).
- `aton_ligar.bat` (liga), `3_parar.bat` / `aton_desligar.bat` (desligam — só a cópia **desta** pasta),
  `aton_pausar_retomar.bat` ou **Ctrl+Alt+P** (pausa/retoma a escuta sem fechar).
- `2_iniciar.bat` liga o Aton numa janela de console (útil para acompanhar o log).

## 12. Detector da sua voz (opcional, melhora a ativação)

1. `gravar_minha_voz.bat` (uns 7 minutos, sem TV) e `gravar_com_tv.bat` (se houver TV perto do microfone).
   A gravação desliga o Aton e liga de novo no fim, pela tarefa `AI Core Aton`.
2. `treinar_aton.bat`. O modelo fica em `modelos\` (só no seu PC).

## 13. Seus próprios comandos (`meus_comandos.txt`)

Cada bloco é um comando: um nome entre colchetes, as frases que o disparam (`frases:`, separadas por `;`) e um passo
por linha. Passos:

| Passo | Exemplo |
|---|---|
| `abrir <programa ou site>` | `abrir Netflix` |
| `site <nome ou endereço>` | `site g1.globo.com` |
| `esperar <segundos>` | `esperar 3` |
| `teclas <teclas>` | `teclas ctrl+shift+t` |
| `clicar <texto>` (clica num botão pelo texto) | `clicar Continuar assistindo` |
| `digitar <texto>` | `digitar olá` |
| `falar <texto>` | `falar Bom filme.` |
| `volume <0-100>` / `volume <programa> <0-100>` | `volume spotify 30` |
| `musica tocar\|pausar\|proxima\|anterior` | `musica pausar` |
| `spotify <nome>` | `spotify Queen` |
| `pausar_escuta` | `pausar_escuta` |
| `comando <frase>` (qualquer comando que o Aton entende) | `comando fecha a guia` |

```
[modo cinema]
frases: modo cinema; hora do filme
musica pausar
abrir Netflix
esperar 4
volume 40
falar Bom filme.
```

## 14. Portas usadas (todas só no próprio PC)

| Porta | Usada por |
|---|---|
| 8765 | Painel opcional da área de trabalho (`porta`) |
| 8766 | App do celular — a que você publica com `tailscale serve` |
| 8767 | Ponte com a extensão do Chrome |
| 8888 | Login do Spotify (só durante o `spotify.py login`) |
| 11434 | Ollama |

## 15. Opcional: usar as ferramentas do Aton no Claude Code (MCP)

```
claude mcp add aton -- "<pasta do Aton>\venv\Scripts\python.exe" "<pasta do Aton>\aton_mcp.py"
```

## 16. Mensagens comuns do log

| Mensagem | Significado |
|---|---|
| `Pronto. Diga "Aton"...` | Pronto para ouvir. |
| `Microfone ... não encontrado` | O microfone do campo `microfone` não foi achado: o Aton espera ele ser conectado. Confira o nome, ou use `"microfone_obrigatorio": false` para cair no padrão do Windows. |
| `A porta ... já está em uso` | Já existe outra cópia do Aton ligada. |
| `Ignorado: "..."` | Ouviu uma fala que não era a palavra de ativação (só com `log_ativacao`). |

## O que nunca vai para o GitHub

`config.json`, `aton_token.txt`, `outlook_token.json`, `spotify_token.json`, `memoria.json`, `agenda.json`,
`lembretes.json`, `monitores.json`, `ultima_organizacao.json`, logs, `amostras_ativacao/`,
`vocabulario_aprendido.json`, `venv/` e `modelos/` — veja o `.gitignore`.
