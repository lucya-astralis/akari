/* Linux apps in Akari windows.

   Two kinds:
   - an app from the dock (Firefox, XTerm): the workspace starts it on a
     display of its own (/api/display/<app>); closing the window ends it.
   - the desktop's default display ("Linux-Apps"): every terminal has DISPLAY
     set to it, so anything started there with a window shows up here. The
     window opens by itself when the first X window maps and closes when the
     last one goes; its title follows the active program, a switcher in the
     bar raises the others. Closing it ends the programs on it.

   noVNC draws the display and sends keys and pointer back; the display
   follows the window's size. A running app survives a reload. */
import RFB from '/vendor/novnc/core/rfb.js';

const ICONS = { firefox: 'i-globe', desktop: 'i-window' };
const ART = { firefox: 'web', xterm: 'xterm', desktop: 'window' };
const ready = Akari.ready ? Promise.resolve() : new Promise(res => Akari.on('ready', res));
const esc = s => String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

const register = app => app.terminal
  // a terminal program (htop, vim): it opens in Akari's terminal
  ? Akari.register(`x:${app.id}`, {
      title: app.title, comment: app.comment, keywords: app.keywords, img: app.icon, art: app.icon ? null : app.art,
      icon: 'i-term', dock: false, order: 95, extra: app.extra,
      redirect: () => Akari.open('terminal', { run: app.id.slice(2), title: app.title }, { fresh: true }),
    })
  : Akari.register(`x:${app.id}`, {
  title: app.title, comment: app.comment, keywords: app.keywords, img: app.icon, icon: ICONS[app.id] || 'i-window',
  art: app.icon ? null : (ART[app.id] || app.art || 'window'), multi: !app.single,
  size: [1120, 720], order: app.id.startsWith('d:') ? 95 : 40, desk: app.id === 'firefox',
  dock: !app.id.startsWith('d:') && app.id !== 'desktop' && !app.extra, launch: app.id !== 'desktop', extra: app.extra,
  create(win, args) {
    const isDefault = app.id === 'desktop';
    win.body.classList.add('xapp');
    win.body.innerHTML = `
      <div class="xapp__screen" data-screen></div>
      <div class="xapp__veil" data-veil>
        <svg class="xapp__icon"><use href="#${ICONS[app.id] || 'i-window'}"/></svg>
        <span class="f-status f-status--warn" data-say>${isDefault ? 'Verbinde …' : `${esc(app.title)} startet …`}</span>
        <button class="f-btn f-btn--sm" data-retry hidden>Noch einmal</button>
      </div>`;
    const screen = win.body.querySelector('[data-screen]');
    const veil = win.body.querySelector('[data-veil]');
    const say = (text, tone = 'warn') => {
      const s = win.body.querySelector('[data-say]');
      s.textContent = text; s.className = `f-status f-status--${tone}`;
    };
    let sid = args.sid || null;
    let rfb = null, closing = false, xwins = [];

    const background = () => Akari.color('--surface');

    const connect = () => {
      const proto = location.protocol === 'https:' ? 'wss' : 'ws';
      rfb = new RFB(screen, `${proto}://${location.host}/api/display/${sid}/ws`, { shared: true });
      rfb.resizeSession = true;     // the display takes the window's size
      rfb.scaleViewport = false;
      rfb.clipViewport = false;
      rfb.focusOnClick = true;
      rfb.background = background();
      rfb.addEventListener('connect', () => { veil.hidden = true; rfb.focus(); });
      rfb.addEventListener('disconnect', async () => {
        rfb = null;
        if (closing) return;
        // why: the app quit, another tab took it over, or the line broke
        let st = null;
        try { st = await Akari.api(`/api/display/${sid}`, { quiet: true }); } catch {}
        if (st && !st.running) { closing = true; win.close(); return; }
        veil.hidden = false;
        const retry = win.body.querySelector('[data-retry]');
        retry.hidden = false;
        if (st?.viewed) { say(`${win.title} ist in einem anderen Tab geöffnet.`, 'warn'); retry.textContent = 'Hierher holen'; }
        else { say(`Verbindung zu ${win.title} verloren.`, 'err'); retry.textContent = 'Neu verbinden'; }
      });
      // the app copied: to Akari's clipboard, the other Linux apps and the computer
      rfb.addEventListener('clipboard', e => Akari.clip.set(e.detail.text, toX));
    };

    const start = async () => {
      const r = screen.getBoundingClientRect();
      try {
        const res = await Akari.api(`/api/display/${app.id}`, { method: 'POST', json: { w: Math.round(r.width) || 1024, h: Math.round(r.height) || 700 } });
        sid = res.id;
        connect();
      } catch {
        say(`${app.title} ließ sich nicht starten.`, 'err');
        win.body.querySelector('[data-retry]').hidden = false;
      }
    };

    win.body.querySelector('[data-retry]').addEventListener('click', () => {
      win.body.querySelector('[data-retry]').hidden = true;
      say(`${win.title} startet …`);
      sid ? connect() : start();
    });

    // the default display: title after the active program, a switcher for the others
    const switcher = document.createElement('select');
    switcher.className = 'f-input xapp__switch';
    switcher.setAttribute('aria-label', 'Programm nach vorn holen');
    switcher.addEventListener('change', () => {
      Akari.api(`/api/display/${sid}/raise`, { method: 'POST', json: { id: switcher.value }, quiet: true }).catch(() => {});
      rfb?.focus({ preventScroll: true });
    });
    const update = st => {
      xwins = st.windows || [];
      const active = xwins.find(w => w.id === st.active) || xwins[xwins.length - 1];
      win.setTitle(active ? active.title : 'Linux-Apps');
      switcher.innerHTML = xwins.map(w => `<option value="${esc(w.id)}"${w === active ? ' selected' : ''}>${esc(w.title)}</option>`).join('');
      switcher.hidden = xwins.length < 2;
    };
    if (isDefault) {
      win.tools.append(switcher);
      if (args.state) update(args.state);
    }

    /* the clipboard: what is copied elsewhere arrives on this app's X display */
    const toX = text => { try { rfb?.clipboardPasteFrom(text); } catch {} };
    const unsink = Akari.clip.sink(toX);

    /* keys a Linux app understands differently. On a Mac, ⌘C, ⌘V and their
       friends become Ctrl+…: Linux apps know no ⌘ for that, and the ⌘ key
       itself is not passed on. Pasting first fetches the computer's
       clipboard, so a copy made outside Akari arrives too. */
    const MAC = /Mac|iPhone|iPad/.test(navigator.platform);
    const XK = { ctrl: 0xffe3, shift: 0xffe1 };
    const combo = (letter, shift) => {
      if (!rfb) return;
      const ks = letter.toLowerCase().charCodeAt(0);
      const code = `Key${letter.toUpperCase()}`;
      rfb.sendKey(XK.ctrl, 'ControlLeft', true);
      if (shift) rfb.sendKey(XK.shift, 'ShiftLeft', true);
      rfb.sendKey(ks, code, true); rfb.sendKey(ks, code, false);
      if (shift) rfb.sendKey(XK.shift, 'ShiftLeft', false);
      rfb.sendKey(XK.ctrl, 'ControlLeft', false);
    };
    win.body.addEventListener('keydown', async e => {
      if (!rfb) return;
      if (MAC && e.key === 'Meta') { e.preventDefault(); e.stopImmediatePropagation(); return; }
      const mod = MAC ? e.metaKey : e.ctrlKey;
      if (!mod || e.altKey || !/^[a-z]$/i.test(e.key)) return;
      const k = e.key.toLowerCase();
      if (k === 'v' && !(e.shiftKey && !MAC)) {
        e.preventDefault(); e.stopImmediatePropagation();
        const text = await Akari.clip.read();
        if (text) toX(text);
        setTimeout(() => combo('v', false), 40);   // let the app's display take the text first
        return;
      }
      if (MAC) { e.preventDefault(); e.stopImmediatePropagation(); combo(k, e.shiftKey); }
    }, true);
    win.body.addEventListener('keyup', e => { if (MAC && rfb && (e.key === 'Meta' || e.metaKey)) { e.preventDefault(); e.stopImmediatePropagation(); } }, true);

    // whatever in the window is clicked, the keys go to the app
    win.body.addEventListener('pointerup', () => rfb?.focus({ preventScroll: true }));
    Akari.on('theme', () => { if (rfb) rfb.background = background(); });
    requestAnimationFrame(() => (sid ? connect() : start()));

    return {
      focus: () => rfb?.focus({ preventScroll: true }),
      state: update,
      close: async () => {
        if (isDefault && !closing && xwins.length) {
          const names = xwins.map(w => w.title).join(', ');
          const ok = await Akari.ask({ title: 'Programme beenden?', text: `Dieses Fenster zeigt, was aus dem Terminal gestartet wurde: ${names}. Schließen beendet diese Programme.`, ok: 'Beenden', danger: true });
          if (!ok) return false;
        }
        const quit = !closing || !isDefault;
        closing = true;
        unsink();
        rfb?.disconnect();
        if (sid && quit) Akari.api(`/api/display/${sid}`, { method: 'DELETE', quiet: true }).catch(() => {});
        return true;
      },
      quiet: () => { closing = true; },   // the last program went: close without ending anything
    };
  },
});

/* what the desktop's default display does, pushed from the workspace */
const onDisplay = st => {
  const w = Akari.windows().find(x => x.app === 'x:desktop');
  if (st.windows?.length) {
    if (w) w.hooks.state?.(st);
    else Akari.open('x:desktop', { sid: st.sid, state: st });
  } else if (w) {
    w.hooks.quiet?.();
    Akari.close(w);
  }
};

(async () => {
  await ready;
  let info;
  try { info = await Akari.api('/api/display/apps', { quiet: true }); } catch { return; }
  info.apps.forEach(register);
  register({ id: 'desktop', title: 'Linux-Apps', single: true });
  // installed or removed with apt meanwhile: the start menu asks again whenever it opens
  let known = new Set(info.apps.map(a => a.id));
  Akari.on('launcher', async () => {
    let now;
    try { now = await Akari.api('/api/display/apps', { quiet: true }); } catch { return; }
    const ids = new Set(now.apps.map(a => a.id));
    now.apps.filter(a => !known.has(a.id)).forEach(register);
    [...known].filter(id => !ids.has(id) && id.startsWith('d:')).forEach(id => Akari.unregister(`x:${id}`));
    known = ids;
  });
  // windows for apps that were running before the reload
  info.running.forEach(r => Akari.open(`x:${r.app}`, { sid: r.id }, { fresh: true }));
  if (info.default) onDisplay(info.default);
  Akari.on('xdisplay', onDisplay);
})();
