/* Docker: the containers on this machine, for accounts that manage it.

   Overview (the engine, tidy up), Container (grouped by Compose project,
   start, stop, details with load and logs), a form for a new container,
   Images (pull, remove), Volumes, Networks, and Lucent: lucya.systems'
   management, started through its helper lucya-aio with one click and
   paired with Akari. All of it talks to akarid (/api/docker, docker.py);
   whoever holds Docker's socket is root, so nothing here is for others. */
(() => {
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const t = s => Akari.t(s);
  const ago = sec => {
    const s = Math.max(0, Date.now() / 1000 - sec);
    return s < 3600 ? `${Math.max(1, Math.round(s / 60))} min` : s < 86400 ? `${Math.round(s / 3600)} h` : `${Math.round(s / 86400)} d`;
  };
  const STATE = { running: ['läuft', 'ok'], paused: ['pausiert', 'warn'], restarting: ['startet neu', 'warn'], created: ['angelegt', ''], exited: ['beendet', ''], dead: ['tot', 'err'], removing: ['wird entfernt', 'warn'] };
  const badge = s => { const [l, tone] = STATE[s] || [s, '']; return `<span class="f-badge ${tone ? `f-badge--${tone}` : ''}">${esc(t(l))}</span>`; };
  const PAGES = [['overview', 'Übersicht', 'i-info'], ['containers', 'Container', 'i-box'], ['images', 'Images', 'i-archive'],
    ['volumes', 'Volumes', 'i-drive'], ['networks', 'Netzwerke', 'i-net'], ['lucent', 'Lucent', 'i-globe']];

  Akari.register('docker', {
    title: 'Docker', icon: 'i-box', art: 'docker', size: [1000, 640], order: 70, dock: false,
    create(win, args) {
      win.body.classList.add('dk');
      win.body.innerHTML = `
        <aside class="dk__side">
          <nav class="f-nav" data-nav aria-label="Bereiche">
            ${PAGES.map(([id, label, icon]) => `<a class="f-nav__item" href="#${id}" data-go="${id}"><svg><use href="#${icon}"/></svg>${label}<span class="dk__count" data-count="${id}"></span></a>`).join('')}
          </nav>
          <div class="dk__engine f-dim" data-engine></div>
        </aside>
        <main class="dk__main" data-main></main>`;
      const main = win.body.querySelector('[data-main]');
      const side = win.body.querySelector('.dk__side');
      let page = args.page || 'overview', st = null, timer = null, detail = null, logTimer = null, alive = true;

      const go = p => {
        page = p; detail = null; clearTimeout(logTimer);
        side.querySelectorAll('[data-go]').forEach(a => { a.classList.toggle('is-on', a.dataset.go === p); a.toggleAttribute('aria-current', a.dataset.go === p); });
        main.scrollTop = 0;
        refresh(true);
      };
      side.addEventListener('click', e => { const a = e.target.closest('[data-go]'); if (a) { e.preventDefault(); if (st?.running) go(a.dataset.go); } });

      /* ---------- loading ---------- */
      const refresh = async (draw = false) => {
        clearTimeout(timer);
        if (!alive) return;
        try { st = await Akari.api('/api/docker', { quiet: true }); } catch { st = null; }
        side.hidden = !st?.running;
        win.body.classList.toggle('dk--bare', !st?.running);
        if (st?.running) {
          const run = st.containers_list.filter(c => c.state === 'running').length;
          side.querySelector('[data-count="containers"]').textContent = `${run}/${st.containers_list.length}`;
          side.querySelector('[data-count="images"]').textContent = st.images || '';
          side.querySelector('[data-engine]').textContent = `Docker ${st.version}${st.storage ? ` · ${st.storage}` : ''}`;
          const luc = st.lucent;
          side.querySelector('[data-count="lucent"]').innerHTML = luc?.lucent?.state === 'running' ? '<i class="dk__dot is-ok"></i>' : luc?.job ? '<i class="dk__dot is-warn"></i>' : '';
        }
        // the open details and the form stay as they are (the log follows on its own)
        if (draw || (!detail && ['overview', 'containers', 'lucent'].includes(page))) await render();
        // the lists follow what happens; a setup or an install is looked at more often
        timer = setTimeout(refresh, st?.lucent?.job || installing ? 2000 : 4000);
      };

      /* ---------- pages ---------- */
      let installing = false;
      const render = async () => {
        if (!st) { main.innerHTML = `<div class="dk__empty"><p>${t('Docker antwortet nicht.')}</p></div>`; return; }
        if (!st.admin) {
          main.innerHTML = `<div class="dk__empty"><svg class="dk__hero"><use href="#app-docker"/></svg><h2 class="f-h2">Docker</h2>
            <p class="f-dim">${t('Container verwaltet ein Konto, das verwalten darf: Wer Docker bedient, ist Herr über den ganzen Rechner.')}</p></div>`;
          return;
        }
        if (!st.running) return renderInstall();
        if (detail) return renderDetail();
        ({ overview: renderOverview, containers: renderContainers, images: renderImages, volumes: renderVolumes, networks: renderNetworks, lucent: renderLucent, new: renderNew })[page]?.();
        requestAnimationFrame(() => Facet.layout());
      };

      const head = (title, lede, acts = '') => `<header class="dk__head"><div><h2 class="f-h2">${esc(t(title))}</h2>${lede ? `<p class="f-dim">${esc(t(lede))}</p>` : ''}</div><div class="dk__acts">${acts}</div></header>`;

      /* not there yet: Debian's Docker with one click */
      const renderInstall = async () => {
        let up = null;
        try { up = await Akari.api('/api/host/updates', { quiet: true }); } catch {}
        installing = up?.running === 'docker';
        const failed = !installing && up?.last?.job === 'docker' && !up.last.ok;
        main.innerHTML = `<div class="dk__empty">
          <svg class="dk__hero"><use href="#app-docker"/></svg>
          <h2 class="f-h2">${t(st.installed ? 'Docker läuft nicht' : 'Docker einrichten')}</h2>
          <p class="f-dim">${t(st.installed ? 'Docker ist installiert, aber der Dienst antwortet nicht. Im Terminal: sudo systemctl start docker'
            : 'Container für Dienste neben dem Desktop: Datenbanken, Web-Apps, Lucent. Akari installiert Docker aus Debian (docker.io und Compose).')}</p>
          ${st.installed ? '' : `<button class="f-btn f-btn--primary" data-install ${installing ? 'disabled' : ''}>${t(installing ? 'Wird installiert …' : 'Docker installieren')}</button>`}
          ${failed ? `<p class="f-status f-status--err">${t('Die Installation ist fehlgeschlagen.')}</p>` : ''}
          ${(installing || failed) && up.log.length ? `<pre class="up__log dk__log--small">${esc(up.log.join('\n'))}</pre>` : ''}
        </div>`;
      };

      const renderOverview = () => {
        const cs = st.containers_list, run = cs.filter(c => c.state === 'running').length;
        const projects = new Set(cs.map(c => c.project).filter(Boolean));
        const luc = st.lucent;
        main.innerHTML = `${head('Übersicht', '', `<button class="f-btn f-btn--sm" data-prune><svg><use href="#i-trash"/></svg>${t('Aufräumen')}</button>
            <button class="f-btn f-btn--sm f-btn--primary" data-new><svg><use href="#i-plus"/></svg>${t('Neuer Container')}</button>`)}
          <div class="grp"><dl class="f-metrics f-metrics--grid dk__stats">
            <div class="f-metric"><dt>${t('Laufen')}</dt><dd class="f-metric__value">${run}</dd><dd class="f-metric__note">${cs.length} ${t('insgesamt')}</dd></div>
            <div class="f-metric"><dt>${t('Projekte')}</dt><dd class="f-metric__value">${projects.size}</dd><dd class="f-metric__note">Compose, lucya-aio</dd></div>
            <div class="f-metric"><dt>Images</dt><dd class="f-metric__value">${st.images}</dd><dd class="f-metric__note">${esc(st.root || '')}</dd></div>
            <div class="f-metric"><dt>Docker</dt><dd class="f-metric__value f-metric__value--plain">${esc(st.version)}</dd><dd class="f-metric__note">${esc(st.storage || '')}</dd></div>
          </dl></div>
          <span class="f-label grp__label">${t('Laufende Container')}</span>
          <div class="grp">${cs.filter(c => c.state === 'running').slice(0, 8).map(row).join('') || `<div class="opt"><span class="opt__txt"><small>${t('Kein Container läuft.')}</small></span></div>`}</div>
          <span class="f-label grp__label">Lucent</span>
          <div class="grp"><div class="opt"><span class="opt__txt"><b>${t(luc?.lucent?.state === 'running' ? 'Lucent läuft' : 'Lucent auf diesem Rechner')}</b>
            <small>${t(luc?.lucent?.state === 'running' ? 'Verwaltung, Anmeldung und die Tools von lucya.systems.' : 'Mit einem Klick: Lucent und sein Helfer lucya-aio, Akari gleich gekoppelt.')}</small></span>
            <button class="f-btn f-btn--sm" data-go-page="lucent">${t('Öffnen')}</button></div></div>`;
      };

      /* one container as a row; the same in the overview and the list */
      const row = c => `
        <div class="dk__row" data-cid="${esc(c.id)}" tabindex="0">
          <i class="dk__dot ${c.state === 'running' ? 'is-ok' : c.state === 'paused' || c.state === 'restarting' ? 'is-warn' : ''}"></i>
          <span class="dk__name" translate="no"><b>${esc(c.name)}</b><small>${esc(c.image)}</small></span>
          <span class="dk__ports" translate="no">${c.ports.map(p => `<code>${esc(p)}</code>`).join('')}</span>
          <span class="dk__status">${esc(c.status)}</span>
          <span class="dk__rowacts">
            ${c.owner ? `<span class="f-badge f-tip" data-tip="${t(c.owner === 'lucent' ? 'Verwaltet von Lucent' : 'Auf der Seite Lucent')}">${c.owner === 'lucent' ? 'Lucent' : 'Akari'}</span>`
            : c.state === 'running'
              ? `<button class="f-btn f-btn--ghost f-btn--icon f-tip" data-act="stop" data-tip="${t('Anhalten')}" aria-label="${t('Anhalten')}"><svg><use href="#i-pause"/></svg></button>
                 <button class="f-btn f-btn--ghost f-btn--icon f-tip" data-act="restart" data-tip="${t('Neu starten')}" aria-label="${t('Neu starten')}"><svg><use href="#i-refresh"/></svg></button>`
              : `<button class="f-btn f-btn--ghost f-btn--icon f-tip" data-act="start" data-tip="${t('Starten')}" aria-label="${t('Starten')}"><svg><use href="#i-play"/></svg></button>`}
            ${c.owner ? '' : `<button class="f-btn f-btn--ghost f-btn--icon f-tip" data-more data-tip="${t('Mehr')}" aria-label="${t('Mehr')}"><svg><use href="#i-list"/></svg></button>`}
          </span>
        </div>`;

      let filter = '', onlyRunning = false;
      const renderContainers = () => {
        const q = filter.toLowerCase();
        const cs = st.containers_list.filter(c => (!onlyRunning || c.state === 'running') && (!q || `${c.name} ${c.image} ${c.project || ''}`.toLowerCase().includes(q)));
        const groups = new Map();
        cs.forEach(c => { const k = c.project || ''; groups.set(k, [...(groups.get(k) || []), c]); });
        const keys = [...groups.keys()].sort((a, b) => (a === '') - (b === '') || a.localeCompare(b));
        const hadFocus = main.querySelector('[data-filter]') === document.activeElement;
        main.innerHTML = `${head('Container', '', `<button class="f-btn f-btn--sm f-btn--primary" data-new><svg><use href="#i-plus"/></svg>${t('Neuer Container')}</button>`)}
          <div class="dk__bar">
            <label class="f-search"><svg><use href="#i-search"/></svg><input class="f-input" data-filter placeholder="${t('Container suchen')}" value="${esc(filter)}" autocomplete="off"></label>
            <label class="f-check"><input type="checkbox" data-only ${onlyRunning ? 'checked' : ''}>${t('Nur laufende')}</label>
          </div>
          ${keys.map(k => {
            const g = groups.get(k), on = g.filter(c => c.state === 'running').length;
            return `<div class="dk__group">
              <div class="dk__ghead"><span class="f-label">${esc(k || t('Einzeln'))}</span><span class="f-dim">${on}/${g.length}</span>
                ${k && g.some(c => !c.owner) ? `<span class="dk__gacts"><button class="f-btn f-btn--sm f-btn--ghost" data-group="${esc(k)}" data-gact="start">${t('Alle starten')}</button><button class="f-btn f-btn--sm f-btn--ghost" data-group="${esc(k)}" data-gact="stop">${t('Alle anhalten')}</button></span>` : ''}</div>
              <div class="grp">${g.map(row).join('')}</div></div>`;
          }).join('') || `<div class="dk__empty dk__empty--small"><p class="f-dim">${t(st.containers_list.length ? 'Nichts passt.' : 'Noch keine Container. Lege einen an oder richte Lucent ein.')}</p></div>`}`;
        if (hadFocus) { const i = main.querySelector('[data-filter]'); i.focus(); i.setSelectionRange(i.value.length, i.value.length); }
      };

      /* one container: what it is, what it uses, its logs */
      const renderDetail = async () => {
        let d;
        try { d = await Akari.api(`/api/docker/containers/${detail}`, { quiet: true }); } catch { detail = null; return render(); }
        const s = d.stats;
        main.innerHTML = `<header class="dk__head"><div class="dk__crumbs"><button class="f-btn f-btn--sm f-btn--ghost" data-back><svg><use href="#i-back"/></svg>${t('Container')}</button>
            <h2 class="f-h2" translate="no">${esc(d.name)}</h2>${badge(d.state)}${d.health ? `<span class="f-badge">${esc(d.health)}</span>` : ''}</div>
          <div class="dk__acts">${d.owner === 'lucent'
            ? (st.lucent?.url ? `<a class="f-btn f-btn--sm" href="${esc(st.lucent.url)}" target="_blank" rel="noopener"><svg><use href="#i-globe"/></svg>${t('In Lucent verwalten')}</a>` : '')
            : d.owner === 'aio' ? `<button class="f-btn f-btn--sm" data-go-page="lucent"><svg><use href="#i-globe"/></svg>${t('Zur Seite Lucent')}</button>`
            : `${d.state === 'running'
            ? `<button class="f-btn f-btn--sm" data-act="stop" data-cid="${d.id}"><svg><use href="#i-pause"/></svg>${t('Anhalten')}</button><button class="f-btn f-btn--sm" data-act="restart" data-cid="${d.id}"><svg><use href="#i-refresh"/></svg>${t('Neu starten')}</button>`
            : `<button class="f-btn f-btn--sm f-btn--primary" data-act="start" data-cid="${d.id}"><svg><use href="#i-play"/></svg>${t('Starten')}</button>`}
            <button class="f-btn f-btn--sm f-btn--danger" data-act="remove" data-cid="${d.id}"><svg><use href="#i-trash"/></svg>${t('Entfernen')}</button>`}</div></header>
          ${d.owner ? `<p class="f-dim dk__owner">${t(d.owner === 'lucent'
            ? 'Diesen Container hat lucya-aio für Lucent angelegt und hält ihn aktuell. Starten, anhalten und entfernen geht in Lucent, damit ihn nur einer verwaltet.'
            : 'Der Helfer von lucya.systems. Akari hat ihn gestartet und bringt ihn auf der Seite Lucent auf den neuesten Stand.')}</p>` : ''}
          ${s ? `<div class="grp"><dl class="f-metrics f-metrics--grid dk__stats">
            <div class="f-metric"><dt>CPU</dt><dd class="f-metric__value">${s.cpu.toLocaleString(Akari.locale())} %</dd></div>
            <div class="f-metric"><dt>${t('Speicher')}</dt><dd class="f-metric__value f-metric__value--plain">${Akari.fmtBytes(s.mem)}</dd><dd class="f-metric__note">${s.mem_limit ? `${t('Grenze')} ${Akari.fmtBytes(s.mem_limit)}` : ''}</dd></div>
            <div class="f-metric"><dt>${t('Netz')}</dt><dd class="f-metric__value f-metric__value--plain">↓ ${Akari.fmtBytes(s.rx)}</dd><dd class="f-metric__note">↑ ${Akari.fmtBytes(s.tx)}</dd></div>
            <div class="f-metric"><dt>${t('Prozesse')}</dt><dd class="f-metric__value">${s.pids ?? '–'}</dd></div></dl></div>` : ''}
          <div class="grp dk__facts" translate="no">
            <div class="opt"><span class="opt__txt"><b>Image</b><small>${esc(d.image)}</small></span></div>
            <div class="opt"><span class="opt__txt"><b>${t('Befehl')}</b><small><code>${esc(d.cmd || '–')}</code></small></span></div>
            <div class="opt"><span class="opt__txt"><b>${t('Neustart')}</b><small>${esc(d.restart)}${d.exit && d.state !== 'running' ? ` · ${t('Exit-Code')} ${d.exit}` : ''}</small></span></div>
            <div class="opt"><span class="opt__txt"><b>Ports</b><small>${d.ports.map(p => `${esc(p.host)} → ${esc(p.container)}`).join(' · ') || '–'}</small></span></div>
            <div class="opt"><span class="opt__txt"><b>${t('Netzwerke')}</b><small>${esc(d.networks.join(', ') || '–')}</small></span></div>
            <div class="opt"><span class="opt__txt"><b>${t('Daten')}</b><small>${d.mounts.map(m => `${esc(m.source)} → ${esc(m.target)}${m.rw ? '' : ' (ro)'}`).join(' · ') || '–'}</small></span></div>
          </div>
          ${d.env.length ? `<details class="dk__env"><summary class="f-label">${t('Umgebung')} (${d.env.length})</summary><div class="grp" translate="no">${d.env.map(e => `<div class="dk__kv"><b>${esc(e.name)}</b><code>${esc(e.value)}</code></div>`).join('')}</div></details>` : ''}
          <div class="dk__ghead"><span class="f-label">${t('Protokoll')}</span><label class="f-check"><input type="checkbox" data-follow checked>${t('Mitlaufen')}</label></div>
          <pre class="dk__log" data-log translate="no">…</pre>`;
        loadLog();
      };
      const loadLog = async () => {
        clearTimeout(logTimer);
        const pre = main.querySelector('[data-log]');
        if (!pre || !detail || !alive) return;
        try {
          const r = await Akari.api(`/api/docker/containers/${detail}/logs?tail=400`, { quiet: true });
          const atEnd = pre.scrollTop + pre.clientHeight >= pre.scrollHeight - 8;
          pre.textContent = r.text || t('(noch nichts)');
          if (atEnd || pre.dataset.first !== '1') { pre.scrollTop = pre.scrollHeight; pre.dataset.first = '1'; }
        } catch {}
        if (main.querySelector('[data-follow]')?.checked) logTimer = setTimeout(loadLog, 2000);
      };

      /* a new container: image, name, ports, environment, volumes, restart */
      const renderNew = () => {
        main.innerHTML = `${head('Neuer Container', 'Wie docker run: ein Image, und was der Container vom Rechner bekommt.', `<button class="f-btn f-btn--sm f-btn--ghost" data-go-page="containers">${t('Abbrechen')}</button>`)}
          <form class="grp grp--form dk__form" data-run autocomplete="off">
            <label class="f-field"><span>Image</span><input class="f-input" name="image" required spellcheck="false" placeholder="nginx:latest"><small>${t('Aus Docker Hub oder mit Adresse: ghcr.io/owner/app:1.0. Fehlt es, lädt Akari es.')}</small></label>
            <label class="f-field"><span>Name</span><input class="f-input" name="name" spellcheck="false" placeholder="${t('leer: Docker wählt einen')}"></label>
            <label class="f-field"><span>Ports</span><textarea class="f-input" name="ports" rows="2" spellcheck="false" placeholder="8080:80"></textarea><small>${t('Einer je Zeile, Rechner:Container. Mit 127.0.0.1: davor nur von diesem Rechner aus.')}</small></label>
            <label class="f-field"><span>${t('Umgebung')}</span><textarea class="f-input" name="env" rows="3" spellcheck="false" placeholder="TZ=Europe/Berlin"></textarea><small>${t('Eine Variable je Zeile, NAME=wert.')}</small></label>
            <label class="f-field"><span>Volumes</span><textarea class="f-input" name="volumes" rows="2" spellcheck="false" placeholder="daten:/data"></textarea><small>${t('Einer je Zeile: ein Volume-Name oder ein Ordner des Rechners, dann der Pfad im Container.')}</small></label>
            <label class="f-field"><span>${t('Neustart')}</span><select class="f-input f-select" name="restart">
              <option value="unless-stopped">${t('Immer, außer angehalten')}</option><option value="always">${t('Immer')}</option><option value="on-failure">${t('Bei Fehlern')}</option><option value="no">${t('Nie')}</option></select></label>
            <div class="grp__foot"><span class="f-dim" data-state></span><button class="f-btn f-btn--primary" type="submit"><svg><use href="#i-play"/></svg>${t('Anlegen und starten')}</button></div>
          </form>`;
        main.querySelector('[name="image"]').focus();
      };
      const lines = v => v.split('\n').map(x => x.trim()).filter(Boolean);
      main.addEventListener('submit', async e => {
        if (!e.target.matches('[data-run]')) return;
        e.preventDefault();
        const f = e.target.elements, state = e.target.querySelector('[data-state]'), btn = e.target.querySelector('[type="submit"]');
        state.textContent = t('Image wird geladen, dann gestartet …'); btn.disabled = true;
        try {
          const r = await Akari.api('/api/docker/run', { method: 'POST', json: { image: f.image.value.trim(), name: f.name.value.trim(), ports: lines(f.ports.value), env: lines(f.env.value), volumes: lines(f.volumes.value), restart: f.restart.value } });
          Akari.notify(t('Der Container läuft.'));
          go('containers'); detail = r.id;   // go() loads afresh and then draws the details
        } catch (err) { state.textContent = err.message; btn.disabled = false; }
      });

      const renderImages = async () => {
        let r, p;
        try { [r, p] = await Promise.all([Akari.api('/api/docker/images', { quiet: true }), Akari.api('/api/docker/pulls', { quiet: true })]); } catch { return; }
        const pulling = Object.entries(p.pulls);
        const hadFocus = main.querySelector('[data-pull-in]') === document.activeElement, val = main.querySelector('[data-pull-in]')?.value || '';
        main.innerHTML = `${head('Images', 'Die Vorlagen, aus denen Container werden.')}
          <form class="dk__bar" data-pull><input class="f-input" data-pull-in name="image" placeholder="${t('Image laden, etwa postgres:16')}" spellcheck="false" value="${esc(val)}"><button class="f-btn f-btn--sm f-btn--primary" type="submit"><svg><use href="#i-down"/></svg>${t('Laden')}</button></form>
          ${pulling.length ? `<div class="grp">${pulling.map(([ref, s]) => `<div class="opt"><span class="opt__txt"><b translate="no">${esc(ref)}</b><small>${esc(s.state === 'pulling' ? t('wird geladen …') : s.state === 'done' ? t('geladen') : s.error)}</small></span>${s.state === 'pulling' ? '<span class="dk__spin" aria-hidden="true"></span>' : ''}</div>`).join('')}</div>` : ''}
          <div class="grp" translate="no">${r.images.map(i => `
            <div class="dk__row dk__row--plain"><span class="dk__name"><b>${esc(i.tags[0] || i.id)}</b><small>${esc(i.tags.slice(1).join(', ') || i.id)} · ${ago(i.created)}</small></span>
              <span class="dk__status">${Akari.fmtBytes(i.size)}</span><span class="dk__status">${i.used > 0 ? `${i.used} ${t(i.used === 1 ? 'Container' : 'Container')}` : ''}</span>
              <span class="dk__rowacts"><button class="f-btn f-btn--ghost f-btn--icon f-tip" data-rmi="${esc(i.id)}" data-name="${esc(i.tags[0] || i.id)}" data-tip="${t('Entfernen')}" aria-label="${t('Entfernen')}"><svg><use href="#i-trash"/></svg></button></span></div>`).join('') || `<div class="opt"><span class="opt__txt"><small>${t('Keine Images.')}</small></span></div>`}</div>`;
        if (hadFocus) main.querySelector('[data-pull-in]').focus();
        if (pulling.some(([, s]) => s.state === 'pulling')) { clearTimeout(timer); timer = setTimeout(() => { if (page === 'images') renderImages(); refresh(); }, 2000); }
      };
      main.addEventListener('submit', async e => {
        if (!e.target.matches('[data-pull]')) return;
        e.preventDefault();
        const ref = e.target.elements.image.value.trim(); if (!ref) return;
        try { await Akari.api('/api/docker/pull', { method: 'POST', json: { image: ref } }); e.target.elements.image.value = ''; } catch {}
        renderImages();
      });

      const renderVolumes = async () => {
        let r; try { r = await Akari.api('/api/docker/volumes', { quiet: true }); } catch { return; }
        main.innerHTML = `${head('Volumes', 'Wo Container ihre Daten behalten. Ein Volume bleibt, wenn sein Container geht.')}
          <div class="grp" translate="no">${r.volumes.map(v => `
            <div class="dk__row dk__row--plain"><span class="dk__name"><b>${esc(v.name)}</b><small>${esc(v.used_by.length ? `${t('in')} ${v.used_by.join(', ')}` : t('von keinem Container benutzt'))}</small></span>
              <span class="dk__status">${esc(v.project || '')}</span>
              <span class="dk__rowacts"><button class="f-btn f-btn--ghost f-btn--icon f-tip" data-rmv="${esc(v.name)}" ${v.used_by.length ? 'disabled' : ''} data-tip="${t('Löschen')}" aria-label="${t('Löschen')}"><svg><use href="#i-trash"/></svg></button></span></div>`).join('') || `<div class="opt"><span class="opt__txt"><small>${t('Keine Volumes.')}</small></span></div>`}</div>`;
      };

      const renderNetworks = async () => {
        let r; try { r = await Akari.api('/api/docker/networks', { quiet: true }); } catch { return; }
        main.innerHTML = `${head('Netzwerke', 'Container im selben Netz erreichen sich beim Namen.')}
          <div class="grp" translate="no">${r.networks.map(n => `
            <div class="dk__row dk__row--plain"><span class="dk__name"><b>${esc(n.name)}</b><small>${esc(n.driver)}${n.subnet ? ` · ${esc(n.subnet)}` : ''}${n.internal ? ` · ${t('intern')}` : ''}</small></span>
              <span class="dk__status">${n.builtin ? t('von Docker') : ''}</span>
              <span class="dk__rowacts">${n.builtin ? '' : `<button class="f-btn f-btn--ghost f-btn--icon f-tip" data-rmn="${esc(n.id)}" data-name="${esc(n.name)}" data-tip="${t('Löschen')}" aria-label="${t('Löschen')}"><svg><use href="#i-trash"/></svg></button>`}</span></div>`).join('')}</div>`;
      };

      /* Lucent: its helper lucya-aio makes it; Akari starts the helper, pairs, and keeps the helper up to date.
         Akari pairs with one Lucent: with one elsewhere there is nothing to set up here. */
      const STEPS = { pull: 'Lädt lucya-aio …', start: 'Startet den Helfer …', lucent: 'Der Helfer legt Lucent an …' };
      const UPDATE = { pull: 'Sucht eine neue Version von lucya-aio …', start: 'Startet lucya-aio neu …' };
      const renderLucent = async () => {
        const l = st.lucent || {};
        let paired = null;
        try { paired = (await Akari.api('/api/lucent', { quiet: true })).paired; } catch {}
        const on = l.lucent?.state === 'running', here = l.paired === 'here', setting = l.job && l.doing === 'setup', updating = l.job && l.doing === 'update';
        const pairRow = `<div class="grp"><div class="opt"><span class="opt__txt"><b>${t(paired ? 'Gekoppelt' : 'Mit Lucent koppeln')}</b><small translate="no">${esc(paired ? (here ? t('Mit dem Lucent auf diesem Rechner') : paired.issuer) : t('Nach der Einrichtung in Lucent unter Tools einen Code erzeugen, dann hier koppeln. Die Adressen sind schon eingetragen.'))}</small></span>
                <button class="f-btn f-btn--sm ${paired ? '' : 'f-btn--primary'}" data-lucent-pair>${t(paired ? 'Einstellungen' : 'Koppeln')}</button></div></div>`;
        main.innerHTML = `${head('Lucent', 'Die Verwaltung von lucya.systems: Zustand, Konten, Anmeldung mit einem Konto für alle Tools, ein Store für weitere.')}
          ${l.paired === 'elsewhere' && !l.aio ? `<div class="grp"><div class="opt"><span class="opt__txt"><b>${t('Akari hat schon einen Lucent')}</b><small>${t('Akari ist mit einem Lucent auf einem anderen Rechner gekoppelt und wird von dort verwaltet. Ein zweiter hier wäre doppelt.')}</small></span>
                ${l.issuer ? `<a class="f-btn f-btn--sm" href="${esc(l.issuer)}" target="_blank" rel="noopener">${t('Öffnen')}</a>` : ''}</div></div>
              <span class="f-label grp__label">${t('Akari koppeln')}</span>${pairRow}`
          : !l.aio && !setting ? `<div class="grp"><div class="opt opt--stack">
              <span class="opt__txt"><b>${t('Lucent auf diesem Rechner einrichten')}</b><small>${t('Akari startet lucya-aio, den Helfer von lucya.systems. Er legt Lucent an (Port 8060), hält es aktuell, sichert es und installiert auf Wunsch weitere Tools. Danach richtest du Lucent im Browser ein und koppelst Akari.')}</small></span>
              <button class="f-btn f-btn--primary opt__go" data-lucent-install><svg><use href="#i-down"/></svg>${t('Lucent einrichten')}</button></div></div>`
          : setting ? `<div class="grp"><div class="opt"><span class="opt__txt"><b>${t(STEPS[l.job] || 'Richtet ein …')}</b><small>${t('Das erste Mal lädt Docker ein paar hundert MB.')}</small></span><span class="dk__spin" aria-hidden="true"></span></div></div>`
          : `<div class="grp">
                <div class="opt"><span class="opt__txt"><b>Lucent</b><small>${esc(l.lucent ? l.lucent.status : t('wird vom Helfer angelegt …'))}</small></span>${l.lucent ? badge(l.lucent.state) : '<span class="dk__spin" aria-hidden="true"></span>'}</div>
                ${on && l.url ? `<div class="opt"><span class="opt__txt"><b>${t('Im Browser')}</b><small translate="no">${esc(l.url)}</small></span><a class="f-btn f-btn--sm f-btn--primary" href="${esc(l.url)}${here ? '' : '/setup'}" target="_blank" rel="noopener">${t('Öffnen')}</a></div>` : ''}
                ${on && l.code ? `<div class="opt"><span class="opt__txt"><b>${t('Einrichtungscode')}</b><small>${t('Lucent fragt beim ersten Öffnen danach.')}</small></span><code class="dk__code" translate="no">${esc(l.code)}</code></div>` : ''}
              </div>
              <p class="f-dim dk__owner">${t('Lucent und seine Tools verwaltet lucya-aio im Auftrag von Lucent: Updates, Sicherungen, neue Tools. Akari zeigt sie unter Container nur an.')}</p>
              ${on ? `<span class="f-label grp__label">${t('Akari koppeln')}</span>${pairRow}` : ''}
              <span class="f-label grp__label">${t('Helfer')}</span>
              <div class="grp"><div class="opt"><span class="opt__txt"><b>lucya-aio</b><small>${esc(updating ? t(UPDATE[l.job] || 'Wird aktualisiert …') : l.note === 'current' ? t('Ist auf dem neuesten Stand.') : l.note === 'updated' ? t('Aktualisiert.') : t('Akari hat ihn gestartet und hält ihn aktuell; Lucent und die Tools laufen dabei weiter.'))}</small></span>
                ${updating ? '<span class="dk__spin" aria-hidden="true"></span>' : `${l.aio ? badge(l.aio.state) : ''}<button class="f-btn f-btn--sm" data-helper-update><svg><use href="#i-refresh"/></svg>${t('Aktualisieren')}</button>`}</div></div>
              ${here ? '' : `<span class="f-label grp__label">${t('Entfernen')}</span>
              <div class="grp"><div class="opt"><span class="opt__txt"><b>${t('Lucent entfernen')}</b><small>${t('Hält den Helfer, Lucent und seine Tools an und entfernt die Container. Die Volumes mit den Daten bleiben.')}</small></span>
                <button class="f-btn f-btn--sm f-btn--danger" data-lucent-remove>${t('Entfernen')}</button></div></div>`}`}
          ${l.error ? `<p class="f-status f-status--err">${esc(l.error)}</p>` : ''}`;
      };

      /* ---------- actions ---------- */
      const act = async (cid, action) => {
        const c = st.containers_list.find(x => x.id === cid) || { name: cid };
        if (action === 'remove' && !await Akari.ask({ title: `${c.name} ${t('entfernen?')}`, text: t('Der Container wird angehalten und gelöscht. Seine Volumes bleiben, was nur im Container lag, ist weg.'), ok: t('Entfernen'), danger: true })) return;
        try { await Akari.api(`/api/docker/containers/${cid}`, { method: 'POST', json: { action } }); } catch {}
        if (action === 'remove' && detail === cid) detail = null;
        refresh(true);
      };
      main.addEventListener('click', async e => {
        const b = e.target.closest('button, [data-cid]');
        if (!b) return;
        if (b.matches('[data-new]')) { page = 'new'; detail = null; return render(); }
        if (b.matches('[data-go-page]')) return go(b.dataset.goPage);
        if (b.matches('[data-back]')) { detail = null; clearTimeout(logTimer); return render(); }
        if (b.matches('[data-install]')) {
          b.disabled = true;
          try { await Akari.api('/api/docker/install', { method: 'POST' }); installing = true; } catch { b.disabled = false; }
          return refresh(true);
        }
        if (b.matches('[data-prune]')) {
          if (!await Akari.ask({ title: t('Aufräumen?'), text: t('Entfernt angehaltene Container, Images ohne Namen und unbenutzte Netzwerke. Volumes bleiben.'), ok: t('Aufräumen') })) return;
          try { const r = await Akari.api('/api/docker/prune', { method: 'POST' }); Akari.notify(`${t('Aufgeräumt')}: ${r.containers} Container, ${r.images} Images, ${Akari.fmtBytes(r.space)}.`); } catch {}
          return refresh(true);
        }
        if (b.matches('[data-gact]')) {
          const ids = st.containers_list.filter(c => c.project === b.dataset.group && (b.dataset.gact === 'start' ? c.state !== 'running' : c.state === 'running')).map(c => c.id);
          b.disabled = true;
          for (const id of ids) await Akari.api(`/api/docker/containers/${id}`, { method: 'POST', json: { action: b.dataset.gact } }).catch(() => {});
          return refresh(true);
        }
        if (b.matches('[data-rmi]')) {
          if (!await Akari.ask({ title: `${b.dataset.name} ${t('entfernen?')}`, text: t('Docker lädt es neu, wenn ein Container es wieder braucht.'), ok: t('Entfernen'), danger: true })) return;
          try { await Akari.api(`/api/docker/images/${b.dataset.rmi}`, { method: 'DELETE' }); } catch {}
          return renderImages();
        }
        if (b.matches('[data-rmv]')) {
          if (!await Akari.ask({ title: `${b.dataset.rmv} ${t('löschen?')}`, text: t('Die Daten in diesem Volume sind danach weg.'), ok: t('Löschen'), danger: true })) return;
          try { await Akari.api(`/api/docker/volumes/${encodeURIComponent(b.dataset.rmv)}`, { method: 'DELETE' }); } catch {}
          return renderVolumes();
        }
        if (b.matches('[data-rmn]')) {
          if (!await Akari.ask({ title: `${b.dataset.name} ${t('löschen?')}`, ok: t('Löschen'), danger: true })) return;
          try { await Akari.api(`/api/docker/networks/${b.dataset.rmn}`, { method: 'DELETE' }); } catch {}
          return renderNetworks();
        }
        if (b.matches('[data-lucent-install]')) {
          b.disabled = true;
          try { await Akari.api('/api/docker/lucent', { method: 'POST' }); } catch { b.disabled = false; }
          return refresh(true);
        }
        if (b.matches('[data-helper-update]')) {
          b.disabled = true;
          try { await Akari.api('/api/docker/lucent/helper', { method: 'POST' }); } catch { b.disabled = false; }
          return refresh(true);
        }
        if (b.matches('[data-lucent-remove]')) {
          if (!await Akari.ask({ title: t('Lucent entfernen?'), text: t('Lucent, seine Tools und der Helfer werden angehalten und entfernt. Die Volumes mit den Daten bleiben; ein neues Einrichten findet sie wieder.'), ok: t('Entfernen'), danger: true })) return;
          try { await Akari.api('/api/docker/lucent', { method: 'DELETE' }); } catch {}
          return refresh(true);
        }
        if (b.matches('[data-lucent-pair]')) {
          const l = st.lucent || {};
          return Akari.open('settings', { page: 'lucent', lucent: { lucent_url: `http://127.0.0.1:${l.port || 8060}`, base_url: l.akari_base || '' } });
        }
        const r = b.closest('[data-cid]');
        if (b.matches('[data-act]')) return act(b.dataset.cid || r?.dataset.cid, b.dataset.act);
        if (b.matches('[data-more]') && r) {
          const c = st.containers_list.find(x => x.id === r.dataset.cid);
          return Akari.menu(e, [
            { label: t('Details und Protokoll'), icon: 'i-info', act: () => { detail = c.id; render(); } },
            c.state === 'running' && { label: t('Pausieren'), icon: 'i-pause', act: () => Akari.api(`/api/docker/containers/${c.id}/pause`, { method: 'POST', json: { paused: true } }).then(() => refresh(true)) },
            c.state === 'paused' && { label: t('Fortsetzen'), icon: 'i-play', act: () => Akari.api(`/api/docker/containers/${c.id}/pause`, { method: 'POST', json: { paused: false } }).then(() => refresh(true)) },
            '-',
            { label: t('Entfernen …'), icon: 'i-trash', danger: true, act: () => act(c.id, 'remove') },
          ].filter(Boolean));
        }
        if (r && !b.closest('button')) { detail = r.dataset.cid; render(); }
      });
      main.addEventListener('keydown', e => { const r = e.target.closest('.dk__row[data-cid]'); if (r && e.key === 'Enter') { detail = r.dataset.cid; render(); } });
      main.addEventListener('input', e => { if (e.target.matches('[data-filter]')) { filter = e.target.value; renderContainers(); } });
      main.addEventListener('change', e => {
        if (e.target.matches('[data-only]')) { onlyRunning = e.target.checked; renderContainers(); }
        if (e.target.matches('[data-follow]') && e.target.checked) loadLog();
      });

      go(page);
      return {
        close: () => { alive = false; clearTimeout(timer); clearTimeout(logTimer); return true; },
        args(a) { if (a?.page) go(a.page); },
      };
    },
  });
})();
