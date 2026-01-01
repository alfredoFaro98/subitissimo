import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'subitissimo_project.settings')
django.setup()

from scraper.models import Item

# Update image URLs to use the API endpoint
items_to_update = []
for item in Item.objects.filter(image_url__contains="s.sbito.it/img/"):
    old_url = item.image_url
    new_url = old_url.replace("s.sbito.it/img/", "images.sbito.it/api/v1/sbt-ads-images-pro/images/")
    if "?rule=gallery-desktop-1x-auto" not in new_url:
        if "?" in new_url:
             # handle existing query param if any (unlikely for s.sbito.it but safe)
             # actually s.sbito.it/img/UUID usually has ?rule=...
             pass
        else:
             new_url += "?rule=gallery-desktop-1x-auto"
    
    item.image_url = new_url
    items_to_update.append(item)

if items_to_update:
    Item.objects.bulk_update(items_to_update, ['image_url'])
    print(f"Updated {len(items_to_update)} image URLs.")
else:
    print("No items needed updating.")
