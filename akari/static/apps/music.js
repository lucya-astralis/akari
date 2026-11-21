/* Musik: an audio player for the music in one's home and on a Subsonic server.

   Layout: a sidebar (Start, Suche, Neu hinzugefügt, Künstler, Alben, Titel,
   Favoriten, and the source: Lokal or Server), the main view (album covers in
   a grid, an album or artist page, lists of tracks), a player bar along the
   bottom, and a full view of what plays (big cover, a spectrum of the sound,
   the bar, the buttons) with the queue beside it.

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
  const time = s => !Number.isFinite(s) || s < 0 ? '0:00' : `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`;
  const hue = s => { let h = 0; for (const c of String(s || '')) h = (h * 31 + c.charCodeAt(0)) % 360; return h; };
  const fromServer = t => t?.source === 'subsonic';
  const src = t => (fromServer(t) ? `/api/audio/subsonic/stream?id=${encodeURIComponent(t.id)}` : `/api/audio/stream?path=${encodeURIComponent(t.path)}`);
  const coverUrl = t => (!t?.picture ? null
    : fromServer(t) ? `/api/audio/subsonic/cover?id=${encodeURIComponent(t.cover)}` : `/api/audio/cover?path=${encodeURIComponent(t.path)}`);
  const NO_ALBUM = 'Ohne Album';
  const albumOf = t => t.album || (t.folder && !['Musik', 'Downloads', 'Schreibtisch', ''].includes(t.folder) ? t.folder.split('/').pop() : NO_ALBUM);
  const albumKey = t => `${albumOf(t)}\u0001${t.artist || ''}`;
  const tint = t => hue(albumOf(t) + (t.artist || ''));
  const store = {
    get: (k, d) => { try { return JSON.parse(localStorage.getItem(k)) ?? d; } catch { return d; } },
    set: (k, v) => { try { localStorage.setItem(k, JSON.stringify(v)); } catch {} },
  };
  const NAV = [
    ['home', 'i-home', 'Start'], ['search', 'i-search', 'Suche'], ['added', 'i-plus', 'Neu hinzugefügt'],
    ['artists', 'i-users', 'Künstler'], ['albums', 'i-disc', 'Alben'], ['songs', 'i-list', 'Titel'], ['favs', 'i-heart', 'Favoriten'],
  ];

  Akari.register('music', {
    title: 'Musik', icon: 'i-music', art: 'music', multi: false, size: [980, 660], order: 35, dock: true,
    keywords: ['audio', 'mp3', 'player', 'lieder', 'songs', 'musik', 'subsonic', 'navidrome'],
    create(win, args) {
      win.body.classList.add('mu');
      win.body.innerHTML = `
        <aside class="mu__side" aria-label="Bereiche">
          <div class="mu__brand"><svg><use href="#app-music"/></svg><b>Musik</b></div>
          <nav class="mu__nav">${NAV.map(([id, ic, label]) =>
            `<button data-go="${id}" class="f-tip" data-tip="${label}"><svg><use href="#${ic}"/></svg><span>${label}</span></button>`).join('')}</nav>
          <div class="mu__source">
            <span class="mu__label">Quelle</span>
            <div class="mu__seg" role="tablist" aria-label="Quelle">
              <button role="tab" data-src="local" aria-selected="true">Lokal</button>
              <button role="tab" data-src="server" aria-selected="false">Server</button>
            </div>
            <span class="mu__srv" data-srv translate="no"></span>
          </div>
        </aside>
        <main class="mu__main" data-main tabindex="-1"></main>

        <footer class="mu__bar" aria-label="Wiedergabe">
          <div class="mu__line" data-line role="slider" aria-label="Position" tabindex="0" aria-valuemin="0" aria-valuemax="100" aria-valuenow="0"><i></i></div>
          <button class="mu__mini" data-act="full" aria-label="Großansicht">
            <span class="mu__cover mu__cover--sm" data-mini-cover><svg><use href="#i-music"/></svg></span>
            <span class="mu__minitxt" translate="no"><b data-mini-title>Nichts ausgewählt</b><small data-mini-sub></small></span>
          </button>
          <div class="mu__ctl">
            <button class="mu__btn f-tip" data-act="shuffle" data-tip="Zufällig" aria-label="Zufällig" aria-pressed="false"><svg><use href="#i-shuffle"/></svg></button>
            <button class="mu__btn mu__btn--md" data-act="prev" aria-label="Zurück"><svg><use href="#i-prev"/></svg></button>
            <button class="mu__btn mu__btn--play" data-act="play" aria-label="Abspielen"><svg><use href="#i-play"/></svg></button>
            <button class="mu__btn mu__btn--md" data-act="next" aria-label="Weiter"><svg><use href="#i-next"/></svg></button>
            <button class="mu__btn f-tip" data-act="repeat" data-tip="Wiederholen: aus" aria-label="Wiederholen" data-mode="off" aria-pressed="false"><svg><use href="#i-repeat"/></svg><i class="mu__one">1</i></button>
          </div>
          <div class="mu__right">
            <span class="mu__time"><time data-cur>0:00</time> / <time data-dur>0:00</time></span>
            <button class="mu__btn mu__btn--sm" data-act="mute" aria-label="Stumm"><svg><use href="#i-vol"/></svg></button>
            <input type="range" class="range mu__volrange" min="0" max="100" value="80" step="1" data-vol aria-label="Lautstärke">
            <button class="mu__btn mu__btn--sm f-tip" data-act="queue" data-tip="Warteschlange" aria-label="Warteschlange" aria-pressed="false"><svg><use href="#i-queue"/></svg></button>
          </div>
        </footer>

        <section class="mu__full" data-full hidden aria-label="Läuft gerade">
          <div class="mu__fullbg" data-fullbg></div>
          <button class="mu__round mu__round--l f-tip" data-act="full" data-tip="Schließen" aria-label="Großansicht schließen"><svg><use href="#i-chev-down"/></svg></button>
          <button class="mu__round mu__round--r f-tip" data-act="queue" data-tip="Warteschlange" aria-label="Warteschlange"><svg><use href="#i-queue"/></svg></button>
          <div class="mu__stage">
            <div class="mu__cover mu__cover--xl" data-full-cover><svg><use href="#i-music"/></svg></div>
            <div class="mu__fullmeta" translate="no"><b data-full-title>–</b><span data-full-artist></span><small data-full-album></small></div>
            <canvas class="mu__viz" data-viz width="560" height="110" aria-hidden="true"></canvas>
            <div class="mu__seek"><time data-cur2>0:00</time>
              <input type="range" class="range mu__seekbar" min="0" max="1000" value="0" step="1" data-seek aria-label="Position">
              <time data-dur2>0:00</time></div>
            <div class="mu__ctl mu__ctl--xl">
              <button class="mu__btn" data-act="shuffle" aria-label="Zufällig" aria-pressed="false"><svg><use href="#i-shuffle"/></svg></button>
              <button class="mu__btn mu__btn--md" data-act="prev" aria-label="Zurück"><svg><use href="#i-prev"/></svg></button>
              <button class="mu__btn mu__btn--play" data-act="play" aria-label="Abspielen"><svg><use href="#i-play"/></svg></button>
              <button class="mu__btn mu__btn--md" data-act="next" aria-label="Weiter"><svg><use href="#i-next"/></svg></button>
              <button class="mu__btn" data-act="repeat" aria-label="Wiederholen" data-mode="off" aria-pressed="false"><svg><use href="#i-repeat"/></svg><i class="mu__one">1</i></button>
            </div>
          </div>
        </section>

        <aside class="mu__queue" data-queue hidden aria-label="Warteschlange">
          <header><b>Als Nächstes</b><button class="mu__btn mu__btn--sm" data-act="queue" aria-label="Schließen"><svg><use href="#i-x"/></svg></button></header>
          <div class="mu__qlist" data-qlist></div>
        </aside>`;
      const $ = s => win.body.querySelector(s);
      const $$ = s => [...win.body.querySelectorAll(s)];
      const main = $('[data-main]');
      const audio = new Audio();
      audio.preload = 'metadata';
      audio.crossOrigin = 'anonymous';
      audio.volume = Math.min(1, Math.max(0, +store.get('akari-music-vol', 0.8)));

      const lists = { local: [], server: [] };
      let source = 'local', server = null, route = { view: 'home' }, back = [], homeTab = 'recent';
      let queue = [], qi = -1, playing = null, shuffle = false, repeat = 'off', order = [];
      let recent = store.get('akari-music-recent', []), favs = new Set(store.get('akari-music-fav', []));

      /* ---------- the library ---------- */
      const lib = () => lists[source];
      const albums = tracks => {
        const m = new Map();
        for (const t of tracks) {
          const k = albumKey(t);
          if (!m.has(k)) m.set(k, { key: k, title: Akari.t(albumOf(t)), artist: t.artist || '', tracks: [], mtime: 0 });
          const a = m.get(k);
          a.tracks.push(t);
          a.mtime = Math.max(a.mtime, t.mtime || 0);
        }
        for (const a of m.values()) {
          a.tracks.sort((x, y) => (x.path || '').localeCompare(y.path || '', undefined, { numeric: true }));
          a.cover = a.tracks.find(t => t.picture) || a.tracks[0];
          a.hue = tint(a.tracks[0]);
        }
        return [...m.values()];
      };
      const artists = tracks => {
        const m = new Map();
        for (const t of tracks) {
          const n = t.artist || 'Unbekannt';
          if (!m.has(n)) m.set(n, { name: n, tracks: [] });
          m.get(n).tracks.push(t);
        }
        return [...m.values()].sort((a, b) => a.name.localeCompare(b.name));
      };
      const loadLocal = async () => {
        try { lists.local = (await Akari.api('/api/audio/library', { quiet: true })).tracks || []; } catch { lists.local = []; }
      };
      const loadServer = async q => {
        if (!server) { lists.server = []; return; }
        try { lists.server = (await Akari.api(`/api/audio/subsonic/library?q=${encodeURIComponent(q || '')}`, { quiet: true })).tracks || []; }
        catch { lists.server = []; }
      };
      const loadServerState = async () => {
        try { server = await Akari.api('/api/audio/subsonic', { quiet: true }); } catch { server = null; }
        if (server && !server.url) server = null;
        $('[data-srv]').textContent = server ? `${server.name || 'Subsonic'} · ${server.url.replace(/^https?:\/\//, '')}` : '';
      };

      /* ---------- the pieces of a page ---------- */
      const cover = (t, cls = '', h) => {
        const c = coverUrl(t);
        return `<span class="mu__cover ${cls}" style="--h:${h ?? tint(t || {})}">${c ? `<img src="${esc(c)}" alt="" loading="lazy" decoding="async">` : '<svg><use href="#i-music"/></svg>'}</span>`;
      };
      const albumGrid = list => list.length ? `<div class="mu__grid">${list.map(a => `
        <button class="mu__card" data-album="${esc(a.key)}">
          ${cover(a.cover, 'mu__cover--card', a.hue)}
          <span class="mu__play" aria-hidden="true"><svg><use href="#i-play"/></svg></span>
          <b translate="no">${esc(a.title)}</b><small translate="no">${esc(a.artist || `${a.tracks.length} ${a.tracks.length === 1 ? 'Titel' : 'Titel'}`)}</small>
        </button>`).join('')}</div>` : '';
      const songRows = (list, { numbers = false } = {}) => `<div class="mu__songs" data-songs>${list.map((t, i) => `
        <div class="mu__song" data-i="${i}" role="button" tabindex="0">
          <span class="mu__no">${numbers ? i + 1 : cover(t, 'mu__cover--xs')}<i class="mu__eq"><i></i><i></i><i></i></i></span>
          <span class="mu__st" translate="no"><b>${esc(t.title)}</b><small>${esc(t.artist || '')}</small></span>
          <span class="mu__sa" translate="no">${esc(t.album || albumOf(t))}</span>
          <button class="mu__fav${favs.has(t.path) ? ' is-on' : ''}" data-fav="${i}" aria-label="Favorit" aria-pressed="${favs.has(t.path)}"><svg><use href="#i-heart"/></svg></button>
          <time>${t.duration ? time(t.duration) : ''}</time>
        </div>`).join('')}</div>`;
      const empty = (title, text, action = '') => `<div class="mu__empty"><svg><use href="#i-music"/></svg><b>${title}</b><p>${text}</p>${action}</div>`;

      /* ---------- the pages ---------- */
      let rows = [];          // the tracks of the song list on the page, in order (what a click plays)
      const render = () => {
        $$('[data-go]').forEach(b => b.classList.toggle('is-on', b.dataset.go === route.view || (route.view === 'album' && b.dataset.go === 'albums') || (route.view === 'artist' && b.dataset.go === 'artists')));
        $$('[data-src]').forEach(b => b.setAttribute('aria-selected', b.dataset.src === source));
        rows = [];
        const tracks = lib();
        const head = (title, sub = '') => `<header class="mu__head">${back.length ? '<button class="mu__round" data-act="back" aria-label="Zurück"><svg><use href="#i-back"/></svg></button>' : ''}<div><h2>${title}</h2>${sub ? `<p>${sub}</p>` : ''}</div></header>`;
        let html = '';
        if (source === 'server' && !server) {
          html = `<form class="mu__connect" data-connect autocomplete="off">
            <svg><use href="#i-net"/></svg><h2>Musik-Server verbinden</h2>
            <p>Ein Subsonic-Server wie Navidrome, Airsonic oder Gonic. Akari merkt sich kein Passwort, nur das Zeichen, mit dem Subsonic anmeldet.</p>
            <label class="f-field"><span>Adresse</span><input class="f-input" name="url" type="text" inputmode="url" placeholder="https://musik.example" required spellcheck="false" autocapitalize="off"></label>
            <label class="f-field"><span>Benutzer</span><input class="f-input" name="user" required spellcheck="false" autocomplete="off"></label>
            <label class="f-field"><span>Passwort</span><input class="f-input" name="password" type="password" required autocomplete="new-password"></label>
            <div class="mu__connect-foot"><span class="f-dim" data-connect-msg></span><button class="f-btn f-btn--primary" type="submit">Verbinden</button></div>
          </form>`;
        } else if (!tracks.length && route.view !== 'search') {
          html = source === 'local'
            ? empty('Noch keine Musik', 'Lege Audiodateien in den Ordner <b translate="no">Musik</b> in deinem Home: MP3, M4A, OGG, Opus, FLAC oder WAV. Titel, Künstler und Cover kommen aus den Dateien.',
              '<button class="f-btn f-btn--sm" data-act="folder"><svg><use href="#i-folder"/></svg>Ordner Musik öffnen</button>')
            : empty('Der Server hat keine Titel geliefert.', 'Suche nach einem Titel oder Künstler, manche Server liefern nur auf eine Frage hin.');
        } else if (route.view === 'home') {
          const all = albums(tracks);
          const byKey = new Map(all.map(a => [a.key, a]));
          let list;
          if (homeTab === 'recent') list = recent.map(k => byKey.get(k)).filter(Boolean);
          if (homeTab === 'new' || (homeTab === 'recent' && !list.length)) list = [...all].sort((a, b) => b.mtime - a.mtime);
          if (homeTab === 'random') list = [...all].sort(() => Math.random() - 0.5);
          const tab = homeTab === 'recent' && !recent.some(k => byKey.has(k)) ? 'new' : homeTab;
          html = `<div class="mu__chips">${[['recent', 'i-refresh', 'Zuletzt gespielt'], ['new', 'i-plus', 'Neu'], ['random', 'i-shuffle', 'Zufällig']]
            .map(([id, ic, label]) => `<button class="mu__chip${tab === id ? ' is-on' : ''}" data-home="${id}"><svg><use href="#${ic}"/></svg>${label}</button>`).join('')}</div>
            <h2 class="mu__h">${{ recent: 'Zuletzt gespielt', new: 'Neu hinzugefügt', random: 'Zufällig' }[tab]}</h2>${albumGrid(list.slice(0, 40))}`;
        } else if (route.view === 'search') {
          const q = (route.q || '').trim().toLowerCase();
          const hit = t => [t.title, t.artist, t.album, t.path].some(v => v && v.toLowerCase().includes(q));
          const found = q ? (source === 'server' ? tracks : tracks.filter(hit)) : [];
          const al = q ? albums(found).filter(a => a.title.toLowerCase().includes(q) || a.artist.toLowerCase().includes(q)) : [];
          rows = found.slice(0, 200);
          html = `<label class="f-search mu__search"><svg><use href="#i-search"/></svg><input class="f-input" data-q placeholder="Titel, Künstler, Album" value="${esc(route.q || '')}" aria-label="Suchen" autocomplete="off"></label>
            ${!q ? '<p class="mu__hint">Suche in allen Titeln, Künstlern und Alben.</p>'
              : !found.length ? '<p class="mu__hint">Nichts gefunden.</p>'
              : `${al.length ? `<h2 class="mu__h">Alben</h2>${albumGrid(al.slice(0, 10))}` : ''}<h2 class="mu__h">Titel</h2>${songRows(rows)}`}`;
        } else if (route.view === 'added') {
          html = head('Neu hinzugefügt') + albumGrid(albums(tracks).sort((a, b) => b.mtime - a.mtime));
        } else if (route.view === 'albums') {
          html = head('Alben', `${albums(tracks).length} Alben`) + albumGrid(albums(tracks).sort((a, b) => a.title.localeCompare(b.title)));
        } else if (route.view === 'artists') {
          const ar = artists(tracks);
          html = head('Künstler', `${ar.length} Künstler`) + `<div class="mu__grid mu__grid--artists">${ar.map(a => `
            <button class="mu__card mu__card--artist" data-artist="${esc(a.name)}">
              <span class="mu__face" style="--h:${hue(a.name)}" translate="no">${esc((a.name.match(/\p{L}|\d/u) || ['?'])[0].toUpperCase())}</span>
              <b translate="no">${esc(a.name)}</b><small>${a.tracks.length} Titel</small></button>`).join('')}</div>`;
        } else if (route.view === 'artist') {
          const mine = tracks.filter(t => (t.artist || 'Unbekannt') === route.name);
          rows = mine;
          html = head(esc(route.name), `${albums(mine).length} Alben · ${mine.length} Titel`) + `<div class="mu__actions"><button class="f-btn f-btn--primary" data-act="play-rows"><svg><use href="#i-play"/></svg>Abspielen</button><button class="f-btn" data-act="shuffle-rows"><svg><use href="#i-shuffle"/></svg>Zufällig</button></div>`
            + albumGrid(albums(mine)) + `<h2 class="mu__h">Titel</h2>${songRows(rows)}`;
        } else if (route.view === 'album') {
          const a = albums(tracks).find(x => x.key === route.key);
          if (!a) { route = { view: 'albums' }; return render(); }
          rows = a.tracks;
          const len = a.tracks.reduce((s, t) => s + (t.duration || 0), 0);
          html = `${back.length ? '<button class="mu__round mu__round--back" data-act="back" aria-label="Zurück"><svg><use href="#i-back"/></svg></button>' : ''}
            <header class="mu__album">${cover(a.cover, 'mu__cover--album', a.hue)}
              <div><span class="mu__label">Album</span><h2 translate="no">${esc(a.title)}</h2>
              <button class="mu__link" data-artist="${esc(a.artist || 'Unbekannt')}" translate="no">${esc(a.artist || 'Unbekannt')}</button>
              <p>${a.tracks.length} Titel${len ? ` · ${Math.round(len / 60)} min` : ''}</p>
              <div class="mu__actions"><button class="f-btn f-btn--primary" data-act="play-rows"><svg><use href="#i-play"/></svg>Abspielen</button><button class="f-btn" data-act="shuffle-rows"><svg><use href="#i-shuffle"/></svg>Zufällig</button></div></div>
            </header>${songRows(rows, { numbers: true })}`;
        } else if (route.view === 'songs') {
          rows = [...tracks].sort((a, b) => a.title.localeCompare(b.title));
          html = head('Titel', `${rows.length} Titel`) + songRows(rows);
        } else if (route.view === 'favs') {
          rows = tracks.filter(t => favs.has(t.path));
          html = head('Favoriten', rows.length ? `${rows.length} Titel` : '') + (rows.length ? songRows(rows)
            : empty('Noch keine Favoriten', 'Das Herz neben einem Titel legt ihn hier ab.'));
        }
        main.innerHTML = html;
        mark();
        const q = main.querySelector('[data-q]');
        if (q && route.view === 'search') { q.focus(); q.setSelectionRange(q.value.length, q.value.length); }
      };
      const go = (view, extra = {}, remember = true) => {
        if (remember && ['album', 'artist'].includes(view)) back.push(route); else if (!['album', 'artist'].includes(view)) back = [];
        route = { view, ...extra };
        render();
        main.scrollTop = 0;
      };
      const mark = () => {
        $$('.mu__song').forEach(r => {
          const t = rows[+r.dataset.i], on = !!playing && t?.path === playing.path;
          r.classList.toggle('is-cur', on);
          r.classList.toggle('is-playing', on && !audio.paused);
        });
        renderQueue();
      };

      /* ---------- playing ---------- */
      const play = (list, i, start = true) => {
        if (!list[i]) return;
        queue = list.slice();
        qi = i;
        order = [];
        begin(start);
      };
      const begin = (start = true) => {
        playing = queue[qi];
        audio.src = src(playing);
        if (start) { wakeViz(); audio.play().catch(() => {}); }
        const k = albumKey(playing);
        recent = [k, ...recent.filter(x => x !== k)].slice(0, 30);
        store.set('akari-music-recent', recent);
        show();
        mark();
      };
      const next = dir => {
        if (!queue.length) { if (rows.length) play(rows, 0); return; }
        if (dir < 0 && audio.currentTime > 3) { audio.currentTime = 0; return; }   // back: first to the start of this one
        if (shuffle && queue.length > 1) {
          if (!order.length) order = queue.map((t, j) => j).filter(j => j !== qi).sort(() => Math.random() - 0.5);
          qi = order.shift();
        } else qi = (qi + dir + queue.length) % queue.length;
        begin();
      };
      const toggle = () => {
        if (!playing) return next(1);
        if (audio.paused) { wakeViz(); audio.play().catch(() => {}); } else audio.pause();
      };

      /* ---------- what is shown: bar, full view, taskbar, media keys ---------- */
      const paintCover = (el, t) => {
        const c = coverUrl(t);
        el.style.setProperty('--h', t ? tint(t) : 300);
        el.classList.toggle('is-empty', !t);
        let img = el.querySelector('img');
        if (c) {
          if (!img) { img = document.createElement('img'); img.alt = ''; el.prepend(img); }
          if (img.getAttribute('src') !== c) img.src = c;
        } else img?.remove();
      };
      const show = () => {
        const t = playing, on = !audio.paused;
        $('[data-mini-title]').textContent = t ? t.title : Akari.t('Nichts ausgewählt');
        $('[data-mini-sub]').textContent = t ? (t.artist || albumOf(t)) : '';
        $('[data-full-title]').textContent = t ? t.title : '–';
        $('[data-full-artist]').textContent = t?.artist || '';
        $('[data-full-album]').textContent = t ? albumOf(t) : '';
        paintCover($('[data-mini-cover]'), t);
        paintCover($('[data-full-cover]'), t);
        $('[data-fullbg]').style.setProperty('--h', t ? tint(t) : 300);
        const c = coverUrl(t);
        $('[data-fullbg]').style.backgroundImage = c ? `url("${c}")` : '';
        win.setTitle(t ? t.title : 'Musik');
        $$('[data-act="play"]').forEach(b => {
          b.querySelector('use').setAttribute('href', on ? '#i-pause' : '#i-play');
          b.setAttribute('aria-label', Akari.t(on ? 'Pause' : 'Abspielen'));
        });
        $('[data-full-cover]').classList.toggle('is-playing', on);
        Akari.mediaLocal?.(t ? { title: t.title, artist: t.artist || '', album: albumOf(t), status: on ? 'playing' : 'paused', cover: c, hue: tint(t) } : null, control);
        if ('mediaSession' in navigator && t) {
          try {
            navigator.mediaSession.metadata = new MediaMetadata({ title: t.title, artist: t.artist || '', album: albumOf(t),
              artwork: c ? [{ src: new URL(c, location.href).href }] : [] });
            navigator.mediaSession.playbackState = on ? 'playing' : 'paused';
          } catch {}
        }
      };
      const control = action => {
        if (action === 'play-pause') toggle();
        if (action === 'next') next(1);
        if (action === 'previous') next(-1);
        if (action === 'show') { Akari.focus(win); setFull(true); }
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

      /* the queue: what comes after this one */
      const renderQueue = () => {
        const box = $('[data-qlist]');
        if ($('[data-queue]').hidden) return;
        if (!queue.length) { box.innerHTML = `<p class="mu__hint">${Akari.t('Noch nichts in der Warteschlange.')}</p>`; return; }
        const from = Math.max(0, qi);
        box.innerHTML = queue.slice(from, from + 60).map((t, j) => `
          <button class="mu__qrow${j === 0 ? ' is-cur' : ''}" data-q-i="${from + j}">${cover(t, 'mu__cover--xs')}
            <span class="mu__st" translate="no"><b>${esc(t.title)}</b><small>${esc(t.artist || albumOf(t))}</small></span></button>`).join('');
      };

      /* ---------- the full view, and its spectrum ---------- */
      let ctx = null, analyser = null, bins = null, raf = 0;
      const wakeViz = () => {
        if (ctx || !window.AudioContext) { ctx?.resume?.(); return; }
        try {
          ctx = new AudioContext();
          const node = ctx.createMediaElementSource(audio);
          analyser = ctx.createAnalyser();
          analyser.fftSize = 256;
          analyser.smoothingTimeConstant = 0.78;
          node.connect(analyser);
          analyser.connect(ctx.destination);
          bins = new Uint8Array(analyser.frequencyBinCount);
        } catch { ctx = null; analyser = null; }
      };
      const draw = () => {
        raf = 0;
        if ($('[data-full]').hidden) return;
        const cv = $('[data-viz]'), g = cv.getContext('2d');
        const w = cv.width = cv.clientWidth * devicePixelRatio, h = cv.height = cv.clientHeight * devicePixelRatio;
        g.clearRect(0, 0, w, h);
        const n = 48, gap = 3 * devicePixelRatio, bw = (w - gap * (n - 1)) / n;
        if (analyser) analyser.getByteFrequencyData(bins);
        // the accent as a plain colour: canvas knows no light-dark() (accent.js resolves it)
        if (!draw.col || performance.now() - draw.at > 1000) { draw.col = window.AkariAccent?.hex() || '#8a8aa0'; draw.at = performance.now(); }
        const col = draw.col;
        for (let i = 0; i < n; i++) {
          // low frequencies on the left, spread over the bins that carry sound
          const v = analyser ? bins[Math.min(bins.length - 1, Math.floor(Math.pow(i / n, 1.6) * bins.length * 0.82))] / 255 : 0;
          const bh = Math.max(3 * devicePixelRatio, (audio.paused ? 0.06 : v) * h);
          g.fillStyle = col;
          g.globalAlpha = 0.35 + 0.65 * (1 - i / n);
          const r = Math.min(bw / 2, 3 * devicePixelRatio);
          g.beginPath();
          g.roundRect?.(i * (bw + gap), h - bh, bw, bh, [r, r, 0, 0]) ?? g.rect(i * (bw + gap), h - bh, bw, bh);
          g.fill();
        }
        raf = requestAnimationFrame(draw);
      };
      const setFull = on => {
        $('[data-full]').hidden = !on;
        win.body.classList.toggle('is-full', on);
        if (on && !raf) raf = requestAnimationFrame(draw);
      };

      /* ---------- the bar, the times, the volume ---------- */
      const line = $('[data-line]'), seek = $('[data-seek]');
      let seeking = false;
      const paintTime = () => {
        const d = audio.duration || playing?.duration || 0, c = audio.currentTime || 0, p = d ? c / d : 0;
        $('[data-cur]').textContent = $('[data-cur2]').textContent = time(c);
        $('[data-dur]').textContent = $('[data-dur2]').textContent = time(d);
        line.style.setProperty('--p', `${p * 100}%`);
        line.setAttribute('aria-valuenow', Math.round(p * 100));
        if (!seeking) seek.value = Math.round(p * 1000);
        seek.style.setProperty('--v', `${seek.value / 10}%`);
      };
      const jump = p => { if (audio.duration) audio.currentTime = Math.max(0, Math.min(1, p)) * audio.duration; };
      line.addEventListener('pointerdown', e => {
        const r = line.getBoundingClientRect();
        jump((e.clientX - r.left) / r.width);
      });
      line.addEventListener('keydown', e => {
        if (e.key === 'ArrowRight') audio.currentTime += 5;
        if (e.key === 'ArrowLeft') audio.currentTime -= 5;
      });
      seek.addEventListener('input', () => { seeking = true; seek.style.setProperty('--v', `${seek.value / 10}%`); $('[data-cur2]').textContent = time((audio.duration || 0) * seek.value / 1000); });
      seek.addEventListener('change', () => { jump(seek.value / 1000); seeking = false; });
      const volIn = $('[data-vol]');
      const paintVol = () => {
        volIn.value = Math.round((audio.muted ? 0 : audio.volume) * 100);
        volIn.style.setProperty('--v', `${volIn.value}%`);
        $('[data-act="mute"] use').setAttribute('href', audio.muted || audio.volume === 0 ? '#i-vol-off' : '#i-vol');
      };
      volIn.addEventListener('input', () => { audio.muted = false; audio.volume = volIn.value / 100; store.set('akari-music-vol', audio.volume); paintVol(); });

      audio.addEventListener('timeupdate', paintTime);
      audio.addEventListener('loadedmetadata', paintTime);
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
      const setSource = async s => {
        source = s;
        if (s === 'server' && server && !lists.server.length) await loadServer('');
        go(route.view === 'album' || route.view === 'artist' ? 'home' : route.view, {}, false);
      };
      win.body.addEventListener('click', async e => {
        const fav = e.target.closest('[data-fav]');
        if (fav) {
          e.stopPropagation();
          const t = rows[+fav.dataset.fav];
          favs.has(t.path) ? favs.delete(t.path) : favs.add(t.path);
          store.set('akari-music-fav', [...favs]);
          fav.classList.toggle('is-on', favs.has(t.path));
          fav.setAttribute('aria-pressed', favs.has(t.path));
          if (route.view === 'favs') render();
          return;
        }
        const song = e.target.closest('.mu__song');
        if (song) { const t = rows[+song.dataset.i]; return t && playing && t.path === playing.path ? toggle() : play(rows, +song.dataset.i); }
        const q = e.target.closest('[data-q-i]');
        if (q) { qi = +q.dataset.qI; return begin(); }
        const card = e.target.closest('[data-album]');
        if (card) {
          const a = albums(lib()).find(x => x.key === card.dataset.album);
          if (e.target.closest('.mu__play') && a) return play(a.tracks, 0);
          return go('album', { key: card.dataset.album });
        }
        const ar = e.target.closest('[data-artist]');
        if (ar) return go('artist', { name: ar.dataset.artist });
        const nav = e.target.closest('[data-go]');
        if (nav) return go(nav.dataset.go === 'search' ? 'search' : nav.dataset.go, nav.dataset.go === 'search' ? { q: '' } : {});
        const h = e.target.closest('[data-home]');
        if (h) { homeTab = h.dataset.home; return render(); }
        const s = e.target.closest('[data-src]');
        if (s) return setSource(s.dataset.src);
        const b = e.target.closest('[data-act]'), a = b?.dataset.act;
        if (!a) return;
        if (a === 'play') toggle();
        if (a === 'next') next(1);
        if (a === 'prev') next(-1);
        if (a === 'mute') audio.muted = !audio.muted;
        if (a === 'full') setFull($('[data-full]').hidden);
        if (a === 'back') { route = back.pop() || { view: 'home' }; render(); }
        if (a === 'folder') Akari.open('files', { path: 'Musik' });
        if (a === 'play-rows' && rows.length) { shuffle = false; paintModes(); play(rows, 0); }
        if (a === 'shuffle-rows' && rows.length) { shuffle = true; paintModes(); play(rows, Math.floor(Math.random() * rows.length)); }
        if (a === 'queue') {
          const qd = $('[data-queue]');
          qd.hidden = !qd.hidden;
          $$('.mu__right [data-act="queue"], .mu__round--r').forEach(x => x.setAttribute('aria-pressed', !qd.hidden));
          renderQueue();
        }
        if (a === 'shuffle') { shuffle = !shuffle; order = []; paintModes(); }
        if (a === 'repeat') { repeat = { off: 'all', all: 'one', one: 'off' }[repeat]; paintModes(); }
      });
      const paintModes = () => {
        $$('[data-act="shuffle"]').forEach(b => b.setAttribute('aria-pressed', shuffle));
        $$('[data-act="repeat"]').forEach(b => {
          b.dataset.mode = repeat;
          b.setAttribute('aria-pressed', repeat !== 'off');
          if (b.dataset.tip) b.dataset.tip = Akari.t({ off: 'Wiederholen: aus', all: 'Wiederholen: alle', one: 'Wiederholen: diesen' }[repeat]);
        });
      };
      win.body.addEventListener('keydown', e => {
        const song = e.target.closest?.('.mu__song');
        if (song && e.key === 'Enter') { song.click(); return; }
        if (e.target.closest('input, textarea, [role="slider"]')) return;
        if (e.key === ' ') { e.preventDefault(); toggle(); }
        if (e.key === 'Escape' && !$('[data-full]').hidden) setFull(false);
      });
      // the search: in the list here; on the server, asked there (a moment after typing stops)
      let qT;
      main.addEventListener('input', e => {
        if (!e.target.matches('[data-q]')) return;
        route.q = e.target.value;
        clearTimeout(qT);
        qT = setTimeout(async () => { if (source === 'server') await loadServer(route.q); render(); }, source === 'server' ? 350 : 120);
      });
      main.addEventListener('submit', async e => {
        if (!e.target.matches('[data-connect]')) return;
        e.preventDefault();
        const f = e.target.elements, msg = e.target.querySelector('[data-connect-msg]');
        msg.textContent = Akari.t('Verbinde …');
        try {
          await Akari.api('/api/audio/subsonic', { method: 'PUT', json: { url: f.url.value, user: f.user.value, password: f.password.value }, quiet: true });
          await loadServerState();
          await loadServer('');
          go('home', {}, false);
        } catch (err) { msg.textContent = err.message; }
      });
      // the server's line in the sidebar: a right-click to let it go
      $('[data-srv]').addEventListener('contextmenu', e => Akari.menu?.(e, [{ label: 'Server trennen', icon: 'i-x', danger: true, act: async () => {
        await Akari.api('/api/audio/subsonic', { method: 'DELETE', quiet: true }).catch(() => {});
        server = null; lists.server = []; await loadServerState(); render();
      } }]));

      paintVol();
      paintTime();
      paintModes();
      show();
      // a file handed over (from Dateien): play it once the library is in
      const playPath = async path => {
        if (source !== 'local') { source = 'local'; }
        if (!lists.local.some(t => t.path === path)) await loadLocal();
        const t = lists.local.find(x => x.path === path);
        if (!t) {                                            // outside the library: play it all the same
          const name = path.split('/').pop().replace(/\.[^.]+$/, '');
          return play([{ path, title: name, folder: path.split('/').slice(0, -1).join('/'), picture: false }], 0);
        }
        const a = albums(lists.local).find(x => x.key === albumKey(t));
        go('album', { key: a.key });
        play(a.tracks, a.tracks.indexOf(t));
      };
      Promise.all([loadLocal(), loadServerState()]).then(() => {
        render();
        if (args.path) playPath(args.path);
      });

      // narrow windows: the sidebar becomes a strip of icons (an element cannot ask its own width in CSS)
      const fit = () => win.body.classList.toggle('is-narrow', win.body.clientWidth < 720);
      requestAnimationFrame(fit);

      return {
        resize: fit,
        args: a => { if (a?.path) playPath(a.path); },
        focus: () => main.focus({ preventScroll: true }),
        close: () => {
          cancelAnimationFrame(raf);
          audio.pause();
          audio.removeAttribute('src');
          audio.load();
          ctx?.close?.();
          Akari.mediaLocal?.(null);
          if ('mediaSession' in navigator) { try { navigator.mediaSession.metadata = null; } catch {} }
          return true;
        },
      };
    },
  });
})();
