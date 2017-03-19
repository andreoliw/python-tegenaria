# -*- coding: utf-8 -*-
"""Furnished apartments from City Wohnen."""
import re
import urllib
from datetime import datetime

import requests

from scrapy import Request
from scrapy.linkextractors import LinkExtractor
from scrapy.loader import ItemLoader
from scrapy.spiders import CrawlSpider, Rule
from tegenaria.items import ApartmentItem


class CityWohnenSpider(CrawlSpider):

    """Furnished apartments from City Wohnen."""

    name = 'city_wohnen'
    allowed_domains = ['city-wohnen.de']

    MAX_RECORDS = 200
    start_urls = [
        # This link shows an empty page...
        # 'https://www.city-wohnen.de/eng/berlin/furnished-flats/flat-search/'

        # ... because the actual results are loaded by an AJAX call.
        'https://www.city-wohnen.de/rpc.php?pageid=401&action=services&service=ciwo_search&cmd=search&'
        'filters=city%3Dberlin%26date_from%3D%26room_count%3D1%26rent_amount_min%3D0%26rent_amount_max%3D4375%26'
        'person_count%3D1&order=available_from&page_nr=1&page_size={}'.format(MAX_RECORDS)
    ]

    URL_REGEX = r'/eng/berlin/[0-9]+[a-z-]+'
    rules = (
        Rule(LinkExtractor(allow=URL_REGEX), callback='parse_item', follow=True),
    )

    field_regex = dict(
        availability=re.compile(r'.*from (?P<availability>[0-9/]+).*', re.MULTILINE),
        neighborhood=re.compile(r'furnished apartment in (?P<neighborhood>[^\t]+)\t+'),
        address=re.compile(r'.+/maps/search/(?P<address>.+)/@[0-9.,]+')
    )

    def start_requests(self):
        """Parse the results from the hidden AJAX call, and start requests to parse the ads."""
        for url in self.start_urls:
            response = requests.get(url)
            results = response.json().get('results')
            for link in re.compile(self.URL_REGEX).findall(results):
                yield Request('https://www.city-wohnen.de{}'.format(link), callback=self.parse_item)

    def parse_item(self, response):
        """Parse a page with an apartment."""
        item = ItemLoader(ApartmentItem(), response=response)
        item.add_value('url', response.url)

        item.add_css('title', 'div.text_data > h2::text')
        item.add_css('availability', 'div.row > div.text_data > p::text')
        item.add_css('description', 'div.object_details div.col_left p::text')
        item.add_value('neighborhood',
                       response.css('div.object_meta div.container div.text_data p strong::text').extract()[0])

        # The address is hidden on a Google Maps link, and there is only the street, not the number.
        street = urllib.unquote_plus(response.xpath("//li[@class='map']/a/@href").extract()[0])

        # And the encoding is wrong, so it needs fixing.
        # http://stackoverflow.com/questions/4267019/double-decoding-unicode-in-python
        item.add_value('address', street.encode('raw_unicode_escape').decode('utf-8'))

        keys = response.css('div.object_meta table.object_meta_data th::text').extract()
        values = response.css('div.object_meta table.object_meta_data td::text').extract()
        features = dict(zip(keys, values))
        item.add_value('warm_rent', features.get('Rent'))
        item.add_value('size', features.get('Size'))
        item.add_value('rooms', features.get('Room/s'))

        item_dict = item.load_item()

        # After loading: clean availability date.
        for field, regex in self.field_regex.items():
            clean_field = item_dict.get(field, '').strip(' \t\n')
            match = regex.match(clean_field)
            if match:
                item_dict.update(match.groupdict())

        # Must be an ISO date for the database.
        item_dict['availability'] = datetime.strptime(item_dict.get('availability'), '%d/%m/%Y').date().isoformat()

        return item_dict
