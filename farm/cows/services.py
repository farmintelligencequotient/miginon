from decimal import Decimal

from django.db.models import Sum


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

    by_session = dict(
        MilkRecord.objects.filter(farm=farm, date=date)
        .order_by().values_list('session').annotate(total=Sum('liters'))
    )
    sessions = [
        {
            'key': session.value,
            'label': session.label,
            'icon': SESSION_ICONS[session.value],
            'liters': by_session.get(session.value) or Decimal('0'),
            'logged': session.value in by_session,
        }
        for session in Session
    ]
    return {
        'date': date,
        'sessions': sessions,
        'total': sum((row['liters'] for row in sessions), Decimal('0')),
        'logged_count': sum(1 for row in sessions if row['logged']),
    }
