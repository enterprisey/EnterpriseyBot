"A script that generates the Signpost's Featured Content Report."
import pywikibot
import re

WP_GO_HEADING = (
    r"'''\[\[Wikipedia:Featured (.+?)\|.+?\]\] that gained featured status'''")
WP_GO_ITEM = r"\[\[(.+?)(\|(.+?))?\]\] \((.+?)\)"

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

    # {type: [title of content]}
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

if __name__ == "__main__":
    main()
