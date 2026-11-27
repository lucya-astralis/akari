/* The login screen of Akari OS: pick an account, type the password; on the
   very first start, make the first account with the token from the log. */
(() => {
  const $ = s => document.querySelector(s);
  const esc = s => String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const token = new URLSearchParams(location.search).get('token');
  if (token) history.replaceState(null, '', '/');     // the token does not stay in the address bar

  const post = async (url, json) => {
    const r = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(json) });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Das hat nicht geklappt.');
    return data;
  };

  // the theme a person chose on the desktop, if this browser remembers it
  try {
    const p = JSON.parse(localStorage.getItem('akari-prefs-last') || '{}');
    if (p.tint) document.documentElement.dataset.tint = p.tint;
    const side = p.nova || (p.mirror ? 'right' : 'both');   // a new account: Nova from both sides
    if (side === 'right') document.documentElement.setAttribute('data-mirror', '');
    if (side === 'both') document.documentElement.setAttribute('data-nova', 'both');
    if (p.cursors === false) document.documentElement.setAttribute('data-cursors', 'off');
    if (p.tint === 'custom' && Number.isFinite(+p.tintH)) document.documentElement.style.setProperty('--akari-h', +p.tintH);
  } catch {}

  // an account's face: its picture if it has one, else its initial
  const face = (el, who) => {
    if (!el) return;
    el.textContent = '';
    el.classList.toggle('has-img', !!who.avatar);
    if (who.avatar) { const i = new Image(); i.src = who.avatar; i.alt = ''; el.append(i); } else el.textContent = who.initial;
  };

  // the language, switched right here (the page reloads in it)
  const L = window.AkariI18n;
  if (L) {
    $('#lang').textContent = L.lang().toUpperCase();
    $('#lang').addEventListener('click', () => L.set(L.lang() === 'de' ? 'en' : 'de'));
  } else $('#lang').hidden = true;

  const tick = () => {
    const d = new Date();
    $('#time').textContent = d.toLocaleTimeString(window.AkariI18n?.locale() || 'de-DE', { hour: '2-digit', minute: '2-digit' });
    $('#date').textContent = d.toLocaleDateString(window.AkariI18n?.locale() || 'de-DE', { weekday: 'long', day: 'numeric', month: 'long' });
    $('#time').setAttribute('datetime', d.toISOString());
  };
  tick(); setInterval(tick, 1000);

  const show = id => {
    ['#pick', '#login', '#desks', '#setup', '#need-token'].forEach(s => { $(s).hidden = s !== id; });
    const card = $(id);
    card.classList.remove('is-in'); void card.offsetWidth; card.classList.add('is-in');
  };

  let accounts = [];
  const pick = a => {
    face($('#login-avatar'), a);
    $('#login-name').textContent = a.fullname;
    $('#login-user').textContent = a.active ? `${a.name} · angemeldet` : a.name;
    $('#username').value = a.name;
    $('#password').value = '';
    $('#pw-field').classList.remove('is-error'); $('#pw-msg').hidden = true;
    $('#back').hidden = accounts.length < 2;
    show('#login');
    $('#password').focus();
  };

  /* which desktop: after the password, or from "Desktop wechseln" */
  const enter = () => { document.body.classList.add('is-leaving'); setTimeout(() => location.replace('/'), 380); };
  const ago = t => {
    const d = new Date(t * 1000), now = new Date();
    return d.toDateString() === now.toDateString()
      ? `heute ${d.toLocaleTimeString(window.AkariI18n?.locale() || 'de-DE', { hour: '2-digit', minute: '2-digit' })}`
      : d.toLocaleDateString(window.AkariI18n?.locale() || 'de-DE', { day: 'numeric', month: 'short' });
  };
  let desks = [];
  const chooser = async (who, ask) => {
    // a failure is never "no desktops": that would make a new one every time
    const res = await fetch('/api/desktops').catch(() => null);
    const r = res && res.ok ? await res.json().catch(() => null) : null;
    if (!r) { $('#date').textContent = 'Die Desktops lassen sich gerade nicht laden. Lade die Seite neu.'; return; }
    desks = r.desktops || [];
    if (!desks.length) { await post('/api/session/desktop', { name: 'Standard' }); return enter(); }
    if (desks.length === 1 && !ask) { await post('/api/session/desktop', { id: desks[0].id }); return enter(); }
    face($('#desks-avatar'), who);
    $('#desks-name').textContent = who.fullname;
    $('#desk-list').innerHTML = desks.map((d, i) => `
      <button class="dpick" role="listitem" data-d="${i}">
        <span class="dpick__name">${esc(d.name)}</span>
        <small>${d.apps.length ? `<span class="f-status">${esc(d.apps.join(', '))} läuft</span>` : `zuletzt ${ago(d.last)}`}</small>
      </button>`).join('');
    show('#desks');
  };
  $('#desk-list').addEventListener('click', async e => {
    const b = e.target.closest('[data-d]'); if (!b) return;
    try { await post('/api/session/desktop', { id: desks[+b.dataset.d].id }); enter(); } catch (err) { alert(err.message); }
  });
  $('#desk-new').addEventListener('submit', async e => {
    e.preventDefault();
    try { await post('/api/session/desktop', { name: e.target.elements.desk.value }); enter(); } catch (err) { alert(err.message); }
  });
  $('#desk-other').addEventListener('click', async () => {
    await post('/api/logout', { mode: 'switch' }).catch(() => {});
    location.replace('/');
  });

  const load = async () => {
    let st;
    try { st = await fetch('/api/login/state').then(r => r.json()); }
    catch { $('#date').textContent = 'Akari OS antwortet nicht.'; return; }
    $('#os-name').textContent = st.os;
    $('#host').textContent = st.hostname;
    document.title = `${st.os} · Anmelden`;
    if (st.setup) return show(token ? '#setup' : '#need-token');
    if (st.signed_in && !st.desktop) return chooser(st.signed_in, true);
    accounts = st.accounts;
    $('#lucent-in').hidden = $('#lucent-in2').hidden = !st.lucent;
    // back from Lucent without a session: say why
    const lu = new URLSearchParams(location.search).get('lucent');
    if (lu) {
      history.replaceState(null, '', '/');
      const why = {
        unbekannt: 'Dieses Lucent-Konto ist mit keinem Konto hier verknüpft. Melde dich einmal mit Passwort an und verknüpfe es unter Einstellungen → Lucent.',
        abgelehnt: 'Lucent hat die Anmeldung abgelehnt.', abgelaufen: 'Die Anmeldung über Lucent hat zu lange gedauert. Noch einmal, bitte.',
      }[lu] || 'Anmelden mit Lucent hat nicht geklappt.';
      setTimeout(() => { $('#date').textContent = window.AkariI18n?.t?.(why) || why; $('#date').classList.add('is-note'); }, 0);
    }
    $('#who').innerHTML = accounts.map((a, i) => `
      <button class="who__one" role="listitem" data-i="${i}" style="--i:${i}">
        <span class="f-avatar f-avatar--lg">${esc(a.initial)}</span>
        <span class="who__txt"><b>${esc(a.fullname)}</b>${a.active ? '<small><span class="f-status">angemeldet</span></small>' : ''}</span>
      </button>`).join('');
    accounts.forEach((a, i) => face($('#who').children[i]?.querySelector('.f-avatar'), a));
    if (accounts.length === 1) pick(accounts[0]); else show('#pick');
  };

  $('#who').addEventListener('click', e => { const b = e.target.closest('[data-i]'); if (b) pick(accounts[+b.dataset.i]); });
  $('#back').addEventListener('click', () => show('#pick'));

  $('#login').addEventListener('submit', async e => {
    e.preventDefault();
    const go = $('#go');
    go.disabled = true;
    $('#login').classList.add('is-busy');
    try {
      const who = await post('/api/login', { name: $('#username').value, password: $('#password').value });
      await chooser(who, false);
    } catch (err) {
      $('#pw-field').classList.add('is-error');
      $('#pw-msg').textContent = err.message; $('#pw-msg').hidden = false;
      const card = $('#login'); card.classList.remove('is-shake'); void card.offsetWidth; card.classList.add('is-shake');
      $('#password').select();
    } finally {
      go.disabled = false;
      $('#login').classList.remove('is-busy');
    }
  });

  // setup: the user name follows the full name until it is typed itself
  const f = $('#setup'), F = f.elements;
  let typed = false;
  F['name'].addEventListener('input', () => { typed = true; });
  F.fullname.addEventListener('input', () => {
    if (typed) return;
    F['name'].value = F.fullname.value.toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '')
      .replace(/ß/g, 'ss').split(/\s+/)[0].replace(/[^a-z0-9_-]/g, '').replace(/^[^a-z]+/, '').slice(0, 32);
  });
  f.addEventListener('submit', async e => {
    e.preventDefault();
    const pw2 = $('#setup-pw2-field');
    const same = F.password.value === F.password2.value;
    pw2.classList.toggle('is-error', !same);
    pw2.querySelector('small').hidden = same;
    pw2.querySelector('small').textContent = 'Die beiden Passwörter sind nicht gleich.';
    if (!same) return;
    $('#setup-msg').textContent = 'Lege Konto und Home an …';
    try {
      const who = await post('/api/login/setup', { token, name: F['name'].value, fullname: F.fullname.value, password: F.password.value });
      await chooser(who, false);
    } catch (err) {
      $('#setup-msg').textContent = err.message;
    }
  });

  load().finally(() => window.AkariBoot?.done());
})();
