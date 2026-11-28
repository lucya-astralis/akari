/* AKARI: the desktop surface. Icons and widgets that can be moved with the
   mouse (each desktop keeps its own arrangement), the widgets themselves
   (clock, performance, a note), a picture as background, and the
   right-click menus of the surface. */
(() => {
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => [...el.querySelectorAll(s)];
  const t = s => Akari.t(s);
  const GRID = 8, ICON_W = 88, ICON_H = 92;

  const area = () => $('#windows').getBoundingClientRect();
  const layout = () => Akari.prefs.layout || { icons: {}, widgets: {} };
  const saveLayout = l => Akari.set('layout', l);
  const snap = v => Math.round(v / GRID) * GRID;
  const clamp = (x, y, el) => {
    const a = area();
    return [Math.max(0, Math.min(a.width - el.offsetWidth, x)), Math.max(0, Math.min(a.height - el.offsetHeight, y))];
  };
  const place = (el, x, y) => { el.style.left = `${x}px`; el.style.top = `${y}px`; };

  /* ---------- icons, on a grid ----------
     Each icon owns a cell {c, r}; a dropped icon takes the nearest cell, and
     if another icon is there, the two swap. Without a saved cell, icons fill
     the columns from the right. "Am Raster ausrichten" off: free pixels. */
  const CELL_W = 96, CELL_H = 104, PAD = 12;
  const gridOn = () => Akari.prefs.grid !== false;
  const dims = () => {
    const a = area();
    return { cols: Math.max(1, Math.floor((a.width - PAD * 2) / CELL_W)), rows: Math.max(1, Math.floor((a.height - PAD * 2) / CELL_H)), a };
  };
  const cellXY = ({ c, r }) => [PAD + c * CELL_W + (CELL_W - ICON_W) / 2, PAD + r * CELL_H];
  const nearest = (x, y) => {
    const { cols, rows } = dims();
    return { c: Math.max(0, Math.min(cols - 1, Math.round((x - PAD) / CELL_W))), r: Math.max(0, Math.min(rows - 1, Math.round((y - PAD) / CELL_H))) };
  };
  const key = ({ c, r }) => `${c}:${r}`;
  // where every visible icon sits now: saved cells first, then the free ones from the right
  const cells = () => {
    const l = layout(), { cols, rows } = dims(), hidden = Akari.prefs.hiddenIcons || [];
    const out = {}, taken = new Set();
    const icons = $$('#icons .icon').filter(el => !hidden.includes(el.dataset.app));
    for (const el of icons) {
      const p = l.icons?.[el.dataset.app];
      if (p && typeof p.c === 'number') {
        const cell = { c: Math.min(cols - 1, p.c), r: Math.min(rows - 1, p.r) };
        if (!taken.has(key(cell))) { out[el.dataset.app] = cell; taken.add(key(cell)); }
      }
    }
    let c = cols - 1, r = 0;
    for (const el of icons) {
      if (out[el.dataset.app]) continue;
      while (taken.has(key({ c, r }))) { r++; if (r >= rows) { r = 0; c = Math.max(0, c - 1); } }
      out[el.dataset.app] = { c, r }; taken.add(key({ c, r }));
    }
    return out;
  };
  const placeIcons = () => {
    const l = layout(), a = area(), hidden = Akari.prefs.hiddenIcons || [];
    const grid = gridOn() ? cells() : null;
    $$('#icons .icon').forEach((el, i) => {
      el.hidden = hidden.includes(el.dataset.app);
      if (el.hidden) return;
      if (grid) return place(el, ...cellXY(grid[el.dataset.app]));
      const p = l.icons?.[el.dataset.app];
      const [x, y] = Array.isArray(p) ? clamp(p[0], p[1], el) : [a.width - ICON_W - 16, 16 + i * ICON_H];
      place(el, x, y);
    });
  };
  // the cell an icon will land in, shown while it is dragged
  const ghost = document.createElement('div');
  ghost.className = 'desk-cell';
  ghost.hidden = true;
  $('#icons').before(ghost);
  const showGhost = (x, y) => {
    if (!gridOn()) return;
    const cell = nearest(x, y), [gx, gy] = cellXY(cell);
    ghost.hidden = false;
    ghost.style.transform = `translate(${gx - (CELL_W - ICON_W) / 2}px, ${gy}px)`;
  };
  const dropIcon = (el, x, y) => {
    const l = structuredClone(layout());
    l.icons ||= {};
    if (!gridOn()) { l.icons[el.dataset.app] = [snap(x), snap(y)]; return saveLayout(l); }
    const now = cells(), mine = now[el.dataset.app], cell = nearest(x, y);
    const other = Object.keys(now).find(id => id !== el.dataset.app && key(now[id]) === key(cell));
    for (const [id, c] of Object.entries(now)) l.icons[id] = c;   // everyone keeps their place from now on
    l.icons[el.dataset.app] = cell;
    if (other && mine) l.icons[other] = mine;                       // the two swap
    saveLayout(l);
  };

  /* ---------- dragging: icons and widgets alike ---------- */
  let dragged = false;
  const draggable = (el, kind, key) => {
    el.addEventListener('pointerdown', e => {
      if (e.button !== 0 || e.target.closest('textarea, input, button:not(.icon)')) return;
      const r = el.getBoundingClientRect(), a = area();
      const dx = e.clientX - r.left, dy = e.clientY - r.top, sx = e.clientX, sy = e.clientY;
      let moving = false;
      const move = ev => {
        if (!moving && Math.hypot(ev.clientX - sx, ev.clientY - sy) < 5) return;
        if (!moving) { moving = true; el.classList.add('is-dragging'); el.setPointerCapture(e.pointerId); }
        const [x, y] = clamp(ev.clientX - a.left - dx, ev.clientY - a.top - dy, el);
        place(el, x, y);
        if (kind === 'icons') showGhost(x, y);
      };
      const up = () => {
        removeEventListener('pointermove', move);
        removeEventListener('pointerup', up);
        if (!moving) return;
        el.classList.remove('is-dragging');
        ghost.hidden = true;
        dragged = true; setTimeout(() => { dragged = false; }, 0);
        const x = parseFloat(el.style.left), y = parseFloat(el.style.top);
        if (kind === 'icons') return dropIcon(el, x, y);
        const [sx2, sy2] = clamp(snap(x), snap(y), el);
        place(el, sx2, sy2);
        const l = structuredClone(layout());
        (l[kind] ||= {})[key] = [sx2, sy2];
        saveLayout(l);
      };
      addEventListener('pointermove', move);
      addEventListener('pointerup', up);
    });
  };
  // a drag is not a click: the icon does not open
  document.addEventListener('click', e => { if (dragged && e.target.closest('.icon, .widget')) { e.stopPropagation(); e.preventDefault(); } }, true);

  const iconsReady = () => {
    $$('#icons .icon').forEach(el => { if (!el.dataset.drag) { el.dataset.drag = 1; draggable(el, 'icons', el.dataset.app); } });
    placeIcons();
  };
  Akari.on('launchers', iconsReady);

  /* ---------- widgets ---------- */
  // the weather's pictures, as line icons in the text colour
  const SUN = '<circle cx="12" cy="12" r="4"/><path d="M12 2.5v2M12 19.5v2M4.6 4.6l1.4 1.4M18 18l1.4 1.4M2.5 12h2M19.5 12h2M4.6 19.4 6 18M18 6l1.4-1.4"/>';
  const MOON = '<path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z"/>';
  const CLOUD = d => `<path d="M7 ${d}h10a4 4 0 0 0 .4-8 6 6 0 0 0-11.5 1.6A3.3 3.3 0 0 0 7 ${d}z"/>`;
  const WX = {
    clear: day => day ? SUN : MOON,
    partly: day => `<g transform="translate(-3 -3) scale(.62)">${day ? SUN : MOON}</g>${CLOUD(20)}`,
    cloudy: () => CLOUD(18),
    fog: () => `${CLOUD(14)}<path d="M4 18h16M6 21h12"/>`,
    rain: () => `${CLOUD(15)}<path d="M8 18l-1 3M12 18l-1 3M16 18l-1 3"/>`,
    snow: () => `${CLOUD(15)}<path d="M8 19h.01M12 21h.01M16 19h.01"/>`,
    storm: () => `${CLOUD(14)}<path d="m12 15-2 4h4l-2 4"/>`,
  };
  const weather = async el => {
    const b = $('[data-wx-place]', el);
    if (!b) return;
    if (Akari.prefs.weather === false) { b.hidden = true; return; }      // Einstellungen → Schreibtisch → Wetter
    const r = await Akari.api(`/api/weather?place=${encodeURIComponent(Akari.prefs.weatherPlace || '')}&unit=${Akari.prefs.weatherUnit === 'f' ? 'f' : 'c'}`, { quiet: true }).catch(() => null);
    if (Akari.prefs.weather === false) { b.hidden = true; return; }
    b.hidden = !r?.ok;
    if (!r?.ok) { el.wxAt = Date.now() - 14 * 60e3; return; }     // not reached: again in a minute, not in fifteen
    $('.w-wx__icon', b).innerHTML = (WX[r.kind] || WX.cloudy)(r.day);
    $('.w-wx__temp', b).textContent = `${r.temp}°`;
    $('.w-wx__place', b).textContent = r.place;
    b.dataset.place = r.place;
    b.setAttribute('aria-label', `${r.temp}°, ${r.place}. ${t('Ort ändern')}`);
  };
  document.addEventListener('click', async e => {
    const b = e.target.closest('[data-wx-place]');
    if (!b) return;
    const place = await Akari.ask({ title: t('Wetter für welchen Ort?'), text: t('Ein Ort, wie auf einer Karte. Gefragt wird Open-Meteo, mit nichts als diesem Namen.'), label: t('Ort'), value: b.dataset.place || '', ok: t('Übernehmen') });
    if (!place) return;
    Akari.set('weatherPlace', place.slice(0, 80));
    const el = b.closest('.widget'); el.wxAt = 0; weather(el);
  });
  const WIDGETS = {
    clock: {
      title: 'Uhr', size: [270, 0],
      // the time on the left, the weather on the right (weather.py, Open-Meteo; a click picks the place)
      html: `<div class="w-clock__now"><time class="w-clock__time"></time><span class="w-clock__date"></span></div>
        <button class="w-wx" data-wx-place hidden><svg class="w-wx__icon" viewBox="0 0 24 24" aria-hidden="true"></svg><b class="w-wx__temp"></b><small class="w-wx__place" translate="no"></small></button>`,
      tick(el) {
        const d = new Date();
        $('.w-clock__time', el).textContent = d.toLocaleTimeString(Akari.locale(), { hour: '2-digit', minute: '2-digit' });
        $('.w-clock__date', el).textContent = d.toLocaleDateString(Akari.locale(), { weekday: 'short', day: 'numeric', month: 'short' });
        if (!el.wxAt || Date.now() - el.wxAt > 15 * 60e3) { el.wxAt = Date.now(); weather(el); }
      },
    },
    perf: {
      title: 'Auslastung', size: [240, 0],
      html: `<div class="w-perf__row"><span>CPU</span><b data-v="cpu">–</b></div>
        <svg class="w-perf__spark" viewBox="0 0 100 30" preserveAspectRatio="none"><path data-line/></svg>
        <div class="w-perf__row"><span data-l="mem">Speicher</span><b data-v="mem">–</b></div>
        <div class="f-meter"><b data-m="mem"></b></div>
        <div class="w-perf__row w-perf__net"><span>↓ <b data-v="rx">–</b></span><span>↑ <b data-v="tx">–</b></span></div>`,
    },
    note: {
      title: 'Notiz', size: [240, 0],
      html: '<textarea class="w-note__text" spellcheck="false" placeholder="Notiz …" aria-label="Notiz" translate="no"></textarea>',
    },
    calendar: {
      title: 'Kalender', size: [250, 0],
      html: '<b class="w-cal__title"></b><div class="w-cal__grid"></div>',
      tick(el) {
        const now = new Date(), y = now.getFullYear(), m = now.getMonth(), key = `${y}-${m}-${now.getDate()}`;
        if (el.dataset.day === key) return;
        el.dataset.day = key;
        $('.w-cal__title', el).textContent = now.toLocaleDateString(Akari.locale(), { month: 'long', year: 'numeric' });
        const first = (new Date(y, m, 1).getDay() + 6) % 7, days = new Date(y, m + 1, 0).getDate();
        const dows = [...Array(7)].map((_, i) => new Date(2024, 0, 1 + i).toLocaleDateString(Akari.locale(), { weekday: 'short' }).slice(0, 2));
        const cells = dows.map(d => `<span class="is-dow">${d}</span>`);
        for (let i = 0; i < first; i++) cells.push('<span></span>');
        for (let d = 1; d <= days; d++) cells.push(`<span${d === now.getDate() ? ' class="is-today"' : ''}>${d}</span>`);
        $('.w-cal__grid', el).innerHTML = cells.join('');
      },
    },
    storage: {
      title: 'Speicherplatz', size: [240, 0],
      html: `<div class="w-perf__row"><span>Home</span><b data-v="home">–</b></div>
        <div class="w-perf__row"><span>Datenträger</span><b data-v="disk">–</b></div>
        <div class="f-meter"><b data-m="disk"></b></div>`,
    },
  };
  const DEFAULT_ON = ['clock', 'perf'];          // the note is one click away (Widgets), not there from the start
  const DEFAULT_POS = { clock: [24, 24], perf: [24, 150], note: [24, 330] };
  const host = $('#widgets');
  const cpuHist = [];

  // which widgets are on this desktop (0.4 kept a list of the ones taken away instead)
  const enabled = () => Array.isArray(Akari.prefs.widgetsOn)
    ? Akari.prefs.widgetsOn.filter(id => WIDGETS[id])
    : DEFAULT_ON.filter(id => !(Akari.prefs.widgetsOff || []).includes(id));
  const addWidget = id => {
    if (enabled().includes(id)) return;
    // a new widget goes under the lowest one in the left column, or top left
    const a = area();
    const bottom = Math.max(0, ...$$('.widget', host).map(w => w.getBoundingClientRect().bottom - a.top));
    const l = structuredClone(layout());
    (l.widgets ||= {})[id] = [24, bottom ? snap(bottom + 16) : 24];
    Akari.set('layout', l);
    Akari.set('widgetsOn', [...enabled(), id]);
    if (Akari.prefs.widgets === false) Akari.set('widgets', true);
  };
  const removeWidget = id => {
    const el = $(`.widget[data-w="${id}"]`, host);
    const go = () => Akari.set('widgetsOn', enabled().filter(x => x !== id));
    if (!el || Akari.prefs.motion) return go();
    el.classList.add('is-leaving');
    el.addEventListener('animationend', go, { once: true });
    setTimeout(go, 400);
  };

  const renderWidgets = () => {
    const show = Akari.prefs.widgets !== false, on = enabled();
    host.hidden = !show;
    $$('.widget', host).forEach(el => { if (!on.includes(el.dataset.w)) el.remove(); });
    for (const id of on) {
      const w = WIDGETS[id];
      let el = $(`.widget[data-w="${id}"]`, host);
      if (!el) {
        el = document.createElement('section');
        el.className = `widget widget--${id} f-glass f-glass--hi`;
        el.dataset.w = id;
        el.setAttribute('aria-label', t(w.title));
        el.style.width = `${w.size[0]}px`;
        el.innerHTML = `${w.html}<button class="widget__x" aria-label="${t('Widget entfernen')}" data-wx><svg><use href="#i-x"/></svg></button>`;
        host.append(el);
        draggable(el, 'widgets', id);
        if (id === 'note') {
          const ta = $('textarea', el);
          ta.value = Akari.prefs.note || '';
          let tmo; ta.addEventListener('input', () => { clearTimeout(tmo); tmo = setTimeout(() => Akari.set('note', ta.value.slice(0, 4000)), 500); });
        }
      }
      const p = layout().widgets?.[id] || DEFAULT_POS[id] || [24, 24];
      requestAnimationFrame(() => place(el, ...clamp(p[0], p[1], el)));
    }
    tickWidgets(); pollPerf();
  };
  host.addEventListener('click', e => { const x = e.target.closest('[data-wx]'); if (x) removeWidget(x.closest('.widget').dataset.w); });
  const tickWidgets = () => {
    if (host.hidden) return;
    for (const id of ['clock', 'calendar']) { const el = $(`.widget--${id}`, host); if (el) WIDGETS[id].tick(el); }
  };
  setInterval(tickWidgets, 1000);

  let perfT;
  const pollPerf = async () => {
    clearTimeout(perfT);
    const el = $('.widget--perf', host), st = $('.widget--storage', host);
    if ((!el && !st) || host.hidden || document.hidden) { perfT = setTimeout(pollPerf, 4000); return; }
    try {
      const s = await Akari.api('/api/stats', { quiet: true });
      if (st) {
        $('[data-v="disk"]', st).textContent = `${Akari.fmtBytes(s.disk.used)} / ${Akari.fmtBytes(s.disk.total)}`;
        $('[data-m="disk"]', st).style.setProperty('--v', `${(s.disk.used / s.disk.total * 100).toFixed(1)}%`);
        // the home's own size takes a walk through it: once a minute is enough
        if (!st.dataset.at || Date.now() - st.dataset.at > 60000) {
          st.dataset.at = Date.now();
          Akari.api('/api/system', { quiet: true }).then(sys => { $('[data-v="home"]', st).textContent = Akari.fmtBytes(sys.home_bytes); }).catch(() => {});
        }
      }
      if (!el) { perfT = setTimeout(pollPerf, 5000); return; }
      cpuHist.push(s.cpu); if (cpuHist.length > 40) cpuHist.shift();
      $('[data-v="cpu"]', el).textContent = `${Math.round(s.cpu)} %`;
      $('[data-line]', el).setAttribute('d', cpuHist.map((v, i) => `${i ? 'L' : 'M'}${(i / 39 * 100).toFixed(1)},${(30 - v / 100 * 28 - 1).toFixed(1)}`).join(''));
      $('[data-v="mem"]', el).textContent = `${Math.round(s.mem.used / s.mem.total * 100)} %`;
      $('[data-m="mem"]', el).style.setProperty('--v', `${(s.mem.used / s.mem.total * 100).toFixed(1)}%`);
      $('[data-v="rx"]', el).textContent = `${Akari.fmtBytes(s.net.rx)}/s`;
      $('[data-v="tx"]', el).textContent = `${Akari.fmtBytes(s.net.tx)}/s`;
    } catch {}
    perfT = setTimeout(pollPerf, 2000);
  };

  /* ---------- the background picture ---------- */
  // Akari's own, all drawn (design/wallpapers/make.py): id, name, light or dark
  const WALLS = [
    ['orikaia', 'Orikaia Prime', 'dark'], ['concordia', 'Concordia', 'dark'], ['mitternacht', 'Mitternacht', 'dark'],
    ['aurora', 'Aurora', 'light'], ['glas', 'Glas', 'light'],
  ];
  const wallUrl = w => w === 'own' ? `/api/wallpaper?v=${Akari.prefs.wallpaperV}` : `/assets/wallpapers/${w}.webp`;
  const wallpaper = () => {
    const w = Akari.wallSource(), image = Akari.wallImage(), desk = $('#desk');
    document.documentElement.toggleAttribute('data-wall-image', image);
    desk.style.setProperty('--wall', image ? `url("${wallUrl(w)}")` : 'none');
  };
  const setWall = w => Akari.set('wall', w);
  const pickWallpaper = () => {
    const inp = document.createElement('input');
    inp.type = 'file'; inp.accept = 'image/jpeg,image/png,image/webp,image/gif';
    inp.onchange = async () => {
      const f = inp.files[0]; if (!f) return;
      const fd = new FormData(); fd.append('file', f, f.name);
      try {
        const r = await Akari.api('/api/wallpaper', { method: 'POST', body: fd });
        Akari.set('wallpaperV', r.v);
        setWall('own');
      } catch {}
    };
    inp.click();
  };
  const dropWallpaper = async () => {
    await Akari.api('/api/wallpaper', { method: 'DELETE', quiet: true }).catch(() => {});
    Akari.set('wallpaperV', 0);
    if (Akari.wallSource() === 'own') setWall('nova');
  };

  /* ---------- right-click on the surface, icons, widgets ---------- */
  $('#desk').addEventListener('contextmenu', e => {
    if (e.target.closest('.win, .taskbar, .pop, #ctx, textarea, input')) return;
    const icon = e.target.closest('.icon'), wid = e.target.closest('.widget');
    if (icon) {
      const id = icon.dataset.app;
      return Akari.menu(e, [
        { label: 'Öffnen', icon: 'i-chev', act: () => Akari.open(id) },
        { label: 'Neues Fenster', icon: 'i-plus', act: () => Akari.open(id, {}, { fresh: true }) },
        '-',
        { label: 'Vom Schreibtisch nehmen', icon: 'i-x', act: () => Akari.set('hiddenIcons', [...(Akari.prefs.hiddenIcons || []), id]) },
      ]);
    }
    if (wid) {
      const id = wid.dataset.w;
      return Akari.menu(e, [
        { label: 'Widget entfernen', icon: 'i-x', act: () => removeWidget(id) },
      ]);
    }
    const missing = Object.keys(WIDGETS).filter(id => !enabled().includes(id));
    Akari.menu(e, [
      { label: 'Neues Terminal', icon: 'i-term', hint: '⌃⇧T', act: () => Akari.open('terminal', {}, { fresh: true }) },
      { label: 'Neue Textdatei', icon: 'i-edit', act: () => Akari.open('editor', {}, { fresh: true }) },
      { label: 'Dateien', icon: 'i-drive', act: () => Akari.open('files') },
      '-',
      { label: 'Hintergrund ändern …', icon: 'i-image', act: pickWallpaper },
      Akari.prefs.wallpaperV && { label: 'Bild entfernen', icon: 'i-trash', act: dropWallpaper },
      '-',
      // widgets: each one that is not on the desktop can be added from here
      ...missing.map(id => ({ label: `${t('Widget hinzufügen')}: ${t(WIDGETS[id].title)}`, icon: 'i-plus', act: () => addWidget(id) })),
      enabled().length && { label: Akari.prefs.widgets === false ? 'Widgets zeigen' : 'Widgets ausblenden', icon: 'i-pulse', act: () => Akari.set('widgets', Akari.prefs.widgets === false) },
      { label: 'Alle Symbole zeigen', icon: 'i-eye', disabled: !Akari.prefs.hiddenIcons?.length, act: () => Akari.set('hiddenIcons', []) },
      '-',
      { label: Akari.prefs.grid === false ? 'Am Raster ausrichten' : 'Frei anordnen', icon: 'i-dock', act: () => Akari.set('grid', Akari.prefs.grid === false) },
      { label: 'Anordnung zurücksetzen', icon: 'i-refresh', act: () => { Akari.set('layout', { icons: {}, widgets: {} }); } },
      '-',
      { label: 'Einstellungen', icon: 'i-gear', act: () => Akari.open('settings') },
    ]);
  });

  Akari.desk = { pickWallpaper, dropWallpaper, setWall, WALLS, wallUrl, addWidget, removeWidget, enabledWidgets: enabled, WIDGETS };
  let wxSeen = '';
  Akari.on('prefs', () => {
    wallpaper(); placeIcons(); renderWidgets();
    const P = Akari.prefs, now = `${P.weather}|${P.weatherPlace || ''}|${P.weatherUnit || 'c'}`;
    if (now !== wxSeen) { wxSeen = now; const c = $('.widget--clock'); if (c) { c.wxAt = Date.now(); weather(c); } }
  });
  addEventListener('resize', () => { placeIcons(); renderWidgets(); });
  document.addEventListener('visibilitychange', () => { if (!document.hidden) pollPerf(); });
  const start = () => { wallpaper(); iconsReady(); renderWidgets(); };
  Akari.ready ? start() : Akari.on('ready', start);
})();
