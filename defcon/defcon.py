import datetime
import re
import pywikibot

TEMPLATE_NAME = "Template:Vandalism information"
COMMENT = "[[Wikipedia:Bots/Requests for approval/APersonBot 5|Bot]] updating vandalism level to %d RPM"
TEMPLATE_PATH = "/data/project/apersonbot/bot/defcon/template.txt"
INTERVAL = 60

VANDALISM_KEYWORDS = ("revert", "rv ", "long-term abuse", "long term abuse",
                      "lta", "abuse", "rvv ", "undid")
NOT_VANDALISM_KEYWORDS = ("uaa", "good faith", "agf", "unsourced",
                          "unreferenced", "self", "speculat",
                          "original research", "rv tag", "typo", "incorrect",
                          "format")
SECTION_HEADER = re.compile(r"/\*[\s\S]+?\*/")

def is_edit_revert(edit_summary):
    "Returns True if the edit should be counted in the RPM statistic."
    edit_summary = SECTION_HEADER.sub("", edit_summary.lower())
    if any([word in edit_summary for word in NOT_VANDALISM_KEYWORDS]):
        return False
    elif any([word in edit_summary for word in VANDALISM_KEYWORDS]):
        return True
    else:
        return False

def calculate_rpm(site):
    "Calculate RPM by counting reverts."
    num_reverts = 0
    for change in site.recentchanges(
            start=datetime.datetime.now(),
            end=datetime.datetime.now() - datetime.timedelta(minutes=INTERVAL),
            changetype="edit"):
        if u"comment" not in change:
            continue

        if is_edit_revert(change[u"comment"]):
            num_reverts += 1
    return float(num_reverts) / INTERVAL

def is_edit_necessary(template_page, rpm):
    current_rpm_match = re.search("WikiDefcon/levels\|(\d+)",
                                  template_page.get())
    return ((not current_rpm_match) or
            (int(current_rpm_match.group(1)) != int(rpm)))

def update_template(template_page, rpm):
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
        update_template(template_page, rpm)
    else:
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print("[{}] No edit necessary.".format(timestamp))

if __name__ == "__main__":
    main()
