require 'mediawiki/butt'

class MarshallableButt < MediaWiki::Butt
  def marshal_dump
    [@url, @query_limit_default, @uri, @logged_in, @custom_agent, @cookie, @name]
  end

  def marshal_load array
    @url, @query_limit_default, @uri, @logged_in, @custom_agent, @cookie, @name = array
    @client = HTTPClient.new
  end
end
