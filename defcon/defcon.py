import datetime
import re
import pywikibot

TEMPLATE_NAME = "Template:Vandalism information"
COMMENT = "[[Wikipedia:Bots/Requests for approval/APersonBot 5|Bot]] updating vandalism level to %d RPM"
TEMPLATE_PATH = "/data/project/apersonbot/bot/defcon/template.txt"
site = pywikibot.Site("en", "wikipedia")
site.login()

num_reverts = 0
for change in site.recentchanges(
        start=datetime.datetime.now(),
        end=datetime.datetime.now() - datetime.timedelta(minutes=30),
        changetype="edit"):
    if re.search("revert|rv\ |rvv\ |undid(?!good( |-)faith)", change[u"comment"],
                 flags=re.IGNORECASE):
        num_reverts += 1
rpm = float(num_reverts) / 30

template_page = pywikibot.Page(site, TEMPLATE_NAME)
current_rpm_match = re.search("WikiDefcon/levels\|(\d+)", template_page.get())
if (not current_rpm_match) or (int(current_rpm_match.group(1)) != int(rpm)):
    try:
        template = open(TEMPLATE_PATH)
    except IOError as e:
        print(e)
    else:
        try:
            template_page.text = template.read() % (int(rpm), rpm)
            template_page.save(COMMENT % int(rpm))
        except Exception as e:
            print(e)
        finally:
            template.close()
