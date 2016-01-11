import datetime
import re
import pprint
import pywikibot

TEMPLATE_NAME = "Template:Vandalism information"
COMMENT = "Update to %d RPM (TESTING BOT MANUALLY)"

site = pywikibot.Site("en", "wikipedia")
site.login()

num_reverts = 0
for change in site.recentchanges(
        start=datetime.datetime.now(),
        end=datetime.datetime.now() - datetime.timedelta(minutes=30),
        changetype="edit"):
    if re.search("revert|rv\ |rvv\ |undid/", change[u"comment"],
                 flags=re.IGNORECASE):
        num_reverts += 1
rpm = float(num_reverts) / 30
print("Calculated: %f reverts per minute, over 30 minutes" % rpm)

with open("template.txt") as template:
    new_text = template.read() % int(rpm)

template_page = pywikibot.Page(site, TEMPLATE_NAME)
template_page.text = new_text
print("Saving page...")
template_page.save(COMMENT % int(rpm))
print("Done! Page saved.")
