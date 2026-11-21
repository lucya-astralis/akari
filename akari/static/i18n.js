/* AKARI: languages. German is the source; i18n/en.js holds English.

   Every visible text, placeholder, aria-label, tooltip (data-tip) and title
   is looked up as it appears, including what apps add later (a
   MutationObserver), first exactly, then by the patterns for texts with
   values in them ("Firefox läuft"). Code that builds text itself calls
   AkariI18n.t(). Anything inside [translate="no"] stays as it is: file and
   folder names, user and desktop names, terminal output.

   The choice lives in localStorage (it must be known before the first
   paint, also on the login screen); without one, the browser's language. */
(() => {
  const KEY = 'akari-lang';
  let lang = 'de';
  try { lang = localStorage.getItem(KEY) || ((navigator.language || 'de').slice(0, 2) === 'de' ? 'de' : 'en'); } catch {}
  if (!['de', 'en'].includes(lang)) lang = 'de';
  const EN = window.AKARI_EN || { exact: {}, rules: [] };
  const ATTRS = ['placeholder', 'aria-label', 'data-tip', 'title', 'data-label'];
  const SKIP = new Set(['SCRIPT', 'STYLE', 'TEXTAREA', 'CODE', 'PRE', 'TIME']);

  const t = s => {
    if (lang !== 'en' || typeof s !== 'string') return s;
    const k = s.trim();
    if (!k) return s;
    let v = EN.exact[k];
    if (v === undefined) {
      for (const [re, rep] of EN.rules) {
        if (re.test(k)) { v = k.replace(re, rep); break; }
      }
    }
    return v === undefined ? s : s.replace(k, v);
  };

  const off = el => !el || el.closest?.('[translate="no"], .xterm') || SKIP.has(el.nodeName);
  const textNode = n => { if (!off(n.parentElement)) { const v = t(n.data); if (v !== n.data) n.data = v; } };
  const element = el => {
    if (off(el)) return;
    for (const a of ATTRS) {
      const v = el.getAttribute(a);
      if (v) { const w = t(v); if (w !== v) el.setAttribute(a, w); }
    }
  };
  const walk = root => {
    if (lang !== 'en' || !root) return;
    if (root.nodeType === 3) return textNode(root);
    if (root.nodeType !== 1 && root.nodeType !== 11) return;
    if (root.nodeType === 1) element(root);
    const w = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT);
    for (let n = w.nextNode(); n; n = w.nextNode()) {
      if (n.nodeType === 3) textNode(n);
      else { element(n); if (n.nodeName === 'TEMPLATE') walk(n.content); }
    }
  };

  window.AkariI18n = {
    t, walk,
    lang: () => lang,
    locale: () => (lang === 'en' ? 'en-GB' : 'de-DE'),
    set(l) { try { localStorage.setItem(KEY, l); } catch {} location.reload(); },
  };
  document.documentElement.lang = lang;

  if (lang === 'en') {
    const start = () => {
      walk(document.documentElement);
      new MutationObserver(ms => ms.forEach(m => {
        if (m.type === 'attributes') element(m.target);
        else m.addedNodes.forEach(walk);
      })).observe(document.documentElement, { childList: true, subtree: true, attributes: true, attributeFilter: ATTRS });
    };
    document.readyState === 'loading' ? document.addEventListener('DOMContentLoaded', start) : start();
  }
})();
