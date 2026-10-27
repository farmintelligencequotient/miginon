// FarmIQ service worker.
//
// Network-first for pages: this is a live farm records app, so a page always
// shows fresh data when the device is online. Every page that loads is also
// kept in a cache, and signed-in pages hand us a list of the everyday list/add
// pages to pre-download (core/offline.py), so with no signal the app still
// opens, navigates and takes data entry: forms that can't reach the server are
// queued in IndexedDB and sent once the connection is back (see
// static/js/offline-queue.js). Modules that need a live connection are listed
// in static/js/offline-config.js; they are never served from cache.
importScripts('/static/js/offline-config.js');

var CONFIG = self.FarmIQOfflineConfig;
var SHELL_CACHE = 'farmiq-shell-v3';   // bump when SHELL_FILES / CDN_FILES change
var ASSET_CACHE = 'farmiq-assets-v1';  // static files + CDN scripts/styles/fonts/icons, filled as used
var PAGE_CACHE = 'farmiq-pages-v1';    // the signed-in person's pages
var META_CACHE = 'farmiq-meta';        // small bookkeeping (whose pages are cached, when they were warmed)
var KEEP_CACHES = [SHELL_CACHE, ASSET_CACHE, PAGE_CACHE, META_CACHE];

var NETWORK_TIMEOUT_MS = 6000;        // a page slower than this falls back to its cached copy, if there is one
var REWARM_AFTER_MS = 6 * 60 * 60 * 1000;   // refresh every warmed page this often
var RETRY_WARM_AFTER_MS = 15 * 60 * 1000;   // at most one warm-up pass per this long (pages someone can't open are never cached)

var SHELL_FILES = [
    '/offline/',
    '/static/js/offline-config.js',
    '/static/js/offline.js',
    '/static/js/offline-queue.js',
    '/static/js/nav-history.js',
    '/static/js/map_fullscreen.js',
    '/static/geomap/kenya-counties.geojson',
    '/static/images/logo-mark.png',
    '/static/images/icons/favicon-32.png',
    '/static/images/icons/favicon-16.png',
    '/static/images/icons/icon-192x192.png',
    '/static/images/icons/icon-512x512.png',
    '/static/images/icons/icon-512x512-maskable.png',
    '/static/images/icons/apple-icon-180.png',
];

// Third-party files every page (or the maps) need; precached so the app looks
// right offline even straight after install.
var CDN_FILES = [
    'https://cdn.tailwindcss.com',
    'https://unpkg.com/ionicons@7.1.0/dist/ionicons/ionicons.esm.js',
    'https://unpkg.com/ionicons@7.1.0/dist/ionicons/ionicons.js',
    'https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.js',
    'https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.css',
    'https://unpkg.com/@turf/turf@6.5.0/turf.min.js',
    'https://unpkg.com/three@0.160.0/build/three.module.js',
    'https://unpkg.com/three@0.160.0/examples/jsm/controls/OrbitControls.js',
];
var CDN_HOSTS = ['cdn.tailwindcss.com', 'unpkg.com', 'cdn.jsdelivr.net', 'fonts.googleapis.com', 'fonts.gstatic.com'];

function cacheEach(cacheName, urls) {
    // One unreachable file must not fail the whole install.
    return caches.open(cacheName).then(function (cache) {
        return Promise.all(urls.map(function (url) {
            return cache.add(url).catch(function () {
                return fetch(url, { mode: 'no-cors' }).then(function (r) { return cache.put(url, r); }).catch(function () {});
            });
        }));
    });
}

function cacheMissing(cacheName, urls) {
    return caches.open(cacheName).then(function (cache) {
        return Promise.all(urls.map(function (url) {
            return cache.match(url).then(function (hit) { return hit ? null : url; });
        }));
    }).then(function (todo) { return cacheEach(cacheName, todo.filter(Boolean)); });
}

self.addEventListener('install', function (event) {
    self.skipWaiting();
    event.waitUntil(
        caches.open(SHELL_CACHE)
            .then(function (cache) { return cache.add('/offline/'); })
            .then(function () { return cacheEach(SHELL_CACHE, SHELL_FILES.concat(CDN_FILES)); })
    );
});

self.addEventListener('activate', function (event) {
    event.waitUntil(
        caches.keys().then(function (cacheNames) {
            return Promise.all(
                cacheNames
                    .filter(function (name) {
                        return (name.startsWith('farmiq-') || name.startsWith('miginon-farm-')) && KEEP_CACHES.indexOf(name) === -1;
                    })
                    .map(function (name) { return caches.delete(name); })
            );
        }).then(function () { return self.clients.claim(); })
    );
});

// ------------------------------------------------------------------ fetch

self.addEventListener('fetch', function (event) {
    var request = event.request;
    var url = new URL(request.url);
    var sameOrigin = url.origin === self.location.origin;

    if (request.method === 'POST') {
        if (sameOrigin && request.mode === 'navigate') event.respondWith(handleFormPost(event));
        return;
    }
    if (request.method !== 'GET') return;

    if (sameOrigin) {
        if (CONFIG.isNeverCached(url.pathname)) return;
        if (request.mode === 'navigate') {
            event.respondWith(handlePage(request, url));
        } else if (url.pathname.indexOf('/static/') === 0 || url.pathname.indexOf('/media/') === 0) {
            event.respondWith(staleWhileRevalidate(request));
        }
        return;
    }
    if (CDN_HOSTS.indexOf(url.hostname) !== -1) event.respondWith(cacheFirst(request));
    // Anything else (map tiles, weather APIs...) goes straight to the network.
});

function matchCached(request) {
    return caches.match(request, { ignoreVary: true });
}

function offlinePage() {
    return caches.match('/offline/', { ignoreVary: true }).then(function (r) {
        return r || new Response('<h1>You are offline</h1>', { headers: { 'Content-Type': 'text/html; charset=utf-8' } });
    });
}

function isCacheablePage(response) {
    return response && response.status === 200 && response.type === 'basic'
        && (response.headers.get('Content-Type') || '').indexOf('text/html') === 0;
}

// The stored copy drops one-off flash messages ("Saved!") and is marked so
// the page can tell people they're looking at a copy (see offline.js).
function storePage(request, response) {
    return response.text().then(function (html) {
        html = html.replace(/<!--farmiq:flash-->[\s\S]*?<!--\/farmiq:flash-->/, '')
            .replace(/<html\b/, '<html data-offline-copy="' + Date.now() + '"');
        return caches.open(PAGE_CACHE).then(function (cache) {
            return cache.put(request.url.split('#')[0], new Response(html, {
                status: 200, headers: { 'Content-Type': response.headers.get('Content-Type') },
            }));
        });
    });
}

function handlePage(request, url) {
    var onlineOnly = CONFIG.isOnlineOnly(url.pathname);
    var network = fetch(request).then(function (response) {
        if (!onlineOnly && isCacheablePage(response)) storePage(request, response.clone()).catch(function () {});
        return response;
    });
    if (onlineOnly) return network.catch(offlinePage);

    // On a weak signal a request can hang for ages: after NETWORK_TIMEOUT_MS
    // show the cached copy if there is one, otherwise keep waiting.
    return new Promise(function (resolve) {
        var settled = false;
        function settle(response) { if (!settled) { settled = true; resolve(response); } }
        var timer = setTimeout(function () {
            matchCached(request).then(function (cached) { if (cached) settle(cached); });
        }, NETWORK_TIMEOUT_MS);
        network.then(function (response) {
            clearTimeout(timer);
            settle(response);
        }, function () {
            clearTimeout(timer);
            matchCached(request).then(function (cached) { return cached || offlinePage(); }).then(settle);
        });
    });
}

function staleWhileRevalidate(request) {
    return caches.open(ASSET_CACHE).then(function (cache) {
        return matchCached(request).then(function (cached) {
            var network = fetch(request).then(function (response) {
                if (response.ok) cache.put(request, response.clone());
                return response;
            });
            if (cached) {
                network.catch(function () {});
                return cached;
            }
            return network;
        });
    });
}

function cacheFirst(request) {
    return matchCached(request).then(function (cached) {
        if (cached) return cached;
        return fetch(request).then(function (response) {
            if (response.ok || response.type === 'opaque') {
                var copy = response.clone();
                caches.open(ASSET_CACHE).then(function (cache) { cache.put(request, copy); });
            }
            return response;
        });
    });
}

// A normal form post whose network request fails (the page thought it was
// online - a weak or dropped signal): queue it and send the person back to
// the page they came from, which shows a "saved on this device" note.
// offline-queue.js handles the clearly-offline case before it gets here.
function handleFormPost(event) {
    var request = event.request;
    var copy = request.clone();
    if (CONFIG.isOnlineOnly(new URL(request.url).pathname)) return fetch(request).catch(offlinePage);
    return fetch(request).catch(function () {
        return copy.formData().then(function (formData) {
            var fields = [];
            formData.forEach(function (value, key) { fields.push([key, value]); });
            return queueRecord({ url: request.url, fields: fields, attempts: 0, queuedAt: Date.now() });
        }).then(function () {
            notifyClients({ type: 'queue-changed' });
            if (self.registration.sync) self.registration.sync.register('farmiq-offline-queue').catch(function () {});
            var back = (request.referrer || request.url).split('#')[0];
            return Response.redirect(back + '#farmiq-saved-offline', 303);
        }).catch(offlinePage);
    });
}

function notifyClients(message) {
    return self.clients.matchAll({ type: 'window' }).then(function (clients) {
        clients.forEach(function (client) { client.postMessage(message); });
    });
}

// ------------------------------------------------- pre-downloading pages

function readMeta(name) {
    return caches.open(META_CACHE).then(function (cache) {
        return cache.match('/__farmiq-meta/' + name).then(function (r) { return r ? r.text() : null; });
    });
}

function writeMeta(name, value) {
    return caches.open(META_CACHE).then(function (cache) {
        return cache.put('/__farmiq-meta/' + name, new Response(String(value)));
    });
}

function clearPages() {
    return caches.delete(PAGE_CACHE).then(function () {
        return Promise.all([writeMeta('warmed-at', 0), writeMeta('warm-tried-at', 0)]);
    });
}

function warmPage(url) {
    return fetch(url, { credentials: 'same-origin', headers: { 'X-FarmIQ-Warm': '1' } }).then(function (response) {
        // A redirect means the page isn't available to this person (sign-in, permissions).
        if (!response.redirected && isCacheablePage(response)) return storePage(new Request(url), response);
    }).catch(function () {});
}

function warmAll(urls, force) {
    return caches.open(PAGE_CACHE).then(function (cache) {
        return Promise.all(urls.map(function (url) {
            return cache.match(url).then(function (hit) { return (force || !hit) ? url : null; });
        }));
    }).then(function (todo) {
        todo = todo.filter(Boolean);
        // Two at a time - gentle on the server and on a farm's data bundle.
        var lanes = [0, 1].map(function (lane) {
            return todo.filter(function (_, i) { return i % 2 === lane; }).reduce(function (chain, url) {
                return chain.then(function () { return warmPage(url); });
            }, Promise.resolve());
        });
        return Promise.all(lanes);
    });
}

// The page tells us whose pages it shows: if that changed (sign-out, another
// user, a farm/language/theme switch) the cached pages are wrong - drop them.
function handleContext(data) {
    return readMeta('context').then(function (previous) {
        var changed = previous !== data.key;
        var ready = changed ? clearPages().then(function () { return writeMeta('context', data.key); }) : Promise.resolve();
        return ready.then(function () {
            return Promise.all([readMeta('warmed-at'), readMeta('warm-tried-at')]);
        }).then(function (times) {
            if (data.key === 'anon' || !data.warm || !data.warm.length) return;
            if (Date.now() - Number(times[1] || 0) < RETRY_WARM_AFTER_MS) return;
            var stale = Date.now() - Number(times[0] || 0) > REWARM_AFTER_MS;
            return writeMeta('warm-tried-at', Date.now()).then(function () {
                return Promise.all([warmAll(data.warm, stale), cacheMissing(ASSET_CACHE, data.assets || [])]);
            }).then(function () { if (stale) return writeMeta('warmed-at', Date.now()); });
        });
    });
}

self.addEventListener('message', function (event) {
    var data = event.data || {};
    if (data.type === 'context' && typeof data.key === 'string') event.waitUntil(handleContext(data));
    else if (data.type === 'clear-pages') event.waitUntil(clearPages());
});

// Device push notifications (see notifications/push.py for the send side).
// The payload is the JSON string notify() builds: {title, body, url}.
self.addEventListener('push', function (event) {
    var data = { title: 'FarmIQ', body: 'You have a new notification.', url: '/notifications/' };
    if (event.data) {
        try { data = Object.assign(data, event.data.json()); } catch (e) { /* keep defaults */ }
    }
    event.waitUntil(
        self.registration.showNotification(data.title, {
            body: data.body,
            icon: '/static/images/icons/icon-192x192.png',
            badge: '/static/images/icons/icon-192x192.png',
            data: { url: data.url },
        })
    );
});

// Offline data-entry queue (see static/js/offline-queue.js for the primary
// page-side flush, triggered on the 'online' event - this is the bonus path
// for browsers that support Background Sync (Chrome/Android) so a queued
// record can still flush even if the tab was closed while offline. Reads
// the same IndexedDB database/store the page writes to. Deliberately
// duplicated rather than shared via importScripts: it's a handful of lines.
// A worker can't read document.cookie, so the CSRF token is refreshed from
// the Cookie Store API where it exists; otherwise the form's own
// csrfmiddlewaretoken (queued with the fields) is sent as-is.
var OFFLINE_DB_NAME = 'farmiq-offline-queue';
var OFFLINE_STORE_NAME = 'pending-records';

function openOfflineDb() {
    return new Promise(function (resolve, reject) {
        var request = indexedDB.open(OFFLINE_DB_NAME, 1);
        request.onupgradeneeded = function () {
            if (!request.result.objectStoreNames.contains(OFFLINE_STORE_NAME)) {
                request.result.createObjectStore(OFFLINE_STORE_NAME, { keyPath: 'id', autoIncrement: true });
            }
        };
        request.onsuccess = function () { resolve(request.result); };
        request.onerror = function () { reject(request.error); };
    });
}

function offlineStore(mode, work) {
    return openOfflineDb().then(function (db) {
        return new Promise(function (resolve, reject) {
            var tx = db.transaction(OFFLINE_STORE_NAME, mode);
            var result = work(tx.objectStore(OFFLINE_STORE_NAME));
            tx.oncomplete = function () { resolve(result && 'result' in result ? result.result : undefined); };
            tx.onerror = function () { reject(tx.error); };
        });
    });
}

function queueRecord(record) {
    return offlineStore('readwrite', function (store) { store.add(record); });
}

function currentCsrfToken() {
    if (!self.cookieStore) return Promise.resolve('');
    return self.cookieStore.get('csrftoken').then(function (c) { return c ? c.value : ''; }, function () { return ''; });
}

function recordBody(record, csrfToken) {
    var hasFile = record.fields.some(function (pair) { return typeof pair[1] !== 'string'; });
    var body = hasFile ? new FormData() : new URLSearchParams();
    record.fields.forEach(function (pair) {
        var value = (pair[0] === 'csrfmiddlewaretoken' && csrfToken) ? csrfToken : pair[1];
        body.append(pair[0], value);
    });
    return body;
}

function flushOfflineQueue() {
    return Promise.all([offlineStore('readonly', function (store) { return store.getAll(); }), currentCsrfToken()]).then(function (results) {
        var records = results[0] || [];
        var csrfToken = results[1];
        return records.reduce(function (chain, record) {
            return chain.then(function () {
                return fetch(record.url, {
                    method: 'POST',
                    body: recordBody(record, csrfToken),
                    credentials: 'same-origin',
                }).then(function (response) {
                    if (!response.redirected) return; // leave it for the page-side flush to retry/give up on
                    return offlineStore('readwrite', function (store) { store.delete(record.id); });
                }, function () { /* still offline - leave queued */ });
            });
        }, Promise.resolve());
    }).then(function () { return notifyClients({ type: 'queue-changed' }); });
}

self.addEventListener('sync', function (event) {
    if (event.tag !== 'farmiq-offline-queue') return;
    event.waitUntil(flushOfflineQueue());
});

self.addEventListener('notificationclick', function (event) {
    event.notification.close();
    var url = (event.notification.data && event.notification.data.url) || '/notifications/';
    event.waitUntil(
        self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then(function (clients) {
            for (var i = 0; i < clients.length; i++) {
                if (clients[i].url.indexOf(url) !== -1 && 'focus' in clients[i]) return clients[i].focus();
            }
            if (self.clients.openWindow) return self.clients.openWindow(url);
        })
    );
});
