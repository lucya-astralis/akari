/* Willkommen: the first thing after signing in, until the account says
   "Nicht mehr anzeigen" (for the account, not the desktop: /api/welcome).

   It opens with a short scene. lucya.systems' eagle builds as it did on the
   old lucya.sh splash: its outline drawn in mirrored pairs from the spine
   outwards, a signal drop, the pieces filling in with an RGB split, a
   flicker, and the wordmark locking in. Then the eagle gives way to Akari's
   mark, whose three rays slide in along their slant. Light or dark, as the
   desktop is.
   A click or a key skips it; with reduced motion there is no scene at all.
   Then five short pages: what Akari is, finding one's way, the Linux under
   it, lucya.systems, and making it one's own (accent and light right here).
   The start menu has it too, so it can be opened again. */
(() => {
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const t = s => Akari.t(s);

  // the eagle's pieces (index.html #lm), each its own path so each can arrive on its own
  const EAGLE = [
    ['wl-l1', 'M112,148L260,217L409.69,379.66L467.26,264.53L400,222.08L400,204.02L0,0L112,148Z'],
    ['wl-r1', 'M964,0L564,204.02L564,222.08L496.74,264.53L554.31,379.66L704,217L852,148L964,0Z'],
    ['wl-l2', 'M172.93,266.68L315.8,308.65L247.36,234.28L59.81,146.84L172.93,266.68Z'],
    ['wl-r2', 'M904.19,146.84L716.64,234.28L648.2,308.65L791.07,266.68L904.19,146.84Z'],
    ['wl-l3', 'M289.78,367.82L400.19,400.35L343.4,338.64L191.3,293.96L289.78,367.82Z'],
    ['wl-r3', 'M772.7,293.96L620.6,338.64L563.81,400.35L674.22,367.82L772.7,293.96Z'],
    ['wl-head', 'M518,67L415,100L403,120L454,122L421,210.5L482,249L543,210.5L538,85L518,67Z'],
    ['wl-tail', 'M482,282L544.5,407L482,543L419.5,407L482,282Z'],
  ];
  const MARK = [['am-l', 'M40.4 0L51.4 0L11 100L0 100Z'], ['am-b', 'M51.14 14L75.14 14L40.39 100L16.39 100Z'], ['am-d', 'M71.64 36L95.64 36L69.79 100L45.79 100Z']];
  const eagle = cls => `<svg class="${cls}" viewBox="0 0 964 543" aria-hidden="true">${EAGLE.map(([c, d]) => `<path class="${c}" d="${d}"/>`).join('')}</svg>`;
  // the build, as lucya.sh drew it: in mirrored pairs from the spine outwards, each stroke at about one speed
  const BUILD = [[['wl-tail'], .66], [['wl-head'], .46], [['wl-l1', 'wl-r1'], .86], [['wl-l2', 'wl-r2'], .46], [['wl-l3', 'wl-r3'], .36]];
  const glitchEagle = () => `<div class="wl__glitch" data-glitch>${eagle('wl__eagle wl__eagle--main')}
    <div class="wl__rgb wl__rgb--r" data-rgb>${eagle('wl__eagle')}</div><div class="wl__rgb wl__rgb--b" data-rgb>${eagle('wl__eagle')}</div></div>`;

  /* the scene, step by step; every wait checks whether it was skipped */
  const play = async (stage, ended) => {
    const wait = ms => new Promise(r => setTimeout(r, ms));
    const gone = () => !stage.isConnected || stage.classList.contains('is-leaving');
    const box = stage.querySelector('[data-glitch]'), main = box.querySelector('.wl__eagle--main');
    const [rgbR, rgbB] = box.querySelectorAll('[data-rgb]');
    const word = stage.querySelector('.wl__word');
    const split = dx => { rgbR.style.opacity = rgbB.style.opacity = '.45'; rgbR.style.transform = `translate(${-dx}px, ${dx * .3}px)`; rgbB.style.transform = `translate(${dx}px, ${-dx * .3}px)`; };
    const unsplit = () => { rgbR.style.opacity = rgbB.style.opacity = '0'; rgbR.style.transform = rgbB.style.transform = ''; };
    const jolt = (el, n, k, skew = 0) => new Promise(res => {
      let i = 0;
      const iv = setInterval(() => {
        el.style.transform = `translate(${(Math.random() - .5) * k}px, ${(Math.random() - .5) * k * .55}px)${skew ? ` skewX(${(Math.random() - .5) * skew}deg)` : ''}`;
        if (skew) split(3 + Math.random() * 5);
        if (++i >= n) { clearInterval(iv); el.style.transform = ''; if (skew) unsplit(); res(); }
      }, skew ? 45 : 35);
    });
    const group = ids => ids.map(c => main.querySelector(`.${c}`));
    BUILD.forEach(([ids, dur]) => group(ids).forEach(el => { el.style.setProperty('--len', el.getTotalLength()); el.style.setProperty('--dur', `${dur}s`); }));

    // 1: the outline, pair by pair, with a jolt after the head and the middle feathers
    await wait(250);
    for (let i = 0; i < BUILD.length; i++) {
      if (gone()) return;
      group(BUILD[i][0]).forEach(el => el.classList.add('is-drawn'));
      if (i === 1 || i === 3) await jolt(main, 3, 3);
      await wait(130);
    }
    await wait(380);
    if (gone()) return;
    // 2: the signal drops and comes back solid
    box.style.filter = 'brightness(2.2) contrast(.6)'; split(10);
    await wait(80); box.style.filter = 'brightness(0) opacity(.2)'; unsplit();
    await wait(80); box.style.filter = 'brightness(.7)';
    await wait(100); box.style.filter = '';
    await jolt(main, 6, 15, 3);
    for (let i = 0; i < BUILD.length; i++) {
      if (gone()) return;
      group(BUILD[i][0]).forEach(el => el.classList.add('is-filled'));
      if (i % 2 === 0) { split(2 + Math.random() * 3); await wait(22); unsplit(); }
      await wait(36);
    }
    await jolt(main, 3, 12, 3);
    // 3: a flicker, then the wordmark locks in, overshooting its width before it settles
    for (let i = 0; i < 3; i++) { box.style.opacity = i % 2 ? '1' : '0'; await wait(42 + Math.random() * 26); }
    box.style.opacity = '';
    if (gone()) return;
    word.style.opacity = '1';
    for (const [sx, x, skew] of [[1.5, 9, 3], [.88, -6, -2.4], [1.18, 4, 1.6], [.96, -2, -.8], [1, 0, 0]]) {
      word.style.transform = `translateX(${x}px) scaleX(${sx}) skewX(${skew}deg)`;
      if (sx !== 1) split(2 + Math.abs(x) * .5); else unsplit();
      await wait(95 + Math.random() * 40);
    }
    box.classList.add('is-settled');
    await wait(900);
    if (gone()) return;
    // 4: Akari
    stage.classList.add('is-akari');
    await wait(2100);
    if (!gone()) ended();
  };
  const mark = cls => `<svg class="${cls}" viewBox="0 0 95.64 100" aria-hidden="true">${MARK.map(([c, d], i) => `<path class="${c} wl-ray wl-ray--${i}" d="${d}"/>`).join('')}</svg>`;

  const TINTS = [['', 277, 'Facet'], ['blau', 250, 'Blau'], ['cyan', 215, 'Cyan'], ['gruen', 150, 'Grün'], ['bernstein', 70, 'Bernstein'], ['rot', 25, 'Rot'], ['pink', 350, 'Pink'],
    ['rainbow', 0, 'Regenbogen', 'swatch--rainbow'], ['spectrum', 0, 'Farbverlauf', 'swatch--spectrum']];

  // a row with an icon, as the pages list things
  const item = (icon, title, text, act = '') => `
    <li class="wl__item"><span class="wl__icon"><svg><use href="#${icon}"/></svg></span>
      <span class="wl__txt"><b>${t(title)}</b><small>${t(text)}</small></span>${act}</li>`;
  const go = (app, label, args = '') => `<button class="f-btn f-btn--sm" data-open="${app}"${args ? ` data-args='${esc(args)}'` : ''}>${t(label)}</button>`;

  const PAGES = [
    {
      id: 'hallo', head: () => `<div class="wl__hero">${mark('wl__heromark am')}</div>`,
      title: 'Willkommen bei Akari OS',
      body: s => `<p class="wl__lead">${t('Ein Desktop im Browser, mit einem echten Debian darunter. Dein Konto ist ein Linux-Benutzer mit eigenem Home, eigenen Desktops und eigenen Einstellungen.')}</p>
        <dl class="wl__facts">
          <div><dt>${t('Version')}</dt><dd translate="no">Akari OS ${esc(s?.version || '')}</dd></div>
          <div><dt>${t('Rechner')}</dt><dd translate="no">${esc(s?.hostname || '–')}</dd></div>
          <div><dt>${t('System')}</dt><dd translate="no">${esc(s?.os || '–')}</dd></div>
          <div><dt>${t('Angemeldet als')}</dt><dd translate="no">${esc(Akari.me?.name || '–')}</dd></div>
        </dl>`,
    },
    {
      id: 'orientierung', title: 'So findest du dich zurecht',
      body: () => `<ul class="wl__list">
        ${item('i-home', 'Startmenü', 'Unten links: angeheftete Apps, alle Apps, Orte und zuletzt Geöffnetes. Tippen sucht.')}
        ${item('i-desks', 'Desktops', 'Mehrere Arbeitsflächen nebeneinander, jede mit eigenen Fenstern und eigenem Aussehen.')}
        ${item('i-sliders', 'Kontrollzentrum', 'Rechts in der Leiste: hell oder dunkel, Akzent, Nicht stören, Musik.')}
        ${item('i-dock', 'Leiste', 'Apps per Rechtsklick anheften, per Ziehen sortieren. Größe und Lage unter Einstellungen.')}
      </ul>`,
    },
    {
      id: 'linux', title: 'Ein echtes Linux darunter',
      body: () => `<ul class="wl__list">
        ${item('i-term', 'Terminal', 'zsh mit powerlevel10k, im Browser und über SSH. Auch an der Konsole des Rechners.', go('terminal', 'Öffnen'))}
        ${item('i-window', 'Programme', 'Linux-Programme wie Firefox laufen als Fenster. Wer verwaltet, installiert weitere mit apt.')}
        ${item('i-refresh', 'Updates', 'Akari und Debian halten sich über apt aktuell: Einstellungen → Updates.', go('settings', 'Ansehen', '{"page":"software"}'))}
      </ul>`,
    },
    {
      id: 'lucya', head: () => `<div class="wl__hero wl__hero--lucya">${eagle('wl__heroeagle')}<span class="wordmark" role="img" aria-label="lucya.systems"></span></div>`,
      title: 'Teil von lucya.systems',
      body: () => `<ul class="wl__list">
        ${item('i-globe', 'Lucent', 'Die Verwaltung von lucya.systems: ein Konto für alle Tools, Zustand und Konten auf einen Blick, ein Store für mehr.', go('settings', 'Ansehen', '{"page":"lucent"}'))}
        ${Akari.me?.admin ? item('i-box', 'Docker', 'Container neben dem Desktop verwalten, und Lucent mit einem Klick auf diesem Rechner einrichten.', go('docker', 'Öffnen')) : ''}
      </ul>`,
    },
    {
      id: 'deins', title: 'Mach es zu deinem',
      body: () => `<div class="wl__pick">
          <span class="f-label">${t('Akzent')}</span>
          <div class="wl__tints" role="radiogroup" aria-label="${t('Akzentfarbe')}">${TINTS.map(([id, h, name, cls]) =>
            `<button role="radio" class="f-tip" data-tint="${id}" data-tip="${t(name)}" aria-label="${t(name)}" aria-checked="${(Akari.prefs.tint || '') === id}"><span class="f-swatch ${cls || ''}"${cls ? '' : ` data-h="${h}"`}></span></button>`).join('')}</div>
        </div>
        <div class="wl__pick">
          <span class="f-label">${t('Erscheinungsbild')}</span>
          <div class="f-seg" role="radiogroup">${[['system', 'Automatisch'], ['light', 'Hell'], ['dark', 'Dunkel']].map(([v, l]) =>
            `<input type="radio" name="wl-theme" id="wl-th-${v}" value="${v}" ${(Akari.prefs.theme || 'system') === v ? 'checked' : ''}><label for="wl-th-${v}">${t(l)}</label>`).join('')}<span class="f-seg__thumb"></span></div>
        </div>
        <p class="f-dim wl__more">${t('Hintergrund, Leiste, Schrift und mehr unter Einstellungen → Darstellung.')} ${go('settings', 'Darstellung', '{"page":"darstellung"}')}</p>`,
    },
  ];

  Akari.register('welcome', {
    title: 'Willkommen', icon: 'i-info', art: 'welcome', size: [720, 560], order: 90, dock: false, center: true,
    create(win, args) {
      win.body.classList.add('wl');
      const reduced = Akari.prefs.motion || matchMedia('(prefers-reduced-motion: reduce)').matches;
      const intro = !reduced && args.intro !== false;
      let at = 0, show = true;
      win.body.innerHTML = `
        ${intro ? `<div class="wl__stage" data-stage role="presentation">
          <div class="wl__glow"></div>
          <div class="wl__act wl__act--lucya">${glitchEagle()}<span class="wordmark wl__word" role="img" aria-label="lucya.systems"></span></div>
          <div class="wl__act wl__act--akari">${mark('wl__mark am')}
            <b class="wl__name" translate="no">Akari OS</b><span class="wl__hello">${t('Willkommen')}</span></div>
          <button class="f-btn f-btn--sm f-btn--ghost wl__skip" data-skip>${t('Überspringen')}</button>
        </div>` : ''}
        <div class="wl__tour" data-tour>
          <div class="wl__page" data-page aria-live="polite"></div>
          <footer class="wl__foot">
            <label class="f-check"><input type="checkbox" data-never>${t('Nicht mehr anzeigen')}</label>
            <div class="wl__dots" role="tablist">${PAGES.map((p, i) => `<button class="wl__dot" role="tab" data-dot="${i}" aria-label="${i + 1} / ${PAGES.length}"></button>`).join('')}</div>
            <div class="wl__nav"><button class="f-btn f-btn--sm f-btn--ghost" data-prev>${t('Zurück')}</button><button class="f-btn f-btn--sm f-btn--primary" data-next></button></div>
          </footer>
        </div>`;
      const stage = win.body.querySelector('[data-stage]'), tour = win.body.querySelector('[data-tour]'), page = win.body.querySelector('[data-page]');
      const never = win.body.querySelector('[data-never]');

      Akari.api('/api/welcome', { quiet: true }).then(r => { show = r.show; never.checked = !r.show; }).catch(() => {});

      const draw = (dir = 0) => {
        const p = PAGES[at];
        page.innerHTML = `${p.head?.() || ''}<h2 class="f-h2 wl__title">${t(p.title)}</h2>${p.body(Akari.system)}`;
        page.dataset.id = p.id;
        page.classList.remove('is-in', 'is-back'); void page.offsetWidth;
        page.classList.add(dir < 0 ? 'is-back' : 'is-in');
        win.body.querySelectorAll('[data-dot]').forEach((d, i) => d.setAttribute('aria-selected', i === at));
        win.body.querySelector('[data-prev]').disabled = at === 0;
        win.body.querySelector('[data-next]').textContent = t(at === PAGES.length - 1 ? 'Los geht’s' : 'Weiter');
        requestAnimationFrame(() => Facet.layout());
      };

      // the scene ends by itself, or earlier on a click or a key
      let done = false;
      const finish = () => {
        if (done) return;
        done = true;
        if (stage) { stage.classList.add('is-leaving'); setTimeout(() => stage.remove(), 520); }
        tour.classList.add('is-on');
        draw();
      };
      if (intro) { tour.classList.add('is-waiting'); stage.addEventListener('click', finish); play(stage, finish); } else finish();
      const key = e => { if (!done && win.el.contains(document.activeElement || win.el)) finish(); else if (e.key === 'ArrowRight') step(1); else if (e.key === 'ArrowLeft') step(-1); };
      win.el.addEventListener('keydown', key);

      const remember = () => {
        if (never.checked === !show) return;
        show = !never.checked;
        Akari.api('/api/welcome', { method: 'PUT', json: { show }, quiet: true }).catch(() => {});
      };
      const step = d => {
        const n = at + d;
        if (n >= PAGES.length) { remember(); return win.close(); }
        if (n < 0) return;
        at = n; draw(d);
      };

      win.body.addEventListener('click', e => {
        const b = e.target.closest('button');
        if (!b) return;
        if (b.matches('[data-next]')) return step(1);
        if (b.matches('[data-prev]')) return step(-1);
        if (b.matches('[data-dot]')) { const n = +b.dataset.dot; const d = n - at; at = n; return draw(d); }
        if (b.matches('[data-tint]')) {
          Akari.set('tint', b.dataset.tint);
          win.body.querySelectorAll('[data-tint]').forEach(x => x.setAttribute('aria-checked', x === b));
          return;
        }
        if (b.matches('[data-open]')) {
          let a = {};
          try { a = JSON.parse(b.dataset.args || '{}'); } catch {}
          Akari.open(b.dataset.open, a);
        }
      });
      win.body.addEventListener('change', e => {
        if (e.target.name === 'wl-theme') { Facet.setTheme(e.target.value, e.target.nextElementSibling); Akari.set('theme', e.target.value); }
        if (e.target === never) remember();
      });

      return {
        close: () => { remember(); stage?.classList.add('is-leaving'); win.el.removeEventListener('keydown', key); return true; },
        args(a) { if (a?.page != null) { at = Math.max(0, Math.min(PAGES.length - 1, +a.page || 0)); if (done) draw(); } },
      };
    },
  });

  // once per sign-in (a reload in the same tab does not count again), while the account wants it
  const greet = async () => {
    try { if (sessionStorage.getItem('akari-welcomed')) return; sessionStorage.setItem('akari-welcomed', '1'); } catch {}
    const r = await Akari.api('/api/welcome', { quiet: true }).catch(() => null);
    if (r?.show) setTimeout(() => Akari.open('welcome'), 600);
  };
  // akari.js starts while the later scripts still load: the desktop may be ready before this file is
  if (Akari.ready) greet(); else Akari.on('ready', greet);
})();
