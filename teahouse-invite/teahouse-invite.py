import re

from clint.textui import progress
import pywikibot
import pywikibot.pagegenerators as pagegenerator

COMMENT = "Testing an experimental fixer for Teahouse invites"
CATEGORY = "Category:Wikipedians who have received a Teahouse invitation through AfC"
CATEGORIES = (CATEGORY, "Category:Wikipedians who have received a Teahouse invitation")
WIKI = pywikibot.Site("en", "wikipedia")
WIKI.login()

def main():
    fix_page(raw_input("Page title: "))

def fix_page(page_title):
    page = pywikibot.Page(WIKI, title=page_title)
    page_text = page.get()
    page_text = fix_page_text(page_text)
    if page_text:
        if not any(x in page_text for x in CATEGORIES):
            page_text = page_text + "\n\n[[" + CATEGORY + "]]"
        page.save(text=page_text, comment=COMMENT)

def fix_page_text(page_text):
    with open("template", "r") as template_file:
        INVITE_PATTERN = re.compile(template_file.read())
    matches = INVITE_PATTERN.findall(page_text)
    if not matches:
        return None

    for match in matches[1:]:
        page_text = page_text.replace(match, "")
    return page_text

if __name__=="__main__":
    main()
