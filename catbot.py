import functools
import logging
import logging.config
import mimetypes
import os
import re
import threading
import time

from io import BytesIO

from lxml import html
import mastodon
import requests
import tweepy


TWITTER_CONSUMER_KEY = os.getenv('TWITTER_CONSUMER_KEY')
TWITTER_CONSUMER_SECRET = os.getenv('TWITTER_CONSUMER_SECRET')
TWITTER_ACCESS_KEY = os.getenv('TWITTER_ACCESS_KEY')
TWITTER_ACCESS_SECRET = os.getenv('TWITTER_ACCESS_SECRET')

MASTODON_API_BASE_URL = os.getenv('MASTODON_API_BASE_URL')
MASTODON_CLIENT_KEY = os.getenv('MASTODON_CLIENT_KEY')
MASTODON_CLIENT_SECRET = os.getenv('MASTODON_CLIENT_SECRET')
MASTODON_ACCESS_TOKEN = os.getenv('MASTODON_ACCESS_TOKEN')


GIPHY_API_KEY = os.getenv('GIPHY_API_KEY')

PATTERN = re.compile(
    r'(?:고양이|야옹이|냐옹이|냥이).*필요|'
    r'우울[해하한]|냐짤|(?:죽고\s*싶|살기\s*싫)[어네다]')

logger = logging.getLogger(__name__)


class CatBotTwitterListener(tweepy.streaming.StreamListener):

    def __init__(self, api):
        super().__init__()
        self.api = api
        self.me = api.me()
        self.logger = logging.getLogger('catbot-twitter')

    def on_connect(self):
        super().on_connect()
        self.logger.debug('connected')
        self.follow_all()

    def on_status(self, status):
        if hasattr(status, 'retweeted_status'):
            return

        if PATTERN.search(status.text) or self.is_mentioning_me(status):
            self.reply_with_cat(status)

    def on_event(self, status):
        super().on_event(status)
        if status.event == 'follow':
            user = tweepy.User.parse(self.api, status.source)
            if user == self.me:
                return
            self.logger.info('Follow back new follower {}(@{}).'.format(
                user.name, user.screen_name))
            try:
                self.api.create_friendship(id=user.id)
            except Exception as e:
                self.logger.error(str(e))

    def reply_with_cat(self, status):
        catpic = get_random_catpic()
        try:
            f = BytesIO(requests.get(catpic['image_url']).content)
            media_id = self.api.media_upload('giphy.gif', file=f).media_id
        except tweepy.error.TweepError:
            f = BytesIO(requests.get(
                catpic['fixed_height_downsampled_url']).content)
            media_id = self.api.media_upload('giphy.gif', file=f).media_id
        self.api.update_status(
            status='',
            in_reply_to_status_id=status.id,
            auto_populate_reply_metadata=True,
            media_ids=(media_id,)
        )

    def extract_mentions(self, status):
        pattern = re.compile(r'@\w+')
        mentions = set(pattern.findall(status.text))
        my_name = self.me.screen_name
        dst_name = status.user.screen_name
        return mentions - {'@'+name for name in (my_name, dst_name)}

    def is_mentioning_me(self, status):
        return self.me.id in (x['id'] for x in status.entities['user_mentions'])

    def follow_all(self):
        friends = list(tweepy.Cursor(self.api.friends_ids).items())

        for follower_id in tweepy.Cursor(self.api.followers_ids).items():
            if follower_id not in friends:
                self.logger.info('Follow {}'.format(follower_id))
                try:
                    self.api.create_friendship(follower_id)
                except Exception as e:
                    self.logger.error(str(e))


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
            f = BytesIO(requests.get(url).content)
            media = self.api.media_post(f, mimetypes.guess_type(url)[0])
        except Exception as e:
            self.logger.error(e)
            url = catpic['fixed_height_downsampled_url']
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
        doc = html.fromstring(status['content'])
        for link in doc.xpath('//a'):
            link.drop_tree()

        content = doc.text_content()
        return content.strip()

    @property
    def user_stream(self):
        return functools.partial(self.api.user_stream, self)

    @property
    def local_stream(self):
        return functools.partial(self.api.local_stream, self)

    @property
    def public_stream(self):
        return functools.partial(self.api.public_stream, self)

    @property
    def hashtag_stream(self):
        return functools.partial(self.api.hastag_stream, self)


def get_random_catpic():
    json_result = requests.get('http://api.giphy.com/v1/gifs/random', params={
        'api_key': GIPHY_API_KEY,
        'tag': 'cat',
    }).json()
    url = json_result['data']
    return url


def set_logger():
    logging.config.fileConfig('logging.conf')


def make_twitter_stream():
    try:
        twitter_auth = tweepy.OAuthHandler(TWITTER_CONSUMER_KEY, TWITTER_CONSUMER_SECRET)
        twitter_auth.set_access_token(TWITTER_ACCESS_KEY, TWITTER_ACCESS_SECRET)
        api = tweepy.API(twitter_auth)
        catbot_listener = CatBotTwitterListener(api)
        twitter_stream = tweepy.Stream(twitter_auth, catbot_listener)
    except tweepy.TweepError as e:
        logger.error(e)
    else:
        return twitter_stream


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


def is_mastodon_stream_alive():
    # XXX: Hack to find thread before PR merged.
    for thread in threading.enumerate():
        if thread._target and thread._target.__name__ == '_threadproc':
            return thread.is_alive()

    return False


def main():
    set_logger()

    twitter_stream = make_twitter_stream()
    mastodon_stream = make_mastodon_stream()

    logger.info('Starting')
    if twitter_stream:
        logger.info('Starting twitter bot')
        twitter_stream.userstream(async=True)

    if mastodon_stream:
        logger.info('Starting mastodon bot')
        mastodon_handle = mastodon_stream.user_stream(async=True)

    while True:
        try:
            if mastodon_stream and not is_mastodon_stream_alive():
                mastodon_handle.close()
                mastodon_handle = mastodon_stream.user_stream(async=False)

            if twitter_stream and not twitter_stream._thread.isAlive():
                twitter_stream.userstream(async=False)

            time.sleep(10)
        except KeyboardInterrupt as e:
            logger.info('Closing')
            break

    if twitter_stream:
        twitter_stream.disconnect()

    if mastodon_stream:
        mastodon_handle.close()


def test_twitter():
    auth = tweepy.OAuthHandler(TWITTER_CONSUMER_KEY, TWITTER_CONSUMER_SECRET)
    auth.set_access_token(TWITTER_ACCESS_KEY, TWITTER_ACCESS_SECRET)
    api = tweepy.API(auth)
    catpic_url = get_random_catpic()['image_url']
    f = BytesIO(requests.get(catpic_url).content)
    media_id = api.media_upload('giphy.gif', file=f).media_id
    api.update_status(
        status='',
        media_ids=(media_id,)
    )


if __name__ == '__main__':
    main()
