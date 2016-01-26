import codecs
import datetime
import json
import pywikibot
import re

from clint.textui import progress

CAT_TRACK_TEMPLATE = "Template:CatTrack"
DATE_SUBCAT = re.compile("\d{4}")

site = pywikibot.Site("en", "wikipedia")
site.login()

cat_track = pywikibot.Page(site, CAT_TRACK_TEMPLATE)
cat_track_refs = cat_track.getReferences(onlyTemplateInclusion=True,
                                         namespaces=(14))
cat_track_refs = list(cat_track_refs)

# Key is cat name (w/o namespace); value is number of pages in cat.
data = {}

for category_page in progress.bar(cat_track_refs):
    category_name = codecs.encode(category_page.title(withNamespace=False))
    if DATE_SUBCAT.search(category_name):

        # We're in a date subcategory
        continue

    category = pywikibot.Category(site, category_page.title(withNamespace=True))
    if category.categoryinfo[u"subcats"] == category.categoryinfo[u"size"]:

        # Recurse into monthly categories
        data[category_name] = sum([x.categoryinfo[u"size"]
                                   for x
                                   in category.subcategories()])
    else:
        data[category_name] = category.categoryinfo[u"size"]

print("%d category lengths recorded." % len(data))
file_name = datetime.datetime.now().strftime("%d %B %Y.json")
with open(file_name, "w") as data_file:
    json.dump(data, data_file)
    print("Wrote data to %s." % file_name)
