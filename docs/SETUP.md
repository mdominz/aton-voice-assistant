# Installing and setting up Aton

🇧🇷 [Versão em português](CONFIGURACAO.md)

> Aton speaks and understands **Brazilian Portuguese**. Settings and file names are in Portuguese; this guide explains
> each one in English. Voice examples are given in Portuguese with the English meaning.

Everything personal (accounts, keys, addresses) is created by you and stays only on your PC, in `config.json` and in
token files that are **never** pushed to GitHub.

---

## 1. Requirements

- Windows 10 or 11.
- [Python 3.13](https://www.python.org/downloads/) (check "Add Python to PATH" during setup) and [Git](https://git-scm.com).
- A microphone. An NVIDIA GPU is recommended (speech recognition is much faster), but not required.
- Google Chrome (for page and video control).

## 2. Install Aton

1. Download the repository (`git clone` or *Code → Download ZIP*) into a folder, e.g. `Documents\Aton`.
2. Double-click **`1_instalar.bat`** ("install"). It:
   - creates the Python environment (`venv`) and installs the libraries;
   - creates your **`config.json`** from `config.exemplo.json` ("example config").
3. The speech-recognition models (~1 GB) are downloaded automatically the first time Aton starts.

## 3. Basic settings (`config.json`)

Open `config.json` in Notepad and adjust:

| Field | What to put |
|---|---|
| `cidade` (city) | Your city, for the weather (e.g. `"Curitiba"`) |
| `microfone` (microphone) | Part of your microphone's name as shown in Windows (e.g. `"USB"`); empty = Windows default |
| `tratamento` (form of address) | How Aton addresses you (e.g. `"senhor"` = "sir", `"chefe"` = "boss", or empty) |
| `voz` (voice) | Aton's voice (e.g. `"pt-BR-AntonioNeural"` or `"pt-BR-FranciscaNeural"`) |
| `hotkey` | Shortcut to talk without saying "Aton" (default `ctrl+alt+space`) |

Then start it with **`2_iniciar.bat`** ("start") and say "Aton, que horas são?" ("Aton, what time is it?").

## 4. Local AI (Ollama)

Aton answers built-in commands without AI. For open questions and to read e-mail/WhatsApp, it uses a local AI:

1. Install [Ollama](https://ollama.com/download).
2. In a terminal, download a small model (fits on 8 GB GPUs):
   ```
   ollama pull qwen3.5:4b
   ```
3. In `config.json`, set `"ollama_modelo": "qwen3.5:4b"`.
4. (Optional) Ollama cloud AI: sign in with `ollama signin` and set `"modelo_nuvem"` to a `...-cloud` model. With
   `"rota": "local"` everything stays on your PC.
5. (Optional) Claude: if you use [Claude Code](https://claude.com/claude-code) signed in to your subscription, Aton can
   forward questions ("pergunta pro Claude ..." — "ask Claude ...") and analyze the screen.

Requests about e-mail and WhatsApp use **only the local model** (`"email_local": true`, `"whatsapp_local": true`):
their content never leaves the PC.

## 5. E-mail (Outlook / Hotmail)

Aton reads your inbox (read-only) through an "app" that **you register yourself** with Microsoft:

1. Go to [portal.azure.com](https://portal.azure.com) with your Microsoft account → **App registrations** →
   **New registration**.
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

## 11. Start with Windows

Create a scheduled task that runs `2_iniciar.bat` at logon (Task Scheduler → *Create Basic Task* → *When I log on*).
Handy shortcuts in the folder: `aton_ligar.bat` (start), `aton_desligar.bat` (stop), `aton_pausar_retomar.bat`
(pause/resume listening — also **Ctrl+Alt+P**).

## 12. Detector trained on your voice (optional, improves wake-word accuracy)

1. `gravar_minha_voz.bat` (about 7 minutes, no TV) and `gravar_com_tv.bat` (if there is a TV near the microphone).
2. `treinar_aton.bat`. The model is saved in `modelos\` (only on your PC).

## 13. Your own commands

Edit `meus_comandos.txt` (template and examples at the top of the file). Each block is a command: a name, the phrases
that trigger it, and one step per line (`abrir` = open, `esperar` = wait, `falar` = say, `musica pausar` = pause music):

```
[modo cinema]
frases: modo cinema; hora do filme
musica pausar
abrir Netflix
esperar 4
volume 40
falar Bom filme.
```

## What never goes to GitHub

`config.json`, `aton_token.txt`, `outlook_token.json`, `spotify_token.json`, `memoria.json`, `agenda.json`,
`lembretes.json`, logs, `amostras_ativacao/`, `vocabulario_aprendido.json`, `venv/` and `modelos/` — see `.gitignore`.
