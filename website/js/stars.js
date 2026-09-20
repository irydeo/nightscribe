/* ============================================================
 * NightScribe Landing Page — Star Field Background
 * Renders a subtle twinkling star field on a fixed canvas.
 * Uses requestAnimationFrame only while visible (perf-friendly).
 * ============================================================ */

(() => {
  'use strict';

  const canvas = document.getElementById('stars-canvas');
  if (!canvas) return;

  const ctx = canvas.getContext('2d');

  // Star count scales with viewport size (clamped)
  const STAR_BASE = 160;
  const MAX_STARS = 240;

  let stars = [];
  let width = 0;
  let height = 0;
  let rafId = null;
  let running = false;

  // ---- helpers ----
  const rand = (min, max) => min + Math.random() * (max - min);

  function resize() {
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    width = window.innerWidth;
    height = window.innerHeight;
    canvas.width = width * dpr;
    canvas.height = height * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    const count = Math.min(STAR_BASE + Math.floor(width / 9), MAX_STARS);
    stars = Array.from({ length: count }, () => ({
      x: rand(0, width),
      y: rand(0, height),
      r: rand(0.4, 1.5),
      baseAlpha: rand(0.08, 0.5),
      twinkleSpeed: rand(0.02, 0.06),
      phase: rand(0, Math.PI * 2),
      // Cool blue-white tint to match the navy palette
      hue: Math.random() < 0.45 ? rand(350, 30) : 0,
    }));
  }

  function draw(timestamp) {
    ctx.clearRect(0, 0, width, height);

    const t = timestamp * 0.001;
    for (const star of stars) {
      const alpha = star.baseAlpha * (0.5 + 0.5 * Math.sin(t * star.twinkleSpeed * 60 + star.phase));
      if (alpha <= 0.02) continue;

      ctx.beginPath();
      ctx.arc(star.x, star.y, star.r, 0, Math.PI * 2);
      ctx.fillStyle = star.hue
        ? `hsla(${star.hue}, 45%, 84%, ${alpha})`
        : `rgba(235, 224, 210, ${alpha})`;
      ctx.fill();
    }

    rafId = requestAnimationFrame(draw);
  }

  function start() {
    if (running) return;
    running = true;
    rafId = requestAnimationFrame(draw);
  }

  function stop() {
    running = false;
    if (rafId) {
      cancelAnimationFrame(rafId);
      rafId = null;
    }
    ctx.clearRect(0, 0, width, height);
  }

  // Pause rendering when the tab is hidden (cheap idle)
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) stop();
    else start();
  });

  window.addEventListener('resize', () => { resize(); });

  // Respect reduced-motion preference: static stars only
  const prefersReduced = window.matchMedia('(prefers-reduced-motion: reduce)');
  if (prefersReduced.matches) {
    resize();
    ctx.clearRect(0, 0, width, height);
    for (const star of stars) {
      ctx.beginPath();
      ctx.arc(star.x, star.y, star.r, 0, Math.PI * 2);
      ctx.fillStyle = star.hue
        ? `hsla(${star.hue}, 45%, 84%, ${star.baseAlpha})`
        : `rgba(235, 224, 210, ${star.baseAlpha})`;
      ctx.fill();
    }
  } else {
    resize();
    start();
  }
})();