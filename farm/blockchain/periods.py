"""Period bookkeeping for batch FIQ minting.

Milk certificates and worker data rewards mint FIQ for a *date range* of
records. If two mints could cover the same day, the same records would earn
FIQ twice, so a new period is refused when it overlaps one already minted
(inclusive dates: a period ending 10 Sep and one starting 10 Sep overlap).
"""
from datetime import date, timedelta

from .models import FiqLedgerEntry, MilkProductionCertificate


def overlapping_certificates(farm, start, end):
    """Milk certificates for this farm that share at least one day with [start, end]."""
    return MilkProductionCertificate.objects.filter(farm=farm, start_date__lte=end, end_date__gte=start)


def overlapping_worker_rewards(farm, worker_user, start, end):
    """Data-record rewards already minted for this worker on this farm over any day in [start, end]."""
    return FiqLedgerEntry.objects.filter(
        farm=farm, reason=FiqLedgerEntry.Reason.DATA_RECORDED, earned_by=worker_user,
        period_start__lte=end, period_end__gte=start,
    )


def format_period(start, end):
    return f'{start:%d %b %Y} – {end:%d %b %Y}'


def next_certificate_start(farm, fallback_days=30):
    """The first day after the latest minted milk period - the natural start
    of the next one - or `fallback_days` ago if nothing has been minted yet."""
    latest = MilkProductionCertificate.objects.filter(farm=farm).order_by('-end_date').first()
    today = date.today()
    if latest:
        return min(latest.end_date + timedelta(days=1), today)
    return today - timedelta(days=fallback_days)
