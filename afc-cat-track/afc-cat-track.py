import datetime
import pywikibot

PENDING_CAT = "Category:Pending AfC submissions"
LOG_FILE = "log.txt"

def print_log(what_to_print):
    print(datetime.datetime.utcnow().strftime("[%Y-%m-%dT%H:%M:%SZ] ") + what_to_print)

def main():
    print_log("Starting afc-cat-track at " + datetime.datetime.utcnow().isoformat())
    wiki = pywikibot.Site("en", "wikipedia")
    wiki.login()
    pending = pywikibot.Category(wiki, PENDING_CAT)
    count = pending.categoryinfo[u'pages']
    with open(LOG_FILE, 'a') as log_file:
        log_file.write("%s %d\n" % (datetime.datetime.utcnow().isoformat(), count))

if __name__ == "__main__":
    main()
