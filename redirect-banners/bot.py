import datetime
import mwparserfromhell
import pywikibot
import sys

SOFT_REDIR_CATS = "Wikipedia soft redirected categories"
NUM_PAGES = 1
SUMMARY = "Bot removing the article quality assessment"

def verify_redirect_age(site, page):
    """Returns True iff the page was a redirect/nonexistent a week ago."""
    a_week_ago = site.server_time() - datetime.timedelta(days=7)
    for each_rev_info in page.getVersionHistory():
        if each_rev_info.timestamp <= a_week_ago:
            text_a_week_ago = page.getOldVersion(each_rev_info.revid)
            return "#REDIRECT" in text_a_week_ago

    # If we're here, the page didn't exist a week ago
    earliest_revid = page.getVersionHistory(reverse=True)[0].revid
    earliest_text = page.getOldVersion(earliest_revid)
    return "#REDIRECT" in earliest_text

def is_wikiproject_banner(template):
    return unicode(template.name).lower().startswith("wikiproject")

def main():
    site = pywikibot.Site("en", "wikipedia")
    site.login()

    all_redirect_cats = pywikibot.Category(site, "All redirect categories")

    i = 0

    for redirect_cat in all_redirect_cats.subcategories():
        if redirect_cat.title(withNamespace=False) == SOFT_REDIR_CATS:
            continue

        for each_article in redirect_cat.articles(recurse=True, namespaces=(0)):
            if not verify_redirect_age(site, each_article): continue
            talk_page = each_article.toggleTalkPage()
            if not talk_page.exists(): continue
            talk_text = talk_page.get()
            parse_result = mwparserfromhell.parse(talk_page.get())
            original_talk_text = talk_text
            for each_template in parse_result.ifilter_templates():
                if is_wikiproject_banner(each_template):
                    importance_params = [x for x in each_template.params if "importance" in x.lower()]
                    if importance_params:
                        if len(importance_params) != 1:
                            print("Multiple importance params in " + talk_page.title(withNamespace=True))
                        else:
                            current_unicode = unicode(each_template)
                            each_template.remove(importance_params[0].partition("=")[0])
                            old_quality = importance_params[0].partition("=")[1]
                            new_unicode = unicode(each_template)
                            talk_text = talk_text.replace(current_unicode,
                                new_unicode + " <!-- Formerly assessed as " + old_quality + " -->")
            talk_page.text = talk_text
            talk_page.save(summary=SUMMARY)
            i += 1
            if i > NUM_PAGES:
                break

        if i > NUM_PAGES:
            break

if __name__ == "__main__":
    main()
