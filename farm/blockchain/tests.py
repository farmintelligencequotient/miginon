from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase

from accounts.models import User
from cows.models import Cow, MilkRecord
from farms.models import Block, Farm, FarmMembership, FarmRole

from .models import FiqLedgerEntry, MilkProductionCertificate

MINT_OK = {'transaction_id': '0.0.1@1', 'amount_minted': Decimal('1')}


class PeriodMintingTests(TestCase):
    def setUp(self):
        self.farmer = User.objects.create_user(email='farmer@example.com', first_name='Fay')
        self.worker = User.objects.create_user(email='w1@example.com', first_name='Wes')
        self.worker2 = User.objects.create_user(email='w2@example.com', first_name='Wanda')
        self.farm = Farm.objects.create(name='Mint Farm', owner=self.farmer)
        FarmMembership.objects.create(user=self.farmer, farm=self.farm, role=FarmRole.FARMER)
        self.m1 = FarmMembership.objects.create(user=self.worker, farm=self.farm, role=FarmRole.WORKER)
        self.m2 = FarmMembership.objects.create(user=self.worker2, farm=self.farm, role=FarmRole.WORKER)
        block = Block.objects.create(farm=self.farm, name='A')
        self.cow = Cow.objects.create(
            farm=self.farm, block=block, tag_id='C1', category=Cow.Category.COW, gender=Cow.Gender.FEMALE,
        )
        self.today = date.today()
        # milk on each of the last 20 days, logged by worker 1 (2 records/day on day -1 for worker 2)
        for offset in range(1, 21):
            MilkRecord.objects.create(
                farm=self.farm, cow=self.cow, block=block, date=self.today - timedelta(days=offset),
                session='AM', liters=Decimal('10'), recorded_by=self.worker,
            )
        MilkRecord.objects.create(
            farm=self.farm, cow=self.cow, block=block, date=self.today - timedelta(days=1),
            session='PM', liters=Decimal('5'), recorded_by=self.worker2,
        )
        self.client.force_login(self.farmer)
        session = self.client.session
        session['active_farm_id'] = self.farm.id
        session.save()

    def d(self, days_ago):
        return (self.today - timedelta(days=days_ago)).isoformat()

    def _certificate(self, start_ago, end_ago):
        return self.client.post('/wallet/certificates/mint/', {
            'start_date': self.d(start_ago), 'end_date': self.d(end_ago),
        })

    def _reward(self, membership, start_ago, end_ago):
        return self.client.post('/wallet/rewards/worker/', {
            'worker_id': membership.id, 'start_date': self.d(start_ago), 'end_date': self.d(end_ago),
        })

    # ------------------------------------------------------- milk certificates
    @patch('blockchain.views.mint_fiq', return_value=MINT_OK)
    def test_first_certificate_mints(self, mint):
        self._certificate(10, 6)
        self.assertEqual(MilkProductionCertificate.objects.filter(farm=self.farm).count(), 1)
        mint.assert_called_once()

    @patch('blockchain.views.mint_fiq', return_value=MINT_OK)
    def test_identical_period_is_blocked(self, mint):
        self._certificate(10, 6)
        self._certificate(10, 6)
        self.assertEqual(MilkProductionCertificate.objects.count(), 1)
        self.assertEqual(mint.call_count, 1)

    @patch('blockchain.views.mint_fiq', return_value=MINT_OK)
    def test_partially_overlapping_periods_are_blocked(self, mint):
        self._certificate(10, 6)
        for start_ago, end_ago in ((12, 8), (8, 4), (9, 7), (15, 3)):
            self._certificate(start_ago, end_ago)
        self.assertEqual(MilkProductionCertificate.objects.count(), 1)
        self.assertEqual(mint.call_count, 1)

    @patch('blockchain.views.mint_fiq', return_value=MINT_OK)
    def test_sharing_a_single_boundary_day_is_an_overlap(self, mint):
        self._certificate(10, 6)
        self._certificate(6, 3)  # starts on the day the first one ended
        self.assertEqual(MilkProductionCertificate.objects.count(), 1)

    @patch('blockchain.views.mint_fiq', return_value=MINT_OK)
    def test_back_to_back_periods_are_allowed(self, mint):
        self._certificate(10, 6)
        self._certificate(5, 2)   # starts the day after
        self._certificate(15, 11)  # ends the day before
        self.assertEqual(MilkProductionCertificate.objects.count(), 3)
        self.assertEqual(mint.call_count, 3)

    @patch('blockchain.views.mint_fiq', return_value=MINT_OK)
    def test_blocked_attempt_explains_which_period_clashes(self, mint):
        self._certificate(10, 6)
        response = self._certificate(9, 7)
        follow = self.client.get(response['Location'])
        self.assertContains(follow, 'overlaps a certificate already minted')

    @patch('blockchain.views.mint_fiq', return_value=MINT_OK)
    def test_period_cannot_end_in_the_future(self, mint):
        response = self.client.post('/wallet/certificates/mint/', {
            'start_date': self.d(3), 'end_date': (self.today + timedelta(days=2)).isoformat(),
        })
        self.assertEqual(MilkProductionCertificate.objects.count(), 0)
        mint.assert_not_called()

    @patch('blockchain.views.mint_fiq', return_value=None)
    def test_failed_hedera_mint_leaves_the_period_open_for_a_retry(self, mint):
        self._certificate(10, 6)
        self.assertEqual(MilkProductionCertificate.objects.count(), 0)
        mint.return_value = MINT_OK
        self._certificate(10, 6)
        self.assertEqual(MilkProductionCertificate.objects.count(), 1)

    @patch('blockchain.views.mint_fiq', return_value=MINT_OK)
    def test_wallet_suggests_the_day_after_the_last_certificate(self, mint):
        self._certificate(10, 6)
        response = self.client.get('/wallet/wallet/')
        self.assertContains(response, f'value="{self.d(5)}"')

    # --------------------------------------------------------- worker rewards
    @patch('blockchain.views.mint_fiq', return_value=MINT_OK)
    def test_worker_reward_overlap_is_blocked_for_the_same_worker(self, mint):
        self._reward(self.m1, 10, 6)
        self._reward(self.m1, 8, 4)
        self._reward(self.m1, 10, 6)
        rewards = FiqLedgerEntry.objects.filter(reason=FiqLedgerEntry.Reason.DATA_RECORDED, earned_by=self.worker)
        self.assertEqual(rewards.count(), 1)
        self.assertEqual(mint.call_count, 1)

    @patch('blockchain.views.mint_fiq', return_value=MINT_OK)
    def test_worker_reward_back_to_back_is_allowed(self, mint):
        self._reward(self.m1, 10, 6)
        self._reward(self.m1, 5, 2)
        self.assertEqual(FiqLedgerEntry.objects.filter(earned_by=self.worker).count(), 2)

    @patch('blockchain.views.mint_fiq', return_value=MINT_OK)
    def test_other_workers_can_be_rewarded_for_the_same_days(self, mint):
        self._reward(self.m1, 10, 1)
        self._reward(self.m2, 10, 1)
        self.assertEqual(FiqLedgerEntry.objects.filter(earned_by=self.worker).count(), 1)
        self.assertEqual(FiqLedgerEntry.objects.filter(earned_by=self.worker2).count(), 1)

    @patch('blockchain.views.mint_fiq', return_value=MINT_OK)
    def test_worker_reward_period_cannot_end_in_the_future(self, mint):
        self.client.post('/wallet/rewards/worker/', {
            'worker_id': self.m1.id, 'start_date': self.d(3),
            'end_date': (self.today + timedelta(days=1)).isoformat(),
        })
        mint.assert_not_called()

    def test_milk_certificate_and_worker_reward_do_not_block_each_other(self):
        with patch('blockchain.views.mint_fiq', return_value=MINT_OK):
            self._certificate(10, 6)
            self._reward(self.m1, 10, 6)
        self.assertEqual(MilkProductionCertificate.objects.count(), 1)
        self.assertEqual(FiqLedgerEntry.objects.filter(reason=FiqLedgerEntry.Reason.DATA_RECORDED).count(), 1)
