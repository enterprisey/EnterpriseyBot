# -*- coding: utf-8 -*-

import os
import sys
import re
import ConfigParser
cfgparser = ConfigParser.RawConfigParser()
cfgparser.read("config.txt")
pwb_location = cfgparser.get("configuration", "pwb_location")
sys.path.append(pwb_location)
import pywikibot
import pywikibot.page
import pywikibot.pagegenerators as pagegenerators
import codecs
import json
import time
import mwparserfromhell
from bs4 import BeautifulSoup
# standard enwikipedia site
site = pywikibot.Site('en', 'wikipedia')

# some constants
ALREADY_NOTIFIED_FILE = u"notified_beta.dat"

# LOGGING
import logging
logging.basicConfig(filename='dyknotifier.log',
                    level=logging.DEBUG,
                    datefmt="%d %b. %Y %I:%M:%S",
                    format="[%(asctime)s] [%(levelname)s] %(message)s")
streamHandler = logging.StreamHandler()
streamHandler.setLevel(logging.INFO)
logging.getLogger().addHandler(streamHandler)

def main():
    site.login()

    # master data object to hold most data
    data = {}

    BLACKLISTED_TEXT = ur'(Self nominated|Category:(Failed|passed) DYK)'
    NOM_TEMPLATE = "Template:Did you know nominations/"

    cat = pywikibot.Category(site, u'Category:Pending DYK nominations')
    print("Looping through {} pending DYK nominations."
          .format(len([x for x in cat.articles()])))
    catgen = pagegenerators.CategorizedPageGenerator(cat)
    gen = pagegenerators.NamespaceFilterPageGenerator(catgen, [10])

    # batch get the page contents via the preloading gen in batches of 500
    for template in pagegenerators.PreloadingGenerator(gen, 500):

        # sanity check to make sure we are dealing with a nom subpage
        if not template.title().startswith(NOM_TEMPLATE): continue

        # retrieve the nom text from the preloaded template object
        text = template.get()

        # compare it with the blacklisted string and skip if matched
        if re.search(re.compile(BLACKLISTED_TEXT, re.I), text): continue

        soup = BeautifulSoup(text)

        # find all of the small tags
        small_tags = [unicode(x.string) for x in soup.find_all("small")]

        # extract the usernames and combine them into the contributor list
        for tag in small_tags:

            # Make sure it's the small tag with the nom info
            if not re.search(u"Nominated by", tag): continue

            # Get the sentence describing who worked on the article.
            user_str = tag.split('Nominated by')[0]

            # Get a list of usernames from that sentence.
            contributors = usernames_from_text_with_sigs(user_str)

            # Get the pages that link here
            what_links_here = [x.title() for x in template.getReferences()]

            who_needs_notification = list(set(contributors) - set(what_links_here))

            data[template.title()] = {
                'page': template,
                'contributor': contributors,
                'whatlinkshere': what_links_here,
                'needs_notified': who_needs_notification
            }

    print("Done munching through pending noms. " +\
          "{} articles to send notifications for.".format(len(data)))

    # This file is a JSON dictionary of users and a list of articles that the bot has already notifed them about, failsafe to prevent repeated notifcations to the same user
    already_notified = json.loads(get_file(ALREADY_NOTIFIED_FILE))
    # we are re-organizing the data from a per article format (DYK noms) to a format based on usernames so we can combine multiple notices if we want to.
    group_by_user = {}
    # interate over DYK noms
    for article in data:
        for user in data[article]['needs_notified']:
            # do we have a entry for this user yet? if so just add the next article to the list
            if user in group_by_user:
                group_by_user[user].append(re.sub(u'Template:Did you know nominations/','',article))
            else:
                # otherwise create a list of articles and add the current one to it
                group_by_user[user] = [re.sub(u'Template:Did you know nominations/','',article)]
                # create a list of user talk pages for everyone who needs notified
                user_pages = [pywikibot.Page(site,u'User talk:%s' % x) for x in sorted(group_by_user.keys())]
                for user in pagegenerators.PreloadingGenerator(user_pages,500):
                    # create a placeholder list for new notifications that are needed for the given user
                    needs_notified = []
                    # Have we ever notified this user about a DYK before?
                    if user.title(withNamespace=False) in already_notified:
                        # We have already given some notices, so lets take the list of current DYK noms, and subtract all articles we have already notified the user about
                        # The resulting set is all new DYKs that the user doesnt know about.
                        needs_notified = list(set(group_by_user[user.title(withNamespace=False)]) - set(already_notified[user.title(withNamespace=False)]))
                    else:
                        # If not, we need to notify them for all DYKs we have flagged for them.
                        needs_notified = group_by_user[user.title(withNamespace=False)]
                        # create an empty list for this user for the next part of the process so we can keep track of who we notify and about which articles
                        already_notified[user.title(withNamespace=False)] = []
                        # we can either combine notices here, or default to 1 post per DyK
                        for article_title in needs_notified:
                            # define both edit summary and notification text
                            edit_summary = u"[[Wikipedia:Bots/Requests for approval/APersonBot 2|Bot]] notification about the DYK nomination of [[%s]]" % article_title
                            message = u"\n\n{{{{subst:DYKNom|%s|passive=yes}}}}" % article_title
                            # the page.append message bypasses the normal bot check so let’s verify the bot isn’t prohibited 
                            if user.botMayEdit():
                                try:
                                    # disable actual notices until testing is complete
                                    # user.append(message,comment=edit_summary,section='new')
                                    log(u'{{user|%s}} notified about about [[%s]]'  % (user.title(withNamespace=False),article_title),'dykoutput.log')
                                except:
                                    # edit failed for some reason, we can add extra error handling if desired for each type of failure, but for now lets just catch them all and move on.
                                    log(u'{{user|%s}} failed to notify about [[%s]]'  % (user.title(withNamespace=False),article_title),'dykoutput.log')
                                else:
                                    # log {{nobots}} fails
                                    log(u'{{user|%s}} failed to notify about [[%s]] due to {{tl|nobots}}'  % (user.title(withNamespace=False),article_title),'dykoutput.log')
                                    # add article to the list of already notified DyKs
                                    already_notified[user.title(withNamespace=False)].append(article_title)
                                    # dump notification database
                                    log(json.dumps(already_notified, indent=4, sort_keys=True),ALREADY_NOTIFIED_FILE,True)

# basic file output wrapper for saving data to a file
def log(text,file,purge=False):
    f3 = codecs.open(file, 'a', 'utf-8')
    # if we are truncating empty the file otherwise add a newline and timestamp to the log file
    if purge:
        f3.truncate(0)
    else:
        text = u'\n* [%s UTC] %s' % (time.strftime(u'%Y-%m-%d %H:%M:%S',time.gmtime()),text)
        f3.write(text)
        f3.close()

# Basic wrapper for getting the contents of a file  
def get_file(filename):
    if not os.path.isfile(filename):
        with open(filename, "w+") as newfile:
            newfile.write("{}")

        return "{}"
    else:
        with codecs.open(filename, "r", "utf-8") as thefile:
            return thefile.read()

def usernames_from_text_with_sigs(wikitext):
    "Returns the users whose talk pages are linked to in the wikitext."
    usernames = [wikitext[m.end():m.end()+wikitext[m.end():].find("|")]
                 for m in re.finditer(r"User talk:", wikitext)]

    # Remove empty strings and duplicates
    usernames = [x for x in list(set(usernames)) if x]

    # this is ugly but is needed, further tweaks will probably be needed for oddball cases
    def sanitize_username(username):
        userpage = pywikibot.page.Page(site, u'User:' + x)
        result = userpage.title(withNamespace=False)
        result = pywikibot.page.html2unicode(result)
        
        # Convert some HTML encoded values to their Unicode equivalents
        result = re.sub("&#38;", "&", result)
        result = re.sub("&amp;", "&", result)
        return result
        
    return map(sanitize_username, usernames)

if __name__ == '__main__':
    main()
