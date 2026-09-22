// FarmIQ is a classic multi-page app (every link/form is a real navigation,
// not client-side routing), so the browser's own history already has a
// correct back chain in most cases. The one thing it can't tell us is
// whether THIS tab actually has anywhere of ours to go back to - a deep
// link opened fresh (a notification, a bookmark, a shared link) has no
// prior FarmIQ page in its history, and history.back() there would exit
// the app entirely instead of landing on a sensible page.
//
// So this keeps a small "did we get here by moving through the app"
// breadcrumb of visited paths in sessionStorage (per tab, cleared when the
// tab closes - a light cache of this session's movement, not permanent
// state). It runs on every page via base.html (not a block a child
// template could override) and mirrors real browser back/forward
// (including swipe gestures, not just our own button) by popping when the
// current page matches what used to be one level up.
(function () {
    var KEY = 'farmiq-nav-stack';
    var MAX_DEPTH = 40;

    function readStack() {
        try { return JSON.parse(sessionStorage.getItem(KEY) || '[]'); } catch (e) { return []; }
    }
    function writeStack(stack) {
        try { sessionStorage.setItem(KEY, JSON.stringify(stack.slice(-MAX_DEPTH))); } catch (e) { /* private mode, quota, ... - back still works, just uncached */ }
    }

    var path = location.pathname + location.search;
    var stack = readStack();
    var top = stack[stack.length - 1];
    var below = stack[stack.length - 2];

    if (top === path) {
        // Same page re-rendered (e.g. a form redisplayed with validation
        // errors) - not a move, leave the breadcrumb as-is.
    } else if (below === path) {
        // We're back on the page one level up - a real back navigation
        // happened (our button, the browser's back button, or a swipe).
        stack.pop();
    } else {
        stack.push(path);
    }
    writeStack(stack);

    window.FarmIQNav = {
        // Whether this tab's breadcrumb has anywhere of ours before this page.
        canGoBack: stack.length > 1,
        // Prefer real browser back (keeps scroll position, form state, etc.);
        // fall back to a caller-supplied page (normally the dashboard) when
        // this is the first FarmIQ page this tab has seen.
        back: function (fallbackUrl) {
            var current = readStack();
            if (current.length > 1) history.back();
            else location.href = fallbackUrl || '/';
        },
    };
})();
