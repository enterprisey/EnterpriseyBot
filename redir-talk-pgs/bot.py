import datetime
import mwparserfromhell
import pywikibot
import re
import sys

SOFT_REDIR_CATS = "Wikipedia soft redirected categories"
NUM_PAGES = 2
SUMMARY = "[[Wikipedia:Bots/Requests for approval/EnterpriseyBot 10|Bot]] removing the article class assessment"

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

def is_wikiproject_banner_full(template, wpbs_redirects):
    sanitized_name = unicode(template.name).lower()
    return sanitized_name.startswith("wikiproject") and sanitized_name not in wpbs_redirects

def get_wpbs_redirects(site):
    wpbs = pywikibot.Page(site, "Template:WikiProject banner shell")
    return [page.title(withNamespace=False).lower()
            for page
            in wpbs.getReferences(redirectsOnly=True)
            if page.namespace() == 10]

def main():
    print("Starting redir-talk-pgs at " + datetime.datetime.utcnow().isoformat())
    site = pywikibot.Site("en", "wikipedia")
    site.login()

    all_redirect_cats = pywikibot.Category(site, "All redirect categories")

    i = 0

    wpbs_redirects = get_wpbs_redirects(site)
    print(wpbs_redirects)
    is_wikiproject_banner = lambda template: is_wikiproject_banner_full(template, wpbs_redirects)

    for redirect_cat in all_redirect_cats.subcategories():
        if redirect_cat.title(withNamespace=False) == SOFT_REDIR_CATS:
            continue

        for each_article in redirect_cat.articles(recurse=True, namespaces=(0)):
            print("Considering \"{}\".".format(each_article.title().encode("utf-8")))
            if not verify_redirect_age(site, each_article): continue
            talk_page = each_article.toggleTalkPage()
            if not talk_page.exists() or talk_page.isRedirectPage(): continue
            talk_text = talk_page.get()
            parse_result = mwparserfromhell.parse(talk_text)
            original_talk_text = talk_text

            objects_to_remove = []

            # Remove all talk banners
            objects_to_remove += filter(is_wikiproject_banner, parse_result.filter_templates())

            # Remove all comments
            objects_to_remove += parse_result.filter_comments()

            # Actually perform removals
            for each_object in objects_to_remove:
                talk_text = talk_text.replace(unicode(each_object), "")

            # If there's anything left, skip
            if talk_text.strip():
                print(">" + talk_text + "<")
                continue

            # TODO Redirect this page to the talk page of the target of the redirect at each_article
            talk_page.save(summary=SUMMARY)
            i += 1
            print("{} out of {} done so far.".format(i, NUM_PAGES))
            if i >= NUM_PAGES:
                break

        if i >= NUM_PAGES:
            break

if __name__ == "__main__":
    main()
