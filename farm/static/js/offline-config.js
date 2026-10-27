// Offline rules shared by the pages (static/js/offline.js, offline-queue.js)
// and the service worker (static/pwa/serviceworker.js, via importScripts), so
// both sides always agree on what works without a connection.
(function (root) {
    root.FarmIQOfflineConfig = {
        // Modules that only make sense against a live server or a third-party
        // service: live forecasts, on-chain wallet, partner data-sharing, the
        // public website builder, sign-in/account flows, platform admin. While
        // offline their links are greyed out and not clickable, and the
        // service worker never serves a stale copy of them.
        onlineOnly: [
            '/weather/',
            '/wallet/',
            '/credit-score/',
            '/website/',
            '/advisory/agri-centers/',
            '/accounts/',
            '/geomap/admin/',
            '/farm/admin/',
            '/farm/switch/',
            '/analysis/export/',
            '/django-admin/',
            '/theme/',
            '/language/',
            '/demo/',
        ],

        // GETs the service worker must never cache (non-page responses, push).
        neverCache: [
            '/serviceworker.js',
            '/manifest.json',
            '/notifications/push/',
        ],

        isOnlineOnly: function (pathname) {
            return this.onlineOnly.some(function (prefix) { return pathname.indexOf(prefix) === 0; });
        },

        isNeverCached: function (pathname) {
            return this.neverCache.some(function (prefix) { return pathname.indexOf(prefix) === 0; });
        },
    };
})(self);
