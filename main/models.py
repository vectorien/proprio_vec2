# vim: ai ts=4 sts=4 et sw=4
from django.db import models
from django.db.models import Max
from django.utils.translation import ugettext_lazy as _
from django.utils.translation import ungettext
from django.core.validators import MinValueValidator, ValidationError
from datetime import date, timedelta
from calendar import monthrange
from collections import namedtuple, deque, Counter
import itertools
import fnmatch
from operator import attrgetter
from django.forms import Textarea

class Building(models.Model):
    name = models.CharField(_("name"), max_length=255)
    notes = models.TextField(_("notes"), blank=True)

    class Meta:
        verbose_name = _("building")
        verbose_name_plural = _("buildings")
        ordering = ['name']

    def __unicode__(self):
        return self.name

    def property_count(self):
        return self.property_set.count()

    property_count.short_description = _("number of properties")


class BuildingFile(models.Model):
    building = models.ForeignKey(
        Building, verbose_name=Building._meta.verbose_name)
    name = models.CharField(_("name"), max_length=255)
    file = models.FileField(_('file'), upload_to='building')

    class Meta:
        verbose_name = _("file")

    def __unicode__(self):
        return self.name


class Property(models.Model):
    name = models.CharField(_("name"), max_length=255)
    building = models.ForeignKey(
        Building,
        verbose_name=Building._meta.verbose_name,
        blank=True, null=True, on_delete=models.PROTECT)
    address = models.TextField(_("address"))
    notes = models.TextField(_("notes"), blank=True)
    area = models.DecimalField(
        _("surface area"), max_digits=7, decimal_places=2,
        validators=[MinValueValidator(0)])
    rooms = models.DecimalField(
        _("number of rooms"), max_digits=2, decimal_places=0,
        validators=[MinValueValidator(1)])

    class Meta:
        verbose_name = _("property")
        verbose_name_plural = _("properties")
        ordering = ['name']

    def __unicode__(self):
        return u'{}\n{}'.format(self.name, self.address)


class PropertyFile(models.Model):
    property = models.ForeignKey(
        Property, verbose_name=Property._meta.verbose_name)
    name = models.CharField(_("name"), max_length=255)
    file = models.FileField(_('file'), upload_to='property')

    class Meta:
        verbose_name = _("file")
        verbose_name_plural = _("files")

    def __unicode__(self):
        return self.name


def validate_month(value):
    if value is not None and value.day != 1:
        raise ValidationError(
            _("month expected. Please use first day of the month"))


class Tenant(models.Model):
    property = models.ForeignKey(
        Property,
        verbose_name=Property._meta.verbose_name,
        on_delete=models.PROTECT)
    name = models.CharField(_("name"), max_length=255)
    tenancy_begin_date = models.DateField(
        _("tenancy begin date"))
    tenancy_end_date = models.DateField(
        _("tenancy end date"), blank=True, null=True)
    deposit = models.DecimalField(
        _("deposit"), max_digits=7, decimal_places=2,
        validators=[MinValueValidator(0)], default=0)
    contact_info = models.TextField(_("contact info"), blank=True)
    notes = models.TextField(_("notes"), blank=True)

    def cashflows(self):
        if self.tenancy_end_date:
            last_revision_end_date = next_month(self.tenancy_end_date, -1)
            generate_rent_until = max(date.today(), last_revision_end_date)
        else:
            generate_rent_until = date.today()
        rents = revisions_to_cashflows(
            generate_rent_until, self.rentrevision_set.all())
        payments = payments_to_cashflows(
            date.today(), self.payment_set.all())
        fees = fees_to_cashflows(date.today(), self.fee_set.all())
        non_sorted = itertools.chain.from_iterable([
            payments, rents, fees])
        date_sorted = sorted(non_sorted, key=attrgetter('date', 'amount'))
        result = []
        balance = 0.0
        for c in date_sorted:
            balance += c.amount
            result.append(
                CashflowAndBalance(c.date, c.amount, c.description, balance))
        return reversed(result)

    def trend(self):
        return moving_average(date.today(), list(self.cashflows()), 3)

    def balance(self):
        return sum([c.amount for c in self.cashflows()])

    def rent(self):
        query_set = self.rentrevision_set.all()
        result = query_set.aggregate(Max('rent'))['rent__max']
        if result is None:
            result = 0
        return result

    #def last_payment_date(self):
     #   return max([c.date for c in self.cashflows() if fnmatch.fnmatch(str(c.description), _('payment')+'*') == True])

# Translators: This is the balance of the tenant's payments
    balance.short_description = _("balance")

    def expired_reminders_count(self):
        return (
            self.reminder_set
            .filter(read=False)
            .filter(date__lte=date.today())
            .count())

    def pending_reminders_count(self):
        return (
            self.reminder_set
            .filter(read=False)
            .count())

    class Meta:
        verbose_name = _("tenant")
        verbose_name_plural = _("tenants")
        ordering = ['tenancy_end_date', 'name']

    def __unicode__(self):
        return u"{} {}".format(self.name, self.property)


class TenantFile(models.Model):
    tenant = models.ForeignKey(Tenant, verbose_name=Tenant._meta.verbose_name)
    name = models.CharField(_("name"), max_length=255)
    file = models.FileField(_('file'), upload_to='tenant')

    class Meta:
        verbose_name = _("file")
        verbose_name_plural = _("files")

    def __unicode__(self):
        return self.name


class Reminder(models.Model):
    tenant = models.ForeignKey(Tenant, verbose_name=Tenant._meta.verbose_name)
    date = models.DateField(_("date"))
    text = models.TextField(_("description"))
    text.widget = Textarea(attrs={'rows': 2})
    read = models.BooleanField(_("mark as read"), default=False)

    class Meta:
        verbose_name = _("reminder")
        verbose_name_plural = _("reminders")
        ordering = ['-date']

    def __unicode__(self):
        return u"{} : {}".format(self.tenant, self.text)


class RentRevision(models.Model):
    tenant = models.ForeignKey(Tenant, verbose_name=Tenant._meta.verbose_name)
    start_date = models.DateField(_("start date"))
    end_date = models.DateField(
        _("end date"),blank=True, null=True)
    rent = models.DecimalField(
        _("monthly rent"), max_digits=7, decimal_places=2,
        validators=[MinValueValidator(0)])
    provision = models.DecimalField(
        _("monthly provision"), max_digits=7, decimal_places=2,
        validators=[MinValueValidator(0)])

    class Meta:
        verbose_name = _("rent revision")
        verbose_name_plural = _("rent revisions")
        ordering = ['-start_date']

    def __unicode__(self):
        return u"{} - {}".format(self.start_date, self.end_date or "")


class Payment(models.Model):
    """money received from the tenant"""
    description = models.CharField(
        _("description"), max_length=1024)
    tenant = models.ForeignKey(Tenant, verbose_name=Tenant._meta.verbose_name)
    date = models.DateField(_("date"))
    amount = models.DecimalField(
        _("amount"), max_digits=7, decimal_places=2,
        validators=[MinValueValidator(0)])

    class Meta:
        verbose_name = _("payment received from tenant")
        verbose_name_plural = _("payments received from tenant")
        ordering = ['-date']

    def __unicode__(self):
        return u"{} - {}".format(self.date, self.amount)


class Fee(models.Model):
    """a one-time fee (for example an end of year adjustment fee)"""
    description = models.CharField(_("description"), max_length=255)
    tenant = models.ForeignKey(Tenant, verbose_name=Tenant._meta.verbose_name)
    date = models.DateField(_("date"))
    amount = models.DecimalField(_("amount"), max_digits=7, decimal_places=2)

    class Meta:
        verbose_name = _("one-time fee")
        verbose_name_plural = _("one-time fees")
        ordering = ['-date']

    def __unicode__(self):
        return u"{} - {}".format(self.description, self.date)


Cashflow = namedtuple('Cashflow', ['date', 'amount', 'description'])
CashflowAndBalance = namedtuple('Cashflow',
                                ['date', 'amount', 'description', 'balance'])


def payments_to_cashflows(date, payments):
    for p in payments:
        if p.date > date:
            continue
        if p.description:
            d = _('payment "%(description)s"') % {'description': p.description}
        else:
            d = _('payment')
        yield Cashflow(p.date, float(p.amount), d)


def fees_to_cashflows(date, fees):
    return [Cashflow(x.date, -float(x.amount), x.description)
            for x in fees if x.date <= date]

def revision_to_cashflows(rev, end_date):
    """Converts a revision to a list of cashflows
    end_date -- the first month we do not want to take into account
    """
    end_date = rev.end_date or end_date
    if not end_date:
        end_date = next_month(date.today(),1)

    start_date = rev.start_date

    delta_r = (end_date - start_date).days 

    revision_date_list = [start_date + timedelta(days=x) for x in range(0, delta_r+1)]

    result = []

    month_year_list = [(d.year, d.month) for d in revision_date_list]

    #generate-list-of-tuples (year,month, days-in-month, full-month) from-list-of-dates

    year_month_ndays_full = [(k[0],k[1],v , True if  monthrange(k[0], k[1])[1] == v else False) for k,v in Counter(month_year_list).iteritems()]


    for d in year_month_ndays_full:

        date_info = date(d[0],d[1],1)
        #if full month
        if d[3] == True:
            result.append(Cashflow(date_info, -float(rev.rent), _('RENT ') ))
            if rev.provision != 0:
                result.append(Cashflow(date_info, -float(rev.provision), _('PROVISION ') ))

        #if partial month, divide by days of month rented
        else:
            #generate start date of rent/provision
            if start_date != date_info and start_date.month == date_info.month:
                date_info = start_date
            daysinmonth = monthrange(date_info.year, date_info.month)[1]
            rented_days = d[2]
            #partialrent = round((rev.rent/daysinmonth*rented_days),2)
            partialrent = rev.rent/daysinmonth*rented_days

            result.append(Cashflow(date_info, -round(partialrent,2),\
             ungettext("RENT for %(day)s day in partial month",\
                "RENT for %(day)s days in in partial month", rented_days) % {'day': str(rented_days)}))
            
            if rev.provision != 0:
                #partialprovision = round((rev.provision/daysinmonth*rented_days),2)
                partialprovision = rev.provision/daysinmonth*rented_days

                result.append(Cashflow(date_info, -round(partialprovision,2), \
                    ungettext("PROVISION for %(day)s day in partial month",\
                        "PROVISION for %(day)s days in in partial month", rented_days) % {'day': str(rented_days)}))
    return result


def revisions_to_cashflows(date, revisions):
    date = next_month(date)
    result = map(lambda r: revision_to_cashflows(r, date), revisions)
    joined_result = itertools.chain.from_iterable(result)
    return [c for c in joined_result if c.date < date]


def next_month(date, increment=1):
    date = date.replace(day=1)
    return add_month(date, increment)


def add_month(d, increment=1):
    month = d.month - 1 + increment
    year = d.year + month / 12
    month = month % 12 + 1
    day = d.day
    max_day = monthrange(year, month)[1]
    day = min(day, max_day)
    return date(month=month, year=year, day=day)


def pop_cashflows_until(sorted_cashflows, until):
    result = []
    while len(sorted_cashflows) > 0 and sorted_cashflows[0].date < until:
        c = sorted_cashflows.popleft()
        result.append(c)
    return result


def moving_average(to_date, sorted_cashflows, size):
    """
    Returns an array of the requested size.
    Each point of this array correspond to the average balance of the account
    over the course of a month
    The last point is the average between to_date and to_date - 1 month
    """
    if len(sorted_cashflows) == 0:
        sorted = True
    else:
        sorted = sorted_cashflows[-1].date <= sorted_cashflows[0].date
    assert sorted, "sorted_list is not sorted"
    # clone and sort by ascending date
    cashflows = deque(reversed(sorted_cashflows))
    from_date = add_month(to_date, -size)
    cashflows_before = pop_cashflows_until(cashflows, from_date)
    balance = 0
    balance += sum([float(c.amount) for c in cashflows_before])
    result = []
    for i in range(size):
        to_date = add_month(from_date)
        month_cashflows = pop_cashflows_until(cashflows, to_date)
        product = 0
        last_balance = balance
        last_date = from_date
        for c in month_cashflows:
            product += last_balance * (c.date - last_date).days
            last_balance += float(c.amount)
            last_date = c.date
        product += last_balance * (to_date - last_date).days
        result.append(product / (to_date - from_date).days)
        from_date = to_date
        balance = last_balance
    return result
