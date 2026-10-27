def theme(request):
    """Effective light/dark theme for this request - the signed-in user's
    saved preference, or the `theme` cookie for anonymous visitors (landing,
    login, signup) so the toggle still works before there's a User row to
    save it on."""
    user = getattr(request, 'user', None)
    if user is not None and user.is_authenticated:
        pref = user.theme_preference
    else:
        pref = request.COOKIES.get('theme', 'light')
    return {'theme': pref if pref in ('light', 'dark') else 'light'}


def offline(request):
    """Handed to the service worker by static/js/offline.js. `key` changes
    whenever the cached pages would show something different (another user,
    farm, language or theme) so the worker drops them and warms afresh."""
    from django.utils.translation import get_language

    from .offline import icon_urls, warm_urls

    user = getattr(request, 'user', None)
    if user is None or not user.is_authenticated:
        return {'offline_context': {'key': 'anon', 'warm': [], 'assets': []}}
    key = ':'.join(str(part) for part in (
        user.pk, request.session.get('active_farm_id', ''), get_language(), theme(request)['theme'],
    ))
    return {'offline_context': {'key': key, 'warm': warm_urls(), 'assets': icon_urls()}}
