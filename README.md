# Aton — assistente de voz para Windows

Assistente de voz em português que roda no seu PC: você diz **"Aton"** e o pedido. Ele controla o computador, o Chrome,
a música, o WhatsApp do PC, o Bluetooth e as janelas, lê e-mails, guarda lembretes e tem um app de celular que funciona
de qualquer lugar por uma VPN privada.

![O Aton respondendo, com a pergunta e a resposta em legenda](docs/imagens/wallpaper_conversa.jpg)

### Painel na área de trabalho

O Aton mostra o que está fazendo num wallpaper animado (feito para o Wallpaper Engine; a interface visual é opcional
e não faz parte deste repositório):

![Wallpaper com as partes numeradas](docs/imagens/wallpaper_mapa.jpg)

| Nº | Parte | O que mostra |
|---|---|---|
| 1 | Relógio e saudação | Hora, data e "Bom dia / Boa tarde / Boa noite" |
| 2 | Clima | Temperatura e condição da sua cidade |
| 3 | Mercado | Dólar, euro e bitcoin, com a variação do dia |
| 4 | Contagem | Contagem regressiva para uma data |
| 5 | Núcleo do Aton | Reage ao som do PC e muda quando o Aton está ouvindo, pensando ou falando |
| 6 | Agenda e lembretes | Cartões que giram sozinhos; dá para concluir pelo botão |
| 7 | E-mails | Últimos e-mails da caixa de entrada |
| 8 | Status | Sistema, nível de áudio e estado do núcleo |
| 9 | Música | O que está tocando, com capa e barras de áudio |
| 10 | Console | Mensagens do sistema |

### App do celular

Conversa por voz ou texto com o Aton de qualquer lugar, pela VPN privada (Tailscale), vê a tela do PC e abre o
controle remoto:

![App do celular: tela inicial e conversa](docs/imagens/celular.jpg)

*Todas as imagens usam dados de exemplo.*

## O que ele faz

- **Voz local**: escuta "Aton" no próprio PC (Whisper, de preferência na placa de vídeo), responde com voz sintética,
  continua a conversa sem precisar chamar de novo e aprende palavras que ouviu errado ("não, eu falei ...").
- **Comandos fixos (instantâneos, sem IA)**: volume, música, abrir programas e sites, guias e vídeos do Chrome, teclas,
  clicar pelo nome em qualquer programa, janelas, Bluetooth, hora e clima.
- **Seus próprios comandos** (como as Rotinas da Alexa): escritos no arquivo `meus_comandos.txt`.
- **IA quando não é um comando fixo**: um modelo local (Ollama) e, se você quiser, um modelo na nuvem.
  O modo **"só comandos"** desliga a IA e deixa tudo previsível.
- **Chrome** (extensão própria): pausar e avançar vídeos (Netflix, YouTube, HBO Max...), tela cheia, abrir/fechar guias,
  clicar em links e botões pelo nome, pesquisar no próprio site, ler a página.
- **WhatsApp do PC**: ler mensagens e enviar — **sempre pedindo confirmação antes de enviar**.
- **E-mail (Outlook), agenda, lembretes, Spotify, área de transferência, tarefas em segundo plano.**
- **App do celular** (pasta `pwa/`): conversa por texto e voz, print da tela do PC e controle remoto, pela VPN.

A lista completa de comandos é gerada por `gerar_lista.py` (arquivo `LISTA_DE_COMANDOS.html`) ou dizendo
"Aton, quais comandos você conhece?".

## Instalação e configuração

Passo a passo completo, inclusive para conectar **o seu e-mail**, **a sua VPN (endereço do PC)**, **a IA local**,
o Spotify e o celular: **[docs/CONFIGURACAO.md](docs/CONFIGURACAO.md)**.

Resumo:
1. Python 3.13 e Git; de preferência uma placa NVIDIA.
2. `1_instalar.bat` → cria o ambiente, instala tudo e cria o seu `config.json` a partir do `config.exemplo.json`.
3. Instale o Ollama e baixe um modelo local.
4. Preencha o seu `config.json` (cidade, microfone e, se for usar, os IDs dos seus apps de e-mail e Spotify).
5. `2_iniciar.bat` para ligar, `3_parar.bat` para desligar.

## Privacidade

Nada pessoal fica no repositório. Cada pessoa cria as próprias contas, chaves e configurações, que ficam só no PC dela
e estão no `.gitignore`: `config.json`, tokens de login, memória, agenda, lembretes, logs, gravações de voz, o detector
treinado com a voz, o vocabulário aprendido, o `venv` e os modelos.

O servidor do app do celular só aceita conexões do próprio PC; o acesso de fora é feito exclusivamente pela VPN
privada do Tailscale, e toda conversa exige um token gerado no seu PC.
