import pywikibot
import pywikibot.pagegenerators as generators
import re

from clint.textui import progress

ARTICLE_HISTORY_COUNT = 37095
PRELOAD_SIZE = 5
REDUNDANT_TEMPLATES = ("on this day", "dyk talk", "itn talk")

site = pywikibot.Site("en", "wikipedia")
site.login()

article_history = pywikibot.Page(site, "Template:Article history")
references_gen = article_history.getReferences(onlyTemplateInclusion=True,
                                               namespaces=(1),
                                               content=True)
preloading_gen = generators.PreloadingGenerator(references_gen, PRELOAD_SIZE)
article_histories = []
progress = progress.bar(preloading_gen, expected_size=ARTICLE_HISTORY_COUNT)
def dump():
    print("%d articles found." % len(article_histories))
    print("\n".join(article_histories).encode("utf-8"))

try:
    for each_page in progress:
        each_text = each_page.text
        each_text = each_text[:each_text.find("==")]
        each_text = each_text.lower()
        for each_template in REDUNDANT_TEMPLATES:
            if "{{" + each_template in each_text:
                article_histories += [each_page.title(withNamespace=False)]
    dump()
except KeyboardInterrupt:
    dump()
    raise
