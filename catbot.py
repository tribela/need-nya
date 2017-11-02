import logging
import logging.config
import os
import re
import time

from io import BytesIO

import requests
import tweepy


TWITTER_CONSUMER_KEY = os.getenv('TWITTER_CONSUMER_KEY')
TWITTER_CONSUMER_SECRET = os.getenv('TWITTER_CONSUMER_SECRET')
TWITTER_ACCESS_KEY = os.getenv('TWITTER_ACCESS_KEY')
TWITTER_ACCESS_SECRET = os.getenv('TWITTER_ACCESS_SECRET')

GIPHY_API_KEY = os.getenv('GIPHY_API_KEY')

PATTERN = re.compile(
    r'(?:고양이|야옹이|냐옹이|냥이).*필요|'
    r'우울[해하]|냐짤|(?:죽고\s*싶|살기\s*싫)[어네다]')

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


def main():
    set_logger()

    twitter_stream = make_twitter_stream()

    logger.info('Starting')
    if twitter_stream:
        twitter_stream.userstream(async=True)

    while True:
        try:
            time.sleep(10)
        except KeyboardInterrupt as e:
            logger.info('Closing')
            break

    twitter_stream.disconnect()


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
