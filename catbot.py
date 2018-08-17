import functools
import logging
import logging.config
import mimetypes
import os
import re

from io import BytesIO

from lxml import html
import mastodon
import requests

MASTODON_API_BASE_URL = os.getenv('MASTODON_API_BASE_URL')
MASTODON_CLIENT_KEY = os.getenv('MASTODON_CLIENT_KEY')
MASTODON_CLIENT_SECRET = os.getenv('MASTODON_CLIENT_SECRET')
MASTODON_ACCESS_TOKEN = os.getenv('MASTODON_ACCESS_TOKEN')


GIPHY_API_KEY = os.getenv('GIPHY_API_KEY')

PATTERN = re.compile(
    r'(?:고양이|야옹이|냐옹이|냥이).*필요|'
    r'우울[해하한]|냐짤|(?:죽고\s*싶|살기\s*싫)[어네다]')

logger = logging.getLogger(__name__)


class CatBotMastodonListener(mastodon.StreamListener):

    def __init__(self, api: mastodon.Mastodon):
        super().__init__()
        self.api = api
        self.logger = logging.getLogger('catbot-mastodon')
        self.me = self.api.account_verify_credentials()
        self.logger.info(f'I am {self.me["acct"]}')

    def on_update(self, status):
        self.handle_status(status)

    def on_notification(self, notification):
        if notification['type'] == 'follow':
            try:
                account = notification['account']
                self.logger.info(f'Follow {account["acct"]}')
                self.api.account_follow(account['id'])
            except Exception as e:  # TODO: change this to MastodonError after Mastodon.py release.
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
        if status['reblogged']:
            self.logger.debug('Skipping reblogged status.')
            return

        account = status['account']
        content = self.get_plain_content(status)

        self.logger.debug(f'{account["acct"]}: {content}')

        matched = PATTERN.search(content)
        if matched:
            self.logger.info(f'Repling to {account["acct"]}')
            self.reply_with_catpic(status)
        else:
            self.logger.debug(f'Skip')

    def reply_with_catpic(self, status):
        catpic = get_random_catpic()
        try:
            url = catpic['image_url']
            self.logger.debug(url)
            f = BytesIO(requests.get(url).content)
            media = self.api.media_post(f, mimetypes.guess_type(url)[0])
        except Exception as e:
            self.logger.error(e)
            url = catpic['fixed_height_downsampled_url']
            self.logger.debug(url)
            f = BytesIO(requests.get(url).content)
            media = self.api.media_post(f, mimetypes.guess_type(url)[0])

        # Same privacy except for public.
        visibility = status['visibility']
        if visibility == 'public':
            visibility = 'unlisted'

        mentions = ' '.join(
            f'@{user["acct"]}'
            for user in [status['account']] + status['mentions']
            if user['acct'] != self.me['acct']
        )

        self.api.status_post(
            f'{mentions} nya!',
            in_reply_to_id=status['id'],
            media_ids=(media,),
            visibility=visibility
        )

    @staticmethod
    def get_plain_content(status):
        if not status['content']:
            return ''
        doc = html.fromstring(status['content'])
        for link in doc.xpath('//a'):
            link.drop_tree()

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
    json_result = requests.get('http://api.giphy.com/v1/gifs/random', params={
        'api_key': GIPHY_API_KEY,
        'tag': 'cat',
    }).json()
    url = json_result['data']
    return url


def set_logger():
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
