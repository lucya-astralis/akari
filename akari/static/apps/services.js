/* Dienste: the machine's services and its journal, for accounts that manage it.

   Services (failed first, then what runs, then the rest; search, only running),
   one service in detail (state, memory, CPU, restarts, its log as it grows,
   start / stop / restart / autostart), and the journal of the whole system from
   a chosen level up. All of it from akarid (/api/services, services.py), which
   asks systemd; akarid and Caddy cannot be stopped from here, or the page would
   cut itself off. Laid out like Docker, with Docker's classes. */
(() => {
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const t = s => Akari.t(s);
  const STATE = { active: ['läuft', 'ok'], failed: ['fehlgeschlagen', 'err'], activating: ['startet', 'warn'], deactivating: ['hält an', 'warn'], reloading: ['lädt neu', 'warn'], inactive: ['aus', ''] };
  const badge = (s, sub) => { const [l, tone] = STATE[s] || [s, '']; return `<span class="f-badge ${tone ? `f-badge--${tone}` : ''}">${esc(t(s === 'active' && sub === 'exited' ? 'erledigt' : l))}</span>`; };
  const dot = s => s === 'active' ? 'is-ok' : s === 'failed' ? 'is-err' : ['activating', 'deactivating', 'reloading'].includes(s) ? 'is-warn' : '';
  const PRIO = ['notfall', 'alarm', 'kritisch', 'fehler', 'warnung', 'hinweis', 'info', 'debug'];
  const when = s => new Date(s * 1000).toLocaleString(Akari.locale(), { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit' });
  const entries = list => list.map(e => `<div class="sv__line sv__line--p${Math.min(e.p, 6)}"><time>${esc(when(e.t))}</time><b>${esc(e.who)}</b><span>${esc(e.msg)}</span></div>`).join('')
    || `<p class="f-dim sv__none">${esc(t('Nichts im Protokoll.'))}</p>`;
  const PAGES = [['services', 'Dienste', 'i-list'], ['journal', 'Protokoll', 'i-note']];

  Akari.register('services', {
    title: 'Dienste', icon: 'i-list', art: 'services', size: [1000, 640], order: 72, dock: false,
    create(win, args) {
      win.body.classList.add('dk', 'sv');
      win.body.innerHTML = `
        <aside class="dk__side">
          <nav class="f-nav" data-nav aria-label="${t('Bereiche')}">
            ${PAGES.map(([id, label, icon]) => `<button class="f-nav__item" data-go="${id}"><svg><use href="#${icon}"/></svg>${t(label)}<span class="dk__count" data-count="${id}"></span></button>`).join('')}
          </nav>
          <div class="dk__engine f-dim" data-sum></div>
        </aside>
        <main class="dk__main" data-main></main>`;
      const main = win.body.querySelector('[data-main]'), side = win.body.querySelector('.dk__side');
      let page = args.page || 'services', list = [], detail = args.service || null, filter = '', onlyRunning = false, prio = 'warning';
      let timer = null, logTimer = null, alive = true;

      const head = (title, lede, acts = '') => `<header class="dk__head"><div><h2 class="f-h2">${esc(t(title))}</h2>${lede ? `<p class="f-dim">${esc(t(lede))}</p>` : ''}</div><div class="dk__acts">${acts}</div></header>`;

      const go = p => {
        page = p; detail = null; clearTimeout(logTimer);
        side.querySelectorAll('[data-go]').forEach(a => { a.classList.toggle('is-on', a.dataset.go === p); a.toggleAttribute('aria-current', a.dataset.go === p); });
        main.scrollTop = 0;
        render();
      };
      const load = async () => {
        clearTimeout(timer);
        if (!alive) return;
        try { list = (await Akari.api('/api/services', { quiet: true })).services; } catch { list = null; }
        const failed = (list || []).filter(s => s.active === 'failed').length, running = (list || []).filter(s => s.active === 'active' && s.sub === 'running').length;
        side.querySelector('[data-count="services"]').innerHTML = failed ? `<i class="dk__dot is-err"></i>` : '';
        side.querySelector('[data-sum]').textContent = list ? `${running} ${t('laufen')}${failed ? ` · ${failed} ${t('fehlgeschlagen')}` : ''}` : '';
        timer = setTimeout(() => { load().then(() => { if (page === 'services' && !detail) renderList(); }); }, 5000);
      };

      const render = () => {
        if (!Akari.me?.admin) { main.innerHTML = `<div class="dk__empty"><p>${t('Dienste sehen und ändern dürfen Konten, die verwalten.')}</p></div>`; return; }
        if (detail) return renderDetail();
        if (page === 'journal') return renderJournal();
        renderList();
      };

      const row = s => `
        <div class="dk__row" data-sv="${esc(s.name)}" tabindex="0">
          <i class="dk__dot ${dot(s.active)}"></i>
          <span class="dk__name" translate="no"><b>${esc(s.name.replace(/\.service$/, ''))}</b><small>${esc(s.description || '')}</small></span>
          <span class="dk__status">${esc(s.enabled === 'enabled' ? t('beim Start') : s.enabled === 'disabled' ? t('von Hand') : s.enabled || '')}</span>
          <span class="dk__status">${badge(s.active, s.sub)}</span>
        </div>`;
      const renderList = () => {
        if (!list) { main.innerHTML = `<div class="dk__empty"><p>${t('systemd antwortet nicht.')}</p></div>`; return; }
        const q = filter.toLowerCase();
        const shown = list.filter(s => (!onlyRunning || s.active === 'active') && (!q || `${s.name} ${s.description}`.toLowerCase().includes(q)));
        const failed = shown.filter(s => s.active === 'failed'), rest = shown.filter(s => s.active !== 'failed');
        const hadFocus = main.querySelector('[data-filter]') === document.activeElement;
        main.innerHTML = `${head('Dienste', 'Was auf diesem Rechner läuft, von systemd gestartet.')}
          <div class="dk__bar">
            <label class="f-search"><svg><use href="#i-search"/></svg><input class="f-input" data-filter placeholder="${t('Dienste suchen')}" value="${esc(filter)}" autocomplete="off"></label>
            <label class="f-check"><input type="checkbox" data-only ${onlyRunning ? 'checked' : ''}>${t('Nur aktive')}</label>
          </div>
          ${failed.length ? `<div class="dk__group"><div class="dk__ghead"><span class="f-label">${t('Fehlgeschlagen')}</span><span class="f-dim">${failed.length}</span></div><div class="grp">${failed.map(row).join('')}</div></div>` : ''}
          <div class="dk__group"><div class="dk__ghead"><span class="f-label">${t('Alle')}</span><span class="f-dim">${rest.length}</span></div>
            <div class="grp">${rest.map(row).join('') || `<div class="opt"><span class="opt__txt"><small>${t('Nichts passt.')}</small></span></div>`}</div></div>`;
        if (hadFocus) { const i = main.querySelector('[data-filter]'); i.focus(); i.setSelectionRange(i.value.length, i.value.length); }
      };

      const fmtCpu = ns => ns == null ? '–' : ns < 1e9 ? `${Math.round(ns / 1e6)} ms` : ns < 6e10 ? `${(ns / 1e9).toFixed(1)} s` : `${Math.round(ns / 6e10)} min`;
      const renderDetail = async () => {
        let d;
        try { d = await Akari.api(`/api/services/${encodeURIComponent(detail)}`, { quiet: true }); } catch { detail = null; return render(); }
        const running = d.active === 'active' || d.active === 'activating';
        const acts = d.protected
          ? `<span class="f-dim sv__note">${t('Braucht Akari selbst')}</span>`
          : `${running ? `<button class="f-btn f-btn--sm" data-act="restart"><svg><use href="#i-refresh"/></svg>${t('Neu starten')}</button><button class="f-btn f-btn--sm" data-act="stop"><svg><use href="#i-pause"/></svg>${t('Anhalten')}</button>`
              : `<button class="f-btn f-btn--sm f-btn--primary" data-act="start"><svg><use href="#i-play"/></svg>${t('Starten')}</button>`}`;
        main.innerHTML = `<header class="dk__head"><div class="dk__crumbs"><button class="f-btn f-btn--sm f-btn--ghost" data-back><svg><use href="#i-back"/></svg>${t('Dienste')}</button>
            <h2 class="f-h2" translate="no">${esc(d.name.replace(/\.service$/, ''))}</h2>${badge(d.active, d.sub)}</div><div class="dk__acts">${acts}</div></header>
          <p class="f-dim sv__desc">${esc(d.description)}</p>
          <div class="grp"><dl class="f-metrics f-metrics--grid dk__stats">
            <div class="f-metric"><dt>${t('Speicher')}</dt><dd class="f-metric__value f-metric__value--plain">${d.memory != null ? Akari.fmtBytes(d.memory) : '–'}</dd></div>
            <div class="f-metric"><dt>CPU</dt><dd class="f-metric__value f-metric__value--plain">${fmtCpu(d.cpu_ns)}</dd><dd class="f-metric__note">${t('seit dem Start')}</dd></div>
            <div class="f-metric"><dt>${t('Prozesse')}</dt><dd class="f-metric__value">${d.tasks ?? '–'}</dd></div>
            <div class="f-metric"><dt>${t('Neustarts')}</dt><dd class="f-metric__value">${d.restarts ?? 0}</dd></div></dl></div>
          <div class="grp dk__facts">
            <div class="opt"><span class="opt__txt"><b>${t('Beim Start des Rechners')}</b><small>${esc(d.enabled === 'enabled' ? t('startet von selbst') : d.enabled === 'disabled' ? t('startet nur von Hand') : d.enabled || '–')}</small></span>
              ${!d.protected && ['enabled', 'disabled'].includes(d.enabled) ? `<label class="f-switch"><input type="checkbox" data-autostart ${d.enabled === 'enabled' ? 'checked' : ''}><i></i><span class="sr">${t('Beim Start des Rechners')}</span></label>` : ''}</div>
            <div class="opt"><span class="opt__txt"><b>${t('Seit')}</b><small translate="no">${esc(d.since || '–')}${d.pid ? ` · PID ${d.pid}` : ''}</small></span></div>
            ${d.active === 'failed' ? `<div class="opt"><span class="opt__txt"><b>${t('Ergebnis')}</b><small translate="no">${esc(d.result || '')}${d.status ? ` · exit ${d.status}` : ''}</small></span></div>` : ''}
            <div class="opt"><span class="opt__txt"><b>${t('Datei')}</b><small translate="no"><code>${esc(d.path || '–')}</code></small></span></div>
          </div>
          <div class="dk__ghead"><span class="f-label">${t('Protokoll')}</span><label class="f-check"><input type="checkbox" data-follow checked>${t('Mitlaufen')}</label></div>
          <div class="sv__log" data-log translate="no">…</div>`;
        loadLog();
      };
      const loadLog = async () => {
        clearTimeout(logTimer);
        const box = main.querySelector('[data-log]');
        if (!box || !detail || !alive) return;
        try {
          const r = await Akari.api(`/api/services/${encodeURIComponent(detail)}/log?lines=300`, { quiet: true });
          const atEnd = box.scrollTop + box.clientHeight >= box.scrollHeight - 8;
          box.innerHTML = entries(r.entries);
          if (atEnd || box.dataset.first !== '1') { box.scrollTop = box.scrollHeight; box.dataset.first = '1'; }
        } catch {}
        if (main.querySelector('[data-follow]')?.checked) logTimer = setTimeout(loadLog, 2000);
      };

      const renderJournal = async () => {
        main.innerHTML = `${head('Protokoll', 'Was das System seit dem Start gemeldet hat, ab einer Stufe aufwärts.',
          `<div class="f-seg" role="radiogroup" aria-label="${t('Stufe')}"><span class="f-seg__thumb"></span>${[['err', 'Fehler'], ['warning', 'Warnungen'], ['info', 'Alles']].map(([v, l]) =>
            `<input type="radio" name="sv-prio" id="sv-p-${v}" value="${v}" ${prio === v ? 'checked' : ''}><label for="sv-p-${v}">${t(l)}</label>`).join('')}</div>`)}
          <div class="sv__log sv__log--tall" data-journal translate="no">…</div>`;
        requestAnimationFrame(() => Facet.layout());
        let r; try { r = await Akari.api(`/api/services/journal?priority=${prio}&lines=400`, { quiet: true }); } catch { return; }
        const box = main.querySelector('[data-journal]');
        if (!box) return;
        box.innerHTML = entries(r.entries);
        box.scrollTop = box.scrollHeight;
      };

      win.body.addEventListener('click', async e => {
        const nav = e.target.closest('[data-go]'); if (nav) return go(nav.dataset.go);
        if (e.target.closest('[data-back]')) { detail = null; clearTimeout(logTimer); return render(); }
        const b = e.target.closest('[data-act]');
        if (b) {
          const action = b.dataset.act;
          if (action === 'stop' && !await Akari.ask({ title: `${detail.replace(/\.service$/, '')} ${t('anhalten?')}`, text: t('Was der Dienst anbietet, ist danach nicht mehr erreichbar, bis er wieder startet.'), ok: t('Anhalten'), danger: true })) return;
          b.disabled = true;
          try { await Akari.api(`/api/services/${encodeURIComponent(detail)}`, { method: 'POST', json: { action } }); } catch {}
          await load();
          return renderDetail();
        }
        const r = e.target.closest('[data-sv]');
        if (r) { detail = r.dataset.sv; render(); }
      });
      win.body.addEventListener('keydown', e => { const r = e.target.closest('[data-sv]'); if (r && e.key === 'Enter') { detail = r.dataset.sv; render(); } });
      win.body.addEventListener('input', e => { if (e.target.matches('[data-filter]')) { filter = e.target.value; renderList(); } });
      win.body.addEventListener('change', async e => {
        if (e.target.matches('[data-only]')) { onlyRunning = e.target.checked; return renderList(); }
        if (e.target.matches('[data-follow]') && e.target.checked) return loadLog();
        if (e.target.name === 'sv-prio') { prio = e.target.value; return renderJournal(); }
        if (e.target.matches('[data-autostart]')) {
          try { await Akari.api(`/api/services/${encodeURIComponent(detail)}`, { method: 'POST', json: { action: e.target.checked ? 'enable' : 'disable' } }); } catch {}
          await load();
          renderDetail();
        }
      });

      const first = detail;
      load().then(() => { go(page); if (first) { detail = first; render(); } });
      return {
        close: () => { alive = false; clearTimeout(timer); clearTimeout(logTimer); return true; },
        args(a) { if (a?.service) { detail = a.service; render(); } else if (a?.page) go(a.page); },
      };
    },
  });
})();
