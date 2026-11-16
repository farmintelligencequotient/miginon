from decimal import Decimal

from django.db.models import Count, Sum


def estimate_weight_from_girth(heart_girth_cm):
    """Girth-only liveweight estimate (kg), the same cube-of-girth
    approximation printed on physical cattle weigh tapes - lets a farmer
    without a scale get a usable weight from one tape measurement around
    the chest just behind the front legs. Body-length-adjusted (Schaeffer)
    formulas are more accurate but need a second measurement most
    smallholders don't take."""
    girth = Decimal(heart_girth_cm)
    return round(girth ** 3 / Decimal('11800'), 1)


# Ionicons name per session - the same three icons wherever sessions are shown.
SESSION_ICONS = {'AM': 'sunny-outline', 'NOON': 'partly-sunny-outline', 'PM': 'moon-outline'}


def milk_session_totals(farm, date):
    """A farm's milk for one day, split by session - what the milk records
    page and the dashboard's Milk tile both show. Every session is always
    present (0 with logged=False when nothing was recorded for it), so the
    templates can render three fixed slots without checking for gaps."""
    from .models import MilkRecord, Session

    day_qs = MilkRecord.objects.filter(farm=farm, date=date)
    by_session = {
        row['session']: row
        for row in day_qs.order_by().values('session').annotate(total=Sum('liters'), cows=Count('cow', distinct=True))
    }
    sessions = [
        {
            'key': session.value,
            'label': session.label,
            'icon': SESSION_ICONS[session.value],
            'liters': by_session.get(session.value, {}).get('total') or Decimal('0'),
            'cows': by_session.get(session.value, {}).get('cows', 0),
            'logged': session.value in by_session,
        }
        for session in Session
    ]
    return {
        'date': date,
        'sessions': sessions,
        'total': sum((row['liters'] for row in sessions), Decimal('0')),
        'logged_count': sum(1 for row in sessions if row['logged']),
        'cows_milked': day_qs.order_by().values('cow').distinct().count(),
    }


def milk_cow_breakdown(farm, date):
    """Which cows were milked on one day and how much each gave per session
    (the "Cows milked" table on the milk records page), plus the active
    milking cows with nothing logged for that day.

    Each row's 'sessions' list lines up with cows.models.Session order
    (morning, noon, evening); a slot is None when that session wasn't logged
    for the cow, which is not the same as a logged 0."""
    from .models import Cow, MilkRecord, Session

    order = [session.value for session in Session]
    rows = {}
    records = (
        MilkRecord.objects.filter(farm=farm, date=date)
        .select_related('cow', 'block').order_by('block__name', 'cow__tag_id')
    )
    for record in records:
        row = rows.setdefault(record.cow_id, {
            'cow': record.cow, 'block': record.block, 'sessions': [None] * len(order), 'total': Decimal('0'),
        })
        row['sessions'][order.index(record.session)] = record.liters
        row['total'] += record.liters
    milked = list(rows.values())

    not_milked = list(
        Cow.objects.filter(farm=farm, status=Cow.Status.ACTIVE, category=Cow.Category.COW)
        .exclude(pk__in=rows.keys()).select_related('block').order_by('block__name', 'tag_id')
    )
    return {
        'milked': milked,
        'not_milked': not_milked,
        'session_totals': [
            sum((row['sessions'][i] or Decimal('0') for row in milked), Decimal('0')) for i in range(len(order))
        ],
        'total': sum((row['total'] for row in milked), Decimal('0')),
    }
