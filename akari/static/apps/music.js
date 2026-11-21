/* Musik: a small audio player, for the music in one's home and on a Subsonic server.

   Lokal is ~/Musik (all the way down) and the loose audio files in ~/Downloads
   and ~/Schreibtisch (/api/audio/library). Server is a Subsonic server
   (Navidrome, Airsonic, Gonic …) the agent talks to (/api/audio/subsonic/…):
   the browser may only reach Akari, and the agent keeps no password.

   The sound plays here in the browser, so unlike a Linux app it is heard.
   What plays shows in the taskbar and the control centre (Akari.mediaLocal)
   and answers the computer's media keys (Media Session). Closing the window
   stops it; minimising keeps it playing. */
(() => {
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const time = s => !Number.isFinite(s) ? '0:00' : `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`;
  // a colour of its own for every album (or artist, or title): the cover when the file has none
  const hue = s => { let h = 0; for (const c of String(s || '')) h = (h * 31 + c.charCodeAt(0)) % 360; return h; };
  const fromServer = t => t?.source === 'subsonic';
  const src = t => (fromServer(t) ? `/api/audio/subsonic/stream?id=${encodeURIComponent(t.id)}` : `/api/audio/stream?path=${encodeURIComponent(t.path)}`);
  const coverUrl = t => (!t?.picture ? null
    : fromServer(t) ? `/api/audio/subsonic/cover?id=${encodeURIComponent(t.cover)}` : `/api/audio/cover?path=${encodeURIComponent(t.path)}`);
  const sub = t => [t.artist, t.album].filter(Boolean).join(' · ') || t.folder || 'Unbekannt';
  const tint = t => hue(t?.album || t?.artist || t?.title);

  Akari.register('music', {
    title: 'Musik', icon: 'i-music', art: 'music', multi: false, size: [440, 660], order: 35, dock: true,
    keywords: ['audio', 'mp3', 'player', 'lieder', 'songs', 'musik', 'subsonic', 'navidrome'],
    create(win, args) {
      win.body.classList.add('mu');
      win.body.innerHTML = `
        <section class="mu__now" aria-label="Läuft gerade">
          <div class="mu__art is-empty" data-art><img alt="" hidden draggable="false"><svg><use href="#i-music"/></svg></div>
          <div class="mu__meta"><b data-title translate="no">Nichts ausgewählt</b><small data-sub translate="no">Wähle unten einen Titel.</small></div>
          <div class="mu__seek">
            <input type="range" class="range mu__bar" min="0" max="1000" value="0" step="1" data-seek aria-label="Position" disabled>
            <span class="mu__times"><time data-cur>0:00</time><time data-dur>0:00</time></span>
          </div>
          <div class="mu__ctl">
            <button class="mu__btn f-tip" data-act="shuffle" data-tip="Zufällig" aria-label="Zufällig" aria-pressed="false"><svg><use href="#i-shuffle"/></svg></button>
            <button class="mu__btn mu__btn--md" data-act="prev" aria-label="Zurück"><svg><use href="#i-prev"/></svg></button>
            <button class="mu__btn mu__btn--play" data-act="play" aria-label="Abspielen"><svg><use href="#i-play"/></svg></button>
            <button class="mu__btn mu__btn--md" data-act="next" aria-label="Weiter"><svg><use href="#i-next"/></svg></button>
            <button class="mu__btn f-tip" data-act="repeat" data-tip="Wiederholen: aus" aria-label="Wiederholen" data-mode="off" aria-pressed="false"><svg><use href="#i-repeat"/></svg><i class="mu__one">1</i></button>
          </div>
          <div class="mu__vol">
            <button class="mu__btn mu__btn--sm" data-act="mute" aria-label="Stumm"><svg><use href="#i-vol"/></svg></button>
            <input type="range" class="range" min="0" max="100" value="80" step="1" data-vol aria-label="Lautstärke">
          </div>
        </section>
        <section class="mu__lib" aria-label="Bibliothek">
          <div class="mu__libhead">
            <div class="mu__src" role="tablist" aria-label="Quelle">
              <button role="tab" data-src="local" aria-selected="true">Lokal</button>
              <button role="tab" data-src="server" aria-selected="false">Server</button>
            </div>
            <label class="f-search mu__search"><svg><use href="#i-search"/></svg><input class="f-input" data-q placeholder="Titel, Künstler, Album" aria-label="Suchen" autocomplete="off"></label>
            <button class="f-btn f-btn--ghost f-btn--icon f-btn--sm f-tip" data-act="reload" data-tip="Neu einlesen" aria-label="Neu einlesen"><svg><use href="#i-refresh"/></svg></button>
          </div>
          <div class="mu__server" data-server-bar hidden>
            <span class="f-status f-status--ok" data-server-name translate="no">–</span>
            <button class="f-btn f-btn--ghost f-btn--sm" data-act="disconnect">Trennen</button>
          </div>
          <div class="mu__list" role="list" data-list></div>
          <div class="mu__empty" data-empty hidden>
            <svg><use href="#i-music"/></svg>
            <b>Noch keine Musik</b>
            <p>Lege Audiodateien in den Ordner <b translate="no">Musik</b> in deinem Home: MP3, M4A, OGG, Opus, FLAC oder WAV. Titel, Künstler und Cover kommen aus den Dateien.</p>
            <button class="f-btn f-btn--sm" data-act="folder"><svg><use href="#i-folder"/></svg>Ordner Musik öffnen</button>
          </div>
          <form class="mu__connect" data-connect hidden autocomplete="off">
            <svg><use href="#i-net"/></svg>
            <b>Musik-Server verbinden</b>
            <p>Ein Subsonic-Server wie Navidrome, Airsonic oder Gonic. Akari merkt sich kein Passwort, nur das Zeichen, mit dem Subsonic anmeldet.</p>
            <label class="f-field"><span>Adresse</span><input class="f-input" name="url" type="url" placeholder="https://musik.example" required spellcheck="false"></label>
            <label class="f-field"><span>Benutzer</span><input class="f-input" name="user" required spellcheck="false" autocomplete="off"></label>
            <label class="f-field"><span>Passwort</span><input class="f-input" name="password" type="password" required autocomplete="new-password"></label>
            <div class="mu__connect-foot"><span class="f-dim" data-connect-msg></span><button class="f-btn f-btn--primary f-btn--sm" type="submit">Verbinden</button></div>
          </form>
        </section>`;
      const $ = s => win.body.querySelector(s);
      const audio = new Audio();
      audio.preload = 'metadata';
      try { audio.volume = Math.min(1, Math.max(0, +(localStorage.getItem('akari-music-vol') ?? 0.8))); } catch {}

      const lists = { local: [], server: [] };
      let view = 'local', shown = [], server = null;
      let queue = [], qi = -1, playing = null;          // what plays comes from the list it was started in
      let shuffle = false, repeat = 'off', seeking = false, order = [];

      /* ---------- the library ---------- */
      const loadLocal = async () => {
        let r;
        try { r = await Akari.api('/api/audio/library', { quiet: true }); } catch { r = { tracks: [] }; }
        lists.local = r.tracks || [];
      };
      const loadServer = async q => {
        if (!server) { lists.server = []; return; }
        try {
          const r = await Akari.api(`/api/audio/subsonic/library?q=${encodeURIComponent(q || '')}`, { quiet: true });
          lists.server = r.tracks || [];
        } catch (e) { lists.server = []; $('[data-server-name]').textContent = e.message; }
      };
      const loadServerState = async () => {
        try { server = await Akari.api('/api/audio/subsonic', { quiet: true }); } catch { server = null; }
        if (server && !server.url) server = null;
      };
      const render = () => {
        const q = $('[data-q]').value.trim().toLowerCase();
        const all = lists[view];
        shown = all.filter(t => !q || view === 'server' || [t.title, t.artist, t.album, t.path].some(v => v && v.toLowerCase().includes(q)));
        const needServer = view === 'server' && !server;
        $('[data-connect]').hidden = !needServer;
        $('[data-server-bar]').hidden = view !== 'server' || !server;
        if (server) $('[data-server-name]').textContent = `${server.name || 'Subsonic'} · ${server.url.replace(/^https?:\/\//, '')}`;
        $('[data-empty]').hidden = view !== 'local' || all.length > 0;
        $('[data-list]').hidden = needServer || (view === 'local' && !all.length);
        $('[data-list]').innerHTML = shown.length ? shown.map((t, i) => {
          const c = coverUrl(t);
          return `<button class="mu__row" role="listitem" data-i="${i}">
            <span class="mu__thumb" style="--h:${tint(t)}">${c ? `<img src="${esc(c)}" alt="" loading="lazy" decoding="async">` : '<svg><use href="#i-music"/></svg>'}<i class="mu__eq"><i></i><i></i><i></i></i></span>
            <span class="mu__txt" translate="no"><b>${esc(t.title)}</b><small>${esc(sub(t))}</small></span>
            ${t.duration ? `<time class="mu__len">${time(t.duration)}</time>` : ''}
          </button>`;
        }).join('') : `<p class="mu__none">${Akari.t(view === 'server' && !q ? 'Der Server hat keine Titel geliefert.' : 'Nichts gefunden.')}</p>`;
        mark();
      };
      const mark = () => {
        win.body.querySelectorAll('.mu__row').forEach(r => {
          const t = shown[+r.dataset.i], on = !!playing && t?.path === playing.path;
          r.classList.toggle('is-cur', on);
          r.classList.toggle('is-playing', on && !audio.paused);
        });
      };
      const setView = async v => {
        view = v;
        win.body.querySelectorAll('[data-src]').forEach(b => b.setAttribute('aria-selected', b.dataset.src === v));
        if (v === 'server' && !lists.server.length) await loadServer($('[data-q]').value);
        render();
      };

      /* ---------- playing ---------- */
      const play = (list, i, start = true) => {
        if (!list[i]) return;
        queue = list.slice();
        qi = i;
        playing = queue[qi];
        order = [];
        audio.src = src(playing);
        if (start) audio.play().catch(() => {});
        show();
        mark();
        win.body.querySelector('.mu__row.is-cur')?.scrollIntoView({ block: 'nearest' });
      };
      const next = dir => {
        if (!queue.length) { if (shown.length) play(shown, 0); return; }
        if (dir < 0 && audio.currentTime > 3) { audio.currentTime = 0; return; }   // back: first to the start of this one
        let i;
        if (shuffle && queue.length > 1) {
          if (!order.length) order = queue.map((t, j) => j).filter(j => j !== qi).sort(() => Math.random() - 0.5);
          i = order.shift();
        } else i = (qi + dir + queue.length) % queue.length;
        const keep = order;
        play(queue, i);
        order = keep;
      };
      const toggle = () => {
        if (!playing) return next(1);
        audio.paused ? audio.play().catch(() => {}) : audio.pause();
      };

      /* ---------- what is shown: here, in the taskbar, for the media keys ---------- */
      const show = () => {
        const t = playing;
        $('[data-title]').textContent = t ? t.title : Akari.t('Nichts ausgewählt');
        $('[data-sub]').textContent = t ? sub(t) : Akari.t('Wähle unten einen Titel.');
        win.setTitle(t ? t.title : 'Musik');
        const art = $('[data-art]'), img = art.querySelector('img'), c = coverUrl(t);
        art.style.setProperty('--h', tint(t));
        art.classList.toggle('is-empty', !t);
        if (c) { img.onload = () => { img.hidden = false; }; img.onerror = () => { img.hidden = true; }; if (img.getAttribute('src') !== c) { img.hidden = true; img.src = c; } }
        else { img.hidden = true; img.removeAttribute('src'); }
        const on = !audio.paused;
        const pb = $('[data-act="play"]');
        pb.querySelector('use').setAttribute('href', on ? '#i-pause' : '#i-play');
        pb.setAttribute('aria-label', Akari.t(on ? 'Pause' : 'Abspielen'));
        art.classList.toggle('is-playing', on);
        $('[data-seek]').disabled = !t;
        Akari.mediaLocal?.(t ? { title: t.title, artist: t.artist || '', album: t.album || '', status: on ? 'playing' : 'paused', cover: c, hue: tint(t) } : null, control);
        if ('mediaSession' in navigator && t) {
          try {
            navigator.mediaSession.metadata = new MediaMetadata({ title: t.title, artist: t.artist || '', album: t.album || '',
              artwork: c ? [{ src: new URL(c, location.href).href }] : [] });
            navigator.mediaSession.playbackState = on ? 'playing' : 'paused';
          } catch {}
        }
      };
      const control = action => {
        if (action === 'play-pause') toggle();
        if (action === 'next') next(1);
        if (action === 'previous') next(-1);
        if (action === 'show') Akari.focus(win);
      };
      if ('mediaSession' in navigator) {
        const ms = navigator.mediaSession;
        const on = (a, f) => { try { ms.setActionHandler(a, f); } catch {} };
        on('play', () => audio.play().catch(() => {}));
        on('pause', () => audio.pause());
        on('nexttrack', () => next(1));
        on('previoustrack', () => next(-1));
        on('seekto', d => { if (Number.isFinite(d.seekTime)) audio.currentTime = d.seekTime; });
      }

      /* ---------- the bar, the times, the volume ---------- */
      const seek = $('[data-seek]');
      const paintSeek = () => {
        const d = audio.duration || playing?.duration, c = audio.currentTime;
        $('[data-cur]').textContent = time(c);
        $('[data-dur]').textContent = time(d);
        if (!seeking) seek.value = d ? Math.round(c / d * 1000) : 0;
        seek.style.setProperty('--v', `${seek.value / 10}%`);
      };
      seek.addEventListener('input', () => {
        seeking = true;
        seek.style.setProperty('--v', `${seek.value / 10}%`);
        $('[data-cur]').textContent = time((audio.duration || 0) * seek.value / 1000);
      });
      seek.addEventListener('change', () => {
        if (audio.duration) audio.currentTime = audio.duration * seek.value / 1000;
        seeking = false;
      });
      const volIn = $('[data-vol]');
      const paintVol = () => {
        volIn.value = Math.round((audio.muted ? 0 : audio.volume) * 100);
        volIn.style.setProperty('--v', `${volIn.value}%`);
        $('[data-act="mute"] use').setAttribute('href', audio.muted || audio.volume === 0 ? '#i-vol-off' : '#i-vol');
      };
      volIn.addEventListener('input', () => {
        audio.muted = false;
        audio.volume = volIn.value / 100;
        try { localStorage.setItem('akari-music-vol', String(audio.volume)); } catch {}
        paintVol();
      });

      audio.addEventListener('timeupdate', paintSeek);
      audio.addEventListener('loadedmetadata', paintSeek);
      audio.addEventListener('play', () => { show(); mark(); });
      audio.addEventListener('pause', () => { show(); mark(); });
      audio.addEventListener('volumechange', paintVol);
      audio.addEventListener('ended', () => {
        if (repeat === 'one') { audio.currentTime = 0; audio.play().catch(() => {}); return; }
        if (repeat === 'off' && !shuffle && qi === queue.length - 1) { show(); return; }
        next(1);
      });
      audio.addEventListener('error', () => {
        if (playing && audio.getAttribute('src')) Akari.notify?.(`„${playing.title}“ lässt sich hier nicht abspielen.`, { tone: 'warn' });
      });

      /* ---------- what the person does ---------- */
      win.body.addEventListener('click', async e => {
        const row = e.target.closest('.mu__row');
        if (row) {
          const t = shown[+row.dataset.i];
          return t && playing && t.path === playing.path ? toggle() : play(shown, +row.dataset.i);
        }
        const tab = e.target.closest('[data-src]');
        if (tab) return setView(tab.dataset.src);
        const b = e.target.closest('[data-act]'), a = b?.dataset.act;
        if (!a) return;
        if (a === 'play') toggle();
        if (a === 'next') next(1);
        if (a === 'prev') next(-1);
        if (a === 'mute') audio.muted = !audio.muted;
        if (a === 'folder') Akari.open('files', { path: 'Musik' });
        if (a === 'reload') { view === 'server' ? await loadServer($('[data-q]').value) : await loadLocal(); render(); }
        if (a === 'disconnect') {
          const ok = await Akari.ask({ title: 'Musik-Server trennen?', text: 'Akari vergisst den Server und das Anmeldezeichen. Die Musik auf dem Server bleibt, wie sie ist.', ok: 'Trennen' });
          if (!ok) return;
          await Akari.api('/api/audio/subsonic', { method: 'DELETE', quiet: true }).catch(() => {});
          server = null; lists.server = []; render();
        }
        if (a === 'shuffle') { shuffle = !shuffle; order = []; b.setAttribute('aria-pressed', shuffle); }
        if (a === 'repeat') {
          repeat = { off: 'all', all: 'one', one: 'off' }[repeat];
          b.dataset.mode = repeat;
          b.dataset.tip = Akari.t({ off: 'Wiederholen: aus', all: 'Wiederholen: alle', one: 'Wiederholen: diesen' }[repeat]);
          b.setAttribute('aria-pressed', repeat !== 'off');
        }
      });
      // the search: in the list here; on the server, asked there (a moment after typing stops)
      let qT;
      $('[data-q]').addEventListener('input', () => {
        if (view !== 'server') return render();
        clearTimeout(qT);
        qT = setTimeout(async () => { await loadServer($('[data-q]').value); render(); }, 350);
      });
      $('[data-connect]').addEventListener('submit', async e => {
        e.preventDefault();
        const f = e.target.elements, msg = $('[data-connect-msg]');
        msg.textContent = Akari.t('Verbinde …');
        try {
          server = await Akari.api('/api/audio/subsonic', { method: 'PUT', json: { url: f.url.value, user: f.user.value, password: f.password.value }, quiet: true });
          f.password.value = '';
          msg.textContent = '';
          await loadServer('');
          render();
        } catch (err) { msg.textContent = err.message; }
      });
      // space plays and pauses, the arrows jump, wherever in the window (except in a field)
      win.body.addEventListener('keydown', e => {
        if (e.target.closest('input, textarea')) return;
        if (e.key === ' ') { e.preventDefault(); toggle(); }
        if (e.key === 'ArrowRight' && audio.duration) audio.currentTime = Math.min(audio.duration, audio.currentTime + 10);
        if (e.key === 'ArrowLeft') audio.currentTime = Math.max(0, audio.currentTime - 10);
      });

      paintVol();
      paintSeek();
      show();
      // a file handed over (from Dateien): play it once the library is in
      const playPath = async path => {
        if (view !== 'local') await setView('local');
        if (!lists.local.some(t => t.path === path)) { await loadLocal(); render(); }
        let i = shown.findIndex(t => t.path === path);
        if (i < 0) {                                         // outside the library: play it all the same
          const name = path.split('/').pop().replace(/\.[^.]+$/, '');
          return play([{ path, title: name, folder: path.split('/').slice(0, -1).join('/'), picture: false }], 0);
        }
        play(shown, i);
      };
      Promise.all([loadLocal(), loadServerState()]).then(() => {
        render();
        if (args.path) playPath(args.path);
      });

      return {
        args: a => { if (a?.path) playPath(a.path); },
        focus: () => win.body.querySelector('.mu__btn--play')?.focus({ preventScroll: true }),
        close: () => {
          audio.pause();
          audio.removeAttribute('src');
          audio.load();
          Akari.mediaLocal?.(null);
          if ('mediaSession' in navigator) { try { navigator.mediaSession.metadata = null; } catch {} }
          return true;
        },
      };
    },
  });
})();
