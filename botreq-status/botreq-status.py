import datetime
import itertools
import mwparserfromhell
import pywikibot
import re
import sys
import urllib

BOTREQ = "Wikipedia:Bot requests"
BOTREQ_HTML_URL = "https://en.wikipedia.org/w/index.php?title=Wikipedia:Bot_requests&action=view"
BOTOP_CAT = "Wikipedia bot operators"
REPORT_PAGE = "User:EnterpriseyBot/BOTREQ status"
TABLE_HEADER = """<noinclude>{{botnav}}This is a table of current [[WP:BOTREQ|]] discussions, updated automatically by {{user|EnterpriseyBot}}.</noinclude>
{| border="1" class="sortable wikitable plainlinks"
! # !! Title !! Replies !! Last editor !! Date/Time !! Last botop editor !! Date/Time
"""
SUMMARY = "Bot updating BOTREQ status table ({} requests)"
USER_NONE_WIKITEXT = "{{sort|ω|{{no result|None}}}}"

USER = re.compile(r"\[\[User.*?:(.*?)(?:\||(?:\]\]))")
TIMESTAMP = re.compile(r"\d{2}:\d{2}, \d{1,2} [A-Za-z]* \d{4}")
SIGNATURE = re.compile(r"\[\[User.*?\]\].*?\(UTC\)")
SECTION_HEADER = re.compile(r"^==([^=]|\s+).*?\s*==$", flags=re.M)

SIGNATURE_TIME_FORMAT = "%H:%M, %d %B %Y"
TIME_FORMAT_STRING = "%Y-%m-%d, %H:%M"

class Request:
    pass

def make_table_row(r):
    if type(r.last_edit_time) is datetime.datetime:
        old = (datetime.datetime.now() - r.last_edit_time).days > 60
        r.last_edit_time = ('style="background: red;" | ' if old else '') + r.last_edit_time.strftime(TIME_FORMAT_STRING)

    if type(r.last_botop_time) is datetime.datetime:
        r.last_botop_time = r.last_botop_time.strftime(TIME_FORMAT_STRING)

    # Add a red backgroud to the replies
    replies = ('style="background: red;" | ' if r.replies == 0 else '') + str(r.replies)

    def user_link(username):
        return USER_NONE_WIKITEXT if username == USER_NONE_WIKITEXT else '[[User:' + username + '|' + username + ']]'

    elements = map(str, [r.row_number, r.html_id, r.title, replies, user_link(r.last_editor), r.last_edit_time, user_link(r.last_botop_editor), r.last_botop_time])
    return u"|-\n| {} || [[WP:Bot requests#{}|{}]] || {} || {} || {} || {} || {}".format(*elements)

botop_cache = {}
def is_botop(wiki, username):
    if username in botop_cache:
        return botop_cache[username]

    userpage = pywikibot.Page(wiki, "User:" + username)
    result = any(x.title(with_ns=False) == BOTOP_CAT for x in userpage.categories())
    botop_cache[username] = result
    return result

def get_section_titles_and_ids():
    html = urllib.request.urlopen(BOTREQ_HTML_URL).read().decode('utf-8')
    sections = []
    for matchobj in re.finditer(r'<h2.+?<span class="mw-headline" id="([^"]+)".+?</h2>', html):
        # sorry this is awful
        title = re.sub('<a .+?>(.+?)</a>', '\\1', re.sub('^(<.+?>)+', '', re.sub('<span.+?</span>', '', re.sub('<a (?!href="[^"]).+?</a>', '', matchobj.group(0)))).partition('</span>')[0])
        id = matchobj.group(1)
        sections.append({'title': title, 'id': id})
    return sections

def main():
    wiki = pywikibot.Site("en", "wikipedia")
    wiki.login()
    botreq = pywikibot.Page(wiki, BOTREQ)
    page_content = botreq.text

    section_headers = list(SECTION_HEADER.finditer(page_content))

    # If it's not a level-2 header, the char before a match will be "="
    section_headers = list(filter(lambda h:page_content[h.start(0) - 1] != "=",
                             section_headers))

    # Now, build our list of sections
    sections = []
    for i, section_header_match in enumerate(section_headers):
        if i + 1 < len(section_headers):
            next_section_header = section_headers[i + 1]
            next_section_start = next_section_header.start(0)
        else:
            next_section_start = len(page_content) + 1
        this_section_end = next_section_start - 1
        this_section_start = section_header_match.end(0)
        section_content = page_content[this_section_start:this_section_end]
        section_content = section_content.strip()
        sections.append(section_content)

    def section_to_request(enumerated_section_tuple):
        enum_number, section_wikitext = enumerated_section_tuple
        section = mwparserfromhell.parse(section_wikitext)
        r = Request()
        r.row_number = enum_number + 1
        r.replies = section.count(u"(UTC)") - 1
        signatures = []
        for index, each_node in enumerate(section.nodes):
            if type(each_node) == mwparserfromhell.nodes.text.Text and "(UTC)" in each_node:

                # Get the last timestamp-looking thing (trick from http://stackoverflow.com/a/2988680/1757964)
                each_node = str(each_node)
                for timestamp_match in TIMESTAMP.finditer(each_node): pass
                try:
                    timestamp = datetime.datetime.strptime(timestamp_match.group(0), SIGNATURE_TIME_FORMAT)
                except ValueError:
                    timestamp = "{{unknown}}"

                # Use the last user talk page link before the timestamp
                for user_index in itertools.count(index - 1, -1):
                    user = USER.search(str(section.get(user_index)))
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
        # Process usernames by removing anchors
        signatures = [(x.partition('#')[0], y) for x, y in signatures]

        # Default values for everything
        r.last_editor, r.last_edit_time = r.last_botop_editor, r.last_botop_time = USER_NONE_WIKITEXT, "{{n/a}}"

        if signatures:
            r.last_editor, r.last_edit_time = signatures[-1]
            for user, timestamp in reversed(signatures):
                if is_botop(wiki, user):
                    r.last_botop_editor, r.last_botop_time = user, timestamp
                    break
        return r

    # Why enumerate? Because we need row numbers in the table
    requests = list(map(section_to_request, enumerate(sections)))

    # Add in title & HTML id
    section_titles_and_ids = get_section_titles_and_ids()
    if len(requests) != len(section_titles_and_ids):
        raise Exception('len(requests) != len(section_titles_and_ids): {} != {}'.format(len(requests), len(section_titles_and_ids)))
    for (request, title_and_id) in zip(requests, section_titles_and_ids):
        request.title = title_and_id['title']
        request.html_id = title_and_id['id']

    table_rows = map(make_table_row, requests)
    table = "\n".join(table_rows) + "\n|}"
    wikitext = TABLE_HEADER + table

    report_page = pywikibot.Page(wiki, REPORT_PAGE)
    report_page.text = wikitext
    report_page.save(quiet=True, summary=SUMMARY.format(len(list(requests))))

if __name__ == "__main__":
    main()
