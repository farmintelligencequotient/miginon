from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0005_feedcomposition'),
    ]

    operations = [
        migrations.AddField(
            model_name='stockmovement',
            name='used_by_group',
            field=models.CharField(
                blank=True, choices=[('calves', 'Calves')],
                help_text='Set instead of used_by when the stock went to animals rather than a person, e.g. calves.',
                max_length=10,
            ),
        ),
    ]
