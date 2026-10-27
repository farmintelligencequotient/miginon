// Page side of FarmIQ's offline mode (the service worker is
// static/pwa/serviceworker.js, the shared rules static/js/offline-config.js).
//
// - While offline, links into modules that need a live connection are greyed
//   out and can't be opened; a bar explains what still works.
// - Any POST form submitted offline is queued on the device (offline-queue.js)
//   instead of failing, and sent once the connection is back.
// - Tells the service worker whose pages these are and which ones to
//   pre-download (core/offline.py), so it can keep them ready offline.
//
// Loaded in <head>, before base.html's submit-spinner listener, so a queued
// submission (defaultPrevented) never leaves a spinning, disabled button.
(function () {
    var config = window.FarmIQOfflineConfig;
    var root = document.documentElement;
    var DEFAULT_STRINGS = {
        offlineBar: "You're offline. Saved pages and data entry still work - greyed-out modules need internet.",
        copyFrom: 'Saved copy from',
        needsInternet: 'This needs an internet connection.',
        savedOffline: "No signal - saved on this device. It will sync automatically once you're back online.",
        queueFailed: "Couldn't save this on the device - please try again.",
        backOnline: 'Back online - syncing your saved records.',
        synced: 'records synced.',
    };
    var strings = null;

    function t(key) {
        if (!strings) {
            var el = document.getElementById('farmiq-offline-strings');
            try { strings = el ? JSON.parse(el.textContent) : {}; } catch (e) { strings = {}; }
        }
        return strings[key] || DEFAULT_STRINGS[key];
    }

    function isOffline() { return navigator.onLine === false; }

    function pathOf(href) {
        try { return new URL(href, window.location.href); } catch (e) { return null; }
    }

    function needsInternet(url) {
        return url && url.origin === window.location.origin && config.isOnlineOnly(url.pathname);
    }

    // ---------------------------------------------------------- styles

    var style = document.createElement('style');
    style.textContent = [
        'html.farmiq-offline a[data-online-only]{opacity:.4;filter:grayscale(1);cursor:not-allowed}',
        '#farmiq-offline-bar{display:none;position:sticky;top:0;z-index:40;padding:6px 16px;background:#78350f;color:#fff;',
        'font:600 12px/1.4 "Plus Jakarta Sans",ui-sans-serif,system-ui,sans-serif;text-align:center}',
        'html.farmiq-offline #farmiq-offline-bar{display:block}',
        '#farmiq-toasts{position:fixed;left:50%;bottom:96px;z-index:10000;transform:translateX(-50%);display:flex;',
        'flex-direction:column;gap:8px;width:calc(100% - 32px);max-width:420px;pointer-events:none}',
        '.farmiq-toast{padding:10px 14px;border-radius:14px;background:#1c1917;color:#fff;box-shadow:0 8px 24px rgba(0,0,0,.25);',
        'font:600 13px/1.4 "Plus Jakarta Sans",ui-sans-serif,system-ui,sans-serif;transition:opacity .4s}',
        '.farmiq-toast.is-warn{background:#b45309}.farmiq-toast.is-ok{background:#146a4a}.farmiq-toast.is-error{background:#b91c1c}',
    ].join('');
    document.head.appendChild(style);

    function toast(message, kind) {
        var box = document.getElementById('farmiq-toasts');
        if (!box) {
            box = document.createElement('div');
            box.id = 'farmiq-toasts';
            box.setAttribute('role', 'status');
            box.setAttribute('aria-live', 'polite');
            document.body.appendChild(box);
        }
        var el = document.createElement('div');
        el.className = 'farmiq-toast' + (kind ? ' is-' + kind : '');
        el.textContent = message;
        box.appendChild(el);
        setTimeout(function () { el.style.opacity = '0'; }, 4500);
        setTimeout(function () { el.remove(); }, 5000);
    }

    // ------------------------------------------------- online/offline state

    function copyTimeText() {
        var at = Number(root.getAttribute('data-offline-copy'));
        if (!at) return '';
        var when = new Date(at);
        var sameDay = when.toDateString() === new Date().toDateString();
        return ' (' + t('copyFrom') + ' ' + (sameDay
            ? when.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
            : when.toLocaleString([], { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })) + ')';
    }

    function markLinks() {
        document.querySelectorAll('a[href]').forEach(function (a) {
            if (needsInternet(pathOf(a.href))) a.setAttribute('data-online-only', '');
        });
    }

    function applyState() {
        var offline = isOffline();
        root.classList.toggle('farmiq-offline', offline);
        document.querySelectorAll('a[data-online-only]').forEach(function (a) {
            if (offline) a.setAttribute('aria-disabled', 'true');
            else a.removeAttribute('aria-disabled');
        });
        var bar = document.getElementById('farmiq-offline-bar');
        if (!bar && document.body) {
            bar = document.createElement('div');
            bar.id = 'farmiq-offline-bar';
            document.body.insertBefore(bar, document.body.firstChild);
        }
        if (bar) bar.textContent = t('offlineBar') + copyTimeText();
    }

    // Online-only links can't be opened while offline.
    document.addEventListener('click', function (e) {
        if (!isOffline()) return;
        var link = e.target.closest && e.target.closest('a[href]');
        if (!link || !needsInternet(pathOf(link.href))) return;
        e.preventDefault();
        e.stopImmediatePropagation();
        toast(t('needsInternet'), 'warn');
    }, true);

    // ------------------------------------------------------------- forms

    document.addEventListener('submit', function (e) {
        var form = e.target;
        if (e.defaultPrevented || !(form instanceof HTMLFormElement)) return;
        var url = pathOf(form.getAttribute('action') || window.location.href);

        if (url && url.pathname === '/accounts/logout/' && navigator.serviceWorker && navigator.serviceWorker.controller) {
            // Signed-out devices must not keep the farm's pages.
            navigator.serviceWorker.controller.postMessage({ type: 'clear-pages' });
        }
        if (!isOffline() || (form.getAttribute('method') || 'get').toLowerCase() !== 'post') return;

        e.preventDefault();
        if (needsInternet(url) || form.hasAttribute('data-online-only') || !window.FarmIQOfflineQueue) {
            toast(t('needsInternet'), 'warn');
            return;
        }
        window.FarmIQOfflineQueue.queueFormSubmission(form, e.submitter).then(function () {
            form.reset();
            var banner = document.getElementById('offline-save-banner'); // the milk/feeding forms' inline note
            if (banner) banner.hidden = false;
            toast(t('savedOffline'), 'ok');
        }, function () {
            toast(t('queueFailed'), 'error');
        });
    });

    window.addEventListener('farmiq:synced', function (e) {
        toast(e.detail.sent + ' ' + t('synced'), 'ok');
    });

    // ------------------------------------------- talking to the worker

    function sendContext() {
        // A saved copy carries the context it was saved with - only a fresh
        // page from the server speaks for the current session.
        if (isOffline() || root.hasAttribute('data-offline-copy') || !('serviceWorker' in navigator)) return;
        var el = document.getElementById('farmiq-offline-context');
        if (!el) return;
        var data;
        try { data = JSON.parse(el.textContent); } catch (e) { return; }
        navigator.serviceWorker.ready.then(function (registration) {
            if (registration.active) {
                registration.active.postMessage({ type: 'context', key: data.key, warm: data.warm, assets: data.assets });
            }
        });
    }

    function onReady() {
        markLinks();
        applyState();
        if (window.location.hash === '#farmiq-saved-offline') {
            history.replaceState(null, '', window.location.pathname + window.location.search);
            toast(t('savedOffline'), 'ok');
        }
    }

    window.addEventListener('offline', applyState);
    window.addEventListener('online', function () {
        applyState();
        toast(t('backOnline'), 'ok');
    });
    window.addEventListener('load', function () { setTimeout(sendContext, 1500); });
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', onReady);
    else onReady();

    window.FarmIQOffline = { toast: toast, isOffline: isOffline };
})();
