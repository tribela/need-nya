import os
import re

from io import BytesIO

import requests
import tweepy


CONSUMER_KEY = os.getenv('TWITTER_CONSUMER_KEY')
CONSUMER_SECRET = os.getenv('TWITTER_CONSUMER_SECRET')
ACCESS_KEY = os.getenv('TWITTER_ACCESS_KEY')
ACCESS_SECRET = os.getenv('TWITTER_ACCESS_SECRET')

GIPHY_API_KEY = os.getenv('GIPHY_API_KEY')


class CatBotListener(tweepy.streaming.StreamListener):
    PATTERNS = [
        re.compile(r'(?:고양이|야옹이|냐옹이|냥이).*필요'),
        re.compile(r'우울[해하]|냐짤|죽고\s*싶[어다]'),
    ]

    def __init__(self, api):
        super(CatBotListener, self).__init__()
        self.api = api

    def on_status(self, status):
        if hasattr(status, 'retweeted_status'):
            return

        if any((pattern.search(status.text) for pattern in self.PATTERNS)):
            self.reply_with_cat(status)

    def on_friends(self, friends):
        self.follow_all()

    def reply_with_cat(self, status):
        catpic_url = get_random_catpic_url()
        f = BytesIO(requests.get(catpic_url).content)
        media_id = self.api.media_upload('giphy.gif', file=f).media_id
        self.api.update_status(
            status='@{dest.screen_name} {mentions}'.format(
                dest=status.user,
                mentions=' '.join(self.extract_mentions(status))
            ),
            in_reply_to_stauts_id=status.id,
            media_ids=(media_id,)
        )

    def extract_mentions(self, status):
        pattern = re.compile(r'@\w+')
        mentions = set(pattern.findall(status.text))
        my_name = self.api.me().screen_name
        dst_name = status.user.screen_name
        return mentions - {'@'+name for name in (my_name, dst_name)}

    def follow_all(self):
        friends = list(tweepy.Cursor(self.api.friends_ids).items())

        for follower_id in tweepy.Cursor(self.api.followers_ids).items():
            if follower_id not in friends:
                print(follower_id)
                self.api.create_friendship(follower_id)


def get_random_catpic_url():
    json_result = requests.get('http://api.giphy.com/v1/gifs/random', {
        'api_key': GIPHY_API_KEY,
        'tag': 'cat'
    }).json()
    url = json_result['data']['image_url']
    return url


def main():
    auth = tweepy.OAuthHandler(CONSUMER_KEY, CONSUMER_SECRET)
    auth.set_access_token(ACCESS_KEY, ACCESS_SECRET)

    api = tweepy.API(auth)

    catbot_listener = CatBotListener(api)
    catbot_listener.follow_all()

    stream = tweepy.Stream(auth, catbot_listener)
    while True:
        try:
            stream.userstream()
        except KeyboardInterrupt:
            break
        except:
            continue


def test():
    auth = tweepy.OAuthHandler(CONSUMER_KEY, CONSUMER_SECRET)
    auth.set_access_token(ACCESS_KEY, ACCESS_SECRET)
    api = tweepy.API(auth)
    catpic_url = get_random_catpic_url()
    f = BytesIO(requests.get(catpic_url).content)
    media_id = api.media_upload('giphy.gif', file=f).media_id
    api.update_status(
        status='',
        media_ids=(media_id,)
    )


if __name__ == '__main__':
    main()
