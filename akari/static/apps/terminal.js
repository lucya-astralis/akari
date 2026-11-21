/* Terminal: xterm.js on a real shell in the workspace (/api/term). Colours
   come from Facet's tokens, so it follows the theme and the accent. */
(() => {
  // ANSI colours that hold contrast on both grounds
  const ANSI = {
    dark: ['#2b2b34', '#ff6b72', '#3ecf8e', '#f2b53a', '#7aa2ff', '#c792ea', '#5fd7e6', '#c6c8d7',
           '#5b5b66', '#ff8f94', '#6ee0aa', '#f7cd70', '#9db9ff', '#dab2f2', '#8ae6f0', '#f2f2f4'],
    light: ['#121216', '#c4303d', '#13805a', '#9a5b00', '#2f56d0', '#8a3fb8', '#0f7c8c', '#5b5b66',
            '#73737f', '#d6454f', '#18966b', '#b06b00', '#4a6fe0', '#a052cc', '#1293a6', '#2b2b34'],
  };
  const NAMES = ['black', 'red', 'green', 'yellow', 'blue', 'magenta', 'cyan', 'white',
                 'brightBlack', 'brightRed', 'brightGreen', 'brightYellow', 'brightBlue', 'brightMagenta', 'brightCyan', 'brightWhite'];

  const isDark = () => {
    const bg = Akari.color('--surface').match(/\d+/g)?.map(Number) || [0, 0, 0];
    return (bg[0] + bg[1] + bg[2]) / 3 < 128;
  };
  const theme = () => {
    const t = {
      background: Akari.color('--surface'), foreground: Akari.color('--text'),
      cursor: Akari.color('--acc'), cursorAccent: Akari.color('--surface'),
      selectionBackground: Akari.color('--acc-line'),
    };
    (isDark() ? ANSI.dark : ANSI.light).forEach((c, i) => t[NAMES[i]] = c);
    return t;
  };

  Akari.register('terminal', {
    title: 'Terminal', icon: 'i-term', art: 'terminal', multi: true, size: [780, 480], order: 20, desk: true,
    create(win, args = {}) {
      if (!window.Terminal) { win.body.textContent = 'xterm.js fehlt im Image.'; return {}; }
      win.body.classList.add('win__body--term');
      const host = document.createElement('div');
      host.className = 'term';
      win.body.append(host);

      const term = new Terminal({
        fontFamily: '"MesloLGS NF", "Akari Symbols", "JetBrains Mono", ui-monospace, monospace', fontSize: 13, lineHeight: 1.1, customGlyphs: true,
        cursorBlink: true, cursorStyle: 'bar', scrollback: 5000, theme: theme(), allowTransparency: false,
        macOptionIsMeta: true,
      });
      const fit = new FitAddon.FitAddon();
      term.loadAddon(fit);
      term.open(host);
      // the canvas renderer draws block and box characters edge to edge (fastfetch's logo, TUIs)
      if (window.CanvasAddon) { try { term.loadAddon(new CanvasAddon.CanvasAddon()); } catch {} }
      try { fit.fit(); } catch {}

      const proto = location.protocol === 'https:' ? 'wss' : 'ws';
      // args.run: a terminal program from its .desktop file (htop, vim), else the login shell
      const ws = new WebSocket(`${proto}://${location.host}/api/term?cols=${term.cols}&rows=${term.rows}${args.run ? `&run=${encodeURIComponent(args.run)}` : ''}`);
      if (args.title) win.setTitle(args.title);
      ws.binaryType = 'arraybuffer';
      const enc = new TextEncoder();
      let ended = false;
      ws.onmessage = e => term.write(new Uint8Array(e.data));
      ws.onclose = () => {
        ended = true;
        term.write('\r\n\x1b[2m[Sitzung beendet. Fenster schließt …]\x1b[0m\r\n');
        setTimeout(() => win.close(), 900);
      };
      term.onData(d => { if (ws.readyState === 1) ws.send(enc.encode(d)); });
      term.onBinary(d => { if (ws.readyState === 1) ws.send(Uint8Array.from(d, c => c.charCodeAt(0) & 255)); });
      term.onResize(({ cols, rows }) => { if (ws.readyState === 1) ws.send(JSON.stringify({ t: 'r', c: cols, r: rows })); });
      term.onTitleChange(t => win.setTitle(args.title || (t ? `Terminal · ${t}` : 'Terminal')));

      /* copy and paste: ⌘C/⌘V on a Mac work as in any text field; elsewhere
         Ctrl+Shift+C/V (Ctrl+C stays the interrupt it is in a shell). A copy
         goes to Akari's clipboard, so the Linux apps get it too. */
      const copy = () => {
        const sel = term.getSelection();
        if (!sel) return false;
        Akari.clip.set(sel);
        return true;
      };
      const paste = async () => {
        const text = await Akari.clip.read();
        if (text) term.paste(text);
        term.focus();
      };
      term.attachCustomKeyEventHandler(e => {
        if (e.type !== 'keydown' || !e.ctrlKey || !e.shiftKey || e.metaKey || e.altKey) return true;
        if (e.code === 'KeyC') { copy(); e.preventDefault(); return false; }
        if (e.code === 'KeyV') { paste(); e.preventDefault(); return false; }
        return true;
      });
      host.addEventListener('contextmenu', e => {
        const has = term.hasSelection();
        Akari.menu(e, [
          { label: 'Kopieren', icon: 'i-file', hint: navigator.platform.includes('Mac') ? '⌘C' : '⌃⇧C', disabled: !has, act: () => { copy(); term.focus(); } },
          { label: 'Einfügen', icon: 'i-edit', hint: navigator.platform.includes('Mac') ? '⌘V' : '⌃⇧V', act: paste },
          '-',
          { label: 'Alles auswählen', icon: 'i-max', act: () => { term.selectAll(); term.focus(); } },
          { label: 'Leeren', icon: 'i-x', act: () => { term.clear(); term.focus(); } },
        ]);
      });

      const onTheme = () => { term.options.theme = theme(); };
      Akari.on('theme', onTheme);
      // p10k's icons need MesloLGS NF: once it is there, measure the cells again
      Promise.all([...['400', '700'].map(w => document.fonts?.load(`${w} 13px "MesloLGS NF"`)),
                   document.fonts?.load('13px "Akari Symbols"', '\u{F0000}')]).catch(() => {}).then(() => {
        term.options.fontFamily = term.options.fontFamily;
        try { fit.fit(); } catch {}
      });

      return {
        focus: () => term.focus(),
        resize: () => { try { fit.fit(); } catch {} },
        close: () => {
          if (!ended && ws.readyState === 1) ws.close();
          setTimeout(() => { try { term.dispose(); } catch {} }, 400);   // xterm 5.3: the canvas addon throws while it is torn down
        },
      };
    },
  });
})();
