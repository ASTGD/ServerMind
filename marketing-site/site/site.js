/* ServerAlly marketing site — one shared script. No dependencies, no network. */
(function () {
  'use strict';
  document.documentElement.classList.remove('no-js');

  var reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  /* ---------- Theme (dark is primary; both correct) ---------- */
  var root = document.documentElement;
  function setTheme(t) {
    root.setAttribute('data-theme', t);
    try { localStorage.setItem('sa-theme', t); } catch (e) {}
  }
  var themeBtn = document.querySelector('[data-theme-toggle]');
  if (themeBtn) {
    themeBtn.addEventListener('click', function () {
      setTheme(root.getAttribute('data-theme') === 'dark' ? 'light' : 'dark');
    });
  }

  /* ---------- Mobile nav ---------- */
  var burger = document.querySelector('.nav-burger');
  var menu = document.querySelector('.mobile-menu');
  if (burger && menu) {
    burger.addEventListener('click', function () {
      var open = menu.classList.toggle('open');
      burger.setAttribute('aria-expanded', open ? 'true' : 'false');
    });
  }

  /* ---------- Reveal on scroll ---------- */
  var revealEls = document.querySelectorAll('[data-reveal]');
  if (revealEls.length) {
    if (reduceMotion || !('IntersectionObserver' in window)) {
      revealEls.forEach(function (el) { el.classList.add('revealed'); });
    } else {
      var ro = new IntersectionObserver(function (entries) {
        entries.forEach(function (en) {
          if (en.isIntersecting) { en.target.classList.add('revealed'); ro.unobserve(en.target); }
        });
      }, { threshold: 0.12, rootMargin: '0px 0px -40px 0px' });
      revealEls.forEach(function (el) { ro.observe(el); });
    }
  }

  /* ---------- Scene sequencer (How It Works) ----------
     Elements with [data-seq] inside a .scene reveal in order.
     An element with [data-gate="approve"] pauses the sequence until Approve. */
  var scenes = document.querySelectorAll('.scene');
  scenes.forEach(function (scene) {
    var items = Array.prototype.slice.call(scene.querySelectorAll('[data-seq]'))
      .sort(function (a, b) { return (+a.dataset.seq) - (+b.dataset.seq); });
    if (!items.length) return;

    var idx = 0, started = false, timer = null;

    function showItem(el) {
      el.classList.add('shown');
      if (el.hasAttribute('data-land')) el.classList.add('land');
      var dots = el.querySelector('.typing-dots');
      var text = el.querySelector('.msg-text');
      if (dots && text && !reduceMotion) {
        text.style.display = 'none';
        dots.style.display = 'inline-flex';
        setTimeout(function () { dots.style.display = 'none'; text.style.display = ''; }, 650);
      } else if (dots) { dots.style.display = 'none'; }
    }

    function step() {
      if (idx >= items.length) return;
      var el = items[idx];
      showItem(el);
      idx++;
      if (el.dataset.gate === 'approve') return; /* wait for the click */
      if (idx < items.length) timer = setTimeout(step, reduceMotion ? 0 : 900);
    }

    function startScene() {
      if (started) return; started = true;
      if (reduceMotion) { items.forEach(showItem); idx = items.length; markApprovedStatic(scene); return; }
      step();
    }

    function markApprovedStatic(sc) {
      /* reduced motion: render the end state, keep the buttons usable but resolved */
      var box = sc.querySelector('.approve-box'); if (!box) return;
      var done = box.querySelector('.approve-done'); var act = box.querySelector('.approve-actions');
      if (done && act) { act.style.display = 'none'; done.style.display = 'inline-flex'; }
    }

    if (!('IntersectionObserver' in window)) { startScene(); }
    else {
      var so = new IntersectionObserver(function (entries) {
        entries.forEach(function (en) { if (en.isIntersecting) { startScene(); so.disconnect(); } });
      }, { threshold: 0.25 });
      so.observe(scene);
    }

    /* Approve / pause interaction */
    var approveBtn = scene.querySelector('[data-approve]');
    var stopBtn = scene.querySelector('[data-stop]');
    var approveBox = scene.querySelector('.approve-box');
    function resolveApprove() {
      if (!approveBox) return;
      var act = approveBox.querySelector('.approve-actions');
      var done = approveBox.querySelector('.approve-done');
      var paused = approveBox.querySelector('.approve-paused');
      if (act) act.style.display = 'none';
      if (paused) paused.style.display = 'none';
      if (done) done.style.display = 'inline-flex';
      if (idx < items.length && !timer) step(); else if (idx < items.length) { clearTimeout(timer); step(); }
    }
    if (approveBtn) approveBtn.addEventListener('click', resolveApprove);
    if (stopBtn) stopBtn.addEventListener('click', function () {
      var act = approveBox.querySelector('.approve-actions');
      var paused = approveBox.querySelector('.approve-paused');
      if (act) act.style.display = 'none';
      if (paused) paused.style.display = 'flex';
      var resume = approveBox.querySelector('[data-resume]');
      if (resume) resume.addEventListener('click', resolveApprove, { once: true });
    });
  });

  /* ---------- Scene rail highlighting ---------- */
  var rail = document.querySelector('.scene-rail');
  if (rail && 'IntersectionObserver' in window) {
    var links = rail.querySelectorAll('a[href^="#"]');
    var map = {};
    links.forEach(function (a) { map[a.getAttribute('href').slice(1)] = a; });
    var railObs = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        if (en.isIntersecting) {
          links.forEach(function (a) { a.classList.remove('active'); });
          var a = map[en.target.id]; if (a) a.classList.add('active');
        }
      });
    }, { rootMargin: '-30% 0px -55% 0px' });
    document.querySelectorAll('.scene[id]').forEach(function (s) { railObs.observe(s); });
  }

  /* ---------- GIF: lazy, poster-first, click-to-play (never autoplay) ---------- */
  document.querySelectorAll('[data-gif]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      if (btn.dataset.playing === '1') return;
      btn.dataset.playing = '1';
      var img = document.createElement('img');
      var res = window.__resources && btn.dataset.gifRes ? window.__resources[btn.dataset.gifRes] : null;
      img.src = res || btn.dataset.gif;
      img.alt = btn.dataset.gifAlt || 'Recording: Ally quarantines webshell files, then verifies the site responds HTTP 200.';
      img.style.width = '100%';
      img.style.display = 'block';
      btn.replaceChildren(img);
      btn.style.cursor = 'default';
      btn.setAttribute('aria-label', 'Recording playing');
    });
  });

  /* ---------- Footer year ---------- */
  var yr = document.querySelector('[data-year]');
  if (yr) yr.textContent = String(new Date().getFullYear());
})();
