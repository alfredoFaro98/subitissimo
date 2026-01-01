import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'subitissimo_project.settings')
django.setup()

from scraper.models import Item

# Update existing items effectively "patching" the database
items_to_update = []
for item in Item.objects.filter(shipping_cost__isnull=False, shippable=False):
    item.shippable = True
    items_to_update.append(item)

if items_to_update:
    Item.objects.bulk_update(items_to_update, ['shippable'])
    print(f"Updated {len(items_to_update)} items to be shippable.")
else:
    print("No items needed updating.")
