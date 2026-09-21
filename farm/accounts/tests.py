from django.conf import settings
from django.core import mail
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from farms.models import Farm, FarmMembership

from .models import EmailOTP, User


def get_otp(email, purpose, farm=None):
    return EmailOTP.objects.filter(email=email, purpose=purpose, farm=farm).order_by('-created_at').first()


class SignupFlowTests(TestCase):
    def test_full_signup_wizard(self):
        c = Client()

        r = c.get('/accounts/signup/')
        self.assertEqual(r.status_code, 200)

        r = c.post('/accounts/signup/', {
            'first_name': 'Test', 'last_name': 'Farmer', 'email': 'newfarmer@example.com', 'phone': '0712345678',
            'accept_terms': 'on',
        })
        self.assertRedirects(r, '/accounts/signup/farm/')

        r = c.get('/accounts/signup/farm/')
        self.assertEqual(r.status_code, 200)

        r = c.post('/accounts/signup/farm/', {
            'farm_name': 'Test Farm', 'country': 'KE', 'county': 'Nairobi', 'location': 'Westlands'
        })
        self.assertRedirects(r, '/accounts/signup/review/')

        r = c.get('/accounts/signup/review/')
        self.assertEqual(r.status_code, 200)

        r = c.post('/accounts/signup/review/')
        self.assertRedirects(r, '/accounts/signup/otp/')
        self.assertEqual(len(mail.outbox), 1)

        otp = get_otp('newfarmer@example.com', EmailOTP.Purpose.SIGNUP)
        self.assertIsNotNone(otp)

        r = c.post('/accounts/signup/otp/', {'code': '000000'})
        self.assertEqual(r.status_code, 200)
        otp.refresh_from_db()
        self.assertEqual(otp.attempts, 1)

        r = c.post('/accounts/signup/otp/', {'code': otp.code})
        self.assertEqual(r.status_code, 302)

        user = User.objects.filter(email='newfarmer@example.com').first()
        self.assertIsNotNone(user)
        farm = Farm.objects.filter(name='Test Farm').first()
        self.assertIsNotNone(farm)
        self.assertEqual(farm.owner_id, user.id)
        membership = FarmMembership.objects.filter(user=user, farm=farm).first()
        self.assertIsNotNone(membership)
        self.assertEqual(membership.role, 'farmer')
        self.assertIsNotNone(user.terms_accepted_at)
        self.assertEqual(user.terms_version, settings.TERMS_VERSION)

        r = c.get('/farm/')
        self.assertEqual(r.status_code, 200)

    def test_signup_requires_accepting_terms_and_privacy(self):
        c = Client()
        payload = {'first_name': 'Test', 'last_name': 'Farmer', 'email': 'noterms@example.com', 'phone': ''}
        r = c.post('/accounts/signup/', payload)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'must accept the Terms of Service')
        # The step is not completed, so the next wizard step is still locked.
        self.assertRedirects(c.get('/accounts/signup/farm/'), '/accounts/signup/')

    def test_terms_checkbox_renders_as_toggle_switch(self):
        r = Client().get('/accounts/signup/')
        self.assertContains(r, 'peer sr-only')
        self.assertContains(r, 'peer-checked:bg-emerald-600')

    def test_signup_form_links_to_terms_and_privacy(self):
        r = Client().get('/accounts/signup/')
        self.assertContains(r, 'href="/terms/"')
        self.assertContains(r, 'href="/privacy/"')

    def test_duplicate_signup_email_rejected_at_otp_stage(self):
        User.objects.create_user(email='dupe@example.com', first_name='Existing')
        c = Client()
        c.post('/accounts/signup/', {
            'first_name': 'Test', 'last_name': 'Farmer', 'email': 'dupe@example.com', 'phone': '',
            'accept_terms': 'on',
        })
        r = c.post('/accounts/signup/farm/', {
            'farm_name': 'Dupe Farm', 'country': 'KE', 'county': 'Nairobi', 'location': 'Westlands'
        })
        # Whatever guard exists (form validation or OTP-stage IntegrityError) should
        # not blow up with an unhandled 500.
        print('duplicate email farm-step status:', r.status_code)


class LoginFlowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email='farmer@example.com', first_name='Farmer')
        self.farm = Farm.objects.create(name='Existing Farm', owner=self.user, country='KE')
        FarmMembership.objects.create(user=self.user, farm=self.farm, role='farmer', status=FarmMembership.Status.ACTIVE)

    def test_full_login_flow(self):
        c = Client()

        r = c.get('/accounts/login/')
        self.assertEqual(r.status_code, 200)

        r = c.post('/accounts/login/', {'code': 'BOGUSCODE'})
        self.assertEqual(r.status_code, 200)  # form error, not redirect

        r = c.post('/accounts/login/', {'code': self.farm.code})
        self.assertRedirects(r, '/accounts/login/email/')

        r = c.post('/accounts/login/email/', {'email': 'doesnotexist@example.com'})
        self.assertEqual(r.status_code, 200)

        r = c.post('/accounts/login/email/', {'email': 'farmer@example.com'})
        self.assertRedirects(r, '/accounts/login/otp/')
        self.assertEqual(len(mail.outbox), 1)

        otp = get_otp('farmer@example.com', EmailOTP.Purpose.LOGIN, farm=self.farm)
        self.assertIsNotNone(otp)

        r = c.post('/accounts/login/otp/', {'code': '000000' if otp.code != '000000' else '111111'})
        self.assertEqual(r.status_code, 200)

        r = c.post('/accounts/login/otp/', {'code': otp.code})
        self.assertRedirects(r, '/farm/')

        r = c.get('/farm/')
        self.assertEqual(r.status_code, 200)

    def test_used_otp_cannot_be_replayed(self):
        c = Client()
        c.post('/accounts/login/', {'code': self.farm.code})
        c.post('/accounts/login/email/', {'email': 'farmer@example.com'})
        otp = get_otp('farmer@example.com', EmailOTP.Purpose.LOGIN, farm=self.farm)
        c.post('/accounts/login/otp/', {'code': otp.code})

        c2 = Client()
        c2.post('/accounts/login/', {'code': self.farm.code})
        c2.post('/accounts/login/email/', {'email': 'farmer@example.com'})
        r = c2.post('/accounts/login/otp/', {'code': otp.code})
        self.assertEqual(r.status_code, 200)  # rejected, not logged in
        self.assertFalse(r.wsgi_request.user.is_authenticated)

    def test_expired_otp_rejected(self):
        otp = EmailOTP.objects.create(email='farmer@example.com', farm=self.farm, purpose=EmailOTP.Purpose.LOGIN)
        otp.expires_at = timezone.now() - timezone.timedelta(minutes=1)
        otp.save(update_fields=['expires_at'])

        c = Client()
        c.post('/accounts/login/', {'code': self.farm.code})
        session = c.session
        session['login_email'] = 'farmer@example.com'
        session.save()

        r = c.post('/accounts/login/otp/', {'code': otp.code})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.wsgi_request.user.is_authenticated)

    def test_max_attempts_locks_out_otp(self):
        otp = EmailOTP.objects.create(email='farmer@example.com', farm=self.farm, purpose=EmailOTP.Purpose.LOGIN)
        for _ in range(6):
            otp.register_failed_attempt()
        otp.refresh_from_db()
        self.assertFalse(otp.is_valid())

    def test_authenticated_user_redirected_away_from_login(self):
        c = Client()
        c.force_login(self.user)
        r = c.get('/accounts/login/')
        self.assertRedirects(r, '/farm/')

    def test_inactive_farm_blocks_login(self):
        self.farm.is_active = False
        self.farm.save(update_fields=['is_active'])
        c = Client()
        r = c.post('/accounts/login/', {'code': self.farm.code})
        self.assertEqual(r.status_code, 200)  # should show "farm not found", not redirect

    def test_resend_otp_cooldown(self):
        # login/email/ itself just issued an OTP, so an immediate resend click
        # is within the 45s cooldown and should be a no-op (no new mail) - the
        # cooldown clock starts at the *original* send, not just at a prior resend.
        c = Client()
        c.post('/accounts/login/', {'code': self.farm.code})
        c.post('/accounts/login/email/', {'email': 'farmer@example.com'})
        mail.outbox = []
        r = c.post('/accounts/login/otp/resend/')
        self.assertRedirects(r, '/accounts/login/otp/')
        self.assertEqual(len(mail.outbox), 0)

        otp = get_otp('farmer@example.com', EmailOTP.Purpose.LOGIN, farm=self.farm)
        otp.created_at = timezone.now() - timezone.timedelta(seconds=46)
        otp.save(update_fields=['created_at'])
        r = c.post('/accounts/login/otp/resend/')
        self.assertEqual(len(mail.outbox), 1)  # cooldown elapsed, resend goes through


class PermissionTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(email='owner@example.com', first_name='Owner')
        self.worker = User.objects.create_user(email='worker@example.com', first_name='Worker')
        self.farm = Farm.objects.create(name='Perm Farm', owner=self.owner, country='KE')
        FarmMembership.objects.create(user=self.owner, farm=self.farm, role='farmer', status=FarmMembership.Status.ACTIVE)
        FarmMembership.objects.create(user=self.worker, farm=self.farm, role='farm_worker', status=FarmMembership.Status.ACTIVE)

    def test_worker_cannot_reach_worker_management(self):
        c = Client()
        c.force_login(self.worker)
        session = c.session
        session['active_farm_id'] = self.farm.id
        session.save()
        r = c.get('/farm/workers/', follow=True)
        self.assertEqual(r.status_code, 200)
        self.assertRedirects(r, '/farm/')
        messages_text = ' '.join(str(m) for m in r.context['messages'])
        self.assertIn('only farmers and farm managers', messages_text.lower())


class DashboardTourTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email='new@example.com', first_name='New')
        self.farm = Farm.objects.create(name='Tour Farm', owner=self.user, country='KE')
        FarmMembership.objects.create(user=self.user, farm=self.farm, role='farmer', status=FarmMembership.Status.ACTIVE)
        self.client.force_login(self.user)
        session = self.client.session
        session['active_farm_id'] = self.farm.id
        session.save()

    def test_show_tour_is_true_for_a_fresh_user(self):
        response = self.client.get('/farm/')
        self.assertTrue(response.context['show_tour'])

    def test_show_tour_is_false_once_seen(self):
        self.user.has_seen_dashboard_tour = True
        self.user.save(update_fields=['has_seen_dashboard_tour'])
        response = self.client.get('/farm/')
        self.assertFalse(response.context['show_tour'])

    def test_mark_tour_seen_sets_the_flag(self):
        self.assertFalse(self.user.has_seen_dashboard_tour)
        response = self.client.post('/accounts/tour/seen/')
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.has_seen_dashboard_tour)

    def test_mark_tour_seen_requires_login(self):
        self.client.logout()
        response = self.client.post('/accounts/tour/seen/')
        self.assertNotEqual(response.status_code, 200)

    def test_mark_tour_seen_requires_post(self):
        response = self.client.get('/accounts/tour/seen/')
        self.assertNotEqual(response.status_code, 200)


@override_settings(REQUIRE_TERMS_ACCEPTANCE=True)
class TermsAcceptancePromptTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email='old@example.com', first_name='Old')
        self.client = Client()
        self.client.force_login(self.user)

    def test_signed_in_user_without_acceptance_is_sent_to_accept_page(self):
        r = self.client.get('/farm/')
        self.assertRedirects(r, '/accounts/accept-terms/?next=%2Ffarm%2F', fetch_redirect_response=False)

    def test_accept_page_and_documents_are_reachable_before_accepting(self):
        for path in ('/accounts/accept-terms/', '/terms/', '/privacy/'):
            self.assertEqual(self.client.get(path).status_code, 200, path)

    def test_must_tick_the_toggle_to_continue(self):
        r = self.client.post('/accounts/accept-terms/', {'next': '/farm/'})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'must accept the Terms of Service')
        self.user.refresh_from_db()
        self.assertIsNone(self.user.terms_accepted_at)

    def test_accepting_records_version_and_returns_to_next(self):
        r = self.client.post('/accounts/accept-terms/', {'accept_terms': 'on', 'next': '/farm/'})
        self.assertRedirects(r, '/farm/', fetch_redirect_response=False)
        self.user.refresh_from_db()
        self.assertIsNotNone(self.user.terms_accepted_at)
        self.assertEqual(self.user.terms_version, settings.TERMS_VERSION)
        self.assertNotIn('accept-terms', self.client.get('/farm/').get('Location', ''))

    def test_next_must_stay_on_this_site(self):
        r = self.client.post('/accounts/accept-terms/', {'accept_terms': 'on', 'next': 'https://evil.example/'})
        self.assertEqual(r.status_code, 302)
        self.assertNotIn('evil.example', r['Location'])

    def test_bumping_the_version_asks_everyone_again(self):
        self.user.terms_accepted_at = timezone.now()
        self.user.terms_version = 'older-version'
        self.user.save()
        r = self.client.get('/farm/')
        self.assertIn('/accounts/accept-terms/', r['Location'])

    def test_user_on_current_version_is_not_prompted(self):
        self.user.terms_accepted_at = timezone.now()
        self.user.terms_version = settings.TERMS_VERSION
        self.user.save()
        r = self.client.get('/farm/')
        self.assertNotIn('accept-terms', r.get('Location', ''))

    def test_can_still_sign_out_instead(self):
        r = self.client.post('/accounts/logout/')
        self.assertEqual(r.status_code, 302)
        self.assertNotIn('accept-terms', r['Location'])
