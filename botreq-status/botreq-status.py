import datetime
import itertools
import mwparserfromhell
import pywikibot
import re
import sys

BOTREQ = "Wikipedia:Bot requests"
BOTOP_CAT = "Wikipedia bot owners"
REPORT_PAGE = "User:APersonBot/BOTREQ status"
HEADER = """<noinclude>{{botnav}}This is a table of current [[WP:BOTREQ|]] discussions, updated automatically by {{user|APersonBot}}.</noinclude>
{| border="1" class="sortable wikitable plainlinks"
! Title !! Replies !! Last editor !! Date/Time !! Last botop editor !! Date/Time
"""
SUMMARY = "Bot updating BOTREQ status table ({} requests)"

USER = re.compile(r"\[\[User.*?:(.*?)(?:\||(?:\]\]))")
TIMESTAMP = re.compile(r"\d{2}:\d{2}, \d{1,2} [A-Za-z]* \d{4}")
SIGNATURE = re.compile(r"\[\[User.*?\]\].*?\(UTC\)")

SIGNATURE_TIME_FORMAT = "%H:%M, %d %B %Y"
TIME_FORMAT_STRING = "%Y-%m-%d, %H:%M"

class Request:
    pass

def print_log(what_to_print):
    print(datetime.datetime.utcnow().strftime("[%Y-%m-%dT%H:%M:%SZ] ") + what_to_print)

def make_table_row(r):
    replies = ('style="background: red;" | ' if r.replies == 0 else '') + str(r.replies)
    title = re.sub(r"\[\[(?:.+\|)?(.+)\]\]", r"\1", r.title)
    if (datetime.datetime.now() - r.last_edit_time).days > 60:
        r.last_edit_time = 'style="background: red;" | ' + r.last_edit_time.strftime(TIME_FORMAT_STRING)
    if type(r.last_botop_time) is datetime.datetime:
        r.last_botop_time = r.last_botop_time.strftime(TIME_FORMAT_STRING)
    elements = map(unicode, [title, replies, r.last_editor, r.last_edit_time, r.last_botop_editor, r.last_botop_time])
    return u"|-\n| [[WP:Bot requests#{0}|{0}]] || {1} || {2} || {3} || {4} || {5}".format(*elements)

botop_cache = {}
def is_botop(wiki, username):
    if username in botop_cache:
        return botop_cache[username]

    userpage = pywikibot.Page(wiki, "User:" + username)
    result = any(x.title(withNamespace=False) == BOTOP_CAT for x in userpage.categories())
    botop_cache[username] = result
    return result

def main():
    print_log("Starting botreq-status at " + datetime.datetime.utcnow().isoformat())
    wiki = pywikibot.Site("en", "wikipedia")
    wiki.login()
    botreq = pywikibot.Page(wiki, BOTREQ)
    page_content = botreq.text
    wikicode = mwparserfromhell.parse(page_content)
    sections = wikicode.get_sections(include_lead=False, levels=(2,))
    def section_to_request(section):
        r = Request()
        r.title = section.filter_headings()[0].title.strip()
        r.replies = unicode(section).count(u"(UTC)")
        signatures = []
        for index, each_node in enumerate(section.nodes):
            if type(each_node) == mwparserfromhell.nodes.text.Text and "(UTC)" in each_node:
                timestamp = TIMESTAMP.search(str(each_node)).group(0)
                timestamp = datetime.datetime.strptime(timestamp, SIGNATURE_TIME_FORMAT)

                # Use the last user talk page link before the timestamp
                for user_index in itertools.count(index - 1, -1):
                    user = USER.search(unicode(section.get(user_index)))
                    if user:
                        user = user.group(1)
                        break

                # Check for user renames/redirects
                user_page = pywikibot.Page(wiki, "User:" + user)
                if user_page.isRedirectPage():
                    redirect_text = user_page.get(get_redirect=True)
                    user_wikicode = mwparserfromhell.parse(redirect_text)
                    redirect_link = user_wikicode.filter_wikilinks()[0]
                    user = redirect_link.title.split(":")[1]

                signatures.append((user, timestamp))
        r.last_editor, r.last_edit_time = signatures[-1]
        for user, timestamp in reversed(signatures):
            if is_botop(wiki, user):
                r.last_botop_editor, r.last_botop_time = user, timestamp
                break
        else:
            r.last_botop_editor, r.last_botop_time = "{{no result|None}}", "{{n/a}}"
        return r
    requests = map(section_to_request, sections)
    print_log("Parsed BOTREQ and made a list of {} requests.".format(len(requests)))
    table_rows = map(make_table_row, requests)
    table = "\n".join(table_rows) + "\n|}"
    wikitext = HEADER + table

    report_page = pywikibot.Page(wiki, REPORT_PAGE)
    report_page.text = wikitext
    report_page.save(summary=SUMMARY.format(len(requests)))
    print_log("Saved {}.".format(REPORT_PAGE))

if __name__ == "__main__":
    main()
