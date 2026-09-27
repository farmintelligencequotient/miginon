/* Landing page animations (GSAP).
 *
 * HERO
 * - The background dot grid "twinkles": random dots swell into small
 *   four-point stars with a soft glow and a fading ring, then shrink back.
 *   Moving the mouse over the hero wakes the dots near the cursor, and a
 *   click/tap sends a ripple of stars out from that point.
 * - Intro timeline: headline words rise in, copy/CTAs/stats follow, and the
 *   dashboard card swings up and fills itself in (tiles, rows, check marks).
 * - Idle loops: floating card, breathing glow, CTA shine, status pulse.
 * - Sections below the hero reveal on scroll (ScrollTrigger).
 *
 * LIVE DEMO SECTION
 * - The module chips work as tabs: each one shows a sample-figure panel.
 *   They auto-advance (a thin timer bar runs along the card), pausing on
 *   hover/focus and while the section is off screen.
 * - Panels swap with a count-up number, growing progress bar and icon pop.
 * - "Live" pill ping, drifting background blobs, pulsing rings and a
 *   magnetic pull on the "Explore the live demo" button.
 *
 * All motion is skipped under prefers-reduced-motion or if GSAP fails to load;
 * the page is fully usable without it (the demo chips still switch panels).
 * The `js-hero` class (set in the page head) hides the hero content until the
 * intro timeline has taken over.
 */
(function () {
    'use strict';

    var root = document.documentElement;
    var hero = document.querySelector('[data-hero]');

    function reveal() { root.classList.remove('js-hero'); }

    if (!hero || !window.gsap || window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
        reveal();
        return;
    }

    var gsap = window.gsap;
    if (window.ScrollTrigger) gsap.registerPlugin(window.ScrollTrigger);

    function all(sel, ctx) { return Array.prototype.slice.call((ctx || hero).querySelectorAll(sel)); }
    function one(sel) { return hero.querySelector(sel); }

    // --- Headline: wrap each word so it can rise out of its own clip box -----
    function splitWords(el) {
        var walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
        var nodes = [];
        while (walker.nextNode()) nodes.push(walker.currentNode);
        var words = [];
        nodes.forEach(function (node) {
            var frag = document.createDocumentFragment();
            node.textContent.split(/(\s+)/).forEach(function (part) {
                if (!part) return;
                if (/^\s+$/.test(part)) { frag.appendChild(document.createTextNode(' ')); return; }
                var clip = document.createElement('span');
                clip.style.cssText = 'display:inline-block;overflow:hidden;vertical-align:bottom;padding-bottom:.12em;margin-bottom:-.12em';
                var word = document.createElement('span');
                word.style.display = 'inline-block';
                word.textContent = part;
                clip.appendChild(word);
                frag.appendChild(clip);
                words.push(word);
            });
            node.parentNode.replaceChild(frag, node);
        });
        return words;
    }

    var badge = one('[data-hero-badge]');
    var words = splitWords(one('[data-hero-title]'));
    var fades = all('[data-hero-fade]');
    var ctas = all('[data-hero-ctas] > a');
    var stats = all('[data-hero-stats] > div');
    var stage = one('[data-hero-stage]');
    var card = one('[data-hero-card]');
    var glow = one('[data-hero-glow]');
    var statusPill = one('[data-hero-status]');
    var checks = all('[data-hero-check]');

    // --- Intro timeline ------------------------------------------------------
    var intro = gsap.timeline({ defaults: { ease: 'power3.out' }, onComplete: startIdle });

    intro
        .from(badge, { y: -14, autoAlpha: 0, duration: 0.6 }, 0.1)
        .from(words, { yPercent: 115, rotate: 5, duration: 0.85, stagger: 0.045 }, 0.2)
        .from(fades, { y: 18, autoAlpha: 0, duration: 0.7, stagger: 0.12 }, 0.65)
        .from(ctas, { y: 14, scale: 0.94, autoAlpha: 0, duration: 0.6, stagger: 0.1, ease: 'back.out(1.8)' }, 0.9)
        .from(stats, { y: 14, autoAlpha: 0, duration: 0.5, stagger: 0.06 }, 1.05)
        .add(countUp, 1.1)
        .from(stage, { autoAlpha: 0, duration: 0.01 }, 0.35)
        .from(card, { y: 70, rotateX: 16, rotateY: -12, autoAlpha: 0, duration: 1.2, transformOrigin: '50% 100%' }, 0.35)
        .from(glow, { scale: 0.5, autoAlpha: 0, duration: 1.4 }, 0.45)
        .from(statusPill, { scale: 0, duration: 0.5, ease: 'back.out(2.5)' }, 1.05)
        .from(one('[data-hero-weather]'), { x: -24, autoAlpha: 0, duration: 0.6 }, 1.1)
        .from(one('[data-hero-sun]'), { rotate: -120, scale: 0.3, duration: 0.9, ease: 'back.out(2)' }, 1.15)
        .from(all('[data-hero-tile]'), { y: 20, scale: 0.9, autoAlpha: 0, duration: 0.55, stagger: 0.08, ease: 'back.out(1.6)' }, 1.2)
        .from(all('[data-hero-row]'), { x: 36, autoAlpha: 0, duration: 0.5, stagger: 0.1 }, 1.35)
        .from(checks, { scale: 0, rotate: -60, duration: 0.45, stagger: 0.1, ease: 'back.out(3)' }, 1.6);

    // All start states are applied now, so the head-time hiding can go.
    reveal();

    function countUp() {
        all('[data-count]').forEach(function (el) {
            var target = parseInt(el.getAttribute('data-count'), 10);
            var state = { v: 0 };
            gsap.to(state, {
                v: target, duration: 1.2, ease: 'power2.out',
                onUpdate: function () { el.textContent = Math.round(state.v); }
            });
        });
    }

    // --- Idle loops once the intro has played -----------------------------------
    function startIdle() {
        gsap.to(one('[data-hero-ping]'), { scale: 3.2, autoAlpha: 0, duration: 1.5, repeat: -1, ease: 'power1.out' });
        gsap.to(stage, { y: -9, duration: 3.2, yoyo: true, repeat: -1, ease: 'sine.inOut' });
        gsap.to(glow, { scale: 1.07, opacity: 0.65, duration: 3.6, yoyo: true, repeat: -1, ease: 'sine.inOut' });
        gsap.to(statusPill, { scale: 1.08, duration: 0.35, yoyo: true, repeat: -1, repeatDelay: 2.6, ease: 'power1.inOut' });

        var shine = one('[data-hero-shine]');
        if (shine) {
            gsap.timeline({ repeat: -1, repeatDelay: 3.5 })
                .fromTo(shine, { xPercent: 0, autoAlpha: 0 }, { xPercent: 520, autoAlpha: 1, duration: 0.9, ease: 'power2.inOut' })
                .set(shine, { autoAlpha: 0 });
        }

        // Every few seconds one block row "re-logs" and its check pops.
        (function tick() {
            var c = checks[Math.floor(Math.random() * checks.length)];
            if (c) gsap.fromTo(c, { scale: 1.7, rotate: -25 }, { scale: 1, rotate: 0, duration: 0.6, ease: 'back.out(3)' });
            gsap.delayedCall(2.4 + Math.random() * 2, tick);
        })();

        // Card tilts toward the cursor on large screens with a real pointer.
        if (window.matchMedia('(hover: hover) and (min-width: 1024px)').matches) {
            var tiltX = gsap.quickTo(card, 'rotateX', { duration: 0.8, ease: 'power3.out' });
            var tiltY = gsap.quickTo(card, 'rotateY', { duration: 0.8, ease: 'power3.out' });
            hero.addEventListener('pointermove', function (e) {
                var r = stage.getBoundingClientRect();
                var dx = (e.clientX - (r.left + r.width / 2)) / window.innerWidth;
                var dy = (e.clientY - (r.top + r.height / 2)) / window.innerHeight;
                tiltY(gsap.utils.clamp(-7, 7, dx * 14));
                tiltX(gsap.utils.clamp(-7, 7, -dy * 14));
            });
            hero.addEventListener('pointerleave', function () { tiltX(0); tiltY(0); });
        }
    }

    // --- Twinkling dot grid ------------------------------------------------------
    // Matches the CSS dot layer: radial-gradient dots centred in 26px tiles.
    var canvas = one('[data-hero-stars]');
    var ctx = canvas && canvas.getContext('2d');
    if (!ctx) return;

    var GAP = 26;
    var stars = [];
    var width = 0, height = 0, cols = 0, rows = 0;
    var running = true;

    function resize() {
        var dpr = Math.min(window.devicePixelRatio || 1, 2);
        width = hero.clientWidth;
        height = hero.clientHeight;
        cols = Math.ceil(width / GAP);
        rows = Math.ceil(height / GAP);
        canvas.width = Math.round(width * dpr);
        canvas.height = Math.round(height * dpr);
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    }
    resize();
    var resizeCall;
    window.addEventListener('resize', function () {
        if (resizeCall) resizeCall.kill();
        resizeCall = gsap.delayedCall(0.15, resize);
    });

    function spawn(col, row, delay, big) {
        if (col < 0 || row < 0 || col >= cols || row >= rows) return;
        var s = {
            x: col * GAP + GAP / 2, y: row * GAP + GAP / 2,
            r: 0.8, a: 0, rot: 0, ring: 0, ringA: 0,
            gold: Math.random() < 0.28
        };
        var size = big ? 8 + Math.random() * 3 : 4.5 + Math.random() * 3;
        stars.push(s);
        gsap.timeline({
            delay: delay || 0,
            onComplete: function () { stars.splice(stars.indexOf(s), 1); }
        })
            .to(s, { r: size, a: 1, rot: Math.PI / 4, duration: 0.45, ease: 'back.out(3)' })
            .fromTo(s, { ring: 1, ringA: 0.45 }, { ring: size * 3.2, ringA: 0, duration: 1.1, ease: 'power2.out' }, 0.05)
            .to(s, { r: 0.8, a: 0, rot: Math.PI / 2, duration: 1.1, ease: 'power2.in' }, 0.6);
    }

    function drawStar(s) {
        var rgb = s.gold ? '251,191,36' : '255,255,255';
        if (s.ringA > 0.01) {
            ctx.strokeStyle = 'rgba(' + rgb + ',' + s.ringA + ')';
            ctx.lineWidth = 1;
            ctx.beginPath();
            ctx.arc(s.x, s.y, s.ring, 0, Math.PI * 2);
            ctx.stroke();
        }
        if (s.a < 0.01) return;
        ctx.save();
        ctx.translate(s.x, s.y);
        var halo = s.r * 2.4;
        var g = ctx.createRadialGradient(0, 0, 0, 0, 0, halo);
        g.addColorStop(0, 'rgba(' + rgb + ',' + 0.5 * s.a + ')');
        g.addColorStop(1, 'rgba(' + rgb + ',0)');
        ctx.fillStyle = g;
        ctx.beginPath();
        ctx.arc(0, 0, halo, 0, Math.PI * 2);
        ctx.fill();
        // Four-point sparkle: pinched curves between the tips.
        ctx.rotate(s.rot);
        var r = s.r, k = r * 0.16;
        ctx.fillStyle = 'rgba(' + rgb + ',' + s.a + ')';
        ctx.beginPath();
        ctx.moveTo(0, -r);
        ctx.quadraticCurveTo(k, -k, r, 0);
        ctx.quadraticCurveTo(k, k, 0, r);
        ctx.quadraticCurveTo(-k, k, -r, 0);
        ctx.quadraticCurveTo(-k, -k, 0, -r);
        ctx.fill();
        ctx.restore();
    }

    var dirty = false;
    gsap.ticker.add(function () {
        if (!stars.length && !dirty) return;
        ctx.clearRect(0, 0, width, height);
        stars.forEach(drawStar);
        dirty = stars.length > 0;
    });

    // Ambient twinkles, scaled to the hero's size so phones aren't too busy.
    (function ambient() {
        var max = Math.max(6, Math.round((cols * rows) / 90));
        if (running && stars.length < max) {
            spawn(Math.floor(Math.random() * cols), Math.floor(Math.random() * rows));
        }
        gsap.delayedCall(0.15 + Math.random() * 0.35, ambient);
    })();

    function cellAt(e) {
        var r = hero.getBoundingClientRect();
        return { col: Math.floor((e.clientX - r.left) / GAP), row: Math.floor((e.clientY - r.top) / GAP) };
    }

    // Cursor trail: wake the dot under (or next to) the mouse.
    var lastTrail = 0;
    hero.addEventListener('pointermove', function (e) {
        if (e.pointerType !== 'mouse' || e.timeStamp - lastTrail < 90) return;
        lastTrail = e.timeStamp;
        var c = cellAt(e);
        spawn(c.col + Math.round(Math.random() * 2 - 1), c.row + Math.round(Math.random() * 2 - 1));
    });

    // Click/tap: a ripple of stars spreading out from that point.
    function ripple(col, row, radius) {
        for (var dc = -radius; dc <= radius; dc++) {
            for (var dr = -radius; dr <= radius; dr++) {
                var d = Math.sqrt(dc * dc + dr * dr);
                if (d > radius || (d > 0 && Math.random() < 0.35)) continue;
                spawn(col + dc, row + dr, d * 0.07, d === 0);
            }
        }
    }
    hero.addEventListener('pointerdown', function (e) {
        var c = cellAt(e);
        ripple(c.col, c.row, 4);
    });

    // A welcome ripple behind the headline once the intro is under way.
    gsap.delayedCall(0.9, function () {
        var t = one('[data-hero-title]').getBoundingClientRect();
        var h = hero.getBoundingClientRect();
        ripple(Math.floor((t.left - h.left + t.width * 0.7) / GAP), Math.floor((t.top - h.top + t.height / 2) / GAP), 5);
    });

    // Pause ambient twinkles while the hero is off screen.
    if ('IntersectionObserver' in window) {
        new IntersectionObserver(function (entries) {
            running = entries[0].isIntersecting;
        }).observe(hero);
    }

    // --- Scroll reveals for the sections below the hero -------------------------
    if (!window.ScrollTrigger) return;

    all('body > section h2', document).forEach(function (h2) {
        var group = [h2];
        if (h2.nextElementSibling && h2.nextElementSibling.tagName === 'P') group.push(h2.nextElementSibling);
        gsap.from(group, {
            y: 28, autoAlpha: 0, duration: 0.8, stagger: 0.12, ease: 'power3.out',
            scrollTrigger: { trigger: h2, start: 'top 88%', once: true }
        });
    });

    gsap.set('#features .grid > div, #how-it-works .grid > div, #roles .grid > div', { y: 40, autoAlpha: 0 });
    window.ScrollTrigger.batch('#features .grid > div, #how-it-works .grid > div, #roles .grid > div', {
        start: 'top 90%',
        once: true,
        onEnter: function (batch) {
            gsap.to(batch, { y: 0, autoAlpha: 1, duration: 0.7, stagger: 0.1, ease: 'power3.out', overwrite: true });
        }
    });

    // Step numbers pop in after their cards land.
    all('#how-it-works .grid > div > span:first-child', document).forEach(function (num, i) {
        gsap.from(num, {
            scale: 0, rotate: -90, duration: 0.6, delay: 0.25 + i * 0.1, ease: 'back.out(2.5)',
            scrollTrigger: { trigger: num, start: 'top 90%', once: true }
        });
    });
})();

// --- Live demo section ---------------------------------------------------------
(function () {
    'use strict';

    var section = document.querySelector('[data-demo]');
    if (!section) return;

    var gsap = window.gsap;
    var motion = !!gsap && !window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    function all(sel) { return Array.prototype.slice.call(section.querySelectorAll(sel)); }
    function one(sel) { return section.querySelector(sel); }

    var chips = all('[data-demo-chip]');
    var panels = all('[data-demo-panel]');
    var card = one('[data-demo-card]');
    var timer = one('[data-demo-timer]');
    var ON = ['bg-emerald-700', 'text-white'];
    var OFF = ['bg-emerald-50', 'text-emerald-800', 'dark:bg-emerald-950', 'dark:text-emerald-300'];
    var HIDDEN = ['invisible', 'opacity-0'];
    var current = 0;

    function setChip(chip, active) {
        chip.setAttribute('aria-selected', active ? 'true' : 'false');
        chip.tabIndex = active ? 0 : -1;
        ON.forEach(function (c) { chip.classList.toggle(c, active); });
        OFF.forEach(function (c) { chip.classList.toggle(c, !active); });
    }
    chips.forEach(function (chip, i) { setChip(chip, i === 0); });

    // Without motion the chips just swap panels by toggling classes.
    function show(i) {
        if (i === current) return;
        var prev = panels[current], next = panels[i];
        setChip(chips[current], false);
        setChip(chips[i], true);
        current = i;
        if (!motion) {
            HIDDEN.forEach(function (c) { prev.classList.add(c); next.classList.remove(c); });
            return;
        }
        gsap.to(prev, { autoAlpha: 0, y: -14, duration: 0.3, ease: 'power2.in', overwrite: true });
        gsap.fromTo(next, { autoAlpha: 0, y: 16 }, { autoAlpha: 1, y: 0, duration: 0.5, delay: 0.18, ease: 'power3.out', overwrite: true });
        gsap.fromTo(chips[i], { scale: 0.88 }, { scale: 1, duration: 0.45, ease: 'back.out(3)' });
        fillPanel(next, 0.2);
        restartTimer();
    }

    chips.forEach(function (chip, i) {
        chip.addEventListener('click', function () { show(i); });
        chip.addEventListener('pointerenter', function (e) { if (e.pointerType === 'mouse') show(i); });
        chip.addEventListener('keydown', function (e) {
            var step = e.key === 'ArrowRight' ? 1 : e.key === 'ArrowLeft' ? -1 : 0;
            if (!step) return;
            e.preventDefault();
            var n = (current + step + chips.length) % chips.length;
            show(n);
            chips[n].focus();
        });
    });

    if (!motion) return;

    // Hand the panels over from CSS classes to GSAP.
    panels.forEach(function (p, i) {
        HIDDEN.forEach(function (c) { p.classList.remove(c); });
        gsap.set(p, { autoAlpha: i === 0 ? 1 : 0 });
    });
    all('[data-demo-bar]').forEach(function (bar) { bar.setAttribute('data-width', bar.style.width); });

    function fillPanel(panel, delay) {
        var num = panel.querySelector('[data-demo-num]');
        if (num) {
            var target = parseInt(num.getAttribute('data-demo-num'), 10);
            var state = { v: 0 };
            gsap.to(state, {
                v: target, duration: 1, delay: delay, ease: 'power2.out',
                onUpdate: function () { num.textContent = Math.round(state.v).toLocaleString('en-US'); }
            });
        }
        var bar = panel.querySelector('[data-demo-bar]');
        if (bar) gsap.fromTo(bar, { width: '0%' }, { width: bar.getAttribute('data-width'), duration: 1, delay: delay + 0.05, ease: 'power2.out' });
        var icon = panel.querySelector('span');
        gsap.fromTo(icon, { scale: 0.4, rotate: -35 }, { scale: 1, rotate: 0, duration: 0.6, delay: delay, ease: 'back.out(2.5)' });
    }

    // Auto-advance, paused on hover/focus and while off screen.
    var progress = null, hovering = false, inView = false;
    function syncTimer() {
        if (!progress) return;
        if (hovering || !inView) progress.pause(); else progress.resume();
    }
    function restartTimer() {
        if (progress) progress.kill();
        progress = gsap.fromTo(timer, { scaleX: 0 }, {
            scaleX: 1, duration: 3.6, ease: 'none',
            onComplete: function () { show((current + 1) % panels.length); }
        });
        syncTimer();
    }
    [card, chips[0].parentNode].forEach(function (el) {
        el.addEventListener('pointerenter', function () { hovering = true; syncTimer(); });
        el.addEventListener('pointerleave', function () { hovering = false; syncTimer(); });
        el.addEventListener('focusin', function () { hovering = true; syncTimer(); });
        el.addEventListener('focusout', function () { hovering = false; syncTimer(); });
    });

    // Entrance, the first time the section scrolls into view.
    var live = one('[data-demo-live]');
    var magnet = one('[data-demo-magnet]');
    gsap.set([live, card, magnet], { autoAlpha: 0, y: 24 });
    gsap.set(chips, { autoAlpha: 0, y: 12, scale: 0.8 });

    var entered = false;
    function enter() {
        entered = true;
        gsap.timeline({ defaults: { ease: 'power3.out' }, onComplete: startIdle })
            .to(live, { autoAlpha: 1, y: 0, duration: 0.5, ease: 'back.out(2)' })
            .to(chips, { autoAlpha: 1, y: 0, scale: 1, duration: 0.45, stagger: 0.07, ease: 'back.out(2)' }, 0.25)
            .to(card, { autoAlpha: 1, y: 0, duration: 0.7 }, 0.45)
            .add(function () { fillPanel(panels[current], 0); }, 0.6)
            .to(magnet, { autoAlpha: 1, y: 0, duration: 0.6, ease: 'back.out(1.8)' }, 0.7);
    }

    new IntersectionObserver(function (entries) {
        inView = entries[0].isIntersecting;
        if (inView && !entered) enter();
        syncTimer();
    }, { threshold: 0.25 }).observe(section);

    function startIdle() {
        restartTimer();

        gsap.to(one('[data-demo-live-ping]'), { scale: 2.8, autoAlpha: 0, duration: 1.3, repeat: -1, ease: 'power1.out' });

        all('[data-demo-blob]').forEach(function (blob, i) {
            gsap.to(blob, {
                x: i ? -60 : 70, y: i ? -40 : 50, scale: 1.2,
                duration: 7 + i * 2, yoyo: true, repeat: -1, ease: 'sine.inOut'
            });
        });

        // Two rings take turns rippling out from the button.
        gsap.fromTo(all('[data-demo-ring]'),
            { scaleX: 1, scaleY: 1, opacity: 0.7 },
            { scaleX: 1.18, scaleY: 1.7, opacity: 0, duration: 1.8, stagger: { each: 0.9, repeat: -1 }, ease: 'power1.out' });

        gsap.timeline({ repeat: -1, repeatDelay: 2.4 })
            .to(one('[data-demo-play]'), { scale: 1.35, rotate: 20, duration: 0.25, ease: 'power2.out' })
            .to(one('[data-demo-play]'), { scale: 1, rotate: 0, duration: 0.5, ease: 'elastic.out(1.2, 0.4)' });

        // Magnetic button: drifts toward a nearby cursor, springs back on leave.
        if (window.matchMedia('(hover: hover)').matches) {
            var mx = gsap.quickTo(magnet, 'x', { duration: 0.5, ease: 'power3.out' });
            var my = gsap.quickTo(magnet, 'y', { duration: 0.5, ease: 'power3.out' });
            section.addEventListener('pointermove', function (e) {
                var r = magnet.getBoundingClientRect();
                var dx = e.clientX - (r.left + r.width / 2);
                var dy = e.clientY - (r.top + r.height / 2);
                var near = Math.abs(dx) < r.width / 2 + 60 && Math.abs(dy) < r.height / 2 + 60;
                mx(near ? dx * 0.25 : 0);
                my(near ? dy * 0.35 : 0);
            });
            section.addEventListener('pointerleave', function () { mx(0); my(0); });
        }
    }
})();
