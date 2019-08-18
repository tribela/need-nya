import logging
import logging.config
import os
import time

from datetime import datetime, timezone

import mastodon

APP_NAME = 'need_nya'
THRESHOLD_DAYS = 30

MASTODON_API_BASE_URL = os.getenv('MASTODON_API_BASE_URL')
MASTODON_CLIENT_KEY = os.getenv('MASTODON_CLIENT_KEY')
MASTODON_CLIENT_SECRET = os.getenv('MASTODON_CLIENT_SECRET')
MASTODON_ACCESS_TOKEN = os.getenv('MASTODON_ACCESS_TOKEN')

DEBUG_MODE = 'DEBUG_MODE' in os.environ

logger = logging.getLogger(__name__)


def cleanup(api):
    me = api.account_verify_credentials()
    now = datetime.now().astimezone(timezone.utc)
    count = 0

    try:
        statuses = api.account_statuses(me.id, min_id=0, limit=40)
        while True:
            if not statuses:
                raise StopIteration

            for status in reversed(statuses):
                timedelta = now - status.created_at

                if timedelta.days < THRESHOLD_DAYS:
                    raise StopIteration

                if status.application.name != APP_NAME:
                    continue

                if (
                    status.reblogs_count or
                    status.replies_count or
                    status.favourites_count
                ):
                    continue

                count += 1

                logger.info(f'Deleting {status.id}')
                if not DEBUG_MODE:
                    api.status_delete(status.id)

            statuses = api.fetch_previous(statuses)
    except StopIteration:
        print(f'Removed {count} statuses')


def set_logger():
    if DEBUG_MODE:
        logging.config.fileConfig('logging.debug.conf')
    else:
        logging.config.fileConfig('logging.conf')


def main():
    set_logger()

    api = mastodon.Mastodon(
        api_base_url=MASTODON_API_BASE_URL,
        client_id=MASTODON_CLIENT_KEY,
        client_secret=MASTODON_CLIENT_SECRET,
        access_token=MASTODON_ACCESS_TOKEN
    )
    while True:
        cleanup(api)
        # sleep 1 hour
        time.sleep(1 * 60 * 60)


if __name__ == '__main__':
    main()
