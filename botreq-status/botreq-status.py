import datetime
import itertools
import mwparserfromhell
import pywikibot
import re
import sys

BOTREQ = "Wikipedia:Bot requests"
BOTOP_CAT = "Wikipedia bot operators"
REPORT_PAGE = "User:EnterpriseyBot/BOTREQ status"
TABLE_HEADER = """<noinclude>{{botnav}}This is a table of current [[WP:BOTREQ|]] discussions, updated automatically by {{user|EnterpriseyBot}}.</noinclude>
{| border="1" class="sortable wikitable plainlinks"
! # !! Title !! Replies !! Last editor !! Date/Time !! Last botop editor !! Date/Time
"""
SUMMARY = "Bot updating BOTREQ status table ({} requests)"

USER = re.compile(r"\[\[User.*?:(.*?)(?:\||(?:\]\]))")
TIMESTAMP = re.compile(r"\d{2}:\d{2}, \d{1,2} [A-Za-z]* \d{4}")
SIGNATURE = re.compile(r"\[\[User.*?\]\].*?\(UTC\)")
SECTION_HEADER = re.compile(r"== ?([^=]+) ?==")

SIGNATURE_TIME_FORMAT = "%H:%M, %d %B %Y"
TIME_FORMAT_STRING = "%Y-%m-%d, %H:%M"

class Request:
    pass

def print_log(what_to_print):
    print(datetime.datetime.utcnow().strftime("[%Y-%m-%dT%H:%M:%SZ] ") + what_to_print)

def make_table_row(r):
    replies = ('style="background: red;" | ' if r.replies == 0 else '') + str(r.replies)

    # Utility function for processing
    def take_inner(regex, text):
        """
	Given a regex with exactly one capturing group and some text,
	return the text after all occurrences of the regex have been
	replaced with the group.

	Example: take_inner("a(.)a", "aba") == "b"
	"""
	return re.sub(regex, r"\1", text)

    # Row number
    row_number = r.row_number

    # We'll be putting r.title in a wikilink, so we can't have nested wikilinks
    title = take_inner(r"\[\[(?:.+?\|)?(.+?)\]\]", r.title)

    # Escape some characters in the link target
    encodings = {"#": "%23", "<": "%3C", ">": "%3E", "[": "%5B", "]": "%5D", "|": "%7C", "{": "%7B", "}": "%7D"}
    target = re.sub("[{}]".format("".join(map(re.escape, encodings.keys()))), lambda match: encodings[match.group(0)], title)

    # Remove formatting in the link target
    target = take_inner(r"''([^']+)''", take_inner(r"'''([^']+)'''", target))

    if type(r.last_edit_time) is datetime.datetime:
        old = (datetime.datetime.now() - r.last_edit_time).days > 60
        r.last_edit_time = ('style="background: red;" | ' if old else '') + r.last_edit_time.strftime(TIME_FORMAT_STRING)

    if type(r.last_botop_time) is datetime.datetime:
        r.last_botop_time = r.last_botop_time.strftime(TIME_FORMAT_STRING)

    elements = map(unicode, [row_number, target, title, replies, r.last_editor, r.last_edit_time, r.last_botop_editor, r.last_botop_time])
    return u"|-\n| {} || [[WP:Bot requests#{}|{}]] || {} || {} || {} || {} || {}".format(*elements)

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

    section_headers = list(SECTION_HEADER.finditer(page_content))

    # If it's not a level-2 header, the char before a match will be "="
    section_headers = filter(lambda h:page_content[h.start(0) - 1] != "=",
                             section_headers)

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
        section_header = section_header_match.group(1).strip()

        # In the event of duplicates, use "=" to flag duplication
        while section_header in sections:
            section_header = "=" + section_header

        sections.append((section_header, section_content))

    def section_to_request(enumerated_section_tuple):
        enum_number, section_tuple = enumerated_section_tuple
        section_header, section_wikitext = section_tuple
        section = mwparserfromhell.parse(section_wikitext)
        r = Request()
        r.row_number = enum_number + 1
        r.title = section_header
        r.replies = unicode(section).count(u"(UTC)") - 1
        signatures = []
        for index, each_node in enumerate(section.nodes):
            if type(each_node) == mwparserfromhell.nodes.text.Text and "(UTC)" in each_node:

                # Get the last timestamp-looking thing (trick from http://stackoverflow.com/a/2988680/1757964)
                for timestamp_match in TIMESTAMP.finditer(unicode(each_node)): pass
                try:
                    timestamp = datetime.datetime.strptime(timestamp_match.group(0), SIGNATURE_TIME_FORMAT)
                except ValueError:
                    timestamp = "{{unknown}}"

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
        # Process usernames by removing anchors
        signatures = [(x.partition('#')[0], y) for x, y in signatures]

        # Default values for everything
        r.last_editor, r.last_edit_time = r.last_botop_editor, r.last_botop_time = "{{no result|None}}", "{{n/a}}"

        if signatures:
            r.last_editor, r.last_edit_time = signatures[-1]
            for user, timestamp in reversed(signatures):
                if is_botop(wiki, user):
                    r.last_botop_editor, r.last_botop_time = user, timestamp
                    break
        return r

    # Why enumerate? Because we need row numbers in the table
    requests = map(section_to_request, enumerate(sections))

    print_log("Parsed BOTREQ and made a list of {} requests.".format(len(requests)))
    table_rows = map(make_table_row, requests)
    table = "\n".join(table_rows) + "\n|}"
    wikitext = TABLE_HEADER + table

    report_page = pywikibot.Page(wiki, REPORT_PAGE)
    report_page.text = wikitext
    report_page.save(summary=SUMMARY.format(len(requests)))
    print_log("Saved {}.".format(REPORT_PAGE))

if __name__ == "__main__":
    main()
