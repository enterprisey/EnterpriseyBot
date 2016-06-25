require 'io/console'
require 'mediawiki/butt'
require 'time'
require_relative 'marshallable-butt.rb'

LOGIN_STATE_FILE = 'login_state'
USERNAME = 'APersonBot'
BOTREQ = 'Wikipedia:Bot requests'
BOTOP_CAT = 'Category:Wikipedia bot owners'
REPORT_PAGE = 'User:APersonBot/BOTREQ status'

HEADER = /== ?([^=]+) ?==\n/#/== ?([\w\[\]:\{\},\. ]+) ?==\n/
USER = /\[\[User.*?:(.*?)(?:\||(?:\]\]))/
TIMESTAMP = /\d{2}:\d{2}, \d{1,2} [A-Za-z]* \d{4}/
SIGNATURE = /\[\[User.*?\]\].*?\(UTC\)/

SECONDS_IN_DAY = 24 * 60 * 60
OLD_REQUEST_TIME = 60 * SECONDS_IN_DAY # The number of seconds after which a request is old
TIME_FORMAT_STRING = '%Y-%m-%d, %H:%M'

# Log in
$wiki = nil
if File.exists? LOGIN_STATE_FILE
  puts "Attempting to read login state from #{LOGIN_STATE_FILE}..."
  $wiki = Marshal.load(File.read(LOGIN_STATE_FILE))
  puts $wiki
  puts $wiki.user_bot?
end
if !$wiki || !$wiki.user_bot?
  $wiki = MediaWiki::Butt.new('https://en.wikipedia.org/w/api.php')
  print "Password for #{USERNAME} on en.wikipedia.org: "
  password = STDIN.noecho(&:gets).chomp
  puts ''
  $wiki.login(USERNAME, password)
end
puts "Logged in as #{$wiki.get_current_user_name} (bot: #{$wiki.user_bot?})"

# Set up a couple of classes
class Request
  attr_accessor :title, :replies, :last_editor, :last_edit_time, :last_botop_editor, :last_botop_time

  # Writes out a wikitext row for use in the BOTREQ status page.
  def row
    replies_style = 'style="background: red;" | ' if @replies == 0

    title = @title.gsub(/\[\[(?:.+\|)?(.+)\]\]/, '\1')
    anchor = title.gsub(/{{tl\|(.+)}}/, '.7B.7B\1.7D.7D')
    title = title.gsub(/{{tl\|(.+)}}/, '\1')

    last_edit_time_style = 'style="background: red;" | ' if (Time.now - @last_edit_time) > OLD_REQUEST_TIME

    @last_botop_time = @last_botop_time ? @last_botop_time.strftime(TIME_FORMAT_STRING) : '{{n/a}}'

    %Q{
|-
| [[Wikipedia:Bot requests##{title}|#{title}]] || #{replies_style}#{@replies} || #{@last_editor} || #{last_edit_time_style}#{@last_edit_time.strftime(TIME_FORMAT_STRING)} || #{@last_botop_editor} || #{@last_botop_time}}
  end
end

class BotopChecker
  attr_accessor :results

  def check(user)
    if results.include? user
      results[user]
    else
      categories = $wiki.get_categories_in_page("User:#{user}")
      results[user] = if categories.nil? || categories.length == 0
                        false
                      else
                        categories.include? BOTOP_CAT
                      end
    end
  end
end

# We want a hash of the form {section_title => section_body}
page_content = $wiki.get_text(BOTREQ)
page_content = "==" + page_content.split("==", 2)[1]
section_matches = page_content.to_enum(:scan, HEADER).map { Regexp.last_match }
headings = section_matches.map { |x| x[1].strip }
body_offsets = section_matches.map { |x| x.offset(0) }.flatten[1..-1].each_slice(2)
bodies = body_offsets.map { |x| page_content[x[0]..(x.length == 1 ? -1 : x[1] - 1)] }
sections = Hash[headings.zip(bodies)]
puts "#{sections.length} sections found."

# Build request objects
botop_checker = BotopChecker.new
botop_checker.results = {}
requests = sections.map do |heading, body|
  signatures = body.to_enum(:scan, SIGNATURE)
               .map { Regexp.last_match }
               .map { |x| x.to_s }
               .map { |match| [USER.match(match)[1], TIMESTAMP.match(match)[0]] }
               .select { |user, timestamp| !user.include? '/' }
  request = Request.new
  request.title = heading
  request.replies = body.scan(/\(UTC\)/).length - 1
  request.last_editor = signatures[-1][0]
  request.last_edit_time = Time.parse(signatures[-1][1])
  last_botop_signature = signatures.reverse.find { |user, timestamp| botop_checker.check(user) }
  if last_botop_signature
    request.last_botop_editor, request.last_botop_time = last_botop_signature
    request.last_botop_time = Time.parse(request.last_botop_time)
  else
    request.last_botop_editor = '{{no result|None}}'
    request.last_botop_time = nil
  end
  request
end
header = %({| border="1" class="sortable wikitable plainlinks"
!Title !! Replies !! Last editor !! Date/Time !! Last botop editor !! Date/Time
)
final_text = header + requests.map { |x| x.row }.join('') + "\n|}"

puts "Text generated. Saving to #{REPORT_PAGE}..."

print 'Press enter to continue...'
gets

result = $wiki.edit(REPORT_PAGE, final_text, false, false, 'Generating a statusreport for BOTREQ')
print 'Result: '
puts result
