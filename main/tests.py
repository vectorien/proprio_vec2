# vim: ai ts=4 sts=4 et sw=4
from django.test import TestCase
from models import fees_to_cashflows, payments_to_cashflows, revision_to_cashflows,\
    revisions_to_cashflows, RentRevision, Payment,\
    Fee, Building, Property, Tenant, Cashflow, moving_average, add_month
from django.contrib.auth.models import User
from datetime import date
from django.test import Client
from django.core import urlresolvers

class BasicIntegrationTest(TestCase):
    def setUp(self):
        building = Building.objects.create(name="test building")
        property = Property.objects.create(
            name="test property", building=building,
            address="test address", area=53, rooms=2)
        tenant = Tenant.objects.create(
            property=property, name="test tenant",
            tenancy_begin_date=date(2011, 1, 1),
            tenancy_end_date=date(2013, 9, 1))
        RentRevision.objects.create(
            tenant=tenant, start_date=date(2013, 1, 1),
            end_date=date(2013, 4, 1),
            rent=300, provision=100)
        RentRevision.objects.create(
            tenant=tenant, start_date=date(2013, 4, 1),
            rent=400, provision=200)
        Fee.objects.create(
            tenant=tenant, description="test fee",
            date=date(2013, 3, 12), amount=0.03)
        Payment.objects.create(
            tenant=tenant, date=date(2013, 12, 25), amount=4200.03)
        User.objects.create_user(
            'toto', 'toto@gmail.com', 'toto_pass')
        self.tenant_id = tenant.id

    def test_root(self):
        c = Client()
        c.login(username='toto', password='toto_pass')
        response = c.get('/', follow=True)
        self.assertEqual(response.status_code, 200)

    def test_tenants(self):
        c = Client()
        c.login(username='toto', password='toto_pass')
        reversed = urlresolvers.reverse('tenants')
        response = c.get(reversed)
        self.assertEqual(response.status_code, 200)

    def test_cashflows(self):
        c = Client()
        c.login(username='toto', password='toto_pass')
        reversed = urlresolvers.reverse(
            'tenant_cashflows', args=[self.tenant_id])
        response = c.get(reversed)
        self.assertEqual(response.status_code, 200)


def cashflow_to_tuple(cashflow):
    return (cashflow.date, cashflow.amount)


class TenantBalanceTests(TestCase):

    def test_fees(self):
        fee = Fee(date=date(2011, 3, 15), amount=300.12)
        expected = (fee.date, -fee.amount)
        self.assertEqual([expected], map(
            cashflow_to_tuple,
            fees_to_cashflows(date(2011, 3, 15), [fee])),
            "nominal")

        self.assertSequenceEqual(
            [],
            fees_to_cashflows(date(2011, 3, 14), [fee]),
            "fees are counted")

    def test_payments(self):
        payment = Payment(amount=100, date=date(2011, 6, 15))
        expected = [(payment.date, payment.amount)]
        actual = payments_to_cashflows(date(2011, 6, 15), [payment])
        actual2 = map(cashflow_to_tuple, list(actual))
        self.assertEqual(
            expected, actual2, "payments are counted as positive")
        self.assertEqual(
            [],
            list(payments_to_cashflows(date(2011, 6, 14), [payment])),
            "payments are counted only after current date")

    def test_revision_to_fees(self):
        revision = RentRevision(
            start_date=date(2011, 4, 1),
            rent=200,
            provision=100)
        rentRevision_partial = RentRevision(
            start_date=date(2010, 11, 26),
            end_date=date(2011, 1, 25), 
            rent=200.0,
            provision=100.0)# 591,935483871 fee
        self.assertEqual(
            [],
            revision_to_cashflows(revision, date(2011, 3, 31)),
            "no fees before")
        self.assertEqual(
            [(date(2011, 4, 1), -200), (date(2011, 4, 1), -100)],
            map(cashflow_to_tuple, revision_to_cashflows(
                revision,
                date(2011, 4, 30))))
        self.assertEqual(
            6,
            len(revision_to_cashflows(revision, date(2011, 6, 30))),
            "following fees")


    def test_revisions_to_fees(self):
        rentRevision1 = RentRevision(
            start_date=date(2011, 1, 1),
            end_date=date(2011, 2, 28),
            rent=200,
            provision=100)
        rentRevision2 = RentRevision(
            start_date=date(2011, 3, 1),
            end_date=date(2011, 4, 30),
            rent=300,
            provision=200)
        
        self.assertEqual(0, sum([f.amount for f in revisions_to_cashflows(
            date(1990, 1, 1),
            [rentRevision1, rentRevision2])]))
        self.assertEqual(-300, sum([f.amount for f in revisions_to_cashflows(
            date(2011, 1, 15),
            [rentRevision1, rentRevision2])]))
        self.assertEqual(-1100, sum([f.amount for f in revisions_to_cashflows(
            date(2011, 3, 15),
            [rentRevision1, rentRevision2])]))
        self.assertEqual(-1600, sum([f.amount for f in revisions_to_cashflows(
            date(2011, 8, 15),
            [rentRevision1, rentRevision2])]))

        #partial_months-revisions
        rentRevision_partial_1 = RentRevision(
            start_date=date(2010, 11, 26),
            end_date=date(2011, 1, 25), 
            rent=200.0,
            provision=100.0)# 591,935483871 fee
        rentRevision_partial_2 = RentRevision(
            start_date=date(2011, 1, 26),
            end_date=date(2011, 2, 6), 
            rent=300.0,
            provision=200.0) #203,917050691 fee 
        #sum fees = 795,852534562
        self.assertEqual(-795.86, round(sum([f.amount for f in revisions_to_cashflows(
            date(2011, 2, 6),
            [rentRevision_partial_1,rentRevision_partial_2])]),2))
        self.assertEqual(-591.94, sum([f.amount for f in revisions_to_cashflows(
            date(2011, 2, 6),
            [rentRevision_partial_1])]))


class AnalyticsTest(TestCase):
    def test_moving_average_empty(self):
        self.assertEqual([0, 0], moving_average(
            to_date=date(2013, 1, 1),
            sorted_cashflows=[],
            size=2))

    def test_moving_average(self):
        cashflows = [
            Cashflow(
                date=date(2011, 8, 1),
                amount=200,
                description='',),
            Cashflow(
                date=date(2011, 7, 1),
                amount=100,
                description='',)]
        self.assertEqual([300, 300], moving_average(
            to_date=date(2014, 9, 1),
            sorted_cashflows=cashflows,
            size=2))
        self.assertEqual([0, 0], moving_average(
            to_date=date(2000, 9, 1),
            sorted_cashflows=cashflows,
            size=2))
        self.assertEqual([100, 300], moving_average(
            to_date=date(2011, 9, 1),
            sorted_cashflows=cashflows,
            size=2))


class VariousTest(TestCase):
    def test_add_month(self):
        self.assertEqual(date(2015, 2, 28), add_month(date(2015, 1, 31), 1))
