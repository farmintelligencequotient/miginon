from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path('django-admin/', admin.site.urls),
    path('', include('pwa.urls')),
    path('', include('core.urls')),
    path('accounts/', include('accounts.urls')),
    path('farm/', include('farms.urls')),
    path('cows/', include('cows.urls')),
    path('crops/', include('crops.urls')),
    path('finance/', include('finance.urls')),
    path('inventory/', include('inventory.urls')),
    path('analysis/', include('analysis.urls')),
    path('notifications/', include('notifications.urls')),
    path('tasks/', include('tasks.urls')),
    path('weather/', include('weather.urls')),
    path('advisory/', include('advisory.urls')),
    path('wallet/', include('blockchain.urls')),
    path('credit-score/', include('creditscore.urls')),
    path('geomap/', include('geomap.urls')),
    path('insights/', include('insights.urls')),
    path('website/', include('website.urls')),
    # Kept last: a catch-all "<slug>/" for public farm sites, so every
    # other named route above always wins first (see website.models
    # .RESERVED_SLUGS for the corresponding slug-generation guard).
    path('', include('website.public_urls')),
]

# Errors raised outside a view (middleware, template rendering of a lazy
# response) never reach core.middleware.ExceptionSafetyNetMiddleware -
# these catch the rest with the same pages.
handler500 = 'core.views.server_error'
handler404 = 'core.views.page_not_found'

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
