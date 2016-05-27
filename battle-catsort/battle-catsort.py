import datetime
import pywikibot
import re

BATTLE_TITLE = re.compile(r"Battle of (.+)(?:\(\w+\))?")
SUMMARY = "[[Wikipedia:Bots/Requests for approval/APersonBot 8|Bot]] adding a sensible defaultsort for an article about a battle"

def is_actual_battle(page):
    """Checks if a page is in any battle categories."""
    for each_category in page.categories():
        each_title = each_category.title(withNamespace=False)
        if "battle" in each_title.lower():
            return True
    return False

def main():
    print("Starting battle-catsort at " + datetime.datetime.utcnow().isoformat())

    site = pywikibot.Site("en", "wikipedia")
    site.login()

    for each_page in site.allpages("Battle of", filterredir=False):
        each_title = each_page.title(withNamespace=False)
        title_match = BATTLE_TITLE.search(each_title)

        if not title_match:
            print("Somehow {} didn't match.".format(each_title))
            continue
        if not is_actual_battle(each_page):
            print("{} isn't an actual battle.".format(each_title))
            continue

        wikitext = each_page.get()
        battle_name = title_match.group(1)
        if "DEFAULTSORT" not in wikitext:
            print(each_title)
            category_start = wikitext.find("[[Category:")
            wikitext = wikitext[:category_start] + "{{DEFAULTSORT:%s}}\n" % battle_name + wikitext[category_start:]
            each_page.text = wikitext
            each_page.save(summary=SUMMARY)
            break

if __name__ == "__main__":
    main()
