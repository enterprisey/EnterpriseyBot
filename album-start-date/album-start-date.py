import pywikibot
import pywikibot.pagegenerators as pagegenerator

wiki = pywikibot.Site("en", "wikipedia")
wiki.login()

start_date = pywikibot.Page(wiki, "Template:Start date")
problem_pages = []
counter = 0
for page in start_date.getReferences(onlyTemplateInclusion=True):
    how_many_starts = len([x for x in page.templatesWithParams()
                           if x[0].title(withNamespace=False)=="Start date"])
    if how_many_starts > 1:
        problem_pages.append(page.title(withNamespace=True))
    counter += 1
    if counter % 500 == 0:
        print "%d pages checked" % counter

wikitext_list = "".join(["\n* [[%s]]" % x for x in problem_pages])

with open("list.txt", "w") as text_file:
    text_file.write(wikitext_list.encode("utf-8", "xmlcharrefreplace"))

page = pywikibot.Page(wiki, "User:APersonBot/sandbox/Start date issues")
wikitext_list = ("Last updated: " + date.strftime(date.today(), "%-d %B %Y") +
                 "\n" + wikitext_list)
page.save(text=wikitext_list, comment="Updating maintenance list")
