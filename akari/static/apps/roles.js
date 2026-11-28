/* Server-Manager: what this machine is for, in roles that are added and taken away as a whole.

   The machine at a glance, then its roles: each with what it brings, its
   services and ports, the app that manages it; the roles that can be added;
   and, greyed, the ones still to come. Adding and taking away runs apt in
   akarid's unit (roles.py, host.py); its log shows while it works. Everyone
   sees, accounts that manage change. */
(() => {
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const t = s => Akari.t(s);
  const dot = a => a === 'active' ? 'is-ok' : a === 'failed' ? 'is-err' : ['activating', 'deactivating', 'reloading'].includes(a) ? 'is-warn' : '';

  Akari.register('roles', {
    title: 'Server-Manager', icon: 'i-box', art: 'roles', size: [920, 640], order: 71, dock: false,
    create(win) {
      win.body.classList.add('rm');
      let data = null, sum = null, timer = null, alive = true;

      const load = async () => {
        clearTimeout(timer);
        if (!alive) return;
        try { [data, sum] = await Promise.all([Akari.api('/api/roles', { quiet: true }), Akari.api('/api/host/summary', { quiet: true }).catch(() => null)]); } catch { data = null; }
        draw();
        const busy = data?.apt?.running;
        timer = setTimeout(load, busy ? 2000 : 10000);
      };

      const card = r => {
        const here = r.state === 'installed', busy = r.state === 'adding' || r.state === 'removing', soon = r.state === 'soon';
        const anyBusy = !!data.apt?.running;
        const acts = soon ? `<span class="f-badge">${t('bald')}</span>`
          : busy ? `<span class="dk__spin" aria-hidden="true"></span><span class="f-dim">${t(r.state === 'adding' ? 'wird hinzugefügt …' : 'wird entfernt …')}</span>`
          : !data.admin ? ''
          : here ? `${r.app ? `<button class="f-btn f-btn--sm" data-open-role="${esc(r.app)}">${t('Öffnen')}</button>` : ''}<button class="f-btn f-btn--sm f-btn--ghost" data-role="${r.id}" data-act="remove" ${anyBusy ? 'disabled' : ''}>${t('Entfernen')}</button>`
          : `<button class="f-btn f-btn--sm f-btn--primary" data-role="${r.id}" data-act="add" ${anyBusy ? 'disabled' : ''}><svg><use href="#i-plus"/></svg>${t('Hinzufügen')}</button>`;
        return `<div class="rm__role${soon ? ' is-soon' : ''}${here ? ' is-here' : ''}">
          <svg class="rm__art"><use href="#${esc(r.icon)}"/></svg>
          <div class="rm__txt"><b>${esc(t(r.name))}</b><small>${esc(t(r.summary))}</small>
            ${here && r.services?.length ? `<span class="rm__svcs">${r.services.map(s => `<span class="rm__svc" translate="no"><i class="dk__dot ${dot(s.active)}"></i>${esc(s.name.replace(/\.service$/, ''))}</span>`).join('')}</span>` : ''}
            ${here && r.ports?.length ? `<span class="rm__ports" translate="no">${r.ports.map(p => `<code>${esc(p)}</code>`).join('')}</span>` : ''}
            ${here && r.adopted ? `<span class="f-dim rm__note">${t('Schon von Hand eingerichtet: als Rolle übernommen.')}</span>` : ''}
          </div>
          <div class="rm__acts">${acts}</div></div>`;
      };

      const draw = () => {
        if (!data) { win.body.innerHTML = `<div class="dk__empty"><p>${t('Akari antwortet nicht.')}</p></div>`; return; }
        const here = data.roles.filter(r => ['installed', 'removing'].includes(r.state));
        const add = data.roles.filter(r => ['absent', 'adding'].includes(r.state));
        const soon = data.roles.filter(r => r.state === 'soon');
        const apt = data.apt || {}, failed = apt.last && !apt.last.ok && !apt.running && String(apt.last.job).startsWith('role:');
        const keepScroll = win.body.scrollTop;
        win.body.innerHTML = `
          <header class="rm__head"><div><h2 class="f-h2">${t('Server-Manager')}</h2><p class="f-dim">${t('Wofür dieser Rechner da ist: Rollen, die man als Ganzes hinzufügt und wieder entfernt.')}</p></div></header>
          ${sum ? `<dl class="f-metrics f-metrics--grid rm__sum grp">
            <div class="f-metric"><dt>${t('Rechner')}</dt><dd class="f-metric__value f-metric__value--plain" translate="no">${esc(Akari.system?.hostname || '–')}</dd></div>
            <div class="f-metric"><dt>${t('Last')}</dt><dd class="f-metric__value f-metric__value--plain">${sum.load ? sum.load[0].toLocaleString(Akari.locale(), { maximumFractionDigits: 2 }) : '–'}</dd><dd class="f-metric__note">${sum.cores} ${t(sum.cores === 1 ? 'Kern' : 'Kerne')}</dd></div>
            <div class="f-metric"><dt>${t('Speicher')}</dt><dd class="f-metric__value f-metric__value--plain">${sum.mem ? `${Math.round(sum.mem.used / sum.mem.total * 100)} %` : '–'}</dd></div>
            <div class="f-metric"><dt>${t('Platte')}</dt><dd class="f-metric__value f-metric__value--plain">${sum.disk ? `${Math.round(sum.disk.used / sum.disk.total * 100)} %` : '–'}</dd></div>
          </dl>` : ''}
          ${(apt.running && String(apt.running).startsWith('role:')) || failed ? `<div class="grp rm__apt"><div class="opt"><span class="opt__txt"><b>${t(failed ? 'Das hat nicht geklappt.' : 'apt arbeitet')}</b><small>${t(failed ? 'Das Protokoll steht unten.' : 'Du kannst das Fenster schließen, es läuft weiter.')}</small></span></div>
            <pre class="up__log">${esc((apt.log || []).join('\n'))}</pre></div>` : ''}
          <span class="f-label grp__label">${t('Rollen auf diesem Rechner')}</span>
          <div class="rm__list">${here.map(card).join('') || `<p class="f-dim rm__none">${t('Noch keine. Unten lassen sich welche hinzufügen.')}</p>`}</div>
          ${add.length ? `<span class="f-label grp__label">${t('Rollen hinzufügen')}</span><div class="rm__list">${add.map(card).join('')}</div>` : ''}
          ${soon.length ? `<span class="f-label grp__label">${t('Bald')}</span><div class="rm__list">${soon.map(card).join('')}</div>` : ''}
          ${data.admin ? '' : `<p class="f-dim rm__none">${t('Rollen hinzufügen und entfernen dürfen Konten, die verwalten.')}</p>`}`;
        win.body.scrollTop = keepScroll;
      };

      win.body.addEventListener('click', async e => {
        const o = e.target.closest('[data-open-role]'); if (o) return Akari.open(o.dataset.openRole);
        const b = e.target.closest('[data-role]'); if (!b) return;
        const r = data.roles.find(x => x.id === b.dataset.role), act = b.dataset.act;
        const ok = await Akari.ask(act === 'add'
          ? { title: `${t(r.name)} ${t('hinzufügen?')}`, text: `${t('apt installiert')}: ${r.packages.join(', ')}.`, ok: t('Hinzufügen') }
          : { title: `${t(r.name)} ${t('entfernen?')}`, text: t(r.remove_note || 'Die Pakete der Rolle werden entfernt. Daten bleiben.'), ok: t('Entfernen'), danger: true });
        if (!ok) return;
        b.disabled = true;
        try { await Akari.api(`/api/roles/${r.id}`, { method: 'POST', json: { action: act } }); } catch {}
        load();
      });

      load();
      return { close: () => { alive = false; clearTimeout(timer); return true; } };
    },
  });
})();
