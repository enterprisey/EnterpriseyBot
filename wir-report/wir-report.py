import sys
import datetime
import re
import pywikibot
from pywikibot import pagegenerators

reThreshold = re.compile( '^  @@(\d+)@@' )
rePattern = re.compile( '^ (-?\d+) /([^/]*)/' )
CSD_SUMMARY = re.compile(r"CSD|(^|\s+)(G|A)\d\d?($|[^\d])|db-\w|Nominated\spage\sfor\sdeletion")
CSD_RULE_SUMMARY = re.compile(r"((?:G|A)\d\d?)|(db-.+)(?:\||\}\})")
CSD_TEMPLATE = re.compile(r"\{\{(db-\w+).+?\}\}")

REPORT_PAGE = "User:EnterpriseyBot/WiR CSD report"
SUMMARY = "Bot generating CSD report for WiR"

NUM_ARTICLES = 10
catName = u'Category:Candidates for speedy deletion'
rulesName = 'Womeninred'
if len( sys.argv ) > 1:
  rulesName = sys.argv[ 1 ]

class AlexNewArtBotResult:

  threshold = 10
  patterns = []

  def __init__( self, rule ):
    page = pywikibot.Page( site, 'User:AlexNewArtBot/' + rule )
    gotThreshold = False
    for line in page.text.splitlines():
      if not gotThreshold:
        match = reThreshold.match( line )
        if not match is None:
          self.threshold = int( match.group( 1 ) )
        gotThreshold = True
      else:
        match = rePattern.match( line )
        if not match is None:
          value = int( match.group( 1 ) )
          pattern = match.group( 2 )
          self.patterns.append( ( value, pattern ) )

  def score( self, page_text ):
    score = 0
    for ( value, pattern ) in self.patterns:
      if pattern == r'\whe\w': pattern = r'\she\s'
      if pattern == r'\w(man|men|male)': pattern = r'\s(man|men|male)'
      if re.search( pattern, page_text, re.IGNORECASE ) is not None:
        score = score + value
    return score

class Article:
  def __init__(self, page_object):
    self.page_object = page_object
    self.title = page_object.title(withNamespace=True)
    self.text = page_object.get()
    self.score = rules.score(self.text)

  def get_csd_reason(self):
    if self.title == "Fortifications at Mycenae": print self.text
    match = CSD_TEMPLATE.search(self.text)
    return match.group(1) if match else None

  def get_csd_rev(self):
    csd_revs = (rev for rev in self.page_object.revisions()
        if CSD_SUMMARY.search(rev.comment))
    try:
      return next(csd_revs)
    except StopIteration:
      return None

site = pywikibot.Site()
rules = AlexNewArtBotResult( rulesName )

cat = pywikibot.Category( site, catName )

# Find scores for each article in the category
articles = [Article(page) for page in cat.articles(namespaces=(0))]
articles.sort(key=lambda a: a.score, reverse=True)
articles = articles[:NUM_ARTICLES]

# Upload to the wiki
content = ""
content += "== CSD alerts =="
now = datetime.datetime.utcnow()
for each_article in articles:
  csd_rev = each_article.get_csd_rev()
  if csd_rev:
    deletion_delta = now - csd_rev.timestamp
    age_in_hours = float(deletion_delta.total_seconds())/3600
    formatted_age = "{:.1f} hours ago".format(age_in_hours)
    reason = each_article.get_csd_reason()
    formatted_reason = ("reason: " + reason + ", ") if reason else ""
  else:
    formatted_reason = ""
    formatted_age = ""
  score = each_article.score
  formatted_score = ("'''{}'''".format(score) if score > rules.threshold
      else "{}".format(score))
  content += "\n* {{{{la|{}}}}} put up for CSD {} ({}score: {})".format(
      each_article.title, formatted_age, formatted_reason, formatted_score)

report_page = pywikibot.Page(site, REPORT_PAGE)
report_page.text = content
report_page.save(summary=SUMMARY)
