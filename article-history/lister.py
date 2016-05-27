import json
import pywikibot
import pywikibot.pagegenerators as generators
import re

from clint.textui import progress

ARTICLE_HISTORY_COUNT = 37095
PRELOAD_SIZE = 100
REDUNDANT_TEMPLATES = ("on this day", "dyk talk", "itn talk")
DUMP_FILE = "lister.json"

site = pywikibot.Site("en", "wikipedia")
site.login()

article_history = pywikibot.Page(site, "Template:Article history")
references_gen = article_history.getReferences(onlyTemplateInclusion=True,
                                               namespaces=(1),
                                               content=True)
#preloading_gen = generators.PreloadingGenerator(references_gen, PRELOAD_SIZE)
article_histories = []
progress = progress.bar(references_gen, expected_size=ARTICLE_HISTORY_COUNT)
def dump():
    print("%d articles found." % len(article_histories))
    print("\n".join(article_histories).encode("utf-8"))
    with open(DUMP_FILE, "w") as data_file:
        json.dump(article_histories, data_file)
    print("Dumped to %s." % DUMP_FILE)

try:
    lower = unicode.lower
    add_to_list = article_histories.append
    for each_page in progress:
        each_text = lower(each_page.text)
        each_text = each_text[:each_text.find("==")]
        if any("{{" + template in each_text for template in REDUNDANT_TEMPLATES):
            add_to_list(each_page.title(withNamespace=False))
    dump()
except KeyboardInterrupt:
    dump()
    raise
