import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'subitissimo_project.settings')
django.setup()

from scraper.models import Item

total = Item.objects.count()
with_ship = Item.objects.filter(shipping_cost__isnull=False).count()
shippable = Item.objects.filter(shippable=True).count()

print(f"Total: {total}")
print(f"Shippable: {shippable}")
print(f"With Cost: {with_ship}")

if with_ship > 0:
    print("Sample costs:", list(Item.objects.filter(shipping_cost__isnull=False).values_list('shipping_cost', flat=True)[:5]))
else:
    print("No shipping costs found.")
