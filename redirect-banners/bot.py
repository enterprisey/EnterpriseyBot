import datetime
import mwparserfromhell
import pywikibot
import re
import sys

SOFT_REDIR_CATS = "Wikipedia soft redirected categories"
NUM_PAGES = 2
SUMMARY = "[[Wikipedia:Bots/Requests for approval/EnterpriseyBot 10|Bot]] removing the article class assessment"
DATA_FILE = "current-progress.txt"

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
    print("Starting redirect-banners at " + datetime.datetime.utcnow().isoformat())
    site = pywikibot.Site("en", "wikipedia")
    site.login()

    i = 0

    wpbs_redirects = get_wpbs_redirects(site)
    is_wikiproject_banner = lambda template: is_wikiproject_banner_full(template, wpbs_redirects)

    # If we have a data file, pick up where we left off
    try:
        with open(DATA_FILE) as data_file:
            start_sort = data_file.read()
            print(start_sort)
    except IOError:
        start_sort = ""

    # We always write our progress to the previous category, to avoid
    # skipping any pages
    previous_category = None

    # Because PWB won't let us use hex keys, build our own generator.
    # Random argument keys come from site.py in Pywikibot (specifically,
    # the site.categorymembers() and site._generator() functions)
    gen_args = {"gcmtitle": "Category:All_redirect_categories",
            "gcmprop": "title",
            "gcmstartsortkeyprefix": start_sort}
    members_gen = pywikibot.data.api.PageGenerator("categorymembers", site=site, parameters=gen_args)
    for redirect_cat in members_gen:
        if redirect_cat.title(withNamespace=False) == SOFT_REDIR_CATS:
            continue

        # Record which subcat we were in for the next run
        if previous_category:
            with open(DATA_FILE, "w") as data_file:
                data_file.write(previous_category.title(withNamespace=False))

        for each_article in redirect_cat.articles(recurse=True, namespaces=(0)):
            print("Considering \"{}\".".format(each_article.title().encode("utf-8")))
            if not verify_redirect_age(site, each_article): continue
            talk_page = each_article.toggleTalkPage()
            if not talk_page.exists() or talk_page.isRedirectPage(): continue
            talk_text = talk_page.get()
            parse_result = mwparserfromhell.parse(talk_text)
            original_talk_text = talk_text
            talk_banners = filter(is_wikiproject_banner, parse_result.filter_templates())
            if not talk_banners: continue
            for each_template in talk_banners:
                class_params = [x for x in each_template.params
                        if ("class" in x.lower() and
                        "formerly assessed as" not in x.lower())]
                if class_params:
                    if len(class_params) != 1:
                        print("Multiple class params in " + talk_page.title(withNamespace=True))
                    else:
                        current_unicode = unicode(each_template)
                        each_template.remove(class_params[0].partition("=")[0])

                        old_quality = class_params[0].partition("=")[2]
                        if not re.match("\w+$", old_quality.strip()):
                            print("Invalid class!")
                            continue

                        print(current_unicode)
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

        previous_category = redirect_cat

        if i >= NUM_PAGES:
            break

if __name__ == "__main__":
    main()
