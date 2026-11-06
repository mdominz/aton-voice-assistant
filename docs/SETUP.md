# Installing and setting up Aton

🇧🇷 [Versão em português](CONFIGURACAO.md)

> Aton speaks and understands **Brazilian Portuguese**. Settings, file names and console messages are in Portuguese;
> this guide explains each one in English. Voice examples are given in Portuguese with the English meaning.

Everything personal (accounts, keys, addresses) is created by you and stays only on your PC, in `config.json` and in
token files that are **never** pushed to GitHub.

---

## 1. Requirements

- Windows 10 or 11, about **4 GB** of free disk space and an internet connection.
- **[Python 3.13](https://www.python.org/downloads/windows/)** — use the latest **3.13**, not 3.14 (some libraries
  don't support 3.14 yet). Check **"Add python.exe to PATH"** during setup.
- **[Microsoft Visual C++ Redistributable (x64)](https://aka.ms/vs/17/release/vc_redist.x64.exe)** — many PCs already
  have it; without it the speech libraries fail with "DLL load failed".
- [Git](https://git-scm.com) (optional, to clone) and **Google Chrome** (for page and video control).
- A microphone. An **NVIDIA GPU with an up-to-date driver** is recommended (speech recognition is much faster); without
  it, Aton uses the CPU.

## 2. Install Aton

1. Download the repository: `git clone https://github.com/mdominz/aton-voice-assistant.git`, or *Code → Download ZIP*.
   If you use the ZIP, right-click it → **Properties → Unblock** before extracting (otherwise Windows SmartScreen
   blocks the `.bat` files).
2. Double-click **`1_instalar.bat`** ("install"). It takes **5–15 minutes** and downloads about **2.5 GB** the first
   time (most of it is NVIDIA's CUDA libraries for the GPU). It:
   - creates the Python 3.13 environment (`venv`) and installs the libraries;
   - downloads the wake-word feature models;
   - creates your **`config.json`** from `config.exemplo.json` ("example config").
   If any step fails, it stops and shows the error.
3. On the **first start**, Aton downloads the speech-recognition models (about **600 MB**, saved in `modelos\`). It
   answers only after the log shows `Pronto. Diga "Aton"...` ("Ready. Say 'Aton'...").

## 3. Basic settings and a quick test

Open `config.json` in Notepad. These are the settings most people change:

| Field | What it does |
|---|---|
| `cidade` (city) | Your city, for the weather (e.g. `"Curitiba"`). |
| `microfone` (microphone) | Part of your microphone's name as shown in Windows (e.g. `"USB"`); empty = Windows default. |
| `tratamento` (form of address) | How Aton addresses you (`"senhor"` = "sir", `"chefe"` = "boss", or empty). |
| `voz` (voice) | Online voice, e.g. `"pt-BR-AntonioNeural"` or `"pt-BR-FranciscaNeural"`. |
| `hotkey` / `hotkey_pausa` | Talk without saying "Aton" (`ctrl+alt+space`) / pause listening (`ctrl+alt+p`). |
| `rota` (route) | `"local"` = only the local AI (default); `"auto"` = Ollama cloud first, local as backup. |
| `so_comandos` | `true` = "commands only": no AI at all, only built-in and your own commands. |
| `respostas_por_voz` | `false` = Aton answers only in text (on the dashboard/phone), no voice. |
| `palavra_ativacao` | Ways the wake word may be transcribed (`"aton"`, `"a tom"`...). |
| `ativacao_por_voz` | `false` = only the hotkey wakes Aton (the microphone isn't listening all the time). |
| `whisper_modelo` / `modelo_ativacao` | Speech models (`small` / `base`); larger = more accurate and slower. |
| `abaixar_fundo` / `nivel_fundo` | Lower other apps' volume while you talk to Aton (to 25%). |
| `coletar_amostras_ativacao` | `true` saves up to 300 short clips of you saying "Aton" in `amostras_ativacao\` (only on your PC) to train the detector. Off by default. |
| `log_ativacao` | `true` writes to the log what the microphone heard when it wasn't the wake word (debugging). Off by default. |
| `app_celular` / `ponte_chrome` | Turn the phone-app server / Chrome extension bridge on or off. |
| `reiniciar_wallpaper` | Only for the optional Wallpaper Engine dashboard: restart it when the audio output changes. |
| `rotinas`, `rotinas_horario`, `apps`, `sites`, `vocabulario` | Routines, scheduled routines, extra apps, extra websites and words for the speech recognizer. |

> Tip: `config.json` is JSON — keep the quotes and commas. If there's a typo, Aton shows a message with the line number.

**Quick test (no microphone needed):** double-click **`teste_sem_microfone.bat`**, or run
`venv\Scripts\python.exe assistente.py --frase "que horas são"` ("what time is it"). Aton should answer with the time.

Then start it with **`2_iniciar.bat`** ("start") and say "Aton, que horas são?".

## 4. Local AI (Ollama)

Aton answers built-in commands without AI. For open questions and to read e-mail/WhatsApp it uses an AI model:

1. Install [Ollama](https://ollama.com/download).
2. In a terminal, download a small model (fits on 8 GB GPUs):
   ```
   ollama pull qwen3.5:4b
   ```
3. The example config already uses it: `"ollama_modelo": "qwen3.5:4b"` with `"rota": "local"` — nothing leaves your PC.
4. (Optional) Ollama cloud: sign in with `ollama signin` and set `"rota": "auto"` and `"modelo_nuvem"` to a `...-cloud`
   model. Aton then tries the cloud first and uses the local model as backup.
5. (Optional) Claude: if you use [Claude Code](https://claude.com/claude-code) signed in to your subscription, set
   `"claude_reserva": true`; Aton can forward questions ("pergunta pro Claude ..." — "ask Claude ...") and analyze the
   screen.

**What goes online:** speech recognition and the local AI run on your PC. The spoken **voice** uses Microsoft's online
service (edge-tts), so the text of each reply is sent to it. Requests about e-mail and WhatsApp use only the local model
(`email_local`, `whatsapp_local`) and, with `"voz_offline_privado": true` (default), are spoken with the offline
Windows voice — so that content never leaves the PC. `"respostas_por_voz": false` turns the voice off entirely.
The offline voice is Windows' **Portuguese (Brazil)** voice; if your Windows is in another language, add it under
*Settings → Time & language → Speech → Add voices*.

## 5. E-mail (Outlook / Hotmail)

Aton reads your inbox (read-only) through an "app" that **you register yourself** with Microsoft:

1. Go to [portal.azure.com](https://portal.azure.com) with your Microsoft account → **App registrations** →
   **New registration**. (If the portal asks you to create a directory/tenant first, create the free one it offers.)
2. Name: anything (e.g. `Aton`). Supported account types: **"Personal Microsoft accounts only"**.
3. After creating it, under **Authentication**, enable **"Allow public client flows"** → Save.
4. Copy the **Application (client) ID** and paste it into `config.json` as `"outlook_client_id"`.
5. In a terminal, in the Aton folder:
   ```
   venv\Scripts\python.exe email_outlook.py login
   ```
   It shows an address and a code: open it, type the code and authorize. The login is saved on your PC
   (`outlook_token.json`, which never goes to GitHub).
6. Test: "Aton, tenho e-mail novo?" ("Aton, do I have new e-mail?").

## 6. Spotify (optional)

1. At [developer.spotify.com/dashboard](https://developer.spotify.com/dashboard), create an app.
2. Under *Redirect URIs*, add exactly: `http://127.0.0.1:8888/callback`. Check **Web API**.
3. Copy the **Client ID** into `"spotify_client_id"` in `config.json`.
4. In a terminal: `venv\Scripts\python.exe spotify.py login` → authorize in the browser.
5. Test: "Aton, toca a playlist ..." ("Aton, play the playlist ..."). Playback control requires Spotify Premium.

## 7. Chrome (videos, tabs and page clicks)

1. In Chrome, open `chrome://extensions` and turn on **Developer mode** (top-right corner).
2. **Load unpacked** → choose Aton's `extensao_chrome` folder.
3. The extension only talks to Aton on the same PC. Test with a video open: "Aton, pausa o vídeo" ("pause the video").

## 8. Phone app and the VPN connection (Tailscale)

The app's server only accepts connections from the PC itself. The phone reaches it through a **private Tailscale VPN**
that only your devices can join — you never need to know or type any IP address.

**On the PC (once):**
1. Install [Tailscale](https://tailscale.com/download) and sign in.
2. In the Tailscale admin console (*DNS*), enable **MagicDNS** and **HTTPS Certificates**.
3. In a terminal, publish Aton **only inside your VPN**:
   ```
   tailscale serve --bg 8766
   ```
   It prints your PC's address, in the form `https://PC-NAME.YOUR-NETWORK.ts.net`.
4. With Aton running, open `aton_token.txt` (created automatically in the Aton folder): it is the app's password.

**On the phone (once):**
1. Install the Tailscale app, sign in with the **same account** and keep the VPN on.
2. Open the address from step 3 in the browser (Safari on iPhone).
3. Tap **"SISTEMA OFFLINE"** ("system offline") and paste the contents of `aton_token.txt`.
4. *Share → Add to Home Screen*.

> Security: don't open ports on your router and don't use `tailscale funnel` (that would publish it on the internet).

## 9. Remote control of the PC from the phone (RustDesk, optional)

1. Install [RustDesk](https://rustdesk.com) on the PC. In *Settings → Security*, enable **"Direct IP access"** and set a
   **permanent password**.
2. Install the RustDesk app on the phone.
3. In the Aton app, open the PC screenshot and tap **"CONTROLAR AO VIVO"** ("control live"). Aton finds the PC's
   address on your VPN by itself (it asks Tailscale); no IP is ever saved. Without Tailscale, the button doesn't show.

## 10. WhatsApp desktop (optional)

Install **WhatsApp for Windows** (Microsoft Store) and sign in. Aton reads the app window through Windows
accessibility (the app can stay minimized). Sending a message **always** asks for your "sim" ("yes").

## 11. Start with Windows, stop, pause

- Create a scheduled task (Task Scheduler → *Create Task*):
  - **Name: exactly `AI Core Aton`** (the helper scripts use this name);
  - Trigger: *At log on* of your user;
  - Action: Program `<Aton folder>\venv\Scripts\pythonw.exe`, Arguments `assistente.py`,
    Start in `<Aton folder>` (`pythonw` = no console window).
- `aton_ligar.bat` (start), `3_parar.bat` / `aton_desligar.bat` (stop — they only stop the copy in **this** folder),
  `aton_pausar_retomar.bat` or **Ctrl+Alt+P** (pause/resume listening without closing).
- `2_iniciar.bat` starts Aton in a console window (useful to watch the log).

## 12. Detector trained on your voice (optional, improves wake-word accuracy)

1. `gravar_minha_voz.bat` (about 7 minutes, no TV) and `gravar_com_tv.bat` (if there is a TV near the microphone).
   Recording stops Aton and starts it again at the end through the `AI Core Aton` task.
2. `treinar_aton.bat`. The model is saved in `modelos\` (only on your PC).

## 13. Your own commands (`meus_comandos.txt`)

Each block is a command: a name in brackets, the phrases that trigger it (`frases:`, separated by `;`) and one step per
line. Steps:

| Step | Meaning | Example |
|---|---|---|
| `abrir <app or site>` | open | `abrir Netflix` |
| `site <name or address>` | open a website | `site g1.globo.com` |
| `esperar <seconds>` | wait | `esperar 3` |
| `teclas <keys>` | press keys | `teclas ctrl+shift+t` |
| `clicar <text>` | click a button by its text | `clicar Continue watching` |
| `digitar <text>` | type text | `digitar hello` |
| `falar <text>` | say something | `falar Bom filme.` |
| `volume <0-100>` / `volume <app> <0-100>` | set PC / app volume | `volume spotify 30` |
| `musica tocar\|pausar\|proxima\|anterior` | play / pause / next / previous | `musica pausar` |
| `spotify <name>` | play on Spotify | `spotify Queen` |
| `pausar_escuta` | stop listening | `pausar_escuta` |
| `comando <phrase>` | run any command Aton understands | `comando fecha a guia` |

```
[modo cinema]
frases: modo cinema; hora do filme
musica pausar
abrir Netflix
esperar 4
volume 40
falar Bom filme.
```

## 14. Ports used (all only on the PC itself)

| Port | Used by |
|---|---|
| 8765 | Optional desktop dashboard (`porta`) |
| 8766 | Phone app — the one you publish with `tailscale serve` |
| 8767 | Chrome extension bridge |
| 8888 | Spotify login (only during `spotify.py login`) |
| 11434 | Ollama |

## 15. Optional: use Aton's tools from Claude Code (MCP)

```
claude mcp add aton -- "<Aton folder>\venv\Scripts\python.exe" "<Aton folder>\aton_mcp.py"
```

## 16. Common messages (the log is in Portuguese)

| Message | Meaning |
|---|---|
| `Pronto. Diga "Aton"...` | Ready — say "Aton". |
| `Microfone ... não encontrado` | The microphone named in `microfone` wasn't found: Aton waits until it's connected. Check the name, or set `"microfone_obrigatorio": false` to fall back to the Windows default. |
| `A porta ... já está em uso` | Another copy of Aton is already running. |
| `Ignorado: "..."` | It heard speech that wasn't the wake word (only with `log_ativacao`). |

## What never goes to GitHub

`config.json`, `aton_token.txt`, `outlook_token.json`, `spotify_token.json`, `memoria.json`, `agenda.json`,
`lembretes.json`, `monitores.json`, `ultima_organizacao.json`, logs, `amostras_ativacao/`,
`vocabulario_aprendido.json`, `venv/` and `modelos/` — see `.gitignore`.
