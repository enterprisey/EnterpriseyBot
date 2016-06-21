require 'io/console'
require 'mediawiki/butt'

USERNAME = 'APersonBot'
BOTREQ = 'Wikipedia:Bot requests'
BOTOP_CAT = 'Category:Wikipedia bot owners'
REPORT_PAGE = 'User:APersonBot/BOTREQ status'

HEADER = /== ?([^=]+) ?==\n/#/== ?([\w\[\]:\{\},\. ]+) ?==\n/
USER = /\[\[User.*?:(.*?)(?:\||(?:\]\]))/
TIMESTAMP = /\d{2}:\d{2}, (\d{1,2}) ([A-Za-z]*) (\d{4})/
SIGNATURE = /\[\[User.*?\]\].*?\(UTC\)/

# Log in
wiki = MediaWiki::Butt.new('https://en.wikipedia.org/w/api.php')
print "Password for #{USERNAME} on en.wikipedia.org: "
password = STDIN.noecho(&:gets).chomp
puts ''
wiki.login(USERNAME, password)
puts "Logged in as #{USERNAME}."

# Set up a class and a predicate
class Request
  attr_accessor :title, :replies, :last_editor, :last_edit_time, :last_botop_editor, :last_botop_time

  # Writes out a wikitext row for use in the BOTREQ status page.
  def row
    style = self.replies == 0 ? 'style="background: red;" | ' : ''
    title = self.title.gsub(/\[\[(?:.+\|)?(.+)\]\]/, '\1')
    anchor = title.gsub(/{{tl\|(.+)}}/, '.7B.7B\1.7D.7D')
    title = title.gsub(/{{tl\|(.+)}}/, '\1')
    %Q{
|-
| [[Wikipedia:Bot requests##{title}|#{title}]] || #{style}#{self.replies} || #{self.last_editor} || #{self.last_edit_time} || #{self.last_botop_editor} || #{self.last_botop_time}}
  end
end

# We want a hash of the form {section_title => section_body}
page_content = wiki.get_text(BOTREQ)
page_content = "==" + page_content.split("==", 2)[1]
section_matches = page_content.to_enum(:scan, HEADER).map { Regexp.last_match }
headings = section_matches.map { |x| x[1].strip }
body_offsets = section_matches.map { |x| x.offset(0) }.flatten[1..-1].each_slice(2)
bodies = body_offsets.map { |x| page_content[x[0]..(x.length == 1 ? -1 : x[1] - 1)] }
sections = Hash[headings.zip(bodies)]
puts "#{sections.length} sections found."

# Build request objects
requests = sections.map do |heading, body|
  signatures = body.to_enum(:scan, SIGNATURE)
               .map { Regexp.last_match }
               .map { |x| x.to_s }
               .map { |match| [USER.match(match)[1], TIMESTAMP.match(match)] }
               .select { |user, timestamp| !user.include? '/' }
  request = Request.new
  request.title = heading
  request.replies = body.scan(/\(UTC\)/).length - 1
  request.last_editor = signatures[-1][0]
  request.last_edit_time = signatures[-1][1]
  last_botop_signature = signatures.reverse.find do |user, timestamp|
    categories = wiki.get_categories_in_page("User:#{user}")
    if categories.nil? || categories.length == 0
      false
    else
      categories.include? BOTOP_CAT
    end
  end
  if last_botop_signature
    request.last_botop_editor, request.last_botop_time = last_botop_signature
  else
    request.last_botop_editor = '{{no result|None}}'
    request.last_botop_time = '{{n/a}}'
  end
  request
end
header = %({| border="1" class="sortable wikitable plainlinks"
!Title !! Replies !! Last editor !! Date/Time !! Last botop editor !! Date/Time
)
final_text = header + requests.map { |x| x.row }.join('') + "\n|}"

puts "Text generated. Saving to #{REPORT_PAGE}..."
result = wiki.edit(REPORT_PAGE, final_text, false, false, 'Generating a status report for BOTREQ (testing)')
print 'Result: '
puts result
