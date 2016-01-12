import datetime
import re
import pprint
import pywikibot

TEMPLATE_NAME = "Template:Vandalism information"
COMMENT = "[[Wikipedia:Bots/Requests for approval/APersonBot 5|Bot]] updating vandalism level to %d RPM"

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

template_page = pywikibot.Page(site, TEMPLATE_NAME)
with open("template.txt") as template:
    template_page.text = template.read() % int(rpm)
template_page.save(COMMENT % int(rpm))
