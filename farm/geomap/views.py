from django.conf import settings
from django.contrib import messages
from django.db.models import Count, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _

from farms.models import Farm
from farms.permissions import any_member_required, manage_herd_required, platform_admin_required
from notifications.models import Notification
from notifications.services import notify

from .colors import farm_color, farm_parcel_color, parcel_color
from .forms import LandParcelForm
from .models import LandParcel


def _tomtom_style_url():
    if not (settings.TOMTOM_API_KEY and settings.TOMTOM_STYLE_ID):
        return ''
    return (
        f'https://api.tomtom.com/style/2/custom/style/{settings.TOMTOM_STYLE_ID}.json'
        f'?key={settings.TOMTOM_API_KEY}'
    )


@any_member_required
def parcel_map(request):
    farm = request.farm
    # Parcels are private to the farm that mapped them: this page only ever
    # queries request.farm's own parcels (platform admins see every farm's on
    # geomap:admin_map instead).
    parcels = list(LandParcel.objects.filter(farm=farm).select_related('block', 'created_by'))
    for index, p in enumerate(parcels):
        p.color = parcel_color(index)
    parcels_data = [
        {
            'id': p.id,
            'color': p.color,
            'name': p.name,
            'coordinates': p.coordinates,
            'area_sqm': float(p.area_sqm),
            'perimeter_m': float(p.perimeter_m),
            'block': p.block.name if p.block_id else '',
        }
        for p in parcels
    ]
    has_center = farm.latitude is not None and farm.longitude is not None
    config = {
        'styleUrl': _tomtom_style_url(),
        'center': [float(farm.longitude), float(farm.latitude)] if has_center else None,
        'canEdit': request.membership.can_manage_herd,
        'saveUrl': reverse('geomap:parcel_create'),
    }
    return render(request, 'geomap/map.html', {
        'parcels': parcels,
        'parcels_data': parcels_data,
        'config': config,
        'form': LandParcelForm(farm=farm),
    })


@platform_admin_required
def admin_map(request):
    """Every farm's mapped parcels on one map, colour-coded per farm."""
    farm_stats = {
        row['farm_id']: row
        for row in LandParcel.objects.values('farm_id').annotate(n=Count('id'), sqm=Sum('area_sqm'))
    }
    farms = Farm.objects.filter(id__in=farm_stats.keys()).select_related('owner').order_by('name')
    groups, farm_index = [], {}
    for index, farm in enumerate(farms):
        farm_index[farm.id] = index
        stats = farm_stats[farm.id]
        groups.append({
            'id': farm.id, 'name': farm.name, 'owner': farm.owner.get_full_name() or farm.owner.email,
            'color': farm_color(index), 'parcel_count': stats['n'],
            'total_ha': float((stats['sqm'] or 0) / 10000),
        })

    parcel_counter = {}
    parcels_data = []
    for p in LandParcel.objects.filter(farm_id__in=farm_index).select_related('farm', 'block', 'created_by').order_by('farm_id', 'id'):
        n = parcel_counter.get(p.farm_id, 0)
        parcel_counter[p.farm_id] = n + 1
        parcels_data.append({
            'id': p.id, 'farm_id': p.farm_id, 'farm': p.farm.name, 'name': p.name,
            'coordinates': p.coordinates, 'area_ha': float(p.area_ha),
            'block': p.block.name if p.block_id else '',
            'by': (p.created_by.get_full_name() or p.created_by.email) if p.created_by_id else '',
            'on': p.created_at.strftime('%d %b %Y'),
            'color': farm_parcel_color(farm_index[p.farm_id], n),
        })
    config = {'styleUrl': _tomtom_style_url(), 'center': [36.817223, -1.286389]}
    return render(request, 'geomap/admin_map.html', {
        'groups': groups, 'parcels_data': parcels_data, 'config': config,
    })


@manage_herd_required
def parcel_create(request):
    if request.method != 'POST':
        return redirect('geomap:map')
    form = LandParcelForm(request.POST, farm=request.farm)
    if form.is_valid():
        parcel = form.save(commit=False)
        parcel.created_by = request.user
        parcel.save()
        notify(request.farm, request.user, Notification.Verb.CREATED, 'land parcel', parcel.name)
        messages.success(request, _('"%(name)s" saved - %(area)s hectares.') % {
            'name': parcel.name, 'area': parcel.area_ha,
        })
    else:
        errors = ' '.join(e for field_errors in form.errors.values() for e in field_errors)
        messages.error(request, errors or _("Couldn't save that shape."))
    return redirect('geomap:map')


@manage_herd_required
def parcel_delete(request, parcel_id):
    parcel = get_object_or_404(LandParcel, id=parcel_id, farm=request.farm)
    if request.method == 'POST':
        name = parcel.name
        parcel.delete()
        notify(request.farm, request.user, Notification.Verb.DELETED, 'land parcel', name)
        messages.success(request, _('%(name)s deleted.') % {'name': name})
    return redirect('geomap:map')
