/* Aktivität (the task manager) and Auslastung (what the machine is doing).
   Both read /api/procs and /api/stats from the session agent. Every process
   in the container is listed; only your own can be ended. */
(() => {
  const esc = s => String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const age = s => s < 60 ? `${s} s` : s < 3600 ? `${Math.floor(s / 60)} min` : s < 86400 ? `${Math.floor(s / 3600)} h` : `${Math.floor(s / 86400)} d`;
  const STATES = { R: 'läuft', S: 'wartet', D: 'wartet (E/A)', Z: 'Zombie', T: 'angehalten', I: 'ruht' };

  Akari.register('tasks', {
    title: 'Aktivität', icon: 'i-pulse', art: 'tasks', size: [900, 560], order: 60, dock: false,
    create(win) {
      win.body.classList.add('tm');
      win.body.innerHTML = `
        <div class="tm__bar">
          <label class="f-search"><svg><use href="#i-search"/></svg><input class="f-input" data-q placeholder="Prozesse suchen" aria-label="Prozesse suchen" autocomplete="off"></label>
          <div class="f-seg" role="radiogroup" aria-label="Welche Prozesse">
            <span class="f-seg__thumb"></span>
            <input type="radio" name="tm-who-${win.el.dataset.n || ''}" id="tmw-mine" value="mine" checked><label for="tmw-mine">Meine</label>
            <input type="radio" name="tm-who-${win.el.dataset.n || ''}" id="tmw-all" value="all"><label for="tmw-all">Alle</label>
          </div>
          <span class="tm__spacer"></span>
          <button class="f-btn f-btn--sm f-btn--danger" data-end disabled><svg><use href="#i-x"/></svg>Beenden</button>
        </div>
        <div class="tm__table" role="grid" translate="no">
          <div class="tm__head" role="row">
            <button data-sort="name">Name</button><button data-sort="pid">PID</button><button data-sort="user">Benutzer</button>
            <button data-sort="cpu">CPU</button><button data-sort="rss">Speicher</button><button data-sort="age">Läuft seit</button>
          </div>
          <div class="tm__rows" data-rows></div>
        </div>
        <div class="tm__foot f-dim" data-foot></div>`;
      const q = win.body.querySelector('[data-q]'), rows = win.body.querySelector('[data-rows]');
      let data = [], sel = null, sort = 'cpu', dir = -1, who = 'mine', timer;

      const render = () => {
        const term = q.value.trim().toLowerCase();
        let list = data.filter(p => (who === 'all' || p.mine) && (!term || p.name.toLowerCase().includes(term) || p.cmd.toLowerCase().includes(term) || String(p.pid) === term));
        list.sort((a, b) => (a[sort] > b[sort] ? 1 : a[sort] < b[sort] ? -1 : 0) * dir);
        rows.innerHTML = list.map(p => `
          <div class="tm__row${p.pid === sel ? ' is-sel' : ''}${p.mine ? '' : ' is-other'}" role="row" data-pid="${p.pid}" title="${esc(p.cmd)}">
            <span class="tm__name"><b>${esc(p.name)}</b><small>${esc(p.cmd)}</small></span>
            <span>${p.pid}</span><span>${esc(p.user)}</span>
            <span class="tm__num${p.cpu > 50 ? ' is-hot' : ''}">${p.cpu.toFixed(1)} %</span>
            <span class="tm__num">${Akari.fmtBytes(p.rss)}</span><span class="tm__num">${age(p.age)}</span>
          </div>`).join('');
        const mine = data.filter(p => p.mine);
        win.body.querySelector('[data-foot]').textContent =
          `${data.length} Prozesse · ${mine.length} von dir · CPU ${data.reduce((s, p) => s + p.cpu, 0).toFixed(0)} %`;
        const p = data.find(x => x.pid === sel);
        win.body.querySelector('[data-end]').disabled = !p || !p.mine;
        win.body.querySelectorAll('.tm__head button').forEach(b => b.classList.toggle('is-sort', b.dataset.sort === sort));
      };
      const load = async () => {
        clearTimeout(timer);
        try { data = (await Akari.api('/api/procs', { quiet: true })).procs; render(); } catch {}
        timer = setTimeout(load, 2000);
      };
      const end = async (pid, sig = 'TERM') => {
        const p = data.find(x => x.pid === pid); if (!p) return;
        const ok = await Akari.ask({ title: `${p.name} beenden?`, text: `PID ${p.pid}. Nicht gesicherte Arbeit darin geht verloren.`, ok: 'Beenden', danger: true });
        if (!ok) return;
        try { await Akari.api(`/api/procs/${pid}/signal`, { method: 'POST', json: { sig } }); Akari.notify(`${p.name} beendet.`); } catch {}
        load();
      };

      q.addEventListener('input', render);
      win.body.addEventListener('change', e => { if (e.target.name?.startsWith('tm-who')) { who = e.target.value; render(); } });
      win.body.querySelector('.tm__head').addEventListener('click', e => {
        const b = e.target.closest('[data-sort]'); if (!b) return;
        dir = sort === b.dataset.sort ? -dir : (['name', 'user'].includes(b.dataset.sort) ? 1 : -1);
        sort = b.dataset.sort; render();
      });
      rows.addEventListener('click', e => { const r = e.target.closest('[data-pid]'); if (r) { sel = +r.dataset.pid; render(); } });
      rows.addEventListener('contextmenu', e => {
        const r = e.target.closest('[data-pid]'); if (!r) return;
        sel = +r.dataset.pid; render();
        const p = data.find(x => x.pid === sel);
        Akari.menu(e, [
          { label: 'Beenden', icon: 'i-x', disabled: !p.mine, act: () => end(p.pid) },
          { label: 'Sofort beenden (KILL)', icon: 'i-x', danger: true, disabled: !p.mine, act: () => end(p.pid, 'KILL') },
          '-',
          { label: 'Anhalten', icon: 'i-min', disabled: !p.mine || p.state === 'T', act: () => Akari.api(`/api/procs/${p.pid}/signal`, { method: 'POST', json: { sig: 'STOP' } }).then(load) },
          { label: 'Fortsetzen', icon: 'i-chev', disabled: !p.mine || p.state !== 'T', act: () => Akari.api(`/api/procs/${p.pid}/signal`, { method: 'POST', json: { sig: 'CONT' } }).then(load) },
        ]);
      });
      win.body.querySelector('[data-end]').addEventListener('click', () => end(sel));
      load();
      requestAnimationFrame(() => Facet.layout());
      return { close: () => { clearTimeout(timer); return true; }, focus: () => q.focus() };
    },
  });

  /* ---------- Auslastung ---------- */
  const N = 60;   // two minutes at one sample every two seconds
  const spark = (vals, max) => vals.map((v, i) => `${i ? 'L' : 'M'}${(i / (N - 1) * 100).toFixed(2)},${(40 - Math.min(1, v / max) * 38 - 1).toFixed(2)}`).join('');
  const area = d => d ? `${d}L100,40L${(100 - (d.split('L').length - 1) / (N - 1) * 100).toFixed(2)},40Z` : '';

  Akari.register('monitor', {
    title: 'Auslastung', icon: 'i-cpu', art: 'monitor', size: [820, 600], order: 61, dock: false,
    create(win) {
      win.body.classList.add('mon');
      win.body.innerHTML = `
        <div class="mon__grid">
          <section class="mon__card mon__card--wide"><header><b>CPU</b><span data-v="cpu">–</span></header>
            <svg class="mon__chart" viewBox="0 0 100 40" preserveAspectRatio="none"><path class="mon__area" data-a="cpu"/><path class="mon__line" data-l="cpu"/></svg>
            <div class="mon__cores" data-cores></div></section>
          <section class="mon__card"><header><b>Speicher</b><span data-v="mem">–</span></header>
            <svg class="mon__chart" viewBox="0 0 100 40" preserveAspectRatio="none"><path class="mon__area mon--2" data-a="mem"/><path class="mon__line mon--2" data-l="mem"/></svg>
            <div class="f-meter"><b data-m="mem"></b></div><small class="f-dim" data-n="swap"></small></section>
          <section class="mon__card"><header><b>Netz</b><span data-v="net">–</span></header>
            <svg class="mon__chart" viewBox="0 0 100 40" preserveAspectRatio="none"><path class="mon__line mon--3" data-l="rx"/><path class="mon__line mon--4" data-l="tx"/></svg>
            <small class="f-dim"><span class="mon__key mon--3"></span>empfangen · <span class="mon__key mon--4"></span>gesendet</small></section>
          <section class="mon__card"><header><b>Datenträger</b><span data-v="disk">–</span></header>
            <div class="f-meter"><b data-m="disk"></b></div><small class="f-dim">Das Volume, auf dem die Homes liegen.</small></section>
          <section class="mon__card"><header><b>System</b></header>
            <dl class="mon__kv"><dt>Last (1/5/15 min)</dt><dd data-v="load">–</dd><dt>Prozesse</dt><dd data-v="procs">–</dd><dt>Läuft seit</dt><dd data-v="up">–</dd></dl></section>
        </div>
        <p class="mon__note f-dim">Die Werte sind die des ganzen Rechners, geteilt mit allen Konten darauf.</p>`;
      const h = { cpu: [], mem: [], rx: [], tx: [] };
      const q = s => win.body.querySelector(s);
      let timer;
      const load = async () => {
        clearTimeout(timer);
        try {
          const s = await Akari.api('/api/stats', { quiet: true });
          const push = (k, v) => { h[k].push(v); if (h[k].length > N) h[k].shift(); };
          push('cpu', s.cpu); push('mem', s.mem.used / s.mem.total * 100); push('rx', s.net.rx); push('tx', s.net.tx);
          const netMax = Math.max(1024, ...h.rx, ...h.tx);
          for (const k of ['cpu', 'mem']) {
            const d = spark(h[k], 100);
            q(`[data-l="${k}"]`).setAttribute('d', d);
            q(`[data-a="${k}"]`).setAttribute('d', area(d));
          }
          q('[data-l="rx"]').setAttribute('d', spark(h.rx, netMax));
          q('[data-l="tx"]').setAttribute('d', spark(h.tx, netMax));
          q('[data-v="cpu"]').textContent = `${s.cpu.toFixed(1)} % · ${s.cores.length} Kerne`;
          q('[data-cores]').innerHTML = s.cores.map((c, i) => `<span title="Kern ${i + 1}: ${c} %"><i style="--v:${c}%"></i></span>`).join('');
          q('[data-v="mem"]').textContent = `${Akari.fmtBytes(s.mem.used)} von ${Akari.fmtBytes(s.mem.total)}`;
          q('[data-m="mem"]').style.setProperty('--v', `${(s.mem.used / s.mem.total * 100).toFixed(1)}%`);
          q('[data-n="swap"]').textContent = s.mem.swap_total ? `Auslagerung: ${Akari.fmtBytes(s.mem.swap_used)} von ${Akari.fmtBytes(s.mem.swap_total)}` : '';
          q('[data-v="net"]').textContent = `↓ ${Akari.fmtBytes(s.net.rx)}/s · ↑ ${Akari.fmtBytes(s.net.tx)}/s`;
          q('[data-v="disk"]').textContent = `${Akari.fmtBytes(s.disk.used)} von ${Akari.fmtBytes(s.disk.total)}`;
          q('[data-m="disk"]').style.setProperty('--v', `${(s.disk.used / s.disk.total * 100).toFixed(1)}%`);
          q('[data-v="load"]').textContent = s.load.map(v => v.toFixed(2)).join(' · ');
          q('[data-v="procs"]').textContent = s.procs;
          q('[data-v="up"]').textContent = age(s.uptime);
        } catch {}
        timer = setTimeout(load, 2000);
      };
      load();
      return { close: () => { clearTimeout(timer); return true; } };
    },
  });
})();
