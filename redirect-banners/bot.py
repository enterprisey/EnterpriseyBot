import datetime
import mwparserfromhell
import pywikibot
import sys

SOFT_REDIR_CATS = "Wikipedia soft redirected categories"
NUM_PAGES = 6
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
            print(unicode("Considering \"{}\".").format(each_article.title()))
            if not verify_redirect_age(site, each_article): continue
            talk_page = each_article.toggleTalkPage()
            if not talk_page.exists() or talk_page.isRedirectPage(): continue
            talk_text = talk_page.get()
            parse_result = mwparserfromhell.parse(talk_text)
            original_talk_text = talk_text
            talk_banners = filter(is_wikiproject_banner, parse_result.filter_templates())
            if not talk_banners: continue
            for each_template in talk_banners:
                class_params = [x for x in each_template.params if "class" in x.lower()]
                if class_params:
                    if len(class_params) != 1:
                        print("Multiple class params in " + talk_page.title(withNamespace=True))
                    else:
                        current_unicode = unicode(each_template)
                        print(current_unicode)
                        each_template.remove(class_params[0].partition("=")[0])
                        old_quality = class_params[0].partition("=")[2]
                        new_unicode = unicode(each_template)
                        new_unicode += " <!-- Formerly assessed as " + old_quality.strip() + "-class -->"
                        print(new_unicode)
                        talk_text = talk_text.replace(current_unicode, new_unicode)
            if talk_page.text != talk_text:
                talk_page.text = talk_text
                talk_page.save(summary=SUMMARY)
                i += 1
                print("{} out of {} done so far.".format(i, NUM_PAGES))
                if i >= NUM_PAGES:
                    break

        if i >= NUM_PAGES:
            break

if __name__ == "__main__":
    main()
