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
    global wikitools_wiki
    wikitools_login()

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

    # Get notification metadata
    for fc_cat, fc_items in fc_cats.items():
        def add_metadata(fc_item):
            name, label, date = fc_item
            nom_link = "Wikipedia:Featured " + fc_cat[:-1] + " candidates/"
            if fc_cat == "pictures":
                nom_link += label[2:-2] if "''" in label else label
                #if not WikitoolsPage(wikitools_wiki, title=nom_link).exists:
                if not wiki.page_exists(nom_link):
                    print(nom_link + " DOESN'T EXIST")
            else:
                nom_link += name[2:-2] if "''" in name else name
                nom_link += "/archive1"
            return (name, label, date, nom_link)
        fc_cats[fc_cat] = map(add_metadata, fc_items)

    # Build "report"
    report = ""
    for fc_cat, fc_items in fc_cats.items():
        report += "\n\n===Featured {}===".format(fc_cat)
        report += "\n{} {} were promoted this week.".format(len(fc_items),
                                                            FC_LINKS[fc_cat])
        for fc_item in fc_items:
            name, label, date, nom_link = fc_item
            piped = "|" + label if label else ""
            report += u"\n* '''[[{}{}]]''' <small>([[{}|nominated]] by [[User:Example|Example]])</small> Description.".format(name, piped, nom_link)
    report = report.strip()

    # Write report to Wikipedia
    report_page = WikitoolsPage(wikitools_wiki, title="User:APersonBot/sandbox")
    print("Editing report page...")
    result = report_page.edit(text=report.encode("ascii", "ignore"),
                              bot=True,
                              summary="Test FC report")
    if result[u"edit"][u"result"] == u"Success":
        print "Success!"
    else:
        print "Error! Couldn't write report - result: {}".format(str(result))

def wikitools_login():
    global wikitools_wiki
    wikitools_wiki = WikitoolsWiki("http://en.wikipedia.org/w/api.php")
    while True:
        username = raw_input("Username: ")
        password = getpass.getpass("Password for " + username + " on enwiki: ")
        print("Logging in to enwiki as " + username + "...")
        wikitools_wiki.login(username, password)
        if wikitools_wiki.isLoggedIn():
            break
        print("Error logging in. Try again.")

if __name__ == "__main__":
    main()
