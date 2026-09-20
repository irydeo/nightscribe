/* ============================================================
 * NightScribe Landing Page — Observatory Terminal
 * Handles: reticle cursor + spotlight, altitude scale,
 * control-bar clock (GMST/RA), language toggle (ES/EN),
 * scroll reveal, accordion (OBSERVE), active nav.
 * ============================================================ */

(() => {
  'use strict';

  const STORAGE_KEY = 'nightscribe-lang';
  const LANGS = ['en', 'es'];

  // Mark JS active (enables reveal/hidden styles)
  document.documentElement.classList.remove('no-js');
  document.documentElement.classList.add('js');

  // Central i18n dictionary (all texts live in js/i18n.js)
  const I18N = window.I18N || {};

  /* ---------------- Language toggle ---------------- */
  const langToggle = document.getElementById('lang-toggle');
  const langLabel = document.querySelector('.lang-label');
  const html = document.documentElement;

  function currentLang() {
    return html.dataset.lang === 'es' ? 'es' : 'en';
  }

  function i18n(lang, key) {
    return (I18N[lang] && I18N[lang][key]) || '';
  }

  function applyLang(lang) {
    if (!LANGS.includes(lang)) lang = 'en';
    html.setAttribute('lang', lang);
    html.dataset.lang = lang;

    // Apply dictionary strings: every [data-i18n] element
    document.querySelectorAll('[data-i18n]').forEach((el) => {
      const key = el.getAttribute('data-i18n');
      const value = i18n(lang, key);
      if (value !== '') el.textContent = value;
    });

    // OBSERVE/HIDE labels reflect state
    document.querySelectorAll('.btn-observe').forEach((btn) => {
      const block = btn.closest('.feature-block');
      const expanded = block ? block.classList.contains('expanded') : false;
      const label = btn.querySelector('.observe-label');
      if (label) label.textContent = i18n(lang, expanded ? 'ui.hide' : 'ui.observe');
    });

    // Toggle button shows the language you switch TO
    if (langLabel) {
      langLabel.textContent = lang === 'es' ? 'EN' : 'ES';
      langLabel.title = i18n(lang, lang === 'es' ? 'ui.toggle.toEn' : 'ui.toggle.toEs');
    }

    try { localStorage.setItem(STORAGE_KEY, lang); } catch (_) {}
  }

  langToggle?.addEventListener('click', () => {
    applyLang(currentLang() === 'es' ? 'en' : 'es');
  });

  // Initial language: stored > browser > english
  let storedLang = null;
  try { storedLang = localStorage.getItem(STORAGE_KEY); } catch (_) {}

  let initialLang = 'en';
  if (storedLang === 'es' || storedLang === 'en') {
    initialLang = storedLang;
  } else {
    try {
      initialLang = (navigator.language || 'en').toLowerCase().startsWith('es') ? 'es' : 'en';
    } catch (_) { initialLang = 'en'; }
  }
  applyLang(initialLang);

  /* ---------------- Reticle cursor + spotlight ---------------- */
  const reticle = document.getElementById('reticle');
  const spotlight = document.getElementById('spotlight');
  const finePointer = window.matchMedia('(pointer: fine)').matches;

  if (finePointer && reticle && spotlight) {
    document.body.classList.add('reticle-active');

    let rafPending = false;
    window.addEventListener('mousemove', (e) => {
      if (rafPending) return;
      rafPending = true;
      requestAnimationFrame(() => {
        const t = `translate(${e.clientX}px, ${e.clientY}px) translate(-50%, -50%)`;
        reticle.style.transform = t;
        spotlight.style.transform = t;
        rafPending = false;
      });
    });
  }

  /* ---------------- Altitude scale (scroll progress) ---------------- */
  const altFill = document.getElementById('alt-fill');
  const altBubble = document.getElementById('alt-bubble');
  const altReadout = document.getElementById('alt-readout');

  function updateAltitude() {
    if (!altFill || !altBubble || !altReadout) return;
    const doc = document.documentElement;
    const max = doc.scrollHeight - window.innerHeight;
    const p = max > 0 ? Math.min(1, Math.max(0, window.scrollY / max)) : 0;
    const deg = Math.round(p * 90);

    altFill.style.height = `${p * 100}%`;
    altBubble.style.bottom = `${p * 100}%`;
    altReadout.textContent = `${deg}°`;
  }
  window.addEventListener('scroll', updateAltitude, { passive: true });
  updateAltitude();

  /* ---------------- Control bar: GMST/RA + UTC clock ---------------- */
  const coordsEl = document.getElementById('cb-coords');
  const clockEl = document.getElementById('cb-clock');
  const pad = (n) => String(n).padStart(2, '0');

  function updateClock() {
    const now = new Date();
    if (clockEl) {
      clockEl.textContent =
        `${pad(now.getUTCHours())}:${pad(now.getUTCMinutes())}:${pad(now.getUTCSeconds())} UTC`;
    }
    if (coordsEl) {
      // Approximate GMST (low precision, cosmetic)
      const j2000 = Date.UTC(2000, 0, 1, 12, 0, 0);
      const d = (now.getTime() - j2000) / 86400000;
      const gmstDeg = ((280.46061837 + 360.98564736629 * d) % 360 + 360) % 360;
      const gmstH = gmstDeg * 24 / 360;
      const h = Math.floor(gmstH) % 24;
      const m = Math.floor((gmstH - Math.floor(gmstH)) * 60);
      const s = Math.round(((gmstH - Math.floor(gmstH)) * 60 - m) * 60);
      coordsEl.textContent = `RA ${pad(h)}:${pad(m)}:${pad(s === 60 ? 0 : s)} +00°00'`;
    }
  }
  setInterval(updateClock, 1000);
  updateClock();

  /* ---------------- Control bar visibility ---------------- */
  const controlBar = document.getElementById('control-bar');

  function updateBar() {
    const hero = document.getElementById('hero');
    const heroBottom = hero ? hero.offsetHeight * 0.55 : 600;
    controlBar?.classList.toggle('visible', window.scrollY > heroBottom);
  }
  window.addEventListener('scroll', updateBar, { passive: true });
  updateBar();

  /* ---------------- Scroll reveal ---------------- */
  const revealObserver = new IntersectionObserver((entries) => {
    for (const entry of entries) {
      if (entry.isIntersecting) {
        entry.target.classList.add('revealed');
        revealObserver.unobserve(entry.target);
      }
    }
  }, { threshold: 0.1, rootMargin: '0px 0px -50px 0px' });

  document.querySelectorAll(
    '.features, .sources-section, .about-section, .section-header, .feature-block'
  ).forEach((el) => revealObserver.observe(el));

  /* ---------------- Accordion (OBSERVE / title) ---------------- */
  function setExpanded(block) {
    const expanded = block.classList.toggle('expanded');
    const btn = block.querySelector('.btn-observe');
    if (btn) btn.setAttribute('aria-expanded', String(expanded));

    const lang = currentLang();
    const label = btn?.querySelector('.observe-label');
    if (label) label.textContent = i18n(lang, expanded ? 'ui.hide' : 'ui.observe');
  }

  document.querySelectorAll('.feature-block').forEach((block) => {
    const btn = block.querySelector('.btn-observe');
    const title = block.querySelector('.feature-title');

    const toggle = () => {
      // Close all others
      document.querySelectorAll('.feature-block.expanded').forEach((b) => {
        if (b !== block) setExpanded(b);
      });
      setExpanded(block);
      title?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    };

    btn?.addEventListener('click', (e) => { e.stopPropagation(); toggle(); });
    title?.addEventListener('click', toggle);
  });

  /* ---------------- Smooth anchor scrolling ---------------- */
  document.querySelectorAll('a[href^="#"]').forEach((anchor) => {
    anchor.addEventListener('click', (e) => {
      const targetId = anchor.getAttribute('href');
      if (targetId === '#') return; // placeholder links
      const target = document.querySelector(targetId);
      if (target) {
        e.preventDefault();
        target.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
    });
  });

  /* ---------------- Active nav link ---------------- */
  const navLinks = document.querySelectorAll('.nav-link');
  const navObserver = new IntersectionObserver((entries) => {
    for (const entry of entries) {
      if (entry.isIntersecting) {
        navLinks.forEach((link) => {
          const href = link.getAttribute('href');
          link.classList.toggle('active', href === `#${entry.target.id}`);
        });
      }
    }
  }, { threshold: 0.35 });

  ['hero', 'features', 'sources', 'about'].forEach((id) => {
    const el = document.getElementById(id);
    if (el) navObserver.observe(el);
  });
})();