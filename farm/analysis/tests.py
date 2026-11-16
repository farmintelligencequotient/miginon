from datetime import date
from unittest.mock import Mock, patch

from django.test import TestCase

from accounts.models import User
from farms.models import Farm

from .exporters import build_pdf_bytes, export_csv, export_xlsx
from .reports import build_report

_OPEN_METEO_PAYLOAD = {
    'current': {'temperature_2m': 24.5, 'weather_code': 3},
    'daily': {
        'time': ['2026-08-30', '2026-08-31', '2026-09-01', '2026-09-02', '2026-09-03'],
        'weather_code': [3, 1, 61, 0, 2],
        'temperature_2m_max': [26, 27, 24, 28, 25],
        'temperature_2m_min': [14, 15, 13, 16, 14],
        'precipitation_probability_max': [10, 5, 60, 0, 20],
    },
}


class ReportWeatherTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email='report@example.com', first_name='Rep')
        self.farm = Farm.objects.create(name='Report Farm', owner=self.user, county='Uasin Gishu', location='Eldoret')
        self.start = date(2026, 8, 1)
        self.end = date(2026, 8, 31)

    def test_report_has_no_weather_without_coordinates(self):
        report = build_report(self.farm, self.start, self.end, 'August 2026')
        self.assertIsNone(report['weather'])

    def test_exporters_do_not_crash_without_weather(self):
        report = build_report(self.farm, self.start, self.end, 'August 2026')
        self.assertEqual(export_csv(report).status_code, 200)
        self.assertEqual(export_xlsx(report).status_code, 200)
        self.assertTrue(build_pdf_bytes(report).startswith(b'%PDF'))

    @patch('weather.services.requests.get')
    def test_report_includes_weather_when_available(self, mock_get):
        self.farm.latitude = 0.52
        self.farm.longitude = 35.27
        self.farm.save(update_fields=['latitude', 'longitude'])
        mock_get.return_value = Mock(status_code=200, json=lambda: _OPEN_METEO_PAYLOAD)
        mock_get.return_value.raise_for_status = lambda: None

        report = build_report(self.farm, self.start, self.end, 'August 2026')
        self.assertIsNotNone(report['weather'])
        self.assertEqual(len(report['weather']['days']), 5)

        self.assertEqual(export_csv(report).status_code, 200)
        self.assertEqual(export_xlsx(report).status_code, 200)
        self.assertTrue(build_pdf_bytes(report).startswith(b'%PDF'))


class ReportMilkSessionTests(TestCase):
    """Every milk breakdown in the report carries its morning/noon/evening split."""

    def setUp(self):
        from datetime import time
        from decimal import Decimal
        from cows.models import Cow, MilkRecord, Session
        from farms.models import Block
        self.user = User.objects.create_user(email='sessions@example.com', first_name='Ses')
        self.farm = Farm.objects.create(name='Session Farm', owner=self.user)
        block = Block.objects.create(farm=self.farm, name='Block A', created_by=self.user)
        cow_a = Cow.objects.create(farm=self.farm, block=block, tag_id='S-1', added_by=self.user)
        cow_b = Cow.objects.create(farm=self.farm, block=block, tag_id='S-2', added_by=self.user)
        rows = [
            (cow_a, date(2026, 8, 1), Session.AM, '8.00'),
            (cow_a, date(2026, 8, 1), Session.PM, '6.00'),
            (cow_b, date(2026, 8, 1), Session.AM, '7.00'),
            (cow_a, date(2026, 8, 2), Session.NOON, '4.00'),
            (cow_a, date(2026, 9, 1), Session.AM, '9.00'),  # outside the period
        ]
        for cow, day, session, liters in rows:
            MilkRecord.objects.create(
                farm=self.farm, cow=cow, block=block, date=day, session=session,
                recorded_time=time(6, 0), liters=Decimal(liters),
            )
        self.report = build_report(self.farm, date(2026, 8, 1), date(2026, 8, 31), 'August 2026')

    def test_by_session_totals(self):
        by_key = {row['key']: row for row in self.report['milk']['by_session']}
        self.assertEqual(float(by_key['am']['liters']), 15.0)
        self.assertEqual(float(by_key['noon']['liters']), 4.0)
        self.assertEqual(float(by_key['pm']['liters']), 6.0)
        self.assertEqual(by_key['am']['share'], 60.0)
        self.assertEqual(float(self.report['milk']['total_liters']), 25.0)

    def test_daily_and_cow_rows_carry_sessions(self):
        first_day = self.report['milk']['daily'][0]
        self.assertEqual((float(first_day['am']), float(first_day['noon']), float(first_day['pm'])), (15.0, 0.0, 6.0))
        cow_a = next(r for r in self.report['milk']['by_cow'] if r['cow__tag_id'] == 'S-1')
        self.assertEqual((float(cow_a['am']), float(cow_a['noon']), float(cow_a['pm'])), (8.0, 4.0, 6.0))
        self.assertEqual(float(cow_a['liters']), 18.0)

    def test_every_export_format_includes_the_sessions(self):
        import io
        from openpyxl import load_workbook
        csv_text = export_csv(self.report).content.decode('utf-8')
        self.assertIn('By session', csv_text)
        self.assertIn('Morning (L),Noon (L),Evening (L),Total (L)', csv_text)
        sheet = load_workbook(io.BytesIO(export_xlsx(self.report).content))['Milk']
        cells = [cell for row in sheet.iter_rows(values_only=True) for cell in row]
        self.assertIn('By session', cells)
        self.assertIn('Evening (L)', cells)
        self.assertTrue(build_pdf_bytes(self.report).startswith(b'%PDF'))

    def test_email_summary_lists_the_sessions(self):
        from django.template.loader import render_to_string
        html = render_to_string('emails/farm_report.html', {
            'report': self.report, 'farm': self.farm, 'analysis_url': 'https://example.com/',
        })
        self.assertIn('Morning', html)
        self.assertIn('15L', html)

    def test_report_lists_cows_milked_and_not_milked(self):
        from cows.models import Cow
        from farms.models import Block
        block = Block.objects.get(farm=self.farm, name='Block A')
        Cow.objects.create(farm=self.farm, block=block, tag_id='S-3', added_by=self.user)
        Cow.objects.create(farm=self.farm, block=block, tag_id='S-4', status=Cow.Status.DRY, added_by=self.user)
        Cow.objects.create(farm=self.farm, block=block, tag_id='S-5', category=Cow.Category.CALF, added_by=self.user)
        Cow.objects.create(farm=self.farm, block=block, tag_id='S-6', status=Cow.Status.SOLD, added_by=self.user)
        report = build_report(self.farm, date(2026, 8, 1), date(2026, 8, 31), 'August 2026')
        self.assertEqual(report['milk']['cows_milked'], 2)
        self.assertEqual(
            {row['tag_id']: row['note'] for row in report['milk']['not_milked']},
            {'S-3': 'No milk recorded', 'S-4': 'Dry', 'S-5': 'Calf'},
        )
        self.assertEqual({row['key']: row['cows'] for row in report['milk']['by_session']}, {'am': 2, 'noon': 1, 'pm': 1})
        csv_text = export_csv(report).content.decode('utf-8')
        self.assertIn('Not milked in this period', csv_text)
        self.assertIn('S-4,,Block A,Dry', csv_text)
        self.assertEqual(export_xlsx(report).status_code, 200)
        self.assertTrue(build_pdf_bytes(report).startswith(b'%PDF'))

    def test_an_empty_period_still_exports(self):
        report = build_report(self.farm, date(2025, 1, 1), date(2025, 1, 31), 'January 2025')
        self.assertEqual([float(r['liters']) for r in report['milk']['by_session']], [0.0, 0.0, 0.0])
        self.assertEqual(export_csv(report).status_code, 200)
        self.assertEqual(export_xlsx(report).status_code, 200)
        self.assertTrue(build_pdf_bytes(report).startswith(b'%PDF'))
