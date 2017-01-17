import os

import tweepy


CONSUMER_KEY = os.getenv('TWITTER_CONSUMER_KEY')
CONSUMER_SECRET = os.getenv('TWITTER_CONSUMER_SECRET')
ACCESS_KEY = os.getenv('TWITTER_ACCESS_KEY')
ACCESS_SECRET = os.getenv('TWITTER_ACCESS_SECRET')

GIPHY_API_KEY = os.getenv('GIPHY_API_KEY')


class CatBotListener(tweepy.streaming.StreamListener):

    def on_status(self, status):
        if hasattr(status, 'retweeted_status'):
            return

        self.process_status(status)

    def process_status(self, status):
        print(status.text)


def main():
    catbot_listener = CatBotListener()

    auth = tweepy.OAuthHandler(CONSUMER_KEY, CONSUMER_SECRET)
    auth.set_access_token(ACCESS_KEY, ACCESS_SECRET)

    stream = tweepy.Stream(auth, catbot_listener)
    stream.userstream()


if __name__ == '__main__':
    main()
