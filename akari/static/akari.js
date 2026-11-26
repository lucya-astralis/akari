/* AKARI — the shell: preferences, windows, dock, bar. Apps register
   themselves (apps/*.js) with Akari.register(id, spec) and get a window:

     spec = { title, icon, multi, size:[w,h], dock:true, desk:true, order,
              create(win, args) -> { focus?, resize?, theme?, close? } }

   close() may return false (or a promise of false) to keep the window open.
   Facet (facet.js) does the theme, toasts, ripples and segment thumbs. */
(() => {
  const root = document.documentElement;
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => [...el.querySelectorAll(s)];
  // a phone: narrow, or a touch screen lying on its side. Then the desktop is a
  // home screen with every app, and apps fill the screen (root[data-phone])
  const narrow = matchMedia('(max-width: 639px), (pointer: coarse) and (max-height: 479px)');
  const setForm = () => root.toggleAttribute('data-phone', narrow.matches);
  setForm();
  // language (i18n.js): German is the source, t() gives the reader's language
  const t = s => window.AkariI18n?.t(s) ?? s;
  const locale = () => window.AkariI18n?.locale() ?? 'de-DE';

  /* ---------- talking to the workspace ---------- */
  const api = async (path, { method = 'GET', json, body, quiet = false } = {}) => {
    const opts = { method, headers: {} };
    if (json !== undefined) { opts.body = JSON.stringify(json); opts.headers['Content-Type'] = 'application/json'; }
    else if (body !== undefined) opts.body = body;
    let r;
    try { r = await fetch(path, opts); }
    catch { if (!quiet) Facet.toast('Der Workspace antwortet nicht.', { tone: 'err' }); throw new Error('offline'); }
    if (r.status === 401) { location.reload(); throw new Error('signed out'); }
    const data = (r.headers.get('content-type') || '').includes('json') ? await r.json() : null;
    if (!r.ok) {
      const msg = data?.detail || `Fehler ${r.status}`;
      if (!quiet) Facet.toast(typeof msg === 'string' ? msg : `Fehler ${r.status}`, { tone: 'err' });
      throw new Error(msg);
    }
    return data;
  };

  /* ---------- preferences: in the home folder, cached for a fast first paint ---------- */
  const DEFAULTS = {
    theme: 'system', tint: '', wallpaper: true, mirror: false, motion: false, lite: false, cursors: true, novaLogo: 'none', tintH: 300,
    dock: 'm', autohide: false, icons: true, seconds: false, date: true, dnd: false, widgets: true, bar: 'bottom', grid: true, pinned: null,
  };
  let P = { ...DEFAULTS };
  let prefsLoaded = false;     // nothing is written back before this desktop's own prefs have arrived
  let saveT;
  const save = () => {
    if (!prefsLoaded) return;
    try { localStorage.setItem('akari-prefs-last', JSON.stringify({ tint: P.tint, nova: novaSide(), wallpaper: P.wallpaper !== false && !P.wallpaperV, cursors: P.cursors !== false, tintH: P.tintH })); } catch {}
    clearTimeout(saveT);
    saveT = setTimeout(() => api('/api/prefs', { method: 'PUT', json: P, quiet: true }).catch(() => {}), 400);
  };
  const set = (k, v) => { P[k] = v; save(); apply(); emit('prefs'); };

  if (window.Facet && !Facet.layout.akari) {
    const layout = Facet.layout;
    Facet.layout = () => {
      const marks = document.querySelectorAll('.f-seg__thumb, .f-tabs__ink');
      marks.forEach(m => { m.style.transition = 'none'; });
      layout();
      void document.body.offsetWidth;
      requestAnimationFrame(() => marks.forEach(m => { m.style.transition = ''; }));
    };
    Facet.layout.akari = true;
  }
  const novaSide = () => (['left', 'right', 'both'].includes(P.nova) ? P.nova : (P.mirror ? 'right' : 'left'));
  const flag = (name, on, val = '') => on ? root.setAttribute(name, val) : root.removeAttribute(name);
  const apply = () => {
    if (P.tint) root.dataset.tint = P.tint; else delete root.dataset.tint;
    // a hue of the person's own (Akzent → Eigene): the tint's hue, Facet keeps lightness and chroma
    if (P.tint === 'custom') root.style.setProperty('--akari-h', +P.tintH || 0); else root.style.removeProperty('--akari-h');
    dispatchEvent(new Event('akari:hue'));   // accent.js paints the cursors anew
    flag('data-wallpaper', !P.wallpaper, 'off');
    // Nova's light: from the left, the right or both sides (before 0.6.1: mirror on or off)
    flag('data-mirror', novaSide() === 'right');
    flag('data-nova', novaSide() === 'both', 'both');
    flag('data-nova-logo', ['akari', 'lucya'].includes(P.novaLogo), P.novaLogo);
    flag('data-motion', P.motion, 'reduced');
    flag('data-cursors', P.cursors === false, 'off');   // the own cursor set (cursors.css)
    root.classList.toggle('fx-lite', P.lite);
    root.dataset.dock = P.dock;
    root.dataset.bar = P.bar === "top" ? "top" : "bottom";
    root.dataset.barAlign = ['left', 'right', 'split'].includes(P.barAlign) ? P.barAlign : 'center';
    flag('data-autohide', P.autohide);
    $('#icons').hidden = !P.icons;
    tick();
    requestAnimationFrame(() => Facet.layout());
  };

  /* tiny event bus: 'prefs', 'theme', 'system' */
  const listeners = {};
  const on = (ev, fn) => (listeners[ev] ||= []).push(fn);
  const emit = (ev, data) => (listeners[ev] || []).forEach(fn => { try { fn(data); } catch (e) { console.error(e); } });

  // a Facet token, resolved to a colour the canvas of xterm or noVNC can use
  const probe = document.createElement('span');
  probe.style.display = 'none';
  document.body.append(probe);
  const color = token => { probe.style.color = `var(${token})`; return getComputedStyle(probe).color; };

  // theme: Facet owns the switch; we keep the choice in prefs and tell the apps
  const themeChanged = () => { clearTimeout(themeChanged.t); themeChanged.t = setTimeout(() => emit('theme'), 60); };
  new MutationObserver(() => {
    const t = root.dataset.theme || 'system';
    if (t !== P.theme) { P.theme = t; save(); emit('prefs'); }
    themeChanged();
    setTimeout(themeChanged, 760);   // the hue glides for --dur-4
  }).observe(root, { attributes: true, attributeFilter: ['data-theme', 'data-tint'] });
  matchMedia('(prefers-color-scheme: dark)').addEventListener('change', themeChanged);

  /* ---------- system facts ---------- */
  let SYS = null, ME = null;
  const loadSystem = () => api('/api/system', { quiet: true }).then(s => {
    SYS = s;
    emit('system', s);
    return s;
  }).catch(() => null);
  const loadSession = () => api('/api/session', { quiet: true }).then(me => {
    ME = me;
    avatar($('#bar-avatar'), me);
    $('#launch-name').textContent = me.fullname;
    $('#launch-desk').textContent = me.desktop ? `${me.name} · ${t('Desktop')} „${me.desktop.name}“` : me.name;
    const desk = $('#bar-desk');
    desk.hidden = $('#tb-desk-sep').hidden = !me.desktop;
    if (me.desktop) $('span', desk).textContent = me.desktop.name;
    emit('session', me);
    return me;
  }).catch(() => null);

  /* leaving: switch user keeps the apps, sign out ends them */
  const leave = async mode => {
    if (mode === 'end') {
      const ok = await ask({ title: 'Abmelden?', text: 'Alle Desktops dieses Kontos, ihre Apps und Terminals werden beendet. Nicht gesicherte Änderungen gehen verloren.', ok: 'Abmelden', danger: true });
      if (!ok) return;
    }
    if (mode === 'end-desktop') {
      const ok = await ask({ title: `Desktop „${ME?.desktop?.name || ''}“ beenden?`, text: 'Seine Apps werden beendet. Der Desktop bleibt und startet beim nächsten Mal leer.', ok: 'Beenden', danger: true });
      if (!ok) return;
    }
    if (mode === 'end' || mode === 'end-desktop') {
      // everything ends: windows close first, so editors can still ask about unsaved changes
      for (const w of [...WINS]) { await close(w); if (WINS.has(w)) return; }
    } else if ([...WINS].some(w => w.hooks.dirty?.())) {
      // the apps keep running, but this page goes: unsaved text would be lost
      const ok = await ask({ title: 'Nicht gesicherte Änderungen', text: 'Ein Editor hat Text, der noch nicht gesichert ist. Er geht verloren, wenn du jetzt wechselst.', ok: 'Trotzdem wechseln', danger: true });
      if (!ok) return;
    }
    document.body.classList.add('is-leaving');
    await api('/api/logout', { method: 'POST', json: { mode }, quiet: true }).catch(() => {});
    location.replace('/');
  };

  /* ---------- clock ---------- */
  const tick = () => {
    const d = new Date();
    $('#clock').textContent = d.toLocaleTimeString(locale(), { hour: '2-digit', minute: '2-digit', ...(P.seconds ? { second: '2-digit' } : {}) });
    $('#clock').dateTime = d.toISOString();
    const date = $('#clock-date');
    date.hidden = !P.date;
    date.textContent = d.toLocaleDateString(locale(), { day: '2-digit', month: '2-digit', year: 'numeric' });
    const ht = $('#home-time');
    if (ht) {
      ht.textContent = d.toLocaleTimeString(locale(), { hour: '2-digit', minute: '2-digit' });
      $('#home-date').textContent = d.toLocaleDateString(locale(), { weekday: 'long', day: 'numeric', month: 'long' });
    }
  };
  setInterval(tick, 1000);

  /* notifications: a toast (unless "Nicht stören"), and always kept in the bell's list */
  const BELL = [];
  const escHtml = v => String(v).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  // an account's face: its picture if it has one, else its initial
  const avatar = (el, who) => {
    if (!el || !who) return;
    el.textContent = '';
    el.classList.toggle('has-img', !!who.avatar);
    if (who.avatar) { const i = new Image(); i.src = who.avatar; i.alt = ''; i.decoding = 'async'; el.append(i); }
    else el.textContent = who.initial;
  };
  const renderBell = () => {
    $('#bell-list').innerHTML = BELL.length ? BELL.map(n => `
      <div class="bell__item"><span class="f-status f-status--${n.tone}"></span><span>${escHtml(n.msg)}</span>
      <small>${n.at.toLocaleTimeString(locale(), { hour: '2-digit', minute: '2-digit' })}</small></div>`).join('')
      : `<div class="bell__empty">${t('Keine Mitteilungen.')}</div>`;
  };
  const notify = (msg, opts = {}) => {
    BELL.unshift({ msg, tone: opts.tone || 'ok', at: new Date() });
    BELL.length = Math.min(BELL.length, 50);
    $('#tb-bell-dot').hidden = false;
    renderBell();
    if (!P.dnd || opts.tone === 'err') Facet.toast(msg, opts);
  };

  /* ---------- dialogs: ask / confirm / prompt ---------- */
  const dlg = $('#dlg-ask');
  const ask = ({ title, text = '', label, value, ok = 'OK', danger = false, type = 'text' }) => new Promise(res => {
    $('[data-title]', dlg).textContent = title;
    $('[data-text]', dlg).textContent = text;
    $('[data-text]', dlg).hidden = !text;
    const field = $('[data-field]', dlg), input = $('input', dlg);
    field.hidden = label === undefined;
    if (label !== undefined) { $('[data-label]', dlg).textContent = label; input.value = value || ''; input.type = type; }
    const okBtn = $('[data-ok]', dlg);
    okBtn.textContent = ok;
    okBtn.className = `f-btn ${danger ? 'f-btn--danger' : 'f-btn--primary'}`;
    dlg.returnValue = '';
    dlg.showModal();
    if (label !== undefined) {
      input.focus();
      const dot = (value || '').lastIndexOf('.');
      if (type === 'text') input.setSelectionRange(0, dot > 0 ? dot : (value || '').length);
    }
    dlg.addEventListener('close', () => {
      if (dlg.returnValue !== 'ok') return res(label === undefined ? false : null);
      res(label === undefined ? true : input.value.trim() || null);
    }, { once: true });
  });
  // Enter in the field means OK: the browser would otherwise submit with the
  // first button in the form, which is "Abbrechen"
  $('input', dlg).addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.isComposing) { e.preventDefault(); dlg.close('ok'); }
  });

  /* ---------- the app registry ---------- */
  const APPS = new Map();
  const unregister = id => { if (APPS.delete(id)) renderLaunchers(); };
  const register = (id, spec) => {
    APPS.set(id, { id, dock: true, desk: false, multi: false, size: [760, 520], order: 50, ...spec });
    renderLaunchers();
  };

  // an app's colour icon (index.html: #app-*), or its line icon when it has none
  const art = a => a.art ? `app-${a.art}` : a.icon;
  // an app's picture as markup: its own image (an installed Linux program) or Akari's tile
  const artHtml = (a, cls = 'app-art') => a?.img
    ? `<img class="${cls}" src="${escHtml(a.img)}" alt="" draggable="false" decoding="async">`
    : `<svg class="${cls}"><use href="#${art(a || {})}"/></svg>`;

  /* ---------- the taskbar's apps ----------
     Pinned apps first, in the order the person dragged them; then whatever
     runs without being pinned. Changes are applied as a diff, so icons can
     glide in and out and the pill slides to its new width. */
  const reduced = () => P.motion || matchMedia('(prefers-reduced-motion: reduce)').matches;
  const SPRING = 'cubic-bezier(.34, 1.4, .64, 1)';
  const pinned = () => {
    if (Array.isArray(P.pinned)) return P.pinned.filter(id => APPS.has(id));
    return [...APPS.values()].filter(a => a.dock).sort((a, b) => a.order - b.order).map(a => a.id);
  };
  const isPinned = id => pinned().includes(id);
  const pin = (id, on) => {
    const list = pinned().filter(x => x !== id);
    if (on) list.push(id);
    set('pinned', list);
    renderDock();
  };
  // the pill takes its new width with a spring instead of jumping
  // a pill glides to its new width. Its content is already where it ends up, so
  // while the pill is narrower than that it clips sideways (never up: the icons
  // grow out of it); a glide that is still running is stopped first, else the
  // new width would be measured on the old animation's width.
  const glidePill = (pill, change) => {
    const w0 = pill.getBoundingClientRect().width;
    pill.getAnimations().forEach(a => a.cancel());
    change();
    if (reduced()) return;
    const w1 = pill.getBoundingClientRect().width;
    if (Math.abs(w1 - w0) <= 1) return;
    pill.classList.add('is-gliding');
    const a = pill.animate([{ width: `${w0}px` }, { width: `${w1}px` }], { duration: 420, easing: SPRING });
    const done = () => { if (!pill.getAnimations().length) pill.classList.remove('is-gliding'); };
    a.finished.then(done, done);
  };
  const renderDock = () => {
    const dock = $('#dock');
    const pins = pinned();
    const running = [...new Set([...WINS].map(w => w.app))].filter(id => !pins.includes(id) && APPS.get(id)?.launch !== false);
    const want = [...pins, ...running];
    const have = $$('.dock__app', dock).filter(b => !b.classList.contains('is-leaving')).map(b => b.dataset.app);
    if (want.join() === have.join()) return markRunning();
    glidePill(dock.closest('.tb'), () => {
      // leaving: shrink away, then go
      $$('.dock__app', dock).forEach(b => {
        if (want.includes(b.dataset.app) || b.classList.contains('is-leaving')) return;
        if (reduced()) return b.remove();
        b.classList.add('is-leaving');
        b.addEventListener('animationend', () => b.remove(), { once: true });
        setTimeout(() => b.remove(), 500);
      });
      // staying and coming, in order
      want.forEach((id, i) => {
        const a = APPS.get(id);
        let b = $(`.dock__app[data-app="${CSS.escape(id)}"]:not(.is-leaving)`, dock);
        if (!b) {
          b = document.createElement('button');
          b.className = 'dock__app f-tip';
          b.dataset.tip = a.title; b.dataset.app = a.id; b.setAttribute('aria-label', a.title);
          b.innerHTML = artHtml(a);
          if (have.length && !reduced()) b.classList.add('is-entering');
          b.addEventListener('animationend', () => b.classList.remove('is-entering'), { once: true });
        }
        b.classList.toggle('is-pinned', pins.includes(id));
        const at = dock.children[i];
        if (at !== b) dock.insertBefore(b, at || null);
      });
    });
    markRunning();
  };

  let showAll = null;
  on('prefs', () => {
    if (!APPS.size) return;
    if (showAll !== !!P.showAllApps) { showAll = !!P.showAllApps; return renderLaunchers(); }
    renderDock();
  });   // pinned apps changed elsewhere (another tab, a reset)

  const renderLaunchers = () => {
    const apps = [...APPS.values()].sort((a, b) => a.order - b.order);
    renderDock();
    const grid = $('#launch-apps');
    grid.innerHTML = '';
    // extras (terminal programs, other desktops' settings, XTerm) only when asked for
    apps.filter(a => a.launch !== false && (!a.extra || P.showAllApps)).forEach((a, i) => {
      const b = document.createElement('button');
      b.className = 'launch__app'; b.dataset.app = a.id; b.setAttribute('role', 'menuitem'); b.style.setProperty('--i', i);
      b.innerHTML = `${artHtml(a)}<span></span>`;
      b.lastChild.textContent = a.title;
      grid.append(b);
    });
    const home = $('#home-apps');
    if (home) {
      home.innerHTML = '';
      apps.filter(a => a.launch !== false && (!a.extra || P.showAllApps)).forEach((a, i) => {
        const b = document.createElement('button');
        b.className = 'home__app'; b.dataset.app = a.id; b.style.setProperty('--i', i);
        b.innerHTML = `<span class="home__art">${artHtml(a)}</span><span class="home__name"></span>`;
        b.lastChild.textContent = a.title;
        home.append(b);
      });
    }
    const icons = $('#icons');
    icons.innerHTML = '';
    apps.filter(a => a.desk).forEach((a, i) => {
      const b = document.createElement('button');
      b.className = 'icon'; b.dataset.app = a.id; b.style.setProperty('--i', i);
      b.innerHTML = `<span class="icon__img">${artHtml(a)}</span><span class="icon__name"></span>`;
      b.lastChild.textContent = a.title;
      icons.append(b);
    });
    markRunning();
    emit('launchers');
  };

  /* ---------- windows ---------- */
  let z = 10, cascade = 0;
  const WINS = new Set();
  const front = () => [...WINS].filter(w => !w.el.hidden).sort((a, b) => b.z - a.z)[0];
  const ofApp = id => [...WINS].filter(w => w.app === id).sort((a, b) => b.z - a.z);

  const markRunning = () => {
    const f = front();
    $$('.dock__app').forEach(b => {
      b.classList.toggle('is-run', ofApp(b.dataset.app).length > 0);
      b.classList.toggle('is-front', !!f && f.app === b.dataset.app);
    });
  };
  const updateBar = () => {
    const f = front();
    WINS.forEach(w => w.el.classList.toggle('is-front', w === f));
    root.toggleAttribute('data-app-open', !!(f && !f.el.hidden));
    renderDock();
    renderMin();
  };

  /* minimised windows: a shelf of their own at the end of the apps pill, the
     way macOS keeps them right of the dock. Oldest first; a new one opens
     its slot, the window flies into it, then the tile shows. */
  const minTile = w => $$('.min__win', $('#tb-min')).find(t => t.win === w && !t.classList.contains('is-leaving'));
  const renderMin = () => {
    const box = $('#tb-min');
    const want = [...WINS].filter(w => w.minimised).sort((a, b) => a.minAt - b.minAt);
    const tiles = $$('.min__win:not(.is-leaving)', box);
    tiles.forEach(tl => { tl.dataset.tip = tl.win.title; tl.setAttribute('aria-label', tl.win.title); });
    if (want.length === tiles.length && want.every((w, i) => tiles[i].win === w)) return;
    glidePill(box.closest('.tb'), () => {
      $('#tb-min-sep').hidden = !want.length;
      tiles.forEach(tl => {
        if (want.includes(tl.win)) return;
        if (reduced()) return tl.remove();
        tl.classList.add('is-leaving');
        tl.addEventListener('animationend', () => tl.remove(), { once: true });
        setTimeout(() => tl.remove(), 500);
      });
      want.forEach((w, i) => {
        let tl = tiles.find(x => x.win === w);
        if (!tl) {
          tl = document.createElement('button');
          tl.className = 'min__win f-tip is-waiting';
          tl.win = w;
          tl.dataset.tip = w.title; tl.setAttribute('aria-label', w.title);
          tl.innerHTML = `<span class="min__frame"><i></i>${artHtml(APPS.get(w.app))}</span>`;
        }
        const live = $$('.min__win:not(.is-leaving)', box);
        if (live[i] !== tl) box.insertBefore(tl, live[i] || null);
      });
      // where each new tile ends up, before the pill starts gliding to its width
      $$('.min__win.is-waiting', box).forEach(tl => { tl.target = tl.getBoundingClientRect(); });
    });
  };
  // the offset from a window's middle to a tile's middle: where minimising goes and restoring comes from
  const aim = (w, d) => {
    const r = w.el.getBoundingClientRect();
    w.el.style.setProperty('--mx-to', `${d.left + d.width / 2 - (r.left + r.width / 2)}px`);
    w.el.style.setProperty('--my-to', `${d.top + d.height / 2 - (r.top + r.height / 2)}px`);
  };
  const focus = w => {
    if (w.el.hidden || w.minimised) restore(w);
    w.z = ++z; w.el.style.zIndex = w.z;
    updateBar();
    w.hooks.focus?.();
  };

  const anim = (el, cls) => new Promise(res => {
    el.classList.add(cls);
    const done = () => { el.classList.remove(cls); res(); };
    el.addEventListener('animationend', done, { once: true });
    setTimeout(done, 700);
  });

  const place = w => {
    const area = $('#windows').getBoundingClientRect();
    const [ww, hh] = w.size;
    const W = Math.min(ww, area.width - 32), H = Math.min(hh, area.height - 96);
    w.el.style.width = `${W}px`; w.el.style.height = `${H}px`;
    const off = (cascade++ % 6) * 26;
    w.el.style.left = `${Math.max(16, (area.width - W) / 2 + off - 65)}px`;
    w.el.style.top = `${Math.max(10, (area.height - H) / 2 + off - 75)}px`;
  };

  const open = (id, args = {}, { fresh = false } = {}) => {
    const a = APPS.get(id);
    if (!a) return null;
    if (a.redirect) return a.redirect(args);
    const existing = ofApp(id);
    if (existing.length && (!a.multi || !fresh) && !args.path) { focus(existing[0]); existing[0].hooks.args?.(args); return existing[0]; }

    const el = $('#tpl-win').content.firstElementChild.cloneNode(true);
    el.dataset.app = id;
    $('.win__icon', el).outerHTML = artHtml(a, 'win__icon');
    const w = {
      app: id, el, z: 0, size: a.size, title: a.title, body: $('.win__body', el), tools: $('.win__tools', el), hooks: {},
      setTitle(t) { this.title = t || a.title; $('.win__name', el).textContent = this.title; el.setAttribute('aria-label', this.title); updateBar(); },
      close: () => close(w),
    };
    w.setTitle(a.title);
    $('#windows').append(el);
    WINS.add(w);
    place(w);
    bindWin(w);
    focus(w);
    anim(el, 'is-opening');
    const b = $(`.dock__app[data-app="${id}"]`);
    if (b) { b.classList.remove('is-bounce'); void b.offsetWidth; b.classList.add('is-bounce'); }
    try { w.hooks = a.create(w, args) || {}; }
    catch (e) { console.error(e); w.body.textContent = 'Diese App ist beim Start gescheitert.'; }
    new ResizeObserver(() => w.hooks.resize?.()).observe(w.body);
    requestAnimationFrame(() => { Facet.layout(); w.hooks.focus?.(); });
    markRunning();
    return w;
  };

  const close = async w => {
    if (w.closing) return;
    w.closing = true;
    const keep = await w.hooks.close?.();
    if (keep === false) { w.closing = false; return; }
    if (!w.el.hidden) await anim(w.el, 'is-closing');
    w.el.remove();
    WINS.delete(w);
    updateBar();
  };

  const minimise = async w => {
    if (w.minimised || w.closing) return;
    w.minimised = true; w.minAt = Date.now();
    renderMin();
    const tl = minTile(w);
    if (narrow.matches) aim(w, $(`.dock__app[data-app="${w.app}"]`)?.getBoundingClientRect() || { left: innerWidth / 2, top: innerHeight, width: 0, height: 0 });
    else if (tl) aim(w, tl.target || tl.getBoundingClientRect());
    await anim(w.el, 'is-minimising');
    if (!w.minimised) return;            // restored while it was still on its way
    w.el.hidden = true;
    tl?.classList.remove('is-waiting');
    updateBar();
  };
  // a minimised window comes back out of its tile, the way it went in
  const restore = w => {
    const tl = minTile(w);
    w.minimised = false;
    w.el.hidden = false;
    w.el.classList.remove('is-minimising');
    if (tl) aim(w, tl.getBoundingClientRect());
    anim(w.el, tl ? 'is-restoring' : 'is-opening');
  };

  const toggleMax = w => { w.el.classList.toggle('is-max'); requestAnimationFrame(() => Facet.layout()); };

  const bindWin = w => {
    const el = w.el, bar = $('[data-drag]', el), grip = $('[data-grip]', el);
    el.addEventListener('pointerdown', () => { if (front() !== w) focus(w); }, true);
    el.addEventListener('click', e => {
      const act = e.target.closest('[data-win]')?.dataset.win;
      if (act === 'close') close(w);
      if (act === 'min') minimise(w);
      if (act === 'max') toggleMax(w);
    });
    bar.addEventListener('dblclick', e => { if (!e.target.closest('button, input') && !narrow.matches) toggleMax(w); });

    const drag = (handle, onMove) => handle.addEventListener('pointerdown', e => {
      if (e.target.closest('button, input, select') || narrow.matches || e.button !== 0) return;
      e.preventDefault();
      const area = $('#windows').getBoundingClientRect();
      const r0 = el.getBoundingClientRect();
      const start = { x: e.clientX, y: e.clientY, r: r0, area };
      if (handle === bar && el.classList.contains('is-max')) {   // pull a maximised window out under the pointer
        const fx = (e.clientX - area.left) / area.width;
        el.classList.remove('is-max');
        const r = el.getBoundingClientRect();
        el.style.left = `${e.clientX - area.left - r.width * fx}px`;
        el.style.top = `${e.clientY - area.top - 22}px`;
        start.r = el.getBoundingClientRect();
      }
      handle.setPointerCapture(e.pointerId);
      el.classList.add('is-dragging');
      const move = ev => onMove(ev, start);
      const up = () => { el.classList.remove('is-dragging'); handle.removeEventListener('pointermove', move); w.hooks.focus?.(); };
      handle.addEventListener('pointermove', move);
      handle.addEventListener('pointerup', up, { once: true });
      handle.addEventListener('pointercancel', up, { once: true });
    });
    drag(bar, (ev, s) => {
      const x = Math.min(s.area.width - 80, Math.max(80 - s.r.width, s.r.left - s.area.left + ev.clientX - s.x));
      const y = Math.min(s.area.height - 44, Math.max(0, s.r.top - s.area.top + ev.clientY - s.y));
      el.style.left = `${x}px`; el.style.top = `${y}px`;
    });
    drag(grip, (ev, s) => {
      el.style.width = `${Math.max(320, s.r.width + ev.clientX - s.x)}px`;
      el.style.height = `${Math.max(220, s.r.height + ev.clientY - s.y)}px`;
    });
  };

  /* launchers: dock, desktop, menu. Dock: running → focus or minimise the
     front one; Shift opens another window of an app that can have several. */
  document.addEventListener('click', e => {
    const act = e.target.closest('[data-act]');
    if (act && act.closest('#brand-menu')) {
      closeMenu();
      if (act.dataset.act === 'switch') return leave('switch');
      if (act.dataset.act === 'logout') return leave('end');
      if (act.dataset.act === 'desktop') return leave('desktop');
      if (act.dataset.act === 'end-desktop') return leave('end-desktop');
    }
    if (e.target.closest('#bar-desk')) return leave('desktop');
    const tile = e.target.closest('.min__win');
    if (tile) return tile.win && focus(tile.win);
    const t = e.target.closest('.dock__app, .icon, .home__app, .launch__app, .launch__item[data-app], [data-open]');
    if (!t) return;
    const id = t.dataset.app || t.dataset.open;
    closeMenu();
    const ws = ofApp(id);
    let args = {};
    try { args = JSON.parse(t.dataset.args || '{}'); } catch {}
    if (t.classList.contains('dock__app') && ws.length && !e.shiftKey) {
      const w = ws[0];
      if (w === front() && !w.el.hidden) return minimise(w);
      return focus(w);
    }
    open(id, args, { fresh: e.shiftKey || t.hasAttribute('data-new') });
  });

  /* ---------- popovers over the taskbar: one at a time ---------- */
  let openPop = null;   // { pop, btn }
  const closePops = () => {
    if (!openPop) return;
    const { pop, btn } = openPop;
    openPop = null;
    btn?.setAttribute('aria-expanded', 'false');
    if (reduced()) { pop.hidden = true; return; }
    // out the way it came in, then gone
    pop.classList.add('is-closing');
    const done = () => { if (pop.classList.contains('is-closing')) { pop.classList.remove('is-closing'); pop.hidden = true; } };
    pop.addEventListener('animationend', done, { once: true });
    setTimeout(done, 300);
  };
  const closeMenu = closePops;
  // place a popover above its button, inside the window
  const placePop = (pop, btn) => {
    const b = btn.getBoundingClientRect(), w = pop.offsetWidth;
    // the start menu sits flush with the left edge of the apps pill; the others centre on their button
    const left = pop.id === 'brand-menu' ? btn.closest('.tb').getBoundingClientRect().left : b.left + b.width / 2 - w / 2;
    pop.style.left = `${Math.max(8, Math.min(innerWidth - w - 8, left))}px`;
  };
  const togglePop = (pop, btn, onOpen) => {
    if (openPop?.pop === pop) return closePops();
    closePops();
    pop.classList.remove('is-closing');
    pop.hidden = false;
    btn.setAttribute('aria-expanded', 'true');
    openPop = { pop, btn };
    onOpen?.();
    placePop(pop, btn);
    requestAnimationFrame(() => Facet.layout());
  };
  document.addEventListener('pointerdown', e => {
    if (openPop && !openPop.pop.contains(e.target) && !openPop.btn?.contains(e.target) && !e.target.closest?.("#ctx")) closePops();
  });

  /* ---------- the start menu ---------- */
  const brand = $('#brand'), menu = $('#brand-menu');
  const timeAgo = ts => {
    const s = Math.max(0, (Date.now() - ts) / 1000);
    if (s < 60) return t('gerade eben');
    if (s < 3600) return `${Math.floor(s / 60)} min`;
    const d = new Date(ts);
    return new Date().toDateString() === d.toDateString()
      ? d.toLocaleTimeString(locale(), { hour: '2-digit', minute: '2-digit' })
      : d.toLocaleDateString(locale(), { day: 'numeric', month: 'short' });
  };
  // files opened lately, kept in the desktop's prefs (the editor and Dateien report them)
  const recent = path => {
    const r = (P.recent || []).filter(x => x.path !== path);
    r.unshift({ path, at: Date.now() });
    set('recent', r.slice(0, 12));
  };
  const renderRecent = () => {
    const r = (P.recent || []).slice(0, 6);
    $('#launch-recent').innerHTML = r.length ? r.map(x => `
      <button class="launch__item" data-recent="${escHtml(x.path)}"><svg><use href="#i-file"/></svg>
        <span><b>${escHtml(x.path.split('/').pop())}</b><small>~/${escHtml(x.path)}</small></span><time>${timeAgo(x.at)}</time></button>`).join('')
      : `<p class="launch__empty">${t('Hier erscheinen Dateien, die du öffnest.')}</p>`;
  };
  // what the search can find: apps, the settings' pages, recent files
  const settingsPages = () => [...($('#tpl-settings')?.content.querySelectorAll('[data-nav] .f-nav__item') || [])]
    .filter(a => !a.hasAttribute('data-admin') || ME?.admin)
    .map(a => ({ page: a.dataset.page, title: a.textContent.trim(), keys: a.dataset.keys || '' }));
  const search = q => {
    q = q.trim().toLowerCase();
    $('#launch-body').hidden = !!q;
    const box = $('#launch-results');
    box.hidden = !q;
    if (!q) return;
    const hit = s => s.toLowerCase().includes(q);
    const apps = [...APPS.values()].filter(a => a.launch !== false && (!a.extra || P.showAllApps) && (hit(t(a.title)) || hit(a.comment || '') || (a.keywords || []).some(hit)));
    const pages = settingsPages().filter(p => hit(p.title) || hit(p.keys));
    const files = (P.recent || []).filter(x => hit(x.path));
    const rows = [
      ...apps.map(a => `<button class="launch__item" data-app="${a.id}">${artHtml(a)}<span><b>${escHtml(t(a.title))}</b><small>${escHtml(a.comment || t('App'))}</small></span></button>`),
      ...pages.map(p => `<button class="launch__item" data-open="settings" data-args='{"page":"${p.page}"}'><svg><use href="#i-gear"/></svg><span><b>${escHtml(p.title)}</b><small>${t('Einstellungen')}</small></span></button>`),
      ...files.map(x => `<button class="launch__item" data-recent="${escHtml(x.path)}" translate="no"><svg><use href="#i-file"/></svg><span><b>${escHtml(x.path.split('/').pop())}</b><small>~/${escHtml(x.path)}</small></span></button>`),
    ];
    box.innerHTML = rows.length ? rows.join('') : `<p class="launch__empty">${t('Nichts gefunden.')}</p>`;
    box.querySelector('.launch__item')?.classList.add('is-first');
  };
  brand.addEventListener('click', () => togglePop(menu, brand, () => {
    const q = $('#launch-q'); q.value = ''; search(''); renderRecent(); setTimeout(() => q.focus(), 30);
    emit('launcher');   // e.g. Linux programs installed meanwhile come in
  }));
  $('#launch-q').addEventListener('input', e => search(e.target.value));
  $('#launch-q').addEventListener('keydown', e => {
    if (e.key === 'Enter') { const b = $('#launch-results .launch__item') || $('.launch__app'); b?.click(); }
    if (e.key === 'ArrowDown') { e.preventDefault(); ($('#launch-results:not([hidden]) .launch__item') || $('.launch__app'))?.focus(); }
  });
  menu.addEventListener('keydown', e => {
    if (!['ArrowDown', 'ArrowUp'].includes(e.key) || e.target.id === 'launch-q') return;
    const items = $$('.launch__app, .launch__item', menu).filter(b => b.offsetParent);
    const i = items.indexOf(document.activeElement);
    if (i < 0) return;
    e.preventDefault();
    const n = items[i + (e.key === 'ArrowDown' ? 1 : -1)];
    n ? n.focus() : $('#launch-q').focus();
  });
  menu.addEventListener('click', e => {
    const r = e.target.closest('[data-recent]');
    if (r) { closePops(); open('editor', { path: r.dataset.recent }); }
  });
  $('#launch-power').addEventListener('click', e => {
    const b = e.currentTarget.getBoundingClientRect();
    menuAt({ preventDefault() {}, target: e.currentTarget, clientX: b.left, clientY: b.bottom + 6 }, [
      { label: 'Desktop beenden …', icon: 'i-x', act: () => { closePops(); leave('end-desktop'); } },
      { label: 'Abmelden …', icon: 'i-power', danger: true, act: () => { closePops(); leave('end'); } },
    ]);
  });

  // quick settings: a control centre of modules
  const popQuick = $('#pop-quick'), btnQuick = $('#tb-quick');
  const TINTS = [['', 277, 'Facet'], ['blau', 250, 'Blau'], ['cyan', 215, 'Cyan'], ['gruen', 150, 'Grün'], ['bernstein', 70, 'Bernstein'], ['rot', 25, 'Rot'], ['pink', 350, 'Pink'],
    ['custom', 0, 'Eigene', 'swatch--custom'], ['rainbow', 0, 'Regenbogen', 'swatch--rainbow'], ['spectrum', 0, 'Farbverlauf', 'swatch--spectrum']];
  $('#quick-tints').innerHTML = TINTS.map(([id, h, name, cls]) =>
    `<button role="radio" data-qtint="${id}" aria-label="${name}" class="f-tip" data-tip="${name}"><span class="f-swatch ${cls || ''}"${cls ? '' : ` data-h="${h}"`}></span></button>`).join('');
  // on or off, as each pref means it (some are on unless switched off)
  const qOn = k => (k === 'widgets' || k === 'cursors' ? P[k] !== false : !!P[k]);
  const syncQuick = () => {
    const theme = P.theme || 'system';
    const th = $(`input[name="qtheme"][value="${theme}"]`, popQuick); if (th) th.checked = true;
    $('[data-qc-theme]', popQuick).textContent = t({ system: 'Wie das System', light: 'Hell', dark: 'Dunkel' }[theme]);
    $$('[data-qtint]', popQuick).forEach(b => b.setAttribute('aria-checked', b.dataset.qtint === (P.tint || '')));
    $('[data-qc-tint]', popQuick).textContent = t(TINTS.find(x => x[0] === (P.tint || ''))?.[2] || 'Facet');
    $$('[data-qpref]', popQuick).forEach(b => b.setAttribute('aria-pressed', qOn(b.dataset.qpref)));
    $('[data-qc-dnd]', popQuick).textContent = t(P.dnd ? 'An' : 'Aus');
    // Nova: means nothing under a picture of one's own
    $('[data-qc-nova]', popQuick).hidden = !!P.wallpaperV;
    $('[data-qc-wall]', popQuick).checked = P.wallpaper !== false;
    $('[data-qc-nova-opts]', popQuick).classList.toggle('is-off', P.wallpaper === false);
    const nv = $(`input[name="qnova"][value="${novaSide()}"]`, popQuick); if (nv) nv.checked = true;
    const nl = $(`input[name="qlogo"][value="${P.novaLogo || 'none'}"]`, popQuick); if (nl) nl.checked = true;
    $('[data-qc-desk]', popQuick).textContent = $('#bar-desk span')?.textContent || t('Schreibtisch');
    requestAnimationFrame(() => Facet.layout());
  };
  btnQuick.addEventListener('click', () => togglePop(popQuick, btnQuick, syncQuick));
  popQuick.addEventListener('change', e => {
    const i = e.target;
    if (i.name === 'qtheme') { Facet.setTheme(i.value, i.nextElementSibling); set('theme', i.value); }
    if (i.name === 'qnova') set('nova', i.value);
    if (i.name === 'qlogo') set('novaLogo', i.value);
    if (i.hasAttribute('data-qc-wall')) set('wallpaper', i.checked);
    syncQuick();
  });
  popQuick.addEventListener('click', e => {
    const tint = e.target.closest('[data-qtint]');
    if (tint) { set('tint', tint.dataset.qtint); syncQuick(); }
    const tile = e.target.closest('[data-qpref]');
    if (tile) { set(tile.dataset.qpref, !qOn(tile.dataset.qpref)); syncQuick(); }
    if (e.target.closest('[data-open]')) closePops();
  });
  on('prefs', () => { if (!popQuick.hidden) syncQuick(); });

  // notifications
  const popBell = $('#pop-bell'), btnBell = $('#tb-bell');
  btnBell.addEventListener('click', () => togglePop(popBell, btnBell, () => { $('#tb-bell-dot').hidden = true; renderBell(); }));
  $('#bell-clear').addEventListener('click', () => { BELL.length = 0; renderBell(); });

  // calendar
  const popCal = $('#pop-cal'), btnClock = $('#tb-clock');
  let calAt = new Date();
  const renderCal = () => {
    const y = calAt.getFullYear(), m = calAt.getMonth(), today = new Date();
    $('#cal-title').textContent = calAt.toLocaleDateString(locale(), { month: 'long', year: 'numeric' });
    const first = (new Date(y, m, 1).getDay() + 6) % 7;            // Monday first
    const days = new Date(y, m + 1, 0).getDate(), prev = new Date(y, m, 0).getDate();
    const dows = [...Array(7)].map((_, i) => new Date(2024, 0, 1 + i).toLocaleDateString(locale(), { weekday: 'short' }).slice(0, 2));
    let cells = dows.map(d => `<span class="is-dow">${d}</span>`);
    for (let i = 0; i < 42; i++) {
      const d = i - first + 1;
      if (d < 1) cells.push(`<span class="is-out">${prev + d}</span>`);
      else if (d > days) cells.push(`<span class="is-out">${d - days}</span>`);
      else cells.push(`<span${y === today.getFullYear() && m === today.getMonth() && d === today.getDate() ? ' class="is-today"' : ''}>${d}</span>`);
    }
    $('#cal-grid').innerHTML = cells.join('');
  };
  btnClock.addEventListener('click', () => togglePop(popCal, btnClock, () => { calAt = new Date(); renderCal(); }));
  popCal.addEventListener('click', e => {
    const b = e.target.closest('[data-cal]'); if (!b) return;
    calAt = new Date(calAt.getFullYear(), calAt.getMonth() + +b.dataset.cal, 1); renderCal();
  });

  // the device's battery, where the browser tells it
  navigator.getBattery?.().then(bat => {
    const show = () => {
      const el = $('#tb-batt');
      el.hidden = false;
      el.style.setProperty('--lvl', bat.level.toFixed(2));
      el.classList.toggle('is-low', bat.level < .15 && !bat.charging);
      el.dataset.tip = `${t('Akku')} ${Math.round(bat.level * 100)} %${bat.charging ? ` · ${t('lädt')}` : ''}`;
    };
    show();
    ['levelchange', 'chargingchange'].forEach(ev => bat.addEventListener(ev, show));
  }).catch(() => {});

  /* ---------- taskbar auto-hide ---------- */
  const taskbar = $('#taskbar');
  let hideT;
  const showBar = () => { clearTimeout(hideT); taskbar.classList.add('is-shown'); };
  const hideBar = () => { hideT = setTimeout(() => { if (!openPop) taskbar.classList.remove('is-shown'); }, 400); };
  $('#dock-edge').addEventListener('pointerenter', showBar);
  taskbar.addEventListener('pointerenter', showBar);
  taskbar.addEventListener('pointerleave', hideBar);
  taskbar.addEventListener('focusin', showBar);
  taskbar.addEventListener('focusout', hideBar);

  /* ---------- keys ---------- */
  document.addEventListener('keydown', e => {
    if ((e.metaKey || e.ctrlKey) && e.key === ',') { e.preventDefault(); open('settings'); }
    if (e.ctrlKey && e.shiftKey && (e.key === 'T' || e.key === 't')) { e.preventDefault(); open('terminal', {}, { fresh: true }); }
    if (e.key === 'Escape' && openPop) { const b = openPop.btn; closePops(); b?.focus(); }
  });
  narrow.addEventListener('change', () => { setForm(); updateBar(); Facet.layout(); });

  const fmtBytes = n => {
    if (n == null) return '–';
    const u = ['B', 'KB', 'MB', 'GB', 'TB']; let i = 0;
    while (n >= 1024 && i < u.length - 1) { n /= 1024; i++; }
    return `${n.toLocaleString(window.AkariI18n?.locale() || 'de-DE', { maximumFractionDigits: i ? 1 : 0 })} ${u[i]}`;
  };

  /* ---------- one clipboard for the whole desktop ----------
     The browser's clipboard, the X clipboard of every Linux app (each runs on
     a display of its own, so each has its own) and the computer's clipboard
     are three things. Akari keeps the last text copied anywhere and hands it
     to the others:
       - a copy in Akari (text, terminal, editor) reaches every Linux app;
       - a copy in a Linux app reaches the other Linux apps and the computer;
       - pasting into a Linux app first fetches the computer's clipboard.
     Sinks are the Linux app windows; each is told when the text changes. */
  let CLIP = '';
  const clipSinks = new Set();
  const clipSet = (text, from = null, { system = true } = {}) => {
    if (typeof text !== 'string' || !text || text === CLIP) return;
    CLIP = text;
    clipSinks.forEach(fn => { if (fn !== from) { try { fn(text); } catch {} } });
    if (system) navigator.clipboard?.writeText(text).catch(() => {});
    emit('clipboard', text);
  };
  // the computer's clipboard if the browser lets us read it (it asks once), else Akari's
  // (a browser may ask first, or never answer: after half a second Akari's own text is used)
  const clipRead = async () => {
    try {
      const t0 = await Promise.race([navigator.clipboard.readText(), new Promise((_, no) => setTimeout(() => no(new Error('slow')), 500))]);
      if (t0) { clipSet(t0, null, { system: false }); return t0; }
    } catch {}
    return CLIP;
  };
  const clipSink = fn => { clipSinks.add(fn); if (CLIP) fn(CLIP); return () => clipSinks.delete(fn); };
  // what a copy or cut in the page selected: set by the app (xterm does), or the selection
  const copied = e => {
    let text = '';
    try { text = e.clipboardData?.getData('text/plain') || ''; } catch {}
    if (!text) {
      const a = document.activeElement;
      if (a && /^(TEXTAREA|INPUT)$/.test(a.tagName) && a.selectionStart !== a.selectionEnd) text = a.value.slice(a.selectionStart, a.selectionEnd);
      else text = String(getSelection() || '');
    }
    // the browser fills its own clipboard; Akari only passes it on
    setTimeout(() => clipSet(text, null, { system: false }), 0);
  };
  document.addEventListener('copy', copied);
  document.addEventListener('cut', copied);
  // a paste anywhere in Akari also tells the Linux apps what the computer had
  document.addEventListener('paste', e => {
    const text = e.clipboardData?.getData('text/plain');
    if (text) clipSet(text, null, { system: false });
  });

  /* ---------- right-click menus ----------
     Akari.menu(event, [{ label, icon, act, danger, disabled, hint } | '-']) */
  const ctx = $('#ctx');
  const menuAt = (ev, items) => {
    ev.preventDefault();
    if (!openPop?.pop.contains(ev.target)) closePops();   // a menu from inside a popover (the start menu) keeps it open
    ctx.innerHTML = '';
    items.filter(Boolean).forEach(it => {
      if (it === '-') { ctx.append(document.createElement('hr')); return; }
      const b = document.createElement('button');
      b.setAttribute('role', 'menuitem');
      if (it.danger) b.classList.add('is-danger');
      b.disabled = !!it.disabled;
      b.innerHTML = `<svg width="16" height="16"><use href="#${it.icon || 'i-chev'}"/></svg><span></span>${it.hint ? '<span class="f-kbd"></span>' : ''}`;
      $('span', b).textContent = t(it.label);
      if (it.hint) $('.f-kbd', b).textContent = it.hint;
      b.addEventListener('click', () => { hideCtx(); it.act?.(); });
      ctx.append(b);
    });
    ctx.hidden = false;
    const w = ctx.offsetWidth, h = ctx.offsetHeight;
    ctx.style.left = `${Math.min(ev.clientX, innerWidth - w - 8)}px`;
    ctx.style.top = `${Math.min(ev.clientY, innerHeight - h - 8)}px`;
    ctx.querySelector('button:not(:disabled)')?.focus({ preventScroll: true });
  };
  const hideCtx = () => { ctx.hidden = true; };
  document.addEventListener('pointerdown', e => { if (!ctx.hidden && !ctx.contains(e.target)) hideCtx(); });
  document.addEventListener('keydown', e => {
    if (ctx.hidden) return;
    if (e.key === 'Escape') hideCtx();
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault();
      const bs = $$('button:not(:disabled)', ctx), i = bs.indexOf(document.activeElement);
      bs[(i + (e.key === 'ArrowDown' ? 1 : -1) + bs.length) % bs.length]?.focus();
    }
  });
  addEventListener('blur', hideCtx);

  // the shell's own menus: dock icons, window bars
  document.addEventListener('contextmenu', e => {
    const dockApp = e.target.closest('.dock__app');
    if (dockApp) {
      const a = APPS.get(dockApp.dataset.app), ws = ofApp(a.id);
      return menuAt(e, [
        { label: a.title, icon: 'i-chev', act: () => (ws.length ? focus(ws[0]) : open(a.id)) },
        a.multi && { label: 'Neues Fenster', icon: 'i-plus', act: () => open(a.id, {}, { fresh: true }) },
        ...(ws.length > 1 ? ['-', ...ws.map(w => ({ label: w.title, icon: w.minimised ? 'i-min' : 'i-window', act: () => focus(w) }))] : []),
        '-',
        isPinned(a.id)
          ? { label: 'Von der Leiste lösen', icon: 'i-x', act: () => pin(a.id, false) }
          : { label: 'An die Leiste heften', icon: 'i-plus', act: () => pin(a.id, true) },
        ws.length && '-',
        ws.length && { label: 'Alle minimieren', icon: 'i-min', act: () => ws.forEach(minimise) },
        ws.length && { label: ws.length > 1 ? 'Alle schließen' : 'Schließen', icon: 'i-x', danger: true, act: () => ws.forEach(w => close(w)) },
      ]);
    }
    const tile = e.target.closest('.min__win');
    if (tile?.win) {
      const w = tile.win;
      return menuAt(e, [
        { label: 'Wiederherstellen', icon: 'i-max', act: () => focus(w) },
        '-',
        { label: 'Schließen', icon: 'i-x', danger: true, act: () => close(w) },
      ]);
    }
    const bar = e.target.closest('.win__bar');
    if (bar) {
      const w = [...WINS].find(x => x.el.contains(bar)), a = APPS.get(w.app);
      focus(w);
      return menuAt(e, [
        a.multi && { label: 'Neues Fenster', icon: 'i-plus', act: () => open(a.id, {}, { fresh: true }) },
        { label: 'Minimieren', icon: 'i-min', act: () => minimise(w) },
        { label: w.el.classList.contains('is-max') ? 'Wiederherstellen' : 'Maximieren', icon: 'i-max', act: () => toggleMax(w) },
        '-',
        { label: 'Schließen', icon: 'i-x', danger: true, act: () => close(w) },
      ]);
    }
    const launchApp = e.target.closest('.launch__app');
    if (launchApp) {
      const id = launchApp.dataset.app;
      return menuAt(e, [
        { label: 'Öffnen', icon: 'i-chev', act: () => { closePops(); open(id); } },
        isPinned(id)
          ? { label: 'Von der Leiste lösen', icon: 'i-x', act: () => pin(id, false) }
          : { label: 'An die Leiste heften', icon: 'i-plus', act: () => pin(id, true) },
      ]);
    }
    // the taskbar itself: size, position, hiding
    if (e.target.closest('.tb')) {
      const size = s => ({ label: { s: 'Klein', m: 'Mittel', l: 'Groß' }[s], icon: P.dock === s ? 'i-chev' : 'i-min', act: () => set('dock', s) });
      return menuAt(e, [
        size('s'), size('m'), size('l'),
        '-',
        { label: P.bar === 'top' ? 'Leiste nach unten' : 'Leiste nach oben', icon: 'i-dock', act: () => set('bar', P.bar === 'top' ? 'bottom' : 'top') },
        { label: P.autohide ? 'Immer zeigen' : 'Automatisch ausblenden', icon: 'i-eye', act: () => set('autohide', !P.autohide) },
        { label: P.magnify === false ? 'Vergrößern beim Zeigen' : 'Nicht vergrößern', icon: 'i-max', act: () => set('magnify', P.magnify === false) },
        '-',
        { label: 'Einstellungen der Leiste …', icon: 'i-gear', act: () => open('settings', { page: 'schreibtisch' }) },
      ]);
    }
    // inside apps the browser's own menu stays (text fields, Linux apps handle their own)
  });

  /* ---------- the dock: drag to reorder, magnify under the pointer ---------- */
  const dockEl = $('#dock');
  let dockDragged = false;
  dockEl.addEventListener('pointerdown', e => {
    const b = e.target.closest('.dock__app');
    if (!b || e.button !== 0) return;
    const sx = e.clientX;
    let moving = false, tx = 0, shift = 0;   // tx: the icon's offset now; shift: how far its slot moved
    const others = () => $$('.dock__app:not(.is-leaving)', dockEl).filter(x => x !== b);
    const move = ev => {
      if (!moving && Math.abs(ev.clientX - sx) < 6) return;
      if (!moving) { moving = true; b.classList.add('is-dragging'); b.setPointerCapture(e.pointerId); unmagnify(); }
      // the slot it would take: before the first other icon whose middle is right of the pointer
      const target = others().find(x => { const r = x.getBoundingClientRect(); return ev.clientX < r.left + r.width / 2; }) || null;
      let next = b.nextElementSibling;
      while (next && next.classList.contains('is-leaving')) next = next.nextElementSibling;
      if (target !== next) {
        const before = new Map(others().map(x => [x, x.getBoundingClientRect().left]));
        const slot0 = b.getBoundingClientRect().left - tx;
        dockEl.insertBefore(b, target);
        shift += b.getBoundingClientRect().left - tx - slot0;
        // FLIP: the others glide to their new places
        if (!reduced()) before.forEach((left, x) => {
          const d = left - x.getBoundingClientRect().left;
          if (d) x.animate([{ transform: `translateX(${d}px)` }, { transform: 'none' }], { duration: 300, easing: SPRING });
        });
      }
      tx = ev.clientX - sx - shift;       // keep the icon under the pointer
      b.style.translate = `${tx}px 0`;
    };
    const up = () => {
      removeEventListener('pointermove', move);
      removeEventListener('pointerup', up);
      if (!moving) return;
      dockDragged = true; setTimeout(() => { dockDragged = false; }, 0);
      const t0 = b.style.translate;
      b.classList.remove('is-dragging');
      b.style.translate = '';
      if (!reduced() && t0) b.animate([{ translate: t0 }, { translate: '0 0' }], { duration: 320, easing: SPRING });
      // the new order is the pinned order; what was dropped is pinned from now on
      const order = $$('.dock__app:not(.is-leaving)', dockEl).map(x => x.dataset.app);
      const pins = pinned();
      set('pinned', order.filter(id => pins.includes(id) || id === b.dataset.app));
      renderDock();
    };
    addEventListener('pointermove', move);
    addEventListener('pointerup', up);
  });
  document.addEventListener('click', e => { if (dockDragged && e.target.closest('.dock__app')) { e.stopPropagation(); e.preventDefault(); } }, true);

  // magnification: the icon under the pointer grows, its neighbours a little less
  const unmagnify = () => $$('.dock__app', dockEl).forEach(x => { x.style.removeProperty('--mag'); });
  // strength (P.magnifyAmount: 0.1 to 1) and reach (P.magnifyRange: icons to each side) are settings
  const magnifyAt = x0 => {
    const size = $('.dock__app', dockEl)?.offsetWidth || 36;
    $$('.dock__app', dockEl).forEach(x => {
      const r = x.getBoundingClientRect();
      const d = Math.abs(x0 - (r.left + r.width / 2)) / (size * (+P.magnifyRange || 2.4));
      x.style.setProperty('--mag', (1 + (P.magnifyAmount ?? .45) * Math.max(0, Math.cos(Math.min(d, 1) * Math.PI / 2))).toFixed(3));
    });
  };
  let overDock = false, previewT;
  dockEl.addEventListener('pointermove', e => {
    overDock = true;
    if (P.magnify === false || reduced() || dockEl.querySelector('.is-dragging')) return;
    magnifyAt(e.clientX);
  });
  dockEl.addEventListener('pointerleave', () => { overDock = false; unmagnify(); });
  // the settings show what a change does: the middle of the dock grows for a moment
  const previewMagnify = () => {
    if (P.magnify === false || reduced() || overDock) return;
    const r = dockEl.getBoundingClientRect();
    magnifyAt(r.left + r.width / 2);
    clearTimeout(previewT);
    previewT = setTimeout(() => { if (!overDock) unmagnify(); }, 900);
  };

  /* ---------- what plays: the media section in the status pill ----------
     The players on this desktop (Firefox, mpv, Spotify …) report over MPRIS;
     the workspace pushes "media" whenever that changes. Hidden while nothing
     plays or pauses. */
  /* Two sources: players on the desktop's Linux side (MPRIS, pushed as "media")
     and Akari's own Musik app (mediaLocal). The one that plays wins; when
     both pause, the app's stays. */
  const media = $('#tb-media'), qMedia = $('[data-qc-media]');
  let fromServer = null, fromApp = null, appControl = null, playing = null;
  const coverOf = p => (p.cover ? p.cover : p.art ? `/api/media/art?v=${encodeURIComponent(p.art)}` : null);
  const paintMedia = () => {
    const p = fromApp && (fromApp.status === 'playing' || !fromServer || fromServer.status !== 'playing') ? fromApp : fromServer;
    if (!!p !== !!playing) glidePill(media.closest('.tb'), () => { media.hidden = $('#tb-media-sep').hidden = !p; });
    playing = p;
    qMedia.hidden = !p;
    if (!p) return;
    const cover = coverOf(p), isOn = p.status === 'playing';
    for (const [box, img] of [[media, $('.tb__cover img', media)], [qMedia, $('.qc__cover img', qMedia)]]) {
      $('b', box).textContent = p.title || p.player;
      $('small', box).textContent = p.artist || p.album || p.player || '';
      if (cover && img.dataset.v !== cover) {
        img.dataset.v = cover;
        img.onload = () => { img.hidden = false; };
        img.onerror = () => { img.hidden = true; };
        img.src = cover;
      } else if (!cover) { img.hidden = true; img.removeAttribute('src'); delete img.dataset.v; }
      // the app's own colour where there is no cover
      box.querySelector('.tb__cover, .qc__cover')?.style.setProperty('--mh', p.hue ?? '');
    }
    const main = $('[data-media="play-pause"]', media);
    $('use', main).setAttribute('href', isOn ? '#i-pause' : '#i-play');
    main.setAttribute('aria-label', t(isOn ? 'Pause' : 'Abspielen'));
    media.classList.toggle('is-paused', !isOn);
    $('[data-qmedia="play-pause"] use', qMedia).setAttribute('href', isOn ? '#i-pause' : '#i-play');
  };
  on('media', m => { fromServer = m.playing || null; paintMedia(); });
  // the Musik app reports what it plays, and takes the buttons back
  const mediaLocal = (state, control) => {
    fromApp = state ? { ...state, local: true } : null;
    if (control) appControl = control;
    paintMedia();
  };
  const mediaDo = action => {
    if (!playing) return;
    if (playing.local) return appControl?.(action);
    if (action === 'show') {
      // to the window the sound comes from: Firefox's own, else the desktop's Linux apps
      const w = (/firefox/i.test(playing.player) && ofApp('x:firefox')[0]) || ofApp('x:desktop')[0]
        || [...WINS].filter(x => x.app.startsWith('x:')).sort((x, y) => y.z - x.z)[0];
      return w && focus(w);
    }
    api(`/api/media/${action}`, { method: 'POST', quiet: true }).catch(() => {});
  };
  media.addEventListener('click', e => { const b = e.target.closest('[data-media]'); if (b) mediaDo(b.dataset.media); });
  qMedia.addEventListener('click', e => {
    const b = e.target.closest('[data-qmedia]');
    if (!b) return;
    if (b.dataset.qmedia === 'show') closePops();
    mediaDo(b.dataset.qmedia);
  });

  /* what happens in the workspace, pushed: each message is emitted by its type */
  let evWait = 1000;
  const events = () => {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    const ws = new WebSocket(`${proto}://${location.host}/api/events`);
    // the connection to the workspace is what the "wifi" symbol in the taskbar shows
    const net = up => {
      const n = $('#tb-net');
      n.classList.toggle('is-off', !up);
      $('use', n).setAttribute('href', up ? '#i-net' : '#i-net-off');
      n.dataset.tip = t(up ? 'Mit dem Workspace verbunden' : 'Keine Verbindung zum Workspace');
    };
    ws.onopen = () => { evWait = 1000; net(true); };
    ws.onmessage = e => { try { const m = JSON.parse(e.data); emit(m.type, m); } catch {} };
    ws.onclose = () => {
      if (document.body.classList.contains('is-leaving')) return;
      net(false);
      setTimeout(events, evWait); evWait = Math.min(evWait * 2, 30000);
    };
  };

  window.Akari = {
    novaSide, mediaLocal, api, register, unregister, open, close, focus, ask, notify, color, on, emit, fmtBytes, t, locale, closePops, menu: menuAt, minimise, avatar, recent, previewMagnify,
    clip: { set: clipSet, read: clipRead, sink: clipSink, get text() { return CLIP; } },
    get prefs() { return P; }, set, get system() { return SYS; }, get me() { return ME; }, loadSystem, loadSession, windows: () => [...WINS],
  };

  /* the taskbar fits the screen: the apps pill never shrinks (its content would
     slide under the status pill); when both do not fit, the status pill gives
     way in two steps: first the track title, the desktop's name and the date,
     then the status icons too. Measured, not guessed by width: how wide the
     pills are depends on what is pinned, what plays, the desktop's name. */
  const fitBar = () => {
    const bar = $('#taskbar'), st = $('.tb--status');
    if (!bar || !st) return;
    bar.classList.remove('is-tight', 'is-tighter');
    const over = () => {
      const edge = st.getBoundingClientRect().right - parseFloat(getComputedStyle(st).paddingRight) + 1;
      const end = Math.max(0, ...[...st.children].filter(k => k.offsetWidth).map(k => k.getBoundingClientRect().right));
      // the pills themselves, never scrollWidth: hidden tooltips count there too
      const b = bar.getBoundingClientRect(), pills = [...bar.querySelectorAll(':scope > .tb')].map(p => p.getBoundingClientRect());
      return end > edge || pills.some(p => p.left < b.left - 1 || p.right > b.right + 1);
    };
    if (over()) bar.classList.add('is-tight');
    if (over()) bar.classList.add('is-tighter');
  };
  let fitting = 0;
  const fitSoon = () => { cancelAnimationFrame(fitting); fitting = requestAnimationFrame(fitBar); };

  /* ---------- start ---------- */
  const start = async () => {
    const tbar = $('#taskbar');
    if (tbar) {
      const ro = new ResizeObserver(fitSoon);
      ro.observe(tbar);
      new MutationObserver(fitSoon).observe(tbar, { childList: true, subtree: true, attributes: true, attributeFilter: ['hidden'] });
    }
    // this account's desktop, from the workspace, never from the browser: a
    // browser is shared by every account that signs in on it (the cache in
    // localStorage is only for the login screen's colour)
    const remote = await api('/api/prefs', { quiet: true }).catch(() => null);
    P = { ...DEFAULTS, ...(remote || {}) };
    prefsLoaded = true;
    try { localStorage.setItem('akari-prefs-last', JSON.stringify({ tint: P.tint, nova: novaSide(), wallpaper: P.wallpaper !== false && !P.wallpaperV, cursors: P.cursors !== false, tintH: P.tintH })); } catch {}
    Facet.setTheme(P.theme || 'system');
    apply();
    emit('prefs');
    await Promise.all([loadSession(), loadSystem()]);
    window.AkariBoot?.done();      // the real look is on: from now on colours may glide
    window.Akari.ready = true;
    emit('ready');
    // back from "Mit Lucent verknüpfen": say how it went, then forget the address
    const lu = new URLSearchParams(location.search).get('lucent');
    if (lu) {
      history.replaceState(null, '', '/');
      const say = { verknuepft: ['Dein Konto ist jetzt mit Lucent verknüpft.', 'ok'], vergeben: ['Diese Lucent-Person ist schon mit einem anderen Konto verknüpft.', 'err'] }[lu]
        || ['Verknüpfen mit Lucent hat nicht geklappt.', 'err'];
      Facet.toast(t(say[0]), { tone: say[1] });
      open('settings', { page: 'lucent' });
    }
    events();
  };
  document.readyState === 'loading' ? document.addEventListener('DOMContentLoaded', start) : start();
})();
