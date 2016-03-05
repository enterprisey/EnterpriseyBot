import datetime
import pywikibot
import re

WP_GO_TITLE = "Wikipedia:Goings-on"
DATE_REGEX = r"\[\[(\w+ \d{1,2})\]\], \[\[(\d{4})\]\]"
CURRENT_ITEM = r"\*\s?[\s\S]+?\(\d{1,2} \w{3}\)\n"

site = pywikibot.Site("en", "wikipedia")
site.login()

wp_go = pywikibot.Page(site, WP_GO_TITLE)
current_text = wp_go.get()

previous_date = ", ".join(re.search(DATE_REGEX, current_text).groups())
archive_title = WP_GO_TITLE + "/" + previous_date
print("Archiving to {}".format(archive_title))
wp_go.move(archive_title, reason="archive", movetalkpage=False)

new_text = current_text
new_date = datetime.datetime.today()
while new_date.weekday() != 6: new_date += datetime.timedelta(1)
new_date = new_date.strftime("[[%B %-d]], [[%Y]]")
new_text = re.sub(DATE_REGEX, new_date, new_text)
new_text = re.sub(CURRENT_ITEM, "", new_text)
print(new_text)

wp_go.text = new_text
wp_go.save(summary="New week ([[User talk:APerson|Bot]])")
