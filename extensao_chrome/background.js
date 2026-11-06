// Aton - controle por voz do Chrome.
// Conecta no Aton (ws://127.0.0.1:8767, só neste PC), recebe comandos {id, cmd, args} e responde {id, ok, res|erro}.
const PORTA = 8767;
let ws = null;

function conectar() {
  if (ws && (ws.readyState === 0 || ws.readyState === 1)) return;
  try { ws = new WebSocket(`ws://127.0.0.1:${PORTA}`); } catch (e) { ws = null; return; }
  ws.onopen = () => ws.send(JSON.stringify({ tipo: "ola", versao: 1 }));
  ws.onmessage = async (e) => {
    let m; try { m = JSON.parse(e.data); } catch { return; }
    if (!m.id) return;
    let r;
    try { r = { ok: true, res: await executar(m.cmd, m.args || {}) }; }
    catch (err) { r = { ok: false, erro: String((err && err.message) || err) }; }
    if (ws && ws.readyState === 1) ws.send(JSON.stringify({ id: m.id, ...r }));
  };
  ws.onclose = () => { ws = null; setTimeout(conectar, 3000); };
  ws.onerror = () => { try { ws.close(); } catch {} };
}
conectar();
// o Chrome adormece a extensão depois de 30 s parada: o ping mantém a conexão e o alarme a reabre se cair
setInterval(() => { if (ws && ws.readyState === 1) ws.send('{"tipo":"ping"}'); }, 20000);
chrome.alarms.create("aton", { periodInMinutes: 0.5 });
chrome.alarms.onAlarm.addListener(conectar);
chrome.runtime.onStartup.addListener(conectar);

// ------------------------------------------------------------------ utilidades
const semAcento = (t) => (t || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
const resumo = (t) => ({ id: t.id, titulo: t.title, url: t.url, ativa: t.active, tocando: !!t.audible, janela: t.windowId });

async function abaAtual() {
  const w = await chrome.windows.getLastFocused({ windowTypes: ["normal"] });
  const [t] = await chrome.tabs.query({ active: true, windowId: w.id });
  return t;
}

async function acharAbas(busca) {
  const b = semAcento(busca).trim();
  if (!b) return [await abaAtual()];
  const todas = await chrome.tabs.query({});
  return todas.filter((t) => semAcento(t.title).includes(b) || semAcento(t.url).includes(b.replace(/\s+/g, "")));
}

async function focar(t) {
  await chrome.tabs.update(t.id, { active: true });
  await chrome.windows.update(t.windowId, { focused: true });
}

async function rodar(tabId, func, args, world = "MAIN") {
  const res = await chrome.scripting.executeScript({ target: { tabId, allFrames: true }, world, func, args });
  return res.map((r) => r.result).filter((x) => x !== null && x !== undefined);
}

// ------------------------------------------------------------------ funções que rodam DENTRO da página
function controlarMidia(acao, valor) {
  const ms = [...document.querySelectorAll("video,audio")].filter((m) => m.readyState > 0 || m.currentSrc);
  if (!ms.length) return null;
  const m = ms.find((x) => !x.paused) || ms.sort((a, b) => b.clientWidth * b.clientHeight - a.clientWidth * a.clientHeight)[0];
  let nf = null;   // Netflix: mexer no currentTime trava o player; o certo é a API dele
  if (location.hostname.includes("netflix.com")) {
    try {
      const api = netflix.appContext.state.playerApp.getAPI().videoPlayer;
      const ids = api.getAllPlayerSessionIds();
      nf = api.getVideoPlayerBySessionId(ids.find((s) => s.startsWith("watch")) || ids[0]);
    } catch (e) { nf = null; }
  }
  const tocar = () => { const p = nf ? nf.play() : m.play(); if (p && p.catch) p.catch(() => {}); };
  const pausar = () => (nf ? nf.pause() : m.pause());
  const ir = (s) => { s = Math.max(0, Math.min(s, (m.duration || 1e9) - 1)); nf ? nf.seek(s * 1000) : (m.currentTime = s); };
  switch (acao) {
    case "pausar": pausar(); break;
    case "tocar": tocar(); break;
    case "alternar": m.paused ? tocar() : pausar(); break;
    case "pular": ir(m.currentTime + valor); break;
    case "ir_para": ir(valor); break;
    case "mudo": m.muted = true; break;
    case "som": m.muted = false; break;
    case "volume": m.muted = false; m.volume = Math.max(0, Math.min(1, valor / 100)); break;
    case "velocidade": m.playbackRate = valor; break;
    case "estado": break;
  }
  return { pausado: acao === "pausar" ? true : acao === "tocar" ? false : m.paused, tempo: Math.round(m.currentTime),
           duracao: Math.round(m.duration || 0), titulo: document.title, site: location.hostname };
}

function botaoPagina(qual) {
  const seletores = {
    pular_anuncio: [".ytp-skip-ad-button", ".ytp-ad-skip-button", ".ytp-ad-skip-button-modern", "[data-uia='player-skip-intro']",
                    "[data-uia='player-skip-recap']", "button.skip-intro", ".atvwebplayersdk-skipelement-button"],
    proximo: [".ytp-next-button", "[data-uia='next-episode-seamless-button']", "[data-uia='control-next']",
              "[data-testid='up-next-button']", ".atvwebplayersdk-nextupcard-button"],
  }[qual] || [];
  for (const s of seletores) {
    const b = document.querySelector(s);
    if (b && b.offsetParent !== null) { b.click(); return s; }
  }
  return null;
}

function lerPagina(limite) {
  return { titulo: document.title, url: location.href, texto: (document.body ? document.body.innerText : "").slice(0, limite) };
}

function rolar(direcao) {
  const h = window.innerHeight * 0.8;
  if (direcao === "topo") window.scrollTo({ top: 0, behavior: "smooth" });
  else if (direcao === "fim") window.scrollTo({ top: document.body.scrollHeight, behavior: "smooth" });
  else window.scrollBy({ top: direcao === "cima" ? -h : h, behavior: "smooth" });
  return true;
}

// ------------------------------------------------------------------ interagir com a página (rodam DENTRO da página)
// Uma só função com várias operações: clicar pelo texto, listar o que dá para clicar, pesquisar no site e
// escolher o N-ésimo vídeo/resultado/episódio. Nunca escreve em campos de senha.
async function pagina(op, a) {
  const dorme = (ms) => new Promise((r) => setTimeout(r, ms));
  const norm = (t) => (t || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/\s+/g, " ").trim();
  const visivel = (el) => {
    const s = getComputedStyle(el);
    if (s.visibility === "hidden" || s.display === "none" || s.opacity === "0") return false;
    // um <a> "inline" que envolve um título tem caixa de tamanho zero: vale o tamanho do que está dentro dele
    const tem = (r) => r.width > 2 && r.height > 2;
    return tem(el.getBoundingClientRect()) || [...el.getClientRects()].some(tem) ||
      [...el.children].some((c) => tem(c.getBoundingClientRect()));
  };
  const caixa = (el) => {   // retângulo útil (o do filho, se o próprio for vazio)
    const r = el.getBoundingClientRect();
    if (r.width > 2 && r.height > 2) return r;
    const c = [...el.children].map((x) => x.getBoundingClientRect()).find((x) => x.width > 2 && x.height > 2);
    return c || r;
  };
  const naTela = (el) => { const r = caixa(el); return r.bottom > 0 && r.top < innerHeight && r.right > 0 && r.left < innerWidth; };
  const textoDe = (el) => (el.getAttribute("aria-label") || el.innerText || el.value || el.title ||
    (el.querySelector("img[alt]") || {}).alt || "").replace(/\s+/g, " ").trim().slice(0, 120);
  const SEL = 'a[href], button, [role="button"], [role="link"], [role="tab"], [role="menuitem"], [role="option"], ' +
    'input[type="submit"], input[type="button"], summary, [onclick], [tabindex="0"]';
  const clicaveis = () => {
    const vistos = new Set(), out = [];
    for (const el of document.querySelectorAll(SEL)) {
      if (!visivel(el) || el.closest("[aria-hidden='true']")) continue;
      const t = textoDe(el);
      if (!t || t.length < 2) continue;
      const k = norm(t) + "|" + (el.getAttribute("href") || "");
      if (vistos.has(k)) continue;
      vistos.add(k); out.push({ el, texto: t, href: el.getAttribute("href") || "", tela: naTela(el) });
    }
    return out;
  };
  const clicar = (el) => {
    el.scrollIntoView({ block: "center", behavior: "instant" });
    const r = caixa(el), x = r.left + r.width / 2, y = r.top + r.height / 2;
    for (const tipo of ["pointerover", "pointerenter", "mouseover", "pointerdown", "mousedown", "pointerup", "mouseup"])
      el.dispatchEvent(new MouseEvent(tipo, { bubbles: true, cancelable: true, view: window, clientX: x, clientY: y }));
    el.click();
  };
  const escrever = (el, texto) => {
    el.focus();
    if (el.isContentEditable) { document.execCommand("selectAll", false, null); document.execCommand("insertText", false, texto); return; }
    const proto = el.tagName === "TEXTAREA" ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
    Object.getOwnPropertyDescriptor(proto, "value").set.call(el, texto);
    el.dispatchEvent(new Event("input", { bubbles: true })); el.dispatchEvent(new Event("change", { bubbles: true }));
  };
  const enter = (el) => {
    for (const tipo of ["keydown", "keypress", "keyup"])
      el.dispatchEvent(new KeyboardEvent(tipo, { key: "Enter", code: "Enter", keyCode: 13, which: 13, bubbles: true, cancelable: true }));
  };

  if (op === "listar") {
    const c = clicaveis();
    const tela = c.filter((x) => x.tela), resto = c.filter((x) => !x.tela);
    return { titulo: document.title, itens: [...tela, ...resto].slice(0, a.max || 40).map((x) => x.texto) };
  }

  if (op === "clicar") {
    const alvo = norm(a.texto);
    const c = clicaveis();
    const pont = (x) => { const t = norm(x.texto); return t === alvo ? 4 : t.startsWith(alvo) ? 3 : (" " + t + " ").includes(" " + alvo + " ") ? 2 : t.includes(alvo) ? 1 : 0; };
    const achados = c.map((x) => ({ ...x, p: pont(x) })).filter((x) => x.p > 0)
      .sort((x, y) => y.p - x.p || (y.tela - x.tela) || x.texto.length - y.texto.length);
    if (!achados.length) throw new Error(`não achei nada escrito "${a.texto}" para clicar nesta página`);
    const esc = achados[Math.min((a.n || 1) - 1, achados.length - 1)];
    if (a.so_ver) {
      // posição na tela (fração da área da página) para o Aton dar um clique REAL do mouse: players como o do
      // HBO Max só começam a tocar com um clique de verdade (regra de autoplay do Chrome)
      esc.el.scrollIntoView({ block: "center", behavior: "instant" });
      await dorme(150);
      const r = caixa(esc.el);
      return { texto: esc.texto, href: esc.href, fx: (r.left + r.width / 2) / innerWidth, fy: (r.top + r.height / 2) / innerHeight,
               visivel: r.width > 2 && r.top >= 0 && r.bottom <= innerHeight };
    }
    clicar(esc.el);
    return { texto: esc.texto, href: esc.href };
  }

  if (op === "pesquisar") {
    const achaBusca = () => [...document.querySelectorAll(
      'input[type="search"], [role="searchbox"], [role="combobox"][aria-label], input[name="q"], input[name="search"], input[name="query"], ' +
      'input[name="s"], input[name="k"], input[name="field-keywords"], input[aria-label], input[placeholder], textarea[aria-label]')]
      .filter((el) => el.type !== "password" && visivel(el) && !el.disabled &&
        (/search|pesquis|busca|procur|query/i.test([el.type, el.name, el.id, el.getAttribute("aria-label"), el.placeholder, el.getAttribute("role")].join(" ")) ||
         el.type === "search" || el.name === "q"));
    let campo = achaBusca()[0];
    if (!campo) {          // a busca está escondida atrás de um ícone de lupa
      const lupa = [...document.querySelectorAll('button, [role="button"], a')].find((el) => visivel(el) &&
        /search|pesquis|busca|procur/i.test([el.getAttribute("aria-label"), el.title, el.getAttribute("data-testid"), el.className].join(" ")));
      if (lupa) { clicar(lupa); await dorme(800); campo = achaBusca()[0]; }
    }
    if (!campo) throw new Error("não achei a caixa de busca deste site");
    escrever(campo, a.termo);
    await dorme(250);
    enter(campo);
    await dorme(300);
    if (campo.form && document.contains(campo) && norm(campo.value) === norm(a.termo)) {
      try { campo.form.requestSubmit(); } catch (e) { try { campo.form.submit(); } catch (e2) {} }
    }
    return { campo: campo.getAttribute("aria-label") || campo.placeholder || campo.name || "busca" };
  }

  if (op === "escolher") {
    const n = a.n || 1, tipo = a.tipo;
    let cands = [];
    if (tipo === "episodio") {
      const re = new RegExp(`(^|\\b)(epis[oó]dio|ep\\.?|e)\\s*0?${n}(\\b|$)|^0?${n}[.\\s-]`, "i");
      cands = clicaveis().filter((x) => re.test(norm(x.texto)) || re.test(x.texto));
      if (!cands.length) {     // às vezes o número está num texto dentro de um cartão clicável
        const el = [...document.querySelectorAll("li, article, [role='listitem'], div")].find((d) => visivel(d) && d.children.length < 30 && re.test(norm(d.innerText || "").slice(0, 40)));
        if (el) cands = [{ el: el.querySelector(SEL) || el, texto: (el.innerText || "").trim().slice(0, 80), href: "" }];
      }
      if (!cands.length) throw new Error(`não achei o episódio ${n} nesta página`);
      clicar(cands[0].el); return { texto: cands[0].texto, href: cands[0].href };
    }
    const links = [...document.querySelectorAll("a[href]")].filter((el) => visivel(el));
    const vistos = new Set();
    const unico = (el) => { const h = el.href.split("&")[0]; if (vistos.has(h)) return false; vistos.add(h); return true; };
    if (tipo === "video") {
      cands = links.filter((el) => /\/watch|\/shorts\/|\/video|\/videos?\/|\/title\/|\/play|\/episode|\/filme|\/movie/i.test(el.href) &&
        (el.querySelector("img, video, yt-image") || caixa(el).width > 120)).filter(unico);
    } else {                   // resultado / link / item: links com título (h1-h3) ou grandes, fora de menus
      cands = links.filter((el) => !el.closest("nav, header, footer, [role='navigation'], [role='banner']") &&
        (el.querySelector("h1, h2, h3, [role='heading']") || el.closest("h1, h2, h3") || caixa(el).width > 200) &&
        !/^(javascript|#)/.test(el.getAttribute("href"))).filter(unico);
    }
    if (n === -1) cands = cands.slice(-1);
    const esc = n === -1 ? cands[0] : cands[n - 1];
    if (!esc) throw new Error(`só achei ${cands.length} ${tipo === "video" ? "vídeos" : "resultados"} nesta página`);
    const t = textoDe(esc) || (esc.querySelector("h1,h2,h3") || {}).innerText || esc.href;
    clicar(esc);
    return { texto: String(t).slice(0, 100), href: esc.href };
  }
  throw new Error("operação de página desconhecida");
}

// ------------------------------------------------------------------ WhatsApp Web (rodam DENTRO de web.whatsapp.com)
// O WhatsApp muda as classes CSS com frequência: aqui só se usa o que é mais estável (ids, roles, aria-label,
// data-pre-plain-text, span[title]) e cada coisa tem mais de um jeito de ser encontrada.
async function wpp(op, a) {
  const dorme = (ms) => new Promise((r) => setTimeout(r, ms));
  const norm = (t) => (t || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/\s+/g, " ").trim();
  const lado = () => document.querySelector("#pane-side");
  const linhas = () => [...document.querySelectorAll('#pane-side [role="listitem"], #pane-side [role="row"]')]
    .filter((r) => r.querySelector("span[title]"));
  const nomeDe = (r) => r.querySelector("span[title]").getAttribute("title");
  const naoLidas = (r) => {
    const b = [...r.querySelectorAll("span[aria-label]")].find((s) => /n[ãa]o lid|unread/i.test(s.getAttribute("aria-label")));
    if (!b) return 0;
    const n = parseInt((b.textContent || b.getAttribute("aria-label")).replace(/\D+/g, " ").trim(), 10);
    return isNaN(n) ? 1 : n;
  };
  const previa = (r) => {
    const t = [...r.querySelectorAll("span[title]")].slice(1).map((s) => s.getAttribute("title")).find((x) => x && x.length > 0);
    return t || "";
  };
  const clicar = (el) => {
    for (const tipo of ["pointerdown", "mousedown", "pointerup", "mouseup", "click"])
      el.dispatchEvent(new MouseEvent(tipo, { bubbles: true, cancelable: true, view: window }));
  };
  const busca = () => document.querySelector('#side [contenteditable="true"]') ||
    document.querySelector('#side input[type="text"], #side input[role="textbox"], input[aria-label*="esquis"], input[aria-label*="earch"]');
  const escreverEm = (el, texto) => {
    el.focus();
    if (el.isContentEditable) {
      document.execCommand("selectAll", false, null);
      document.execCommand(texto ? "insertText" : "delete", false, texto || null);
    } else {
      const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set;
      set.call(el, texto); el.dispatchEvent(new Event("input", { bubbles: true }));
    }
  };
  const cabecalho = () => {
    const h = document.querySelector("#main header");
    if (!h) return "";
    const s = h.querySelector("span[title]") || h.querySelector('span[dir="auto"]');
    return s ? (s.getAttribute("title") || s.textContent) : "";
  };
  async function procurar(nome) {
    // 1) conversas recentes da lista; 2) a busca do WhatsApp (contatos que não estão na lista)
    const n = norm(nome);
    let achados = linhas().map((r) => ({ nome: nomeDe(r), el: r })).filter((x) => norm(x.nome).includes(n));
    if (!achados.length) {
      const b = busca();
      if (!b) throw new Error("não achei a caixa de busca do WhatsApp");
      escreverEm(b, nome);
      await dorme(1500);
      achados = linhas().map((r) => ({ nome: nomeDe(r), el: r })).filter((x) => norm(x.nome).includes(n.split(" ")[0]));
    }
    const vistos = new Set();
    return achados.filter((x) => (vistos.has(x.nome) ? false : vistos.add(x.nome)));
  }
  function limparBusca() { const b = busca(); if (b && (b.value || b.textContent)) escreverEm(b, ""); }
  async function abrir(nomeExato) {
    if (norm(cabecalho()) === norm(nomeExato)) return true;
    const lista = await procurar(nomeExato);
    const alvo = lista.find((x) => norm(x.nome) === norm(nomeExato)) || (lista.length === 1 ? lista[0] : null);
    if (!alvo) throw new Error(`não achei a conversa "${nomeExato}"`);
    clicar(alvo.el.querySelector("span[title]")); clicar(alvo.el);
    for (let i = 0; i < 30; i++) { await dorme(150); if (norm(cabecalho()) === norm(alvo.nome)) { limparBusca(); return true; } }
    throw new Error(`a conversa "${nomeExato}" não abriu`);
  }
  function mensagens(n) {
    return [...document.querySelectorAll("#main [data-pre-plain-text]")].slice(-n).map((m) => {
      const pre = m.getAttribute("data-pre-plain-text") || "";              // "[10:32, 04/11/2026] João: "
      const k = pre.match(/^\[([^\]]+)\]\s*(.*?):\s*$/) || [];
      const eu = !!m.closest(".message-out") || !!m.closest('[class*="message-out"]');
      const txt = (m.querySelector(".selectable-text") || m).innerText.trim();
      return { quando: k[1] || "", de: eu ? "eu" : (k[2] || ""), texto: txt };
    });
  }

  if (!lado()) {
    if (document.querySelector("canvas") || /QR/i.test(document.body.innerText.slice(0, 2000)))
      throw new Error("o WhatsApp Web não está conectado: escaneie o QR code em web.whatsapp.com");
    throw new Error("o WhatsApp Web ainda está carregando");
  }
  switch (op) {
    case "diagnostico": {
      const b = busca();
      return { lista: !!lado(), linhas: linhas().length, busca: b ? (b.isContentEditable ? "editavel" : "input") : null,
               conversa_aberta: !!document.querySelector("#main"), caixa_texto: !!document.querySelector('#main footer [contenteditable="true"]'),
               msgs_com_pre: document.querySelectorAll("#main [data-pre-plain-text]").length,
               linha_com_nao_lida: linhas().some((r) => naoLidas(r) > 0) };
    }
    case "nao_lidas":
      return linhas().map((r) => ({ nome: nomeDe(r), nao_lidas: naoLidas(r), previa: previa(r) })).filter((x) => x.nao_lidas > 0);
    case "recentes":
      return linhas().slice(0, a.n || 10).map((r) => ({ nome: nomeDe(r), nao_lidas: naoLidas(r), previa: previa(r) }));
    case "buscar": { const r = (await procurar(a.nome)).map((x) => x.nome); limparBusca(); return r; }
    case "ler": { await abrir(a.nome); await dorme(600); return { conversa: cabecalho(), mensagens: mensagens(a.n || 10) }; }
    case "enviar": {
      await abrir(a.nome);
      if (norm(cabecalho()) !== norm(a.nome)) throw new Error("abriu a conversa errada; nada foi enviado");
      const caixa = document.querySelector('#main footer [contenteditable="true"]');
      if (!caixa) throw new Error("não achei a caixa de mensagem");
      escreverEm(caixa, a.texto);
      await dorme(300);
      const btn = document.querySelector('#main footer button[aria-label="Enviar"], #main footer button[aria-label="Send"]') ||
        (document.querySelector('#main footer [data-icon="send"], #main footer [data-icon="wds-ic-send-filled"]') || {}).closest?.("button");
      if (btn) clicar(btn);
      else caixa.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", code: "Enter", keyCode: 13, which: 13, bubbles: true }));
      await dorme(800);
      const ult = mensagens(3).filter((m) => m.de === "eu").pop();
      return { conversa: cabecalho(), conferido: !!ult && norm(ult.texto) === norm(a.texto) };
    }
  }
  throw new Error("operação do WhatsApp desconhecida");
}

async function abaWpp(abrirSeFaltar = true) {
  let [t] = await chrome.tabs.query({ url: "https://web.whatsapp.com/*" });
  if (!t && abrirSeFaltar) {
    t = await chrome.tabs.create({ url: "https://web.whatsapp.com/", active: false, pinned: true });
    for (let i = 0; i < 60; i++) {           // até 30 s para carregar
      await new Promise((r) => setTimeout(r, 500));
      try {
        const [r] = await chrome.scripting.executeScript({ target: { tabId: t.id }, func: () => !!document.querySelector("#pane-side") });
        if (r && r.result) break;
      } catch (e) {}
    }
  }
  if (!t) throw new Error("o WhatsApp Web não está aberto");
  return t;
}

// ------------------------------------------------------------------ comandos
async function midia(acao, valor, soAtual) {
  // ordem: aba tocando som > aba da frente > as outras (vídeo pausado em outra aba); soAtual: só a aba da frente
  const todas = await chrome.tabs.query({});
  const atual = await abaAtual().catch(() => null);
  const ordem = soAtual ? (atual ? [atual] : []) :
    [...todas.filter((t) => t.audible), ...(atual ? [atual] : []), ...todas.filter((t) => !t.audible)];
  const vistos = new Set();
  for (const t of ordem) {
    if (vistos.has(t.id) || !/^https?:/.test(t.url || "")) continue;
    vistos.add(t.id);
    try {
      const r = await rodar(t.id, controlarMidia, [acao, valor ?? 0]);
      if (r.length) return { ...r[0], aba: resumo(t) };
    } catch (e) { /* página protegida: tenta a próxima */ }
    if (vistos.size >= 15) break;
  }
  throw new Error("nenhum vídeo ou áudio aberto no Chrome");
}

async function executar(cmd, a) {
  switch (cmd) {
    case "abas": return (await chrome.tabs.query({})).map(resumo);
    case "abrir": {
      const t = await chrome.tabs.create({ url: a.url, active: true });
      await chrome.windows.update(t.windowId, { focused: true });
      return resumo(t);
    }
    case "nova_aba": { const t = await chrome.tabs.create({}); await chrome.windows.update(t.windowId, { focused: true }); return resumo(t); }
    case "fechar": {
      const abas = (await acharAbas(a.busca || "")).filter(Boolean);
      if (!abas.length) throw new Error(`nenhuma aba com "${a.busca}"`);
      await chrome.tabs.remove(abas.map((t) => t.id));
      return abas.map((t) => t.title);
    }
    case "fechar_outras": {
      const atual = await abaAtual();
      const outras = (await chrome.tabs.query({ windowId: atual.windowId })).filter((t) => t.id !== atual.id && !t.pinned);
      await chrome.tabs.remove(outras.map((t) => t.id));
      return outras.length;
    }
    case "ir": {
      const [t] = await acharAbas(a.busca || "");
      if (!t) throw new Error(`nenhuma aba com "${a.busca}"`);
      await focar(t); return resumo(t);
    }
    case "proxima_aba": case "aba_anterior": {
      const atual = await abaAtual();
      const abas = await chrome.tabs.query({ windowId: atual.windowId });
      const i = abas.findIndex((t) => t.id === atual.id);
      const t = abas[(i + (cmd === "proxima_aba" ? 1 : -1) + abas.length) % abas.length];
      await focar(t); return resumo(t);
    }
    case "reabrir": { const s = await chrome.sessions.restore(); return s && s.tab ? resumo(s.tab) : true; }
    case "recarregar": { const t = await abaAtual(); await chrome.tabs.reload(t.id); return resumo(t); }
    case "voltar": case "avancar": {
      const t = await abaAtual();
      try { await (cmd === "voltar" ? chrome.tabs.goBack(t.id) : chrome.tabs.goForward(t.id)); }
      catch (e) {
        // o Chrome "pula" páginas abertas por cliques automáticos; pela própria página o histórico funciona
        const antes = t.url;
        await chrome.scripting.executeScript({ target: { tabId: t.id }, func: (v) => (v ? history.back() : history.forward()), args: [cmd === "voltar"] });
        await new Promise((r) => setTimeout(r, 700));
        const depois = (await chrome.tabs.get(t.id)).url;
        if (depois === antes) throw new Error(cmd === "voltar" ? "não há página anterior nesta guia" : "não há página seguinte nesta guia");
      }
      return true;
    }
    case "midia": return await midia(a.acao, a.valor, !!a.so_atual);
    case "botao": {
      const alvo = (await chrome.tabs.query({ audible: true }))[0] || (await abaAtual());
      const r = await rodar(alvo.id, botaoPagina, [a.qual]);
      if (!r.length) throw new Error("não achei esse botão na página agora");
      return r[0];
    }
    case "ler_pagina": {
      const t = await abaAtual();
      const r = await rodar(t.id, lerPagina, [a.limite || 15000], "ISOLATED");
      return r[0] || { titulo: t.title, url: t.url, texto: "" };
    }
    case "rolar": { const t = await abaAtual(); await rodar(t.id, rolar, [a.direcao || "baixo"], "ISOLATED"); return true; }
    case "focar_video": { // traz para frente a aba do vídeo (o Aton então aperta "f" para a tela cheia)
      const r = await midia("estado");
      await focar({ id: r.aba.id, windowId: r.aba.janela });
      return r;
    }
    case "wpp": {
      const t = await abaWpp(a.op !== "diagnostico");
      const [r] = await chrome.scripting.executeScript({ target: { tabId: t.id }, func: wpp, args: [a.op, a] });
      if (r && r.error) throw new Error(r.error.message || String(r.error));
      return r ? r.result : null;
    }
    case "pagina": {
      const t = await abaAtual();
      if (!/^https?:/.test(t.url || "")) throw new Error("esta guia não é uma página da web (é uma página interna do Chrome)");
      const [r] = await chrome.scripting.executeScript({ target: { tabId: t.id }, func: pagina, args: [a.op, a] });
      return { ...(r ? r.result : {}), guia: t.title };
    }
    case "versao": return chrome.runtime.getManifest().version;
    case "recarregar_extensao": setTimeout(() => chrome.runtime.reload(), 200); return true;   // relê os arquivos da pasta
    default: throw new Error(`comando desconhecido: ${cmd}`);
  }
}
