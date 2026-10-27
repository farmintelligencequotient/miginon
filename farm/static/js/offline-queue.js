// Offline queue for data-entry forms (milk/feeding records) - lets a worker
// in a shed with no signal submit a form as normal; if the device is
// offline the submission is stored in IndexedDB instead of being sent, then
// flushed automatically once connectivity returns. Deliberately does NOT
// rely on the Background Sync API alone (no Safari/iOS support at all) -
// the primary trigger is the cross-browser 'online' window event, with
// Background Sync (see static/pwa/serviceworker.js) as a bonus for the
// tab-closed case on browsers that support it.
(function (global) {
    var DB_NAME = 'farmiq-offline-queue';
    var STORE_NAME = 'pending-records';
    var DB_VERSION = 1;
    var MAX_ATTEMPTS = 5;

    function openDb() {
        return new Promise(function (resolve, reject) {
            var request = indexedDB.open(DB_NAME, DB_VERSION);
            request.onupgradeneeded = function () {
                var db = request.result;
                if (!db.objectStoreNames.contains(STORE_NAME)) {
                    db.createObjectStore(STORE_NAME, { keyPath: 'id', autoIncrement: true });
                }
            };
            request.onsuccess = function () { resolve(request.result); };
            request.onerror = function () { reject(request.error); };
        });
    }

    function withStore(mode, work) {
        return openDb().then(function (db) {
            return new Promise(function (resolve, reject) {
                var tx = db.transaction(STORE_NAME, mode);
                var result = work(tx.objectStore(STORE_NAME));
                tx.oncomplete = function () { resolve(result); };
                tx.onerror = function () { reject(tx.error); };
            });
        });
    }

    function addRecord(record) {
        return withStore('readwrite', function (store) { store.add(record); });
    }

    function getAllRecords() {
        var records = [];
        return openDb().then(function (db) {
            return new Promise(function (resolve, reject) {
                var tx = db.transaction(STORE_NAME, 'readonly');
                var req = tx.objectStore(STORE_NAME).getAll();
                req.onsuccess = function () { records = req.result; };
                tx.oncomplete = function () { resolve(records); };
                tx.onerror = function () { reject(tx.error); };
            });
        });
    }

    function removeRecord(id) {
        return withStore('readwrite', function (store) { store.delete(id); });
    }

    function updateRecord(record) {
        return withStore('readwrite', function (store) { store.put(record); });
    }

    function getCsrfToken() {
        var match = document.cookie.match(/(?:^|; )csrftoken=([^;]+)/);
        return match ? decodeURIComponent(match[1]) : '';
    }

    function queueFormSubmission(form, submitter) {
        var formData;
        try {
            // The pressed button's name/value too ("Save and add another"...).
            formData = new FormData(form, submitter || undefined);
        } catch (e) {
            formData = new FormData(form);
        }
        var fields = [];
        formData.forEach(function (value, key) {
            // Includes the hidden csrfmiddlewaretoken input Django's
            // {% csrf_token %} renders - used as-is by the service worker's
            // background sync (it can't read document.cookie); the page-side
            // flush below swaps in the current cookie's token. Files are kept
            // as Blobs (IndexedDB stores them); an empty file input is skipped.
            if (typeof value === 'string' || value.size > 0) fields.push([key, value]);
        });
        return addRecord({
            url: form.action || window.location.href,
            fields: fields, attempts: 0, queuedAt: Date.now(),
        }).then(function () {
            return updateBadges();
        }).then(function () {
            if ('serviceWorker' in navigator && 'SyncManager' in window) {
                navigator.serviceWorker.ready.then(function (registration) {
                    return registration.sync.register('farmiq-offline-queue');
                }).catch(function () { /* Background Sync unsupported/unavailable - the 'online' listener still covers it */ });
            }
        });
    }

    function submitOne(record) {
        // The token queued with the form goes stale if the person signed in
        // again meanwhile; the cookie always holds the current one.
        var csrfToken = getCsrfToken();
        var hasFile = record.fields.some(function (pair) { return typeof pair[1] !== 'string'; });
        var body = hasFile ? new FormData() : new URLSearchParams();
        record.fields.forEach(function (pair) {
            body.append(pair[0], pair[0] === 'csrfmiddlewaretoken' && csrfToken ? csrfToken : pair[1]);
        });
        return fetch(record.url, {
            method: 'POST',
            headers: { 'X-CSRFToken': csrfToken },
            body: body,
            credentials: 'same-origin',
        }).then(function (response) {
            // This app's convention: a successful create/edit redirects (so
            // fetch, which follows redirects, reports redirected=true); a
            // rejected form just re-renders the same page with a 200 - the
            // only reliable signal to tell them apart without a JSON API.
            if (response.redirected) return removeRecord(record.id).then(function () { return 'sent'; });
            record.attempts += 1;
            if (record.attempts >= MAX_ATTEMPTS) return removeRecord(record.id);
            return updateRecord(record);
        }, function () {
            // Still offline / network error - leave it queued untouched for
            // the next flush trigger.
        });
    }

    var flushing = null;

    function flushQueue() {
        // One flush at a time, or a record could be sent twice.
        if (flushing) return flushing;
        var sent = 0;
        flushing = getAllRecords().then(function (records) {
            return records.reduce(function (chain, record) {
                return chain.then(function () { return submitOne(record); }).then(function (outcome) {
                    if (outcome === 'sent') sent += 1;
                });
            }, Promise.resolve());
        }).then(updateBadges).then(function (left) {
            if (sent) window.dispatchEvent(new CustomEvent('farmiq:synced', { detail: { sent: sent, left: left } }));
            return left;
        }).then(function (left) {
            flushing = null;
            return left;
        }, function (error) {
            flushing = null;
            throw error;
        });
        return flushing;
    }

    var badges = [];

    function updateBadges() {
        return getAllRecords().then(function (records) {
            var count = records.length;
            badges.forEach(function (b) {
                b.countEl.textContent = count;
                b.containerEl.hidden = count === 0;
            });
            return count;
        });
    }

    function registerBadge(countEl, containerEl) {
        badges.push({ countEl: countEl, containerEl: containerEl || countEl });
        updateBadges();
    }

    global.FarmIQOfflineQueue = {
        queueFormSubmission: queueFormSubmission,
        flushQueue: flushQueue,
        registerBadge: registerBadge,
    };

    window.addEventListener('online', function () { flushQueue(); });
    // The service worker queues posts that failed mid-flight and flushes via
    // Background Sync - keep the badge in step either way.
    if ('serviceWorker' in navigator) {
        navigator.serviceWorker.addEventListener('message', function (event) {
            if (event.data && event.data.type === 'queue-changed') updateBadges();
        });
    }
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', flushQueue);
    } else {
        flushQueue();
    }
})(window);
