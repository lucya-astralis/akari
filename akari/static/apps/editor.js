/* Editor: plain text files in the home folder. Ctrl/⌘+S saves; closing with
   unsaved changes asks first. */
(() => {
  Akari.register('editor', {
    title: 'Editor', icon: 'i-edit', art: 'editor', multi: true, size: [720, 520], order: 30, dock: true,
    create(win, args) {
      win.body.classList.add('ed');
      win.body.innerHTML = `
        <textarea class="ed__text" spellcheck="false" aria-label="Text"></textarea>
        <div class="ed__foot">
          <span class="f-dim ed__path" data-path translate="no">Neue Datei</span>
          <span class="f-dim" data-state></span>
          <button class="f-btn f-btn--sm f-btn--primary" data-save><svg><use href="#i-save"/></svg>Sichern</button>
        </div>`;
      const ta = win.body.querySelector('textarea');
      const state = win.body.querySelector('[data-state]');
      let path = args.path || null, saved = '', busy = false;

      const name = () => path ? path.split('/').pop() : 'Unbenannt';
      const dirty = () => ta.value !== saved;
      const show = () => {
        win.setTitle(`${dirty() ? '● ' : ''}${name()}`);
        win.body.querySelector('[data-path]').textContent = path ? `~/${path}` : 'Neue Datei';
        state.textContent = dirty() ? 'Nicht gesichert' : (path ? 'Gesichert' : '');
      };

      const save = async () => {
        if (busy) return;
        if (!path) {
          const p = await Akari.ask({ title: 'Sichern unter', label: 'Pfad im Home-Verzeichnis', value: 'Dokumente/Unbenannt.txt', ok: 'Sichern' });
          if (!p) return false;
          path = p.replace(/^~?\/+/, '');
        }
        busy = true;
        try {
          await Akari.api('/api/fs/text', { method: 'PUT', json: { path, text: ta.value } });
          saved = ta.value;
          show();
          Akari.recent(path);
          return true;
        } catch { return false; }
        finally { busy = false; }
      };

      if (path) {
        ta.disabled = true;
        state.textContent = 'Lädt …';
        Akari.api(`/api/fs/text?path=${encodeURIComponent(path)}`).then(r => {
          ta.value = saved = r.text; path = r.path; ta.disabled = false; show(); ta.focus();
          Akari.recent(path);
        }).catch(() => win.close());
      }
      show();

      ta.addEventListener('input', show);
      ta.addEventListener('keydown', e => {
        if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 's') { e.preventDefault(); save(); }
        if (e.key === 'Tab' && !e.shiftKey) { e.preventDefault(); ta.setRangeText('    ', ta.selectionStart, ta.selectionEnd, 'end'); show(); }
      });
      win.body.querySelector('[data-save]').addEventListener('click', save);

      return {
        dirty,
        focus: () => ta.focus(),
        close: async () => {
          if (!dirty()) return true;
          const keep = await Akari.ask({ title: `„${name()}“ ist nicht gesichert.`, text: 'Schließen verwirft die Änderungen.', ok: 'Verwerfen', danger: true });
          return keep;
        },
      };
    },
  });
})();
