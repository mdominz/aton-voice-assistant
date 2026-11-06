# Instalação e configuração do Aton

🇺🇸 [English version](SETUP.md)

Tudo que é pessoal (contas, chaves, endereços) é criado por você e fica só no seu PC, no `config.json` e em arquivos
de token que **não** vão para o GitHub.

---

## 1. Requisitos

- Windows 10 ou 11.
- [Python 3.13](https://www.python.org/downloads/) (marque "Add Python to PATH" na instalação) e [Git](https://git-scm.com).
- Um microfone. Placa de vídeo NVIDIA é recomendada (o reconhecimento de voz fica bem mais rápido), mas não obrigatória.
- Google Chrome (para o controle de páginas e vídeos).

## 2. Instalar o Aton

1. Baixe o repositório (`git clone` ou *Code → Download ZIP*) para uma pasta, por exemplo `Documentos\Aton`.
2. Dê dois cliques em **`1_instalar.bat`**. Ele:
   - cria o ambiente Python (`venv`) e instala as bibliotecas;
   - cria o seu **`config.json`** a partir do `config.exemplo.json`.
3. Os modelos de reconhecimento de voz (~1 GB) são baixados sozinhos na primeira vez que o Aton liga.

## 3. Configurar o básico (`config.json`)

Abra o `config.json` no Bloco de Notas e ajuste:

| Campo | O que colocar |
|---|---|
| `cidade` | Sua cidade, para o clima (ex.: `"Curitiba"`) |
| `microfone` | Parte do nome do seu microfone como aparece no Windows (ex.: `"USB"`); vazio = o padrão do Windows |
| `tratamento` | Como o Aton te chama (ex.: `"senhor"`, `"chefe"` ou vazio) |
| `voz` | Voz do Aton (ex.: `"pt-BR-AntonioNeural"` ou `"pt-BR-FranciscaNeural"`) |
| `hotkey` | Atalho para falar sem dizer "Aton" (padrão `ctrl+alt+space`) |

Depois, ligue com **`2_iniciar.bat`** e diga "Aton, que horas são?".

## 4. IA local (Ollama)

O Aton responde comandos fixos sem IA. Para perguntas livres e para ler e-mail/WhatsApp, ele usa uma IA local:

1. Instale o [Ollama](https://ollama.com/download).
2. Num terminal, baixe um modelo pequeno (cabe em placas de 8 GB):
   ```
   ollama pull qwen3.5:4b
   ```
3. No `config.json`, deixe `"ollama_modelo": "qwen3.5:4b"`.
4. (Opcional) IA na nuvem do Ollama: entre na sua conta com `ollama signin` e use `"modelo_nuvem"` com um modelo
   `...-cloud`. Com `"rota": "local"` tudo fica só no seu PC.
5. (Opcional) Claude: se você usa o [Claude Code](https://claude.com/claude-code) logado na sua assinatura, o Aton pode
   repassar perguntas ("pergunta pro Claude ...") e analisar a tela.

Pedidos sobre e-mail e WhatsApp usam **só o modelo local** (`"email_local": true`, `"whatsapp_local": true`): o
conteúdo não sai do PC.

## 5. E-mail (Outlook / Hotmail)

O Aton lê a sua caixa de entrada (somente leitura) por um "app" que **você mesmo registra** na Microsoft:

1. Entre em [portal.azure.com](https://portal.azure.com) com a sua conta Microsoft → **Registros de aplicativo** →
   **Novo registro**.
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
5. Teste: "Aton, toca a playlist ...". (Controlar a reprodução exige Spotify Premium.)

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

## 11. Ligar junto com o Windows

Crie uma tarefa agendada que rode `2_iniciar.bat` no logon (Agendador de Tarefas → *Criar tarefa básica* →
*Ao fazer logon*). Atalhos úteis na pasta: `aton_ligar.bat`, `aton_desligar.bat`, `aton_pausar_retomar.bat`
(ou **Ctrl+Alt+P** para pausar a escuta).

## 12. Detector da sua voz (opcional, melhora a ativação)

1. `gravar_minha_voz.bat` (uns 7 minutos, sem TV) e `gravar_com_tv.bat` (se houver TV perto do microfone).
2. `treinar_aton.bat`. O modelo fica em `modelos\` (só no seu PC).

## 13. Seus próprios comandos

Edite `meus_comandos.txt` (modelo e exemplos no topo do arquivo). Ex.:

```
[modo cinema]
frases: modo cinema; hora do filme
musica pausar
abrir Netflix
esperar 4
volume 40
falar Bom filme.
```

## O que nunca vai para o GitHub

`config.json`, `aton_token.txt`, `outlook_token.json`, `spotify_token.json`, `memoria.json`, `agenda.json`,
`lembretes.json`, logs, `amostras_ativacao/`, `vocabulario_aprendido.json`, `venv/` e `modelos/` — veja o `.gitignore`.
