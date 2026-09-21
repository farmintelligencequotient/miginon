import json

from django.test import TestCase

from accounts.models import User
from farms.models import Farm, FarmMembership, FarmRole

from .models import LandParcel
from .services import area_sqm, perimeter_m

# Roughly a 100m x 100m square near the equator, where 1 degree of
# longitude and latitude are both close to 111,320m - used to sanity-check
# the geodesic area/perimeter formulas against an easy expected value.
_SQUARE_100M = [
    [36.8000, -1.2800],
    [36.8009, -1.2800],
    [36.8009, -1.2791],
    [36.8000, -1.2791],
]


class GeodesyServiceTests(TestCase):
    def test_area_of_roughly_square_hectare(self):
        area = area_sqm(_SQUARE_100M)
        self.assertAlmostEqual(area, 10000, delta=200)

    def test_perimeter_of_roughly_square_hectare(self):
        perimeter = perimeter_m(_SQUARE_100M)
        self.assertAlmostEqual(perimeter, 400, delta=10)

    def test_area_of_line_is_zero(self):
        self.assertEqual(area_sqm(_SQUARE_100M[:2]), 0.0)


class ParcelMapViewTests(TestCase):
    def setUp(self):
        self.farmer = User.objects.create_user(email='farmer@example.com', first_name='Fay')
        self.worker = User.objects.create_user(email='worker@example.com', first_name='Wes')
        self.farm = Farm.objects.create(name='Geo Farm', owner=self.farmer, latitude=-1.28, longitude=36.80)
        FarmMembership.objects.create(user=self.farmer, farm=self.farm, role=FarmRole.FARMER)
        FarmMembership.objects.create(user=self.worker, farm=self.farm, role=FarmRole.WORKER)

    def _login(self, user):
        self.client.force_login(user)
        session = self.client.session
        session['active_farm_id'] = self.farm.id
        session.save()

    def test_map_page_loads_for_any_member(self):
        self._login(self.worker)
        response = self.client.get('/geomap/')
        self.assertEqual(response.status_code, 200)

    def test_farmer_can_save_a_parcel(self):
        self._login(self.farmer)
        response = self.client.post('/geomap/save/', {
            'name': 'North boundary',
            'block': '',
            'coordinates_json': json.dumps(_SQUARE_100M),
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        parcel = LandParcel.objects.get(farm=self.farm)
        self.assertEqual(parcel.name, 'North boundary')
        self.assertEqual(parcel.created_by, self.farmer)
        self.assertAlmostEqual(float(parcel.area_sqm), 10000, delta=200)

    def test_worker_cannot_save_a_parcel(self):
        self._login(self.worker)
        response = self.client.post('/geomap/save/', {
            'name': 'Should be blocked',
            'block': '',
            'coordinates_json': json.dumps(_SQUARE_100M),
        })
        self.assertEqual(LandParcel.objects.count(), 0)
        self.assertNotEqual(response.status_code, 200)

    def test_fewer_than_three_points_is_rejected(self):
        self._login(self.farmer)
        self.client.post('/geomap/save/', {
            'name': 'Too few points',
            'block': '',
            'coordinates_json': json.dumps(_SQUARE_100M[:2]),
        })
        self.assertEqual(LandParcel.objects.count(), 0)

    def test_farmer_can_delete_a_parcel(self):
        parcel = LandParcel.objects.create(
            farm=self.farm, name='To delete', coordinates=_SQUARE_100M,
            area_sqm=10000, perimeter_m=400, created_by=self.farmer,
        )
        self._login(self.farmer)
        self.client.post(f'/geomap/{parcel.id}/delete/')
        self.assertFalse(LandParcel.objects.filter(id=parcel.id).exists())


from django.test import override_settings

from .colors import farm_color, farm_parcel_color, parcel_color


class ColorTests(TestCase):
    def test_parcel_colours_are_distinct(self):
        colours = {parcel_color(i) for i in range(30)}
        self.assertEqual(len(colours), 30)

    def test_farm_hues_differ_and_parcels_within_a_farm_vary(self):
        self.assertNotEqual(farm_color(0), farm_color(1))
        within = {farm_parcel_color(0, i) for i in range(5)}
        self.assertEqual(len(within), 5)


@override_settings(TOMTOM_API_KEY='k', TOMTOM_STYLE_ID='s')
class ParcelPrivacyAndAdminMapTests(TestCase):
    def setUp(self):
        self.farmer = User.objects.create_user(email='a@example.com', first_name='Ann', last_name='One')
        self.other_farmer = User.objects.create_user(email='b@example.com', first_name='Bob', last_name='Two')
        self.admin = User.objects.create_user(email='admin@example.com', first_name='Ada', platform_role='admin')
        self.farm = Farm.objects.create(name='Alpha Farm', owner=self.farmer, latitude=-1.28, longitude=36.80)
        self.other = Farm.objects.create(name='Beta Farm', owner=self.other_farmer, latitude=-1.30, longitude=36.90)
        FarmMembership.objects.create(user=self.farmer, farm=self.farm, role=FarmRole.FARMER)
        FarmMembership.objects.create(user=self.other_farmer, farm=self.other, role=FarmRole.FARMER)
        for farm, names in ((self.farm, ['Alpha North', 'Alpha South']), (self.other, ['Beta Field'])):
            for name in names:
                LandParcel.objects.create(
                    farm=farm, name=name, coordinates=_SQUARE_100M, area_sqm=10000, perimeter_m=400,
                )

    def _login_farm(self, user, farm):
        self.client.force_login(user)
        session = self.client.session
        session['active_farm_id'] = farm.id
        session.save()

    def test_farm_only_sees_its_own_parcels(self):
        self._login_farm(self.farmer, self.farm)
        page = self.client.get('/geomap/').content.decode()
        self.assertIn('Alpha North', page)
        self.assertIn('Alpha South', page)
        self.assertNotIn('Beta Field', page)
        self.assertNotIn('Beta Farm', page)

    def test_parcels_on_a_farms_map_get_different_colours(self):
        self._login_farm(self.farmer, self.farm)
        response = self.client.get('/geomap/')
        colours = {p.color for p in response.context['parcels']}
        self.assertEqual(len(colours), 2)

    def test_map_has_a_fullscreen_control_wrapping_the_whole_shell(self):
        self._login_farm(self.farmer, self.farm)
        page = self.client.get('/geomap/').content.decode()
        self.assertIn('js/map_fullscreen.js', page)
        self.assertIn("FarmIQMapFullscreen(document.getElementById('geomap-shell')", page)
        # the draw toolbar and save panel sit inside the shell that goes fullscreen
        shell_start = page.index('id="geomap-shell"')
        self.assertLess(shell_start, page.index('id="geomap-draw-toolbar"'))
        self.assertLess(shell_start, page.index('id="geomap-save-panel"'))

    def test_farm_users_cannot_open_the_admin_map(self):
        self._login_farm(self.farmer, self.farm)
        response = self.client.get('/geomap/admin/')
        self.assertEqual(response.status_code, 302)

    def test_admin_sees_every_farms_parcels_in_farm_colours(self):
        self.client.force_login(self.admin)
        response = self.client.get('/geomap/admin/')
        self.assertEqual(response.status_code, 200)
        data = response.context['parcels_data']
        self.assertEqual({p['name'] for p in data}, {'Alpha North', 'Alpha South', 'Beta Field'})
        self.assertEqual({g['name'] for g in response.context['groups']}, {'Alpha Farm', 'Beta Farm'})
        alpha = {p['color'] for p in data if p['farm'] == 'Alpha Farm'}
        beta = {p['color'] for p in data if p['farm'] == 'Beta Farm'}
        self.assertTrue(alpha.isdisjoint(beta))
        self.assertContains(response, 'geomap-admin-shell')

    def test_farms_without_parcels_are_not_listed(self):
        Farm.objects.create(name='Empty Farm', owner=self.farmer)
        self.client.force_login(self.admin)
        response = self.client.get('/geomap/admin/')
        self.assertNotIn('Empty Farm', {g['name'] for g in response.context['groups']})
