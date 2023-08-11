import functools
import logging
import logging.config
import math
import mimetypes
import os
import re
import time

from collections import defaultdict
from io import BytesIO

from lxml import html
import mastodon
import requests

MASTODON_API_BASE_URL = os.getenv('MASTODON_API_BASE_URL')
MASTODON_CLIENT_KEY = os.getenv('MASTODON_CLIENT_KEY')
MASTODON_CLIENT_SECRET = os.getenv('MASTODON_CLIENT_SECRET')
MASTODON_ACCESS_TOKEN = os.getenv('MASTODON_ACCESS_TOKEN')

DEBUG_MODE = 'DEBUG_MODE' in os.environ
if DEBUG_MODE:
    from pprint import pprint


GIPHY_API_KEY = os.getenv('GIPHY_API_KEY')

PATTERN = re.compile(
    r'(?:고양이|야옹이|냐옹이|냥이).*필요|'
    r'우울[해하한]|냐짤|(?:죽고\s*싶|살기\s*싫)[어네다]')
ADDICT_PATTERN = re.compile(r'필요$')

logger = logging.getLogger(__name__)


class ApiError(Exception):
    pass


class AddictChecker(object):
    def __init__(self, limit=2, cooldown=60*60):
        self._addict = defaultdict(list)
        self.limit = limit
        self.cooldown = cooldown

    def is_addict(self, user_id):
        if len(self._addict[user_id]) > self.limit:
            return True
        else:
            return False

    def add(self, user_id):
        self._addict[user_id].append(time.time())
        self.cleanup()

    def cleanup(self):
        now = time.time()
        for user_id in self._addict.keys():
            self._addict[user_id] = [
                t for t in self._addict[user_id] if t > now - self.cooldown
            ]

            if self._addict[user_id] == []:
                del self._addict[user_id]


class CatBotMastodonListener(mastodon.StreamListener):

    def __init__(self, api: mastodon.Mastodon):
        super().__init__()
        self.api = api
        self.logger = logging.getLogger('catbot-mastodon')
        self.me = self.api.account_verify_credentials()
        self.logger.info(f'I am {self.me["acct"]}')
        self.addict_checker = AddictChecker()

    def on_update(self, status):
        self.handle_status(status)

    def on_notification(self, notification):
        if notification['type'] == 'follow':
            try:
                account = notification['account']
                self.logger.info(f'Follow {account["acct"]}')
                self.api.account_follow(account['id'])
            except mastodon.MastodonError as e:
                self.logger.error(e)
        elif notification['type'] == 'mention':
            account = notification['account']
            status = notification['status']
            self.logger.info(f'{account["acct"]} mentioned me')
            content = self.get_plain_content(status)

            if content == 'follow':
                self.logger.info(f'Follow {account["acct"]} by mention')
                self.api.account_follow(account['id'])
            elif content == 'unfolow':
                self.logger.info(f'Unfollow {account["acct"]} by mention')
                self.api.account_unfollow(account['id'])
        else:
            self.logger.debug(f'Unhandled notification type {notification["type"]}.')

    def handle_status(self, status):
        if status['reblog'] is not None:
            self.logger.debug('Skipping reblogged status.')
            return

        account = status['account']
        content = self.get_plain_content(status)

        self.logger.debug(f'{account["acct"]}: {content}')

        matched = PATTERN.search(content)
        if matched:
            if ADDICT_PATTERN.search(content):
                self.addict_checker.add(account['id'])
                if self.addict_checker.is_addict(account['id']):
                    self.logger.info(f'{account["acct"]} is an addict.')
                    self.reply_with_addict_message(status)
                    return

            self.logger.info(f'Repling to {account["acct"]}')
            self.reply_with_catpic(status)
        else:
            self.logger.debug(f'Skip')

    def reply_with_catpic(self, status):
        try:
            catpic = get_random_catpic()
        except ApiError as e:
            logger.error(e)
            return
        try:
            url = catpic['original']['url']
            self.logger.debug(url)
            f = BytesIO(requests.get(url).content)
            media = self.upload_media(f, mimetypes.guess_type(url)[0])
        except Exception as e:
            self.logger.error(e)
            url = catpic['downsized']['url']
            self.logger.debug(url)
            f = BytesIO(requests.get(url).content)
            media = self.upload_media(f, mimetypes.guess_type(url)[0])

        # Same privacy except for public.
        visibility = status['visibility']
        if visibility == 'public':
            visibility = 'unlisted'

        mentions = ' '.join(
            f'@{user["acct"]}'
            for user in [status['account']] + status['mentions']
            if user['acct'] != self.me['acct']
        )

        if DEBUG_MODE:
            pprint(status['id'])
        else:
            self.api.status_post(
                f'{mentions} nya!',
                in_reply_to_id=status['id'],
                media_ids=(media,),
                visibility=visibility
            )

    def reply_with_addict_message(self, status):
        # Same privacy except for public.
        visibility = status['visibility']
        if visibility == 'public':
            visibility = 'unlisted'

        if DEBUG_MODE:
            pprint(status['id'])
        else:
            acct = status['account']['acct']
            self.api.status_post(
                f"@{acct} 당신은 야짤 중독입니다...",
                in_reply_to_id=status['id'],
                visibility=visibility
            )

    def upload_media(self, *args, **kwargs):
        media = self.api.media_post(*args, **kwargs)
        try_count = 0
        while 'url' not in media or media.url is None:
            try_count += 1
            sleep_duration = math.log2(1 + try_count)
            time.sleep(sleep_duration)
            try:
                media = self.api.media(media)
            except:
                raise
        return media

    @staticmethod
    def get_plain_content(status):
        if not status['content']:
            return ''
        doc = html.fromstring(status['content'])
        for link in doc.xpath('//a'):
            link.drop_tree()

        # Fix br into \n
        for br in doc.xpath('//br'):
            br.tail = '\n' + (br.tail or '')

        content = doc.text_content()
        return content.strip()

    @property
    def stream_user(self):
        return functools.partial(self.api.stream_user, self)

    @property
    def stream_local(self):
        return functools.partial(self.api.stream_local, self)

    @property
    def stream_public(self):
        return functools.partial(self.api.stream_public, self)

    @property
    def stream_hashtag(self):
        return functools.partial(self.api.stream_hashtag, self)


def get_random_catpic():
    resp = requests.get('http://api.giphy.com/v1/gifs/random', params={
        'api_key': GIPHY_API_KEY,
        'tag': 'cat',
    })
    if not resp.ok:
        raise ApiError(resp.json()['message'])

    json_result = resp.json()
    url = json_result['data']['images']
    return url


def set_logger():
    if DEBUG_MODE:
        logging.config.fileConfig('logging.debug.conf')
    else:
        logging.config.fileConfig('logging.conf')


def make_mastodon_stream():
    try:
        api = mastodon.Mastodon(
            api_base_url=MASTODON_API_BASE_URL,
            client_id=MASTODON_CLIENT_KEY,
            client_secret=MASTODON_CLIENT_SECRET,
            access_token=MASTODON_ACCESS_TOKEN
        )
        mastodon_stream = CatBotMastodonListener(api)
    except Exception as e:
        logger.error(e)
    else:
        return mastodon_stream


def main():
    set_logger()

    mastodon_stream = make_mastodon_stream()
    logger.info('Starting mastodon bot')
    mastodon_stream.stream_user(reconnect_async=True)


if __name__ == '__main__':
    main()
