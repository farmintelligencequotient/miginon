"""What the service worker (static/pwa/serviceworker.js) pre-downloads so the
app keeps working with no signal.

Every page someone opens is cached as they go; on top of that, each signed-in
page hands the worker this list of the everyday list/add pages so they're
ready offline even before they've been visited. Pages that change something
just by being opened (the notifications list marks everything read) or are
heavy to compute are left to be cached on a real visit only. What may be used
offline at all lives in static/js/offline-config.js.
"""
import re
from functools import lru_cache
from pathlib import Path

from django.conf import settings
from django.urls import NoReverseMatch, reverse

WARM_URL_NAMES = [
    'farms:dashboard', 'farms:farm_map', 'farms:block_list', 'farms:block_create', 'farms:worker_list',
    'cows:cow_list', 'cows:cow_create',
    'cows:milk_list', 'cows:milk_create',
    'cows:feeding_list', 'cows:feeding_create',
    'cows:health_record_list', 'cows:health_record_create',
    'cows:weight_list', 'cows:weight_create',
    'cows:reproduction_list', 'cows:reproduction_create',
    'crops:crop_list', 'crops:crop_create', 'crops:activity_list', 'crops:activity_create',
    'finance:transaction_list', 'finance:transaction_create', 'finance:milk_sale_create',
    'inventory:item_list', 'inventory:item_create', 'inventory:movement_list', 'inventory:movement_create',
    'inventory:milk_usage_create',
    'tasks:task_list', 'tasks:task_create',
    'analysis:overview',
    'advisory:home', 'advisory:disease_list', 'advisory:guide_list', 'advisory:learning_path_list',
    'geomap:map',
]

IONICONS_SVG_URL = 'https://unpkg.com/ionicons@7.1.0/dist/ionicons/svg/{}.svg'
_ICON_IN_TEMPLATE = re.compile(r'<ion-icon[^>]*\sname="([a-z0-9-]+)"')
_ICON_IN_PYTHON = re.compile(r"""['"]([a-z0-9]+(?:-[a-z0-9]+)*-(?:outline|sharp))['"]""")


def warm_urls():
    urls = []
    for name in WARM_URL_NAMES:
        try:
            urls.append(reverse(name))
        except NoReverseMatch:
            continue
    return urls


@lru_cache(maxsize=1)
def icon_urls():
    """Ionicons loads each icon's SVG from the CDN on first use, so an icon
    never seen online would be blank offline. Collect every icon name the
    templates and Python code use and let the worker cache them all."""
    names = set()
    base = Path(settings.BASE_DIR)
    for path in (base / 'templates').rglob('*.html'):
        names.update(_ICON_IN_TEMPLATE.findall(path.read_text(encoding='utf-8', errors='ignore')))
    for path in base.rglob('*.py'):
        if '.venv' in path.parts or 'site-packages' in path.parts:
            continue
        names.update(_ICON_IN_PYTHON.findall(path.read_text(encoding='utf-8', errors='ignore')))
    return [IONICONS_SVG_URL.format(name) for name in sorted(names)]
