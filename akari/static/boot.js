/* AKARI: before the first picture. Loaded blocking in <head> of both pages.

   The look a person chose (theme, accent, Nova's side, cursors) is known on
   the server only after the page has drawn. Until then Nova would show Facet's
   violet and then glide into the real colour, on the login screen and again on
   every reload. So the last look this browser saw (localStorage, written by the
   desktop) goes onto <html> now, and while the page starts nothing glides
   (.is-booting). AkariBoot.done() ends that once the real look is applied. */
(() => {
  const root = document.documentElement;
  root.classList.add('is-booting');
  try {
    const theme = localStorage.getItem('facet-theme');
    // nothing chosen in this browser yet: light, as a new account starts (akari.js DEFAULTS)
    if (theme === 'light' || theme === 'dark') root.dataset.theme = theme;
    else if (!theme) root.dataset.theme = 'light';
    const p = JSON.parse(localStorage.getItem('akari-prefs-last') || '{}');
    if (p.tint) root.dataset.tint = p.tint;
    if (p.tint === 'custom' && Number.isFinite(+p.tintH)) root.style.setProperty('--akari-h', +p.tintH);
    const side = p.nova || (p.mirror ? 'right' : 'both');   // a new account: Nova from both sides
    if (side === 'right') root.setAttribute('data-mirror', '');
    if (side === 'both') root.setAttribute('data-nova', 'both');
    if (p.cursors === false) root.setAttribute('data-cursors', 'off');
  } catch {}
  let ended = false;
  const done = () => {
    if (ended) return;
    ended = true;
    requestAnimationFrame(() => requestAnimationFrame(() => root.classList.remove('is-booting')));
  };
  setTimeout(done, 5000);           // never stuck, whatever happens while starting
  window.AkariBoot = { done };
})();
