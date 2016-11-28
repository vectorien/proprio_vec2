# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0009_auto_20160511_1217'),
    ]

    operations = [
        migrations.AddField(
            model_name='tenant',
            name='active',
            field=models.BooleanField(default=True, verbose_name='Active tenancy'),
        ),
    ]
