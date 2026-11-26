/* Einstellungen: the desktop's own preferences, plus what the workspace says
   about itself. Account and lifecycle belong to Lucent, not here. */
(() => {
  const $ = (s, el) => el.querySelector(s);
  const $$ = (s, el) => [...el.querySelectorAll(s)];

  const duration = s => {
    const d = Math.floor(s / 86400), h = Math.floor(s / 3600) % 24, m = Math.floor(s / 60) % 60;
    if (d) return `${d} ${d === 1 ? 'Tag' : 'Tagen'}, ${h} h`;
    if (h) return `${h} h ${m} min`;
    return `${m} min`;
  };

  Akari.register('settings', {
    title: 'Einstellungen', icon: 'i-gear', art: 'settings', size: [880, 600], order: 90, desk: true,
    create(win, args) {
      const el = document.getElementById('tpl-settings').content.firstElementChild.cloneNode(true);
      win.body.append(el);
      win.body.classList.add('win__body--settings');
      const narrow = matchMedia('(max-width: 639px)');

      /* pages */
      const go = page => {
        $$('[data-nav] .f-nav__item', el).forEach(a => {
          const on = a.dataset.page === page;
          a.classList.toggle('is-on', on);
          on ? a.setAttribute('aria-current', 'page') : a.removeAttribute('aria-current');
        });
        $$('.page', el).forEach(p => p.hidden = p.dataset.page !== page);
        el.classList.add('is-page');
        $('[data-main]', el).scrollTop = 0;
        if (page === 'workspace') Akari.loadSystem();
        if (page === 'konten') loadAccounts();
        if (page === 'schreibtisch') loadDesks();
        if (page === 'ssh') loadSsh();
        if (page === 'software') loadSoftware();
        if (page === 'konto') fillMe();
        if (page === 'lucent') loadLucent();
        requestAnimationFrame(() => Facet.layout());
      };
      el.addEventListener('click', e => {
        const n = e.target.closest('[data-page]:not(section)');
        if (n) { e.preventDefault(); go(n.dataset.page); }
        if (e.target.closest('[data-back]')) el.classList.remove('is-page');
      });
      const search = $('[data-search]', el);
      search.addEventListener('input', () => {
        const q = search.value.trim().toLowerCase();
        let any = false;
        $$('[data-nav] .f-nav__item', el).forEach(a => {
          const hit = (!a.hasAttribute('data-admin') || Akari.me?.admin) && (!q || (a.textContent + ' ' + a.dataset.keys).toLowerCase().includes(q));
          a.hidden = !hit; any ||= hit;
        });
        $('[data-none]', el).hidden = any;
      });
      search.addEventListener('keydown', e => {
        if (e.key === 'Enter') { const a = $$('[data-nav] .f-nav__item', el).find(x => !x.hidden); if (a) go(a.dataset.page); }
      });

      /* controls ↔ prefs */
      const sync = () => {
        const P = Akari.prefs;
        $$('[data-pref]', el).forEach(i => { i.checked = !!P[i.dataset.pref]; });
        const th = $(`input[name="theme"][value="${P.theme || 'system'}"]`, el); if (th) th.checked = true;
        const dk = $(`input[name="dock"][value="${P.dock}"]`, el); if (dk) dk.checked = true;
        const nv = $(`input[name="nova"][value="${Akari.novaSide()}"]`, el); if (nv) nv.checked = true;
        const nl = $(`input[name="novaLogo"][value="${P.novaLogo || 'none'}"]`, el); if (nl) nl.checked = true;
        const ba = $(`input[name="barAlign"][value="${['left', 'right', 'split'].includes(P.barAlign) ? P.barAlign : 'center'}"]`, el); if (ba) ba.checked = true;
        const bp = $(`input[name="bar"][value="${P.bar === 'top' ? 'top' : 'bottom'}"]`, el); if (bp) bp.checked = true;
        const lg = $(`input[name="lang"][value="${Akari.locale().startsWith('en') ? 'en' : 'de'}"]`, el); if (lg) lg.checked = true;
        $('[data-wall-drop]', el).hidden = !P.wallpaperV;
        const wg = $('[data-pref="widgets"]', el); if (wg) wg.checked = P.widgets !== false;
        const cu = $('[data-pref="cursors"]', el); if (cu) cu.checked = P.cursors !== false;
        // magnification: on unless switched off; strength and reach only while on
        const mg = $('[data-pref="magnify"]', el); if (mg) mg.checked = P.magnify !== false;
        $$('[data-mag-opt]', el).forEach(o => { o.hidden = P.magnify === false; });
        const amount = Math.round((P.magnifyAmount ?? .45) * 100), reach = +(P.magnifyRange || 2.4);
        const ra = $('[data-mag="amount"]', el), rr = $('[data-mag="range"]', el);
        if (ra && document.activeElement !== ra) { ra.value = amount; ra.style.setProperty('--v', `${(amount - 10) / 90 * 100}%`); }
        if (rr && document.activeElement !== rr) { rr.value = reach; rr.style.setProperty('--v', `${(reach - 1) / 3 * 100}%`); }
        $('[data-mag-out="amount"]', el).textContent = `${Akari.t('bis')} ${100 + amount} %`;
        $('[data-mag-out="range"]', el).textContent = `${reach.toLocaleString(Akari.locale(), { maximumFractionDigits: 1 })} ${Akari.t('Symbole zu jeder Seite')}`;
        // with a picture as background, Nova's options mean nothing: they go
        $$('[data-nova-opt]', el).forEach(o => { o.hidden = !!P.wallpaperV; });
        // each widget, on or off
        const W = Akari.desk?.WIDGETS || {}, on = Akari.desk?.enabledWidgets() || [];
        $('[data-widget-list]', el).innerHTML = Object.entries(W).map(([id, w]) => `
          <div class="opt"><span class="opt__txt"><b>${esc(Akari.t(w.title))}</b></span>
            <label class="f-switch"><input type="checkbox" data-widget="${id}"${on.includes(id) ? ' checked' : ''}><i></i><span class="sr">${esc(Akari.t(w.title))}</span></label></div>`).join('');
        $$('[data-swatches] button', el).forEach(b => b.setAttribute('aria-checked', b.dataset.tint === P.tint));
        const hue = $('[data-hue]', el), hin = $('[data-hue-in]', el);
        hue.hidden = P.tint !== 'custom';
        if (document.activeElement !== hin) hin.value = +P.tintH || 0;
        $('[data-tint-name]', el).textContent = $(`[data-swatches] button[data-tint="${P.tint}"]`, el)?.dataset.label || 'Facet · Violett';
        requestAnimationFrame(() => Facet.layout());
      };
      el.addEventListener('change', e => {
        const i = e.target;
        if (i.name === 'theme') return Facet.setTheme(i.value, i.nextElementSibling);
        if (i.name === 'dock') return Akari.set('dock', i.value);
        if (i.name === 'bar') return Akari.set('bar', i.value);
        if (i.name === 'barAlign') return Akari.set('barAlign', i.value);
        if (i.name === 'nova') return Akari.set('nova', i.value);
        if (i.name === 'novaLogo') return Akari.set('novaLogo', i.value);
        if (i.name === 'lang') return window.AkariI18n?.set(i.value);
        if (i.dataset.widget) return i.checked ? Akari.desk?.addWidget(i.dataset.widget) : Akari.desk?.removeWidget(i.dataset.widget);
        if (i.dataset.pref) Akari.set(i.dataset.pref, i.checked);
      });
      // Eigene: a hue to pick; it shows while dragging and is kept when let go
      $('[data-hue-in]', el).addEventListener('input', e => { document.documentElement.style.setProperty('--akari-h', e.target.value); dispatchEvent(new Event('akari:hue')); });
      $('[data-hue-in]', el).addEventListener('change', e => Akari.set('tintH', +e.target.value));
      const sw = $('[data-swatches]', el);
      sw.addEventListener('click', e => {
        const b = e.target.closest('button'); if (!b) return;
        Akari.set('tint', b.dataset.tint);
      });
      sw.addEventListener('keydown', e => {
        if (!['ArrowLeft', 'ArrowRight'].includes(e.key)) return;
        const bs = $$('button', sw), i = bs.indexOf(document.activeElement);
        const n = bs[(i + (e.key === 'ArrowRight' ? 1 : -1) + bs.length) % bs.length];
        n.focus(); n.click(); e.preventDefault();
      });

      /* who is signed in */
      const showMe = me => {
        if (!me) return;
        $$('[data-avatar]', el).forEach(a => Akari.avatar(a, me));
        $('[data-avatar-drop]', el).hidden = !me.avatar;
        $$('[data-name]', el).forEach(n => n.textContent = me.fullname);
        $$('[data-fullname]', el).forEach(n => n.textContent = me.fullname);
        $('[data-acct-note]', el).textContent = `${me.name} · UID ${me.uid}${me.admin ? ` · ${Akari.t('darf Konten verwalten')}` : ''}`;
        $('[data-nav] [data-admin]', el).hidden = !me.admin;
        const n = $('[data-sys="user"]', el); if (n) n.textContent = `${me.fullname} (${me.name}, UID ${me.uid})`;
      };
      const formName = $('[data-form="name"]', el), formPw = $('[data-form="password"]', el);
      const nameDirty = () => {
        const changed = formName.elements.fullname.value.trim() !== (Akari.me?.fullname || '');
        $('button', formName).disabled = !changed || !formName.elements.fullname.value.trim();
        $('[data-state]', formName).textContent = changed ? 'Nicht gesichert' : '';
      };
      const fillMe = () => { if (Akari.me) { formName.elements.fullname.value = Akari.me.fullname; nameDirty(); } };
      formName.addEventListener('input', nameDirty);
      formName.addEventListener('submit', async e => {
        e.preventDefault();
        try {
          await Akari.api('/api/accounts/me', { method: 'PATCH', json: { fullname: formName.elements.fullname.value } });
          await Akari.loadSession(); nameDirty(); Akari.notify('Name gesichert.');
        } catch {}
      });
      formPw.addEventListener('submit', async e => {
        e.preventDefault();
        const f = formPw.elements, rep = $('[data-repeat]', formPw);
        const same = f.new.value === f.new2.value;
        rep.classList.toggle('is-error', !same); $('small', rep).hidden = same;
        if (!same) return;
        try {
          await Akari.api('/api/accounts/me', { method: 'PATCH', json: { old_password: f.old.value, password: f.new.value } });
          formPw.reset(); Akari.notify('Passwort geändert.');
        } catch {}
      });

      /* all accounts (admins) */
      const esc = v => String(v).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
      const toUser = v => v.toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/ß/g, 'ss')
        .split(/\s+/)[0].replace(/[^a-z0-9_-]/g, '').replace(/^[^a-z]+/, '').slice(0, 32);
      const list = $('[data-accounts]', el);
      let known = [];
      const loadAccounts = async () => {
        if (!Akari.me?.admin) return;
        let r; try { r = await Akari.api('/api/accounts'); } catch { return; }
        known = r.accounts;
        list.innerHTML = known.map(a => `
          <div class="acct-row" data-acct="${esc(a.name)}">
            <span class="f-avatar" data-face="${esc(a.name)}">${esc(a.initial)}</span>
            <span class="opt__txt"><b>${esc(a.fullname)}</b><small>${esc(a.name)} · UID ${a.uid}</small>
              <span class="acct-row__tags">${a.admin ? '<span class="f-badge f-badge--acc">Verwaltet</span>' : ''}${a.active ? '<span class="f-badge f-badge--ok">Angemeldet</span>' : ''}${a.name === Akari.me.name ? '<span class="f-badge">Du</span>' : ''}</span></span>
            <span class="acct-row__act">${a.name === Akari.me.name ? '' : `
              <button class="f-btn f-btn--ghost f-btn--sm" data-acct-act="admin">${a.admin ? 'Nicht mehr verwalten' : 'Verwalten lassen'}</button>
              <button class="f-btn f-btn--ghost f-btn--sm" data-acct-act="password">Passwort</button>
              <button class="f-btn f-btn--danger f-btn--sm f-btn--icon" data-acct-act="remove" aria-label="Konto entfernen"><svg><use href="#i-trash"/></svg></button>`}</span>
          </div>`).join('');
        known.forEach(a => Akari.avatar(list.querySelector(`[data-face="${a.name}"]`), a));
      };
      list.addEventListener('click', async e => {
        const b = e.target.closest('[data-acct-act]'); if (!b) return;
        const a = known.find(x => x.name === b.closest('[data-acct]').dataset.acct);
        const path = `/api/accounts/${encodeURIComponent(a.name)}`;
        if (b.dataset.acctAct === 'admin') await Akari.api(path, { method: 'PATCH', json: { admin: !a.admin } }).catch(() => {});
        if (b.dataset.acctAct === 'password') {
          const pw = await Akari.ask({ title: `Neues Passwort für ${a.fullname}`, label: 'Passwort, mindestens 8 Zeichen', value: '', ok: 'Setzen', type: 'password' });
          if (!pw) return;
          try { await Akari.api(path, { method: 'PATCH', json: { password: pw } }); Akari.notify(`Passwort für ${a.name} gesetzt.`); } catch {}
        }
        if (b.dataset.acctAct === 'remove') {
          const ok = await Akari.ask({ title: `${a.fullname} entfernen?`, text: `Das Konto ${a.name}, sein Home und alles darin sind danach weg. Ist es gerade angemeldet, wird es abgemeldet.`, ok: 'Entfernen', danger: true });
          if (!ok) return;
          try { await Akari.api(path, { method: 'DELETE' }); Akari.notify(`${a.name} ist entfernt.`); } catch {}
        }
        loadAccounts();
      });
      const formNew = $('[data-form="new"]', el);
      let userTyped = false;
      formNew.elements.user.addEventListener('input', () => { userTyped = true; });
      formNew.elements.fullname.addEventListener('input', () => { if (!userTyped) formNew.elements.user.value = toUser(formNew.elements.fullname.value); });
      formNew.addEventListener('submit', async e => {
        e.preventDefault();
        const f = formNew.elements, state = $('[data-state]', formNew);
        state.textContent = 'Lege Konto und Home an …';
        try {
          await Akari.api('/api/accounts', { method: 'POST', json: { name: f.user.value, fullname: f.fullname.value, password: f.password.value, admin: f.admin.checked } });
          Akari.notify(`${f.user.value} ist angelegt.`);
          formNew.reset(); userTyped = false; state.textContent = '';
          loadAccounts();
        } catch (err) { state.textContent = err.message; }
      });

      /* desktops of this account */
      const deskBox = $('[data-desks]', el);
      let desks = [];
      const loadDesks = async () => {
        let r; try { r = await Akari.api('/api/desktops'); } catch { return; }
        desks = r.desktops;
        const here = Akari.me?.desktop?.id;
        deskBox.innerHTML = desks.map(d => `
          <div class="acct-row" data-desk="${esc(d.id)}">
            <span class="f-tile"><svg><use href="#i-window"/></svg></span>
            <span class="opt__txt"><b>${esc(d.name)}</b><small>${d.apps.length ? `${esc(d.apps.join(', '))} läuft` : 'Keine App läuft'}</small>
              ${d.id === here ? '<span class="acct-row__tags"><span class="f-badge f-badge--acc">Dieser Desktop</span></span>' : ''}</span>
            <span class="acct-row__act">
              <button class="f-btn f-btn--ghost f-btn--sm" data-desk-act="rename">Umbenennen</button>
              ${d.id === here ? '' : '<button class="f-btn f-btn--danger f-btn--sm f-btn--icon" data-desk-act="remove" aria-label="Desktop entfernen"><svg><use href="#i-trash"/></svg></button>'}
            </span>
          </div>`).join('');
      };
      deskBox.addEventListener('click', async e => {
        const b = e.target.closest('[data-desk-act]'); if (!b) return;
        const d = desks.find(x => x.id === b.closest('[data-desk]').dataset.desk);
        if (b.dataset.deskAct === 'rename') {
          const name = await Akari.ask({ title: 'Desktop umbenennen', label: 'Name', value: d.name, ok: 'Umbenennen' });
          if (!name) return;
          await Akari.api(`/api/desktops/${d.id}`, { method: 'PATCH', json: { name } }).catch(() => {});
          if (d.id === Akari.me?.desktop?.id) {
            await Akari.api('/api/session/desktop', { method: 'POST', json: { id: d.id } }).catch(() => {});
            Akari.loadSession();
          }
        }
        if (b.dataset.deskAct === 'remove') {
          const ok = await Akari.ask({ title: `„${d.name}“ entfernen?`, text: 'Seine Apps werden beendet, sein Firefox-Profil und sein Aussehen gelöscht. Die Dateien im Home bleiben.', ok: 'Entfernen', danger: true });
          if (!ok) return;
          await Akari.api(`/api/desktops/${d.id}`, { method: 'DELETE' }).catch(() => {});
        }
        loadDesks();
      });

      /* magnification: live while the slider moves, with a look at the dock */
      el.addEventListener('input', e => {
        const r = e.target.closest('[data-mag]'); if (!r) return;
        const v = +r.value;
        r.style.setProperty('--v', `${r.dataset.mag === 'amount' ? (v - 10) / 90 * 100 : (v - 1) / 3 * 100}%`);
        Akari.set(r.dataset.mag === 'amount' ? 'magnifyAmount' : 'magnifyRange', r.dataset.mag === 'amount' ? v / 100 : v);
        Akari.previewMagnify?.();
      });

      /* the account picture */
      el.addEventListener('click', async e => {
        if (e.target.closest('[data-avatar-pick]')) {
          const inp = document.createElement('input');
          inp.type = 'file'; inp.accept = 'image/jpeg,image/png,image/webp,image/gif';
          inp.onchange = async () => {
            const f = inp.files[0]; if (!f) return;
            const fd = new FormData(); fd.append('file', f, f.name);
            try { await Akari.api('/api/accounts/me/avatar', { method: 'POST', body: fd }); await Akari.loadSession(); Akari.notify(Akari.t('Bild gesichert.')); } catch {}
          };
          inp.click();
        }
        if (e.target.closest('[data-avatar-drop]')) {
          try { await Akari.api('/api/accounts/me/avatar', { method: 'DELETE' }); await Akari.loadSession(); } catch {}
        }
      });

      /* background picture, arrangement */
      el.addEventListener('click', e => {
        if (e.target.closest('[data-wall-pick]')) Akari.desk?.pickWallpaper();
        if (e.target.closest('[data-wall-drop]')) Akari.desk?.dropWallpaper();
        if (e.target.closest('[data-reset-layout]')) { Akari.set('layout', { icons: {}, widgets: {} }); Akari.set('hiddenIcons', []); Akari.set('widgetsOff', []); }
      });

      /* software: sudo and apt, as on any Debian */
      const loadSoftware = async () => {
        let r; try { r = await Akari.api('/api/software'); } catch { return; }
        const badge = $('[data-sw-badge]', el);
        badge.className = `f-badge ${r.sudo && r.admin ? 'f-badge--ok' : ''}`;
        badge.textContent = Akari.t(r.sudo && r.admin ? 'Verfügbar' : 'Aus');
        $('[data-sw-state]', el).textContent = Akari.t(!r.sudo ? 'sudo ist nicht installiert.'
          : r.admin ? 'Du darfst sudo nutzen, mit deinem Passwort.' : 'Nur Konten, die verwalten, dürfen sudo nutzen.');
        $('[data-sw-howto]', el).hidden = !(r.sudo && r.admin);
        $('[data-sw-count]', el).textContent = r.packages ? Akari.t('{n} Pakete installiert.').replace('{n}', r.packages.toLocaleString()) : '';
      };

      /* lucent: pairing (admins) and linking the own account */
      const luForm = $('[data-form="lucent"]', el);
      let lu = null;
      const loadLucent = async () => {
        try { lu = await Akari.api('/api/lucent'); } catch { return; }
        const p = lu.paired;
        $('[data-lu-paired]', el).hidden = !p;
        $('[data-lu-admin]', el).hidden = !lu.admin;
        luForm.hidden = !!p || !lu.admin;
        $('[data-lu-nonadmin]', el).hidden = !!p || lu.admin;
        $('[data-lu-me]', el).hidden = $('[data-lu-me-label]', el).hidden = !p;
        if (p) {
          const since = new Date(p.since * 1000).toLocaleDateString(window.AkariI18n?.locale() || 'de-DE', { day: 'numeric', month: 'long', year: 'numeric' });
          $('[data-lu-state]', el).textContent = `${p.issuer}, seit ${since}. Akari ist dort als ${p.ui_url} eingetragen.`;
          $('[data-lu-me-state]', el).textContent = lu.me.linked
            ? `Verknüpft mit ${lu.me.email || 'deinem Lucent-Konto'}. Am Anmeldebildschirm: „Mit Lucent anmelden“.`
            : 'Einmal verknüpfen, dann meldest du dich mit deinem Lucent-Konto an. Lucent fragt dich dafür nach der Anmeldung.';
          $('[data-lu-link]', el).textContent = Akari.t(lu.me.linked ? 'Lösen' : 'Verknüpfen');
        }
        if (!luForm.elements.ui_url.value) luForm.elements.ui_url.value = location.origin;
        requestAnimationFrame(() => Facet.layout());
      };
      luForm.addEventListener('submit', async e => {
        e.preventDefault();
        const st = $('[data-state]', luForm), f = luForm.elements;
        st.textContent = Akari.t('Kopple …');
        try {
          await Akari.api('/api/lucent/pair', { method: 'POST', json: { lucent_url: f.lucent_url.value, code: f.code.value, ui_url: f.ui_url.value, base_url: f.base_url.value || null } });
          st.textContent = ''; f.code.value = '';
          Akari.notify('Mit Lucent gekoppelt.');
          loadLucent();
        } catch (err) { st.textContent = err.message; }
      });
      $('[data-lu-leave]', el).addEventListener('click', async () => {
        const ok = await Akari.ask({ title: 'Von Lucent entkoppeln?', text: 'Lucent sieht Akari danach nicht mehr, und niemand meldet sich mehr mit Lucent an. Verknüpfte Konten bleiben verknüpft, für ein neues Koppeln.', ok: 'Entkoppeln', danger: true });
        if (!ok) return;
        await Akari.api('/api/lucent', { method: 'DELETE' }).catch(() => {});
        loadLucent();
      });
      $('[data-lu-link]', el).addEventListener('click', async () => {
        if (!lu?.me.linked) { location.href = '/auth/lucent?link=1'; return; }
        await Akari.api('/api/lucent/link', { method: 'DELETE' }).catch(() => {});
        Akari.notify('Von Lucent gelöst.');
        loadLucent();
      });

      /* ssh */
      const sshOn = $('[data-ssh-on]', el), sshPw = $('[data-ssh-pw]', el), keyBox = $('[data-ssh-keys]', el);
      const loadSsh = async () => {
        let r, k;
        try { [r, k] = await Promise.all([Akari.api('/api/ssh'), Akari.api('/api/ssh/keys')]); } catch { return; }
        sshOn.checked = r.enabled;
        $('[data-ssh-admin]', el).hidden = !r.admin;
        $('[data-ssh-state]', el).textContent = r.running ? 'Läuft. Anmelden geht mit Schlüssel' + (r.me.password ? ' oder Passwort.' : '.')
          : r.enabled ? 'Eingeschaltet, startet aber nicht. Mehr mit: journalctl -u ssh'
          : r.admin ? 'Aus. Einschalten gilt für alle Konten.' : 'Aus. Ein Konto, das verwaltet, kann es einschalten.';
        $('[data-ssh-connect]', el).hidden = !r.running;
        const [host, port] = (r.public || `${location.hostname}:${r.port}`).split(':');
        $('[data-ssh-cmd]', el).textContent = port === '22' ? `ssh ${r.me.name}@${host}` : `ssh -p ${port} ${r.me.name}@${host}`;
        $('[data-ssh-fp]', el).textContent = r.fingerprints.length ? `Beim ersten Mal fragt ssh nach dem Fingerabdruck. Er muss so lauten: ${r.fingerprints.join(' · ')}` : '';
        sshPw.checked = r.me.password;
        keyBox.innerHTML = k.keys.length ? k.keys.map(key => `
          <div class="acct-row">
            <span class="f-tile"><svg><use href="#i-term"/></svg></span>
            <span class="opt__txt"><b>${esc(key.comment || key.type)}</b><small class="ssh-fp">${esc(key.type)} · ${esc(key.fingerprint)}</small></span>
            <span class="acct-row__act"><button class="f-btn f-btn--danger f-btn--sm f-btn--icon" data-key="${esc(key.fingerprint)}" aria-label="Schlüssel entfernen"><svg><use href="#i-trash"/></svg></button></span>
          </div>`).join('') : '<div class="opt"><span class="opt__txt"><small>Noch kein Schlüssel. Ohne Schlüssel (und ohne Passwort) kommt niemand per SSH in dieses Konto.</small></span></div>';
      };
      sshOn.addEventListener('change', async () => {
        try { await Akari.api('/api/ssh', { method: 'PUT', json: { enabled: sshOn.checked } }); Akari.notify(sshOn.checked ? 'SSH ist an.' : 'SSH ist aus.'); } catch {}
        loadSsh();
      });
      sshPw.addEventListener('change', async () => {
        let password = null;
        if (sshPw.checked) {
          password = await Akari.ask({ title: 'Passwort über SSH erlauben', text: 'Gib zur Bestätigung dein Passwort ein.', label: 'Passwort', value: '', ok: 'Erlauben', type: 'password' });
          if (!password) { sshPw.checked = false; return; }
        }
        try { await Akari.api('/api/ssh/password', { method: 'POST', json: { allow: sshPw.checked, password } }); } catch {}
        loadSsh();
      });
      keyBox.addEventListener('click', async e => {
        const b = e.target.closest('[data-key]'); if (!b) return;
        const ok = await Akari.ask({ title: 'Schlüssel entfernen?', text: 'Wer nur diesen Schlüssel hat, kommt danach nicht mehr per SSH herein.', ok: 'Entfernen', danger: true });
        if (!ok) return;
        await Akari.api(`/api/ssh/keys/${encodeURIComponent(b.dataset.key)}`, { method: 'DELETE' }).catch(() => {});
        loadSsh();
      });
      const formKey = $('[data-form="sshkey"]', el);
      formKey.addEventListener('submit', async e => {
        e.preventDefault();
        const state = $('[data-state]', formKey);
        try {
          await Akari.api('/api/ssh/keys', { method: 'POST', json: { key: formKey.elements.key.value } });
          formKey.reset(); state.textContent = ''; Akari.notify('Schlüssel hinzugefügt.');
          loadSsh();
        } catch (err) { state.textContent = err.message; }
      });

      /* what the workspace says */
      const show = s => {
        if (!s) return;
        const set = (k, v) => { const n = $(`[data-sys="${k}"]`, el); if (n) n.textContent = v; };
        set('about-line', `Version ${s.version} · Rechner ${s.hostname}`);
        set('osname', s.os);
        set('version', s.version);
        set('os', s.os);
        set('kernel', `Kernel ${s.kernel}, vom Rechner darunter`);
        set('home', `${Akari.fmtBytes(s.home_bytes)} in ${s.home}`);
        set('disk', `${Akari.fmtBytes(s.disk.used)} von ${Akari.fmtBytes(s.disk.total)} belegt`);
        if (s.memory?.total) set('memory', `${Akari.fmtBytes(s.memory.total - s.memory.available)} von ${Akari.fmtBytes(s.memory.total)} belegt`);
        set('uptime', duration(s.uptime));
        set('processes', s.processes.toLocaleString(window.AkariI18n?.locale() || 'de-DE'));
        set('apps', s.apps.map(a => a.title).join(', ') || 'keine');
        set('managed', s.managed_by || 'Noch nicht mit Lucent gekoppelt');
        Akari.api('/api/lucent', { quiet: true }).then(r => { if (r.paired) set('managed', `Lucent, ${r.paired.issuer}`); }).catch(() => {});
        const meter = (k, v) => { const m = $(`[data-sys-meter="${k}"]`, el); if (m) m.style.setProperty('--v', `${Math.max(1, Math.round(v * 100))}%`); };
        meter('disk', s.disk.used / s.disk.total);
        if (s.memory?.total) meter('memory', 1 - s.memory.available / s.memory.total);
      };
      Akari.on('system', show);
      Akari.on('session', showMe);
      showMe(Akari.me);
      Akari.on('prefs', sync);
      show(Akari.system);
      sync();
      if (!narrow.matches || args.page) go(args.page || 'darstellung');

      return { args(a) { if (a?.page) go(a.page); } };
    },
  });
})();
