require 'io/console'
require 'mediawiki/butt'
require_relative 'marshallable-butt.rb'

OUTPUT_FILE = 'login_state'
USERNAME = 'APersonBot'

wiki = MarshallableButt.new('https://en.wikipedia.org/w/api.php')
print "Password for #{USERNAME} on en.wikipedia.org: "
password = STDIN.noecho(&:gets).chomp
puts ''
wiki.login(USERNAME, password)
puts "Logged in as #{wiki.get_current_user_name} (bot: #{wiki.user_bot?})."
puts "#{wiki}"

File.open(OUTPUT_FILE, 'wb') do |file|
  file.write(Marshal.dump(wiki))
end

puts "Dumped wiki state to #{OUTPUT_FILE}."
