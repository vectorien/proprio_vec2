# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0008_auto_20151118_1708'),
    ]

    operations = [
        migrations.AlterField(
            model_name='rentrevision',
            name='end_date',
            field=models.DateField(null=True, verbose_name='end date', blank=True),
        ),
        migrations.AlterField(
            model_name='rentrevision',
            name='start_date',
            field=models.DateField(verbose_name='start date'),
        ),
    ]
