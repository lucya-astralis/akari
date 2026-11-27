/* AKARI: the accent colour where CSS cannot reach it.

   The cursors are pictures (assets/cursors/*.svg, drawn by tools/cursors.py)
   with one accent colour baked in. CSS cannot recolour a cursor, so this swaps
   that colour for the current accent (tint, light or dark) and hands the
   pictures to cursors.css as data: URLs through its --cur-… variables. With
   the own cursors off, nothing is set and cursors.css falls back by itself.

   hex() is the accent as #rrggbb, for whoever needs it outside CSS (the
   terminal passes it on to fastfetch). Used on the desktop and the login screen. */
(() => {
  const DRAWN = '#5663f0';                      // the accent the pictures were drawn with
  const SET = {                                 // name: hotspot (as in cursors.css)
    default: '4 3', pointer: '4 3', help: '4 3', progress: '4 3',
    text: '16 16', move: '16 16', grab: '16 16', grabbing: '16 16', crosshair: '16 16',
    'ew-resize': '16 16', 'ns-resize': '16 16', 'nwse-resize': '16 16', 'nesw-resize': '16 16',
    wait: '16 16', 'not-allowed': '16 16',
  };
  const root = document.documentElement;
  const svgs = {};
  let painted = '';

  // whatever form the browser computes the colour in (rgb, oklch …), a canvas turns it into bytes
  const hex = () => {
    const probe = document.createElement('i');
    probe.style.cssText = 'position:absolute;width:0;height:0;color:var(--acc)';
    (document.body || root).append(probe);
    const c = getComputedStyle(probe).color;
    probe.remove();
    const cv = document.createElement('canvas'); cv.width = cv.height = 1;
    const x = cv.getContext('2d', { willReadFrequently: true });
    x.fillStyle = '#000'; x.fillStyle = c; x.fillRect(0, 0, 1, 1);
    const [r, g, b] = x.getImageData(0, 0, 1, 1).data;
    return `#${[r, g, b].map(v => v.toString(16).padStart(2, '0')).join('')}`;
  };

  const clear = () => Object.keys(SET).forEach(n => root.style.removeProperty(`--cur-${n}`));

  const paint = async () => {
    if (root.getAttribute('data-cursors') === 'off') { clear(); painted = ''; return; }
    const h = hex();
    if (h === painted) return;
    painted = h;
    if (h === DRAWN) return clear();             // the files as they are
    await Promise.all(Object.keys(SET).map(async n => {
      svgs[n] ??= await fetch(`assets/cursors/${n}.svg`).then(r => (r.ok ? r.text() : null)).catch(() => null);
    }));
    if (painted !== h) return;                    // the accent changed again meanwhile
    for (const [n, spot] of Object.entries(SET)) {
      if (!svgs[n]) continue;
      const svg = svgs[n].replaceAll(DRAWN, h).replaceAll(DRAWN.toUpperCase(), h);
      root.style.setProperty(`--cur-${n}`, `url("data:image/svg+xml,${encodeURIComponent(svg)}") ${spot}, ${n}`);
    }
  };

  /* again whenever tint, theme or the cursor switch changes (not on style: paint
     writes that). A new tint glides to its hue (Facet, 0.7 s): painted at once
     the cursors would keep a colour from halfway, so they are painted once more
     when the glide has ended. The rainbow never ends: it is followed every 2 s. */
  /* WebKit (Safari, every browser on an iPad or iPhone) keeps the picture behind
     glass (backdrop-filter) until something about the glass itself changes;
     Nova's colours walking with --tint-h are not such a change, so the glass
     froze in one colour. While the hue walks, the glass's filter gets a hue turn
     too small to see and loses it again (data-glass-tick, see akari.css), three
     times a second: each time WebKit draws what is behind anew. */
  const webkit = /AppleWebKit/.test(navigator.userAgent) && !/Chrome|Chromium|Edg\//.test(navigator.userAgent);
  let t, t2, walk, tick;
  const soon = () => {
    clearTimeout(t); clearTimeout(t2);
    t = setTimeout(paint, 80);
    t2 = setTimeout(paint, 900);
    clearInterval(walk); clearInterval(tick);
    root.removeAttribute('data-glass-tick');
    if (root.dataset.tint === 'rainbow') {
      walk = setInterval(paint, 2000);
      if (webkit && root.dataset.motion !== 'reduced') tick = setInterval(() => root.toggleAttribute('data-glass-tick'), 333);
    }
  };
  new MutationObserver(soon).observe(root, { attributes: true, attributeFilter: ['data-tint', 'data-theme', 'data-cursors', 'data-motion', 'class'] });
  root.addEventListener('transitionend', e => { if (e.target === root && e.propertyName === '--tint-h') paint(); });
  matchMedia('(prefers-color-scheme: dark)').addEventListener('change', soon);
  // a hue of one's own changes by style (--akari-h), which the observer leaves out
  window.addEventListener('akari:hue', soon);
  document.readyState === 'loading' ? document.addEventListener('DOMContentLoaded', soon) : soon();

  window.AkariAccent = { hex, paint };
})();
