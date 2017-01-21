import datetime
import pywikibot
import sys

SOFT_REDIR_CATS = "Wikipedia soft redirected categories"

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
            if not talk_text.trim().startswith("{{"): continue
            print("\n--- " + talk_page.title(withNamespace=False) + " ---")
            print(talk_page.get()[:500])
            # Here:
            #  - find and remove the class and importance params
            #  - put them in a comment
            #  - save page
            i += 1
            if i > 4:
                break

        if i > 4:
            break

if __name__ == "__main__":
    main()
