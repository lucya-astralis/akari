/* Dateien: the home folder. Places on the left, the folder on the right,
   actions in the window's bar. Double-click opens: a folder goes in, text
   goes to the editor, anything else downloads. Drop files to upload. */
(() => {
  const ICON = { dir: 'i-folder', image: 'i-image', text: 'i-file', archive: 'i-archive', audio: 'i-media', video: 'i-media', pdf: 'i-file', file: 'i-file' };
  const PLACES = [
    ['', 'Home', 'i-home'], ['Schreibtisch', 'Schreibtisch', 'i-folder'], ['Dokumente', 'Dokumente', 'i-folder'],
    ['Downloads', 'Downloads', 'i-down'], ['Bilder', 'Bilder', 'i-image'], ['.local/share/Trash/files', 'Papierkorb', 'i-trash'],
  ];
  const TRASH = '.local/share/Trash/files';
  const esc = s => s.replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const join = (dir, name) => dir ? `${dir}/${name}` : name;
  const when = t => {
    const d = new Date(t * 1000), now = new Date();
    return d.toDateString() === now.toDateString()
      ? `Heute, ${d.toLocaleTimeString(window.AkariI18n?.locale() || 'de-DE', { hour: '2-digit', minute: '2-digit' })}`
      : d.toLocaleDateString(window.AkariI18n?.locale() || 'de-DE', { day: '2-digit', month: '2-digit', year: 'numeric' });
  };

  Akari.register('files', {
    title: 'Dateien', icon: 'i-drive', art: 'files', multi: true, size: [860, 540], order: 10, desk: true,
    create(win, args) {
      win.body.classList.add('fm');
      win.body.innerHTML = `
        <aside class="fm__side"><nav class="f-nav" data-places aria-label="Orte"></nav></aside>
        <div class="fm__main">
          <div class="fm__bar">
            <button class="f-btn f-btn--ghost f-btn--icon f-btn--sm" data-act="back" aria-label="Zurück"><svg><use href="#i-back"/></svg></button>
            <button class="f-btn f-btn--ghost f-btn--icon f-btn--sm" data-act="up" aria-label="Eine Ebene höher"><svg><use href="#i-up"/></svg></button>
            <nav class="fm__crumbs" data-crumbs aria-label="Pfad" translate="no"></nav>
            <span class="fm__spacer"></span>
            <button class="f-btn f-btn--ghost f-btn--icon f-btn--sm f-tip" data-tip="Ausgeblendete zeigen" data-act="hidden" aria-label="Ausgeblendete zeigen" aria-pressed="false"><svg><use href="#i-eye"/></svg></button>
            <button class="f-btn f-btn--ghost f-btn--icon f-btn--sm f-tip" data-tip="Neu laden" data-act="reload" aria-label="Neu laden"><svg><use href="#i-refresh"/></svg></button>
          </div>
          <div class="fm__head" aria-hidden="true"><span>Name</span><span>Größe</span><span>Geändert</span></div>
          <div class="fm__list" data-list role="listbox" aria-label="Inhalt" tabindex="0" translate="no"></div>
          <div class="fm__foot">
            <span class="f-dim" data-status></span>
            <span class="fm__actions">
              <button class="f-btn f-btn--sm" data-act="rename" disabled><svg><use href="#i-rename"/></svg>Umbenennen</button>
              <button class="f-btn f-btn--sm" data-act="download" disabled><svg><use href="#i-down"/></svg>Laden</button>
              <button class="f-btn f-btn--sm f-btn--danger" data-act="trash" disabled><svg><use href="#i-trash"/></svg><span data-trash-label>Papierkorb</span></button>
              <span class="fm__sep"></span>
              <button class="f-btn f-btn--sm" data-act="mkdir"><svg><use href="#i-folder-plus"/></svg>Ordner</button>
              <button class="f-btn f-btn--sm f-btn--primary" data-act="upload"><svg><use href="#i-up-load"/></svg>Hochladen</button>
              <button class="f-btn f-btn--sm f-btn--danger" data-act="empty" hidden>Papierkorb leeren</button>
            </span>
          </div>
          <input type="file" multiple hidden data-picker>
          <div class="fm__drop" data-drop hidden><span>Zum Hochladen loslassen</span></div>
        </div>`;
      const q = s => win.body.querySelector(s);
      const list = q('[data-list]');
      let path = args.path || '', entries = [], sel = null, showHidden = false, inTrash = false;
      const history = [];

      q('[data-places]').innerHTML = PLACES.map(([p, label, icon]) =>
        `<a class="f-nav__item" href="#" data-place="${esc(p)}"><svg><use href="#${icon}"/></svg>${label}</a>`).join('');

      const render = () => {
        const shown = entries.filter(e => showHidden || !e.hidden);
        list.innerHTML = shown.length ? shown.map(e => `
          <div class="fm__row${e.hidden ? ' is-hidden' : ''}" role="option" aria-selected="${e.name === sel}" data-name="${esc(e.name)}" tabindex="-1">
            <span class="fm__name"><svg class="fm__ic fm__ic--${e.kind}"><use href="#${ICON[e.kind] || 'i-file'}"/></svg><span>${esc(e.name)}</span>${e.link ? '<small>Link</small>' : ''}</span>
            <span class="fm__size">${e.dir ? '' : Akari.fmtBytes(e.size)}</span>
            <span class="fm__date">${when(e.mtime)}</span>
          </div>`).join('')
          : `<div class="fm__empty"><svg><use href="#${inTrash ? 'i-trash' : 'i-folder'}"/></svg><span>${inTrash ? 'Der Papierkorb ist leer.' : 'Dieser Ordner ist leer.'}</span></div>`;
        const dirs = shown.filter(e => e.dir).length;
        q('[data-status]').textContent = `${shown.length} ${shown.length === 1 ? 'Eintrag' : 'Einträge'}${dirs ? `, davon ${dirs} Ordner` : ''}`;
        mark();
      };

      // selection changes only attributes, never rebuilds the rows (a rebuild between two clicks eats the double-click)
      const mark = () => {
        const cut = window.AkariFileClip?.op === 'cut' ? window.AkariFileClip.paths : [];
        list.querySelectorAll('.fm__row').forEach(r => {
          r.setAttribute('aria-selected', r.dataset.name === sel);
          r.classList.toggle('is-cut', cut.includes(join(path, r.dataset.name)));
        });
        const e = entries.find(x => x.name === sel);
        q('[data-act="rename"]').disabled = !e || inTrash;
        q('[data-act="download"]').disabled = !e || e.dir;
        q('[data-act="trash"]').disabled = !e;
        q('[data-trash-label]').textContent = inTrash ? 'Endgültig löschen' : 'Papierkorb';
        q('[data-act="empty"]').hidden = !inTrash || !entries.length;
        q('[data-act="mkdir"]').hidden = q('[data-act="upload"]').hidden = inTrash;
      };

      const crumbs = () => {
        const parts = path ? path.split('/') : [];
        const trashAt = path.startsWith(TRASH) ? TRASH.split('/').length : -1;
        let html = `<button data-go="">Home</button>`, acc = '';
        parts.forEach((p, i) => {
          acc = join(acc, p);
          if (trashAt > 0 && i < trashAt - 1) return;
          const label = i === trashAt - 1 ? 'Papierkorb' : p;
          html += `<svg aria-hidden="true"><use href="#i-chev"/></svg><button data-go="${esc(acc)}">${esc(label)}</button>`;
        });
        q('[data-crumbs]').innerHTML = html;
        win.body.querySelectorAll('[data-place]').forEach(a => a.classList.toggle('is-on', a.dataset.place === path));
        const last = parts.length ? (path === TRASH ? 'Papierkorb' : parts[parts.length - 1]) : 'Home';
        win.setTitle(`Dateien · ${last}`);
      };

      const load = async (to = path, push = true) => {
        try {
          const r = await Akari.api(`/api/fs?path=${encodeURIComponent(to)}`);
          if (push && to !== path) history.push(path);
          path = r.path; entries = r.entries; inTrash = r.trash; sel = null;
          crumbs(); render();
          q('[data-act="back"]').disabled = !history.length;
          q('[data-act="up"]').disabled = !path;
        } catch {}
      };

      const selected = () => entries.find(e => e.name === sel);
      const openEntry = e => {
        if (!e) return;
        if (e.dir) return load(join(path, e.name));
        if (e.kind === 'text' || e.size === 0) return Akari.open('editor', { path: join(path, e.name) });
        download(e);
      };
      const download = e => {
        const a = document.createElement('a');
        a.href = `/api/fs/download?path=${encodeURIComponent(join(path, e.name))}`;
        a.download = e.name;
        document.body.append(a); a.click(); a.remove();
      };

      const act = {
        back: () => history.length && load(history.pop(), false),
        up: () => path && load(path.split('/').slice(0, -1).join('/')),
        reload: () => load(path, false),
        hidden: b => { showHidden = !showHidden; b.setAttribute('aria-pressed', showHidden); b.classList.toggle('is-on', showHidden); render(); },
        rename: async () => {
          const e = selected(); if (!e) return;
          const name = await Akari.ask({ title: 'Umbenennen', label: 'Neuer Name', value: e.name, ok: 'Umbenennen' });
          if (!name || name === e.name) return;
          await Akari.api('/api/fs/rename', { method: 'POST', json: { path: join(path, e.name), name } }).catch(() => {});
          await load(path, false); sel = name; render();
        },
        download: () => { const e = selected(); if (e && !e.dir) download(e); },
        trash: async () => {
          const e = selected(); if (!e) return;
          if (inTrash && !await Akari.ask({ title: `„${e.name}“ endgültig löschen?`, text: 'Das lässt sich nicht rückgängig machen.', ok: 'Löschen', danger: true })) return;
          await Akari.api('/api/fs/trash', { method: 'POST', json: { path: join(path, e.name) } }).catch(() => {});
          if (!inTrash) Akari.notify(`„${e.name}“ liegt im Papierkorb.`);
          load(path, false);
        },
        empty: async () => {
          if (!await Akari.ask({ title: 'Papierkorb leeren?', text: `${entries.length} ${entries.length === 1 ? 'Eintrag wird' : 'Einträge werden'} endgültig gelöscht.`, ok: 'Leeren', danger: true })) return;
          await Akari.api('/api/fs/empty-trash', { method: 'POST' }).catch(() => {});
          load(path, false);
        },
        mkdir: async () => {
          const name = await Akari.ask({ title: 'Neuer Ordner', label: 'Name', value: 'Neuer Ordner', ok: 'Anlegen' });
          if (!name) return;
          const r = await Akari.api('/api/fs/mkdir', { method: 'POST', json: { path: join(path, name) } }).catch(() => null);
          await load(path, false);
          if (r) { sel = r.path.split('/').pop(); render(); }
        },
        upload: () => q('[data-picker]').click(),
        // files on Akari's file clipboard, shared by every Dateien window; the path
        // also goes to the text clipboard, so it can be pasted into a terminal
        copy: () => fileClip('copy'),
        cut: () => fileClip('cut'),
        paste: async () => {
          const c = window.AkariFileClip;
          if (!c || inTrash) return;
          try {
            const r = await Akari.api('/api/fs/paste', { method: 'POST', json: { op: c.op, paths: c.paths, dest: path } });
            if (c.op === 'cut') window.AkariFileClip = null;
            await load(path, false);
            sel = r.done[0] || sel; render();
            Akari.emit('fileclip');
          } catch {}
        },
      };
      const fileClip = op => {
        const e = selected(); if (!e || inTrash) return;
        const p = join(path, e.name);
        window.AkariFileClip = { op, paths: [p], names: [e.name] };
        Akari.clip.set(`~/${p}`);
        Akari.emit('fileclip');
      };
      // what is cut shows faded, in every window
      Akari.on('fileclip', () => mark());
      win.body.addEventListener('click', e => {
        const b = e.target.closest('[data-act]');
        if (b && act[b.dataset.act]) return act[b.dataset.act](b);
        const go = e.target.closest('[data-go]');
        if (go) return load(go.dataset.go);
        const place = e.target.closest('[data-place]');
        if (place) { e.preventDefault(); return load(place.dataset.place); }
        const row = e.target.closest('.fm__row');
        if (row) {
          sel = row.dataset.name; mark(); list.focus();
          if (e.detail === 2) openEntry(entries.find(x => x.name === sel));
        }
        else if (e.target === list) { sel = null; mark(); }
      });
      // right-click: on an entry its actions, on the empty list the folder's
      list.addEventListener('contextmenu', e => {
        const row = e.target.closest('.fm__row');
        if (row) {
          sel = row.dataset.name; mark();
          const en = selected();
          return Akari.menu(e, [
            { label: 'Öffnen', icon: en.dir ? 'i-folder' : 'i-chev', act: () => openEntry(en) },
            !en.dir && { label: 'Öffnen mit Editor', icon: 'i-edit', act: () => Akari.open('editor', { path: join(path, en.name) }) },
            !en.dir && { label: 'Laden', icon: 'i-down', act: () => download(en) },
            '-',
            !inTrash && { label: 'Kopieren', icon: 'i-file', hint: MOD + 'C', act: act.copy },
            !inTrash && { label: 'Ausschneiden', icon: 'i-rename', hint: MOD + 'X', act: act.cut },
            !inTrash && en.dir && window.AkariFileClip && { label: 'Hier hinein einfügen', icon: 'i-down', act: () => pasteInto(en) },
            '-',
            !inTrash && { label: 'Umbenennen', icon: 'i-rename', hint: 'F2', act: act.rename },
            { label: inTrash ? 'Endgültig löschen' : 'Papierkorb', icon: 'i-trash', danger: true, hint: 'Entf', act: act.trash },
          ]);
        }
        if (inTrash) return Akari.menu(e, [{ label: 'Papierkorb leeren', icon: 'i-trash', danger: true, disabled: !entries.length, act: act.empty }]);
        Akari.menu(e, [
          { label: 'Einfügen', icon: 'i-down', hint: MOD + 'V', disabled: !window.AkariFileClip, act: act.paste },
          '-',
          { label: 'Neuer Ordner', icon: 'i-folder-plus', act: act.mkdir },
          { label: 'Neue Textdatei', icon: 'i-edit', act: () => Akari.open('editor', {}, { fresh: true }) },
          { label: 'Hochladen', icon: 'i-up-load', act: act.upload },
          '-',
          { label: showHidden ? 'Ausgeblendete verbergen' : 'Ausgeblendete zeigen', icon: 'i-eye', act: () => act.hidden(q('[data-act="hidden"]')) },
          { label: 'Neu laden', icon: 'i-refresh', act: act.reload },
        ]);
      });
      list.addEventListener('keydown', e => {
        const shown = entries.filter(x => showHidden || !x.hidden);
        const i = shown.findIndex(x => x.name === sel);
        if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
          e.preventDefault();
          const n = shown[Math.max(0, Math.min(shown.length - 1, i + (e.key === 'ArrowDown' ? 1 : -1)))];
          if (n) { sel = n.name; mark(); list.querySelector(`[aria-selected="true"]`)?.scrollIntoView({ block: 'nearest' }); }
        }
        if (e.key === 'Enter') openEntry(selected());
        if (e.key === 'Backspace') act.up();
        if (e.key === 'Delete') act.trash();
        if (e.key === 'F2') act.rename();
        const mod = /Mac/.test(navigator.platform) ? e.metaKey : e.ctrlKey;
        if (mod && !e.shiftKey && !e.altKey) {
          const k = e.key.toLowerCase();
          if (k === 'c') { e.preventDefault(); act.copy(); }
          if (k === 'x') { e.preventDefault(); act.cut(); }
          if (k === 'v') { e.preventDefault(); act.paste(); }
        }
      });
      const MOD = /Mac/.test(navigator.platform) ? '⌘' : '⌃';
      const pasteInto = async en => {
        const c = window.AkariFileClip; if (!c) return;
        try {
          await Akari.api('/api/fs/paste', { method: 'POST', json: { op: c.op, paths: c.paths, dest: join(path, en.name) } });
          if (c.op === 'cut') window.AkariFileClip = null;
          load(path, false); Akari.emit('fileclip');
        } catch {}
      };

      /* upload: picker and drop */
      const send = async files => {
        if (!files.length || inTrash) return;
        const fd = new FormData();
        [...files].forEach(f => fd.append('files', f, f.name));
        q('[data-status]').textContent = `Lade ${files.length} ${files.length === 1 ? 'Datei' : 'Dateien'} hoch …`;
        const r = await Akari.api(`/api/fs/upload?path=${encodeURIComponent(path)}`, { method: 'POST', body: fd }).catch(() => null);
        await load(path, false);
        if (r) Akari.notify(`${r.saved.length} ${r.saved.length === 1 ? 'Datei' : 'Dateien'} hochgeladen.`);
      };
      q('[data-picker]').addEventListener('change', e => { send(e.target.files); e.target.value = ''; });
      const drop = q('[data-drop]'), main = q('.fm__main');
      let depth = 0;
      main.addEventListener('dragenter', e => { if (e.dataTransfer?.types.includes('Files')) { depth++; drop.hidden = inTrash; } });
      main.addEventListener('dragleave', () => { if (--depth <= 0) { depth = 0; drop.hidden = true; } });
      main.addEventListener('dragover', e => { if (e.dataTransfer?.types.includes('Files')) e.preventDefault(); });
      main.addEventListener('drop', e => { e.preventDefault(); depth = 0; drop.hidden = true; send(e.dataTransfer.files); });

      load(path, false);
      return { focus: () => list.focus(), args: a => { if (a?.path !== undefined) load(a.path); } };
    },
  });
})();
