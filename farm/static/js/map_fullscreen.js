// Full-screen toggle for FarmIQ's MapLibre maps.
//
// It fullscreens the *shell* element that wraps the map canvas AND all its
// floating controls (draw toolbar, save panel, readouts, legend...), so every
// button needed for mapping comes along. The native Fullscreen API is used
// where available; iPhone Safari and other browsers that lack it get a
// "pseudo" fullscreen (the shell is pinned over the whole viewport with CSS).
// The state is remembered in sessionStorage so that a form post inside the
// map (saving a parcel reloads the page) drops you straight back into
// fullscreen instead of out of it.
(function () {
    var STORAGE_KEY = 'farmiq-map-fullscreen';

    function nativeSupported(el) {
        return !!(el.requestFullscreen && document.fullscreenEnabled !== false);
    }

    function safeStorage(action, value) {
        try {
            if (action === 'set') sessionStorage.setItem(STORAGE_KEY, value);
            else if (action === 'clear') sessionStorage.removeItem(STORAGE_KEY);
            else return sessionStorage.getItem(STORAGE_KEY);
        } catch (e) { /* storage blocked - fullscreen still works, just isn't remembered */ }
        return null;
    }

    window.FarmIQMapFullscreen = function (shell, map, labels) {
        labels = labels || {};
        var enterLabel = labels.enter || 'Full screen';
        var exitLabel = labels.exit || 'Exit full screen';
        var button = null;
        var pseudo = false;

        function isFullscreen() {
            return document.fullscreenElement === shell || pseudo;
        }

        function refresh() {
            var on = isFullscreen();
            if (button) {
                button.title = button.ariaLabel = on ? exitLabel : enterLabel;
                var icon = button.querySelector('ion-icon');
                if (icon) icon.setAttribute('name', on ? 'contract-outline' : 'expand-outline');
                var text = button.querySelector('.geomap-fs-label');
                if (text) text.textContent = on ? exitLabel : enterLabel;
            }
            // The container's size changes - the canvas must be told (twice: once
            // now, once after layout/animation has settled).
            map.resize();
            setTimeout(function () { map.resize(); }, 250);
        }

        function setPseudo(on) {
            pseudo = on;
            shell.classList.toggle('geomap-pseudo-fs', on);
            document.documentElement.classList.toggle('geomap-fs-lock', on);
            refresh();
        }

        function enter() {
            safeStorage('set', '1');
            if (nativeSupported(shell)) {
                var p = shell.requestFullscreen();
                if (p && p.catch) p.catch(function () { setPseudo(true); });
            } else {
                setPseudo(true);
            }
        }

        function exit() {
            safeStorage('clear');
            if (document.fullscreenElement === shell) document.exitFullscreen();
            if (pseudo) setPseudo(false);
        }

        function toggle() { isFullscreen() ? exit() : enter(); }

        document.addEventListener('fullscreenchange', function () {
            if (document.fullscreenElement !== shell && !pseudo) safeStorage('clear');
            refresh();
        });
        document.addEventListener('keydown', function (e) {
            if (e.key === 'Escape' && pseudo) exit();
        });

        var control = {
            onAdd: function () {
                var container = document.createElement('div');
                container.className = 'maplibregl-ctrl maplibregl-ctrl-group';
                button = document.createElement('button');
                button.type = 'button';
                button.className = 'geomap-fs-btn';
                // Icon + words: a bare "expand" glyph on a white square is easy to miss.
                button.innerHTML = '<ion-icon name="expand-outline"></ion-icon><span class="geomap-fs-label"></span>';
                button.querySelector('.geomap-fs-label').textContent = enterLabel;
                button.title = button.ariaLabel = enterLabel;
                button.addEventListener('click', toggle);
                container.appendChild(button);
                return container;
            },
            onRemove: function () { button = null; },
        };
        map.addControl(control, 'top-right');

        // Coming back from a page reload that happened while in fullscreen.
        if (safeStorage('get') === '1') setPseudo(true);

        return { toggle: toggle, enter: enter, exit: exit, isFullscreen: isFullscreen };
    };
})();
