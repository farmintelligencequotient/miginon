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


def cow_group_label(category, status):
    """The one-word group an animal is listed under wherever milk is broken
    down by cow: Dry for a dry cow, otherwise its category (Cow / Heifer /
    Calf / Bull). Takes the raw values so report queries that only select
    those two columns can use it too."""
    from .models import Cow

    if status == Cow.Status.DRY:
        return str(Cow.Status.DRY.label)
    return str(Cow.Category(category).label) if category in Cow.Category.values else str(category or '')


def cows_not_milked(farm, milked_cow_ids):
    """Every animal still on the farm that isn't in milked_cow_ids - dry
    cows, heifers, calves and bulls included; only sold and deceased animals
    are left out. Each comes back with a .note saying why it's expected
    (Dry / Heifer / Calf / Bull), blank for an ordinary active cow - the one
    case that needs chasing. Shared by the milk records page and the farm
    reports so both always list the same animals."""
    from .models import Cow

    cows = list(
        Cow.objects.filter(farm=farm, status__in=[Cow.Status.ACTIVE, Cow.Status.DRY])
        .exclude(pk__in=list(milked_cow_ids)).select_related('block').order_by('block__name', 'tag_id')
    )
    for cow in cows:
        if cow.status == Cow.Status.DRY:
            cow.note = str(cow.get_status_display())
        elif cow.category != Cow.Category.COW:
            cow.note = str(cow.get_category_display())
        else:
            cow.note = ''
    return cows


def milk_cow_breakdown(farm, date):
    """Which cows were milked on one day and how much each gave per session
    (the "Cows milked" table on the milk records page), plus every other
    animal still on the farm with nothing logged for that day - dry cows,
    heifers, calves and bulls included, each tagged with why (see 'note');
    only sold and deceased animals are left out.

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
            'cow': record.cow, 'block': record.block,
            'category': cow_group_label(record.cow.category, record.cow.status),
            'sessions': [None] * len(order), 'total': Decimal('0'),
        })
        row['sessions'][order.index(record.session)] = record.liters
        row['total'] += record.liters
    milked = list(rows.values())

    not_milked = cows_not_milked(farm, rows.keys())
    return {
        'milked': milked,
        'not_milked': not_milked,
        'session_totals': [
            sum((row['sessions'][i] or Decimal('0') for row in milked), Decimal('0')) for i in range(len(order))
        ],
        'total': sum((row['total'] for row in milked), Decimal('0')),
    }
