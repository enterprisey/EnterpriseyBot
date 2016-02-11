import datetime
import re
import pywikibot

TEMPLATE_NAME = "Template:Vandalism information"
COMMENT = "[[Wikipedia:Bots/Requests for approval/APersonBot 5|Bot]] updating vandalism level to %d RPM"
TEMPLATE_PATH = "template.txt" #"/data/project/apersonbot/bot/defcon/template.txt"
INTERVAL = 60

# If it's been longer than this since the last edit, make a null edit to
# keep our session alive.
NULL_EDIT_THRESHOLD = 2 * 60 * 60

def calculate_rpm(site):
    "Calculate RPM by counting reverts."
    num_reverts = 0
    for change in site.recentchanges(
            start=datetime.datetime.now(),
            end=datetime.datetime.now() - datetime.timedelta(minutes=INTERVAL),
            changetype="edit"):
        if u"comment" not in change:
            continue

        if re.search("revert|rv\ |rvv\ |undid(?!good( |-)faith)", change[u"comment"],
                     flags=re.IGNORECASE):
            num_reverts += 1
    return float(num_reverts) / INTERVAL

def is_edit_necessary(template_page, rpm):
    current_rpm_match = re.search("WikiDefcon/levels\|(\d+)", template_page.get())
    rpm_changed = ((not current_rpm_match) or
                   (int(current_rpm_match.group(1)) != int(rpm)))
    last_edit_timestamp = [x for x in template_page.revisions(total=1)][0].timestamp
    seconds_since_last_edit = (datetime.datetime.utcnow() - last_edit_timestamp).total_seconds()
    need_nudge = seconds_since_last_edit > NULL_EDIT_THRESHOLD
    return rpm_changed or need_nudge

def update_template(template_page):
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

def main():
    site = pywikibot.Site("en", "wikipedia")
    site.login()
    template_page = pywikibot.Page(site, TEMPLATE_NAME)
    rpm = calculate_rpm(site)
    if is_edit_necessary(template_page, rpm):
        update_template(template_page)
    else:
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print("[{}] No edit necessary.".format(timestamp))

if __name__ == "__main__":
    main()
