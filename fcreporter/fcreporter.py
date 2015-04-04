"A script that generates the Signpost's Featured Content Report."
import getpass
import pywikibot
import re
from wikitools.wiki import Wiki as WikitoolsWiki
from wikitools.page import Page as WikitoolsPage

WP_GO_HEADING = (
    r"'''\[\[Wikipedia:Featured (.+?)\|.+?\]\] that gained featured status'''")
WP_GO_ITEM = r"\[\[(.+?)(\|(.+?))?\]\] \((.+?)\)"
FC_LINKS = {"articles": "[[WP:FA|featured article]]s",
            "lists": "[[WP:FL|featured list]]s",
            "pictures": "[[WP:FP|featured picture]]s"}

def main():
    "The main function."
    wiki = pywikibot.Site("en", "wikipedia")
    wiki.login()
    wpgo = pywikibot.Page(wiki, "Wikipedia:Goings-on")
    wpgo_content = wpgo.get()
    new_fc = wpgo_content[wpgo_content.find("==New featured content=="):]

    # Trim it down to just the list of featured content
    new_fc = new_fc[:new_fc.find("|-") - 2]

    # Remove the section heading
    new_fc = new_fc[len("==New featured content=="):]

    # Create fc_cats, which looks like this: {type: [title of content]}
    fc_cats = dict()
    for fc_cat in re.finditer(WP_GO_HEADING, new_fc):
        fc_cat_name = fc_cat.groups()[0]
        fc_cat_raw_list = new_fc[fc_cat.start():]
        fc_cat_raw_list = fc_cat_raw_list[len(fc_cat_name) + 1:]
        next_heading = re.search(WP_GO_HEADING, fc_cat_raw_list)
        if next_heading:
            fc_cat_raw_list = fc_cat_raw_list[:next_heading.start()]
        fc_cat_raw_list = fc_cat_raw_list.strip()

        # Now that we have just the list, parse out the items
        for fc_item in re.finditer(WP_GO_ITEM, fc_cat_raw_list):
            name, _, label, date = fc_item.groups()
            print u"{} (a {}) was promoted on {}".format(label if label else name, fc_cat_name[:-1], date)
            fc_cats[fc_cat_name] = fc_cats.get(fc_cat_name, []) + [(name,
                                                                    label,
                                                                    date)]

    # Build "report"
    report = ""
    for fc_cat, fc_items in fc_cats.items():
        report += "\n\n===Featured {}===".format(fc_cat)
        report += "\n{} {} were promoted this week.".format(len(fc_items),
                                                            FC_LINKS[fc_cat])
        for fc_item in fc_items:
            piped = "|"+fc_item[1] if fc_item[1] else ""
            report += u"\n* '''[[{}{}]]'''".format(fc_item[0], piped)
    report = report.strip()

    # Write report to Wikipedia
    wikitools_wiki = WikitoolsWiki("http://en.wikipedia.org/w/api.php")
    while True:
        username = raw_input("Username: ")
        password = getpass.getpass("Password for " + username + " on enwiki: ")
        print("Logging in to enwiki as " + username + "...")
        wikitools_wiki.login(username, password)
        if wikitools_wiki.isLoggedIn():
            break
        print("Error logging in. Try again.")
    print("Successfully logged in as " + wikitools_wiki.username + ".")
    report_page = WikitoolsPage(wikitools_wiki, title="User:APersonBot/sandbox")
    print("Editing report page...")
    result = report_page.edit(text=report.encode("ascii", "ignore"),
                              bot=True,
                              summary="Test FC report")
    if result[u"edit"][u"result"] == u"Success":
        print "Success!"
    else:
        print "Error! Couldn't write report - result: {}".format(str(result))

if __name__ == "__main__":
    main()
