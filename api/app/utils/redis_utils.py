from functools import cache
from redis import Redis
from config import REDIS_HOST, REDIS_PORT, REDIS_DB, REDIS_JOB_LIST

@cache
def get_redis_client():
    return Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        db=REDIS_DB,
        decode_responses=True,
    )

def enqueue_job(submission_id: int):
    get_redis_client().lpush(REDIS_JOB_LIST, submission_id)

def check_submission_rate_limit(user_id: int, limit: int = 5, window_seconds: int = 60) -> tuple[bool, int]:
    """
    Returns (is_allowed, retry_after_seconds).
    Uses Redis key expiration to enforce rate limit per user.
    """
    client = get_redis_client()
    key = f"ratelimit:submission:{user_id}"
    
    current = client.incr(key)
    if current == 1:
        client.expire(key, window_seconds)
        ttl = window_seconds
    else:
        ttl = client.ttl(key)
        if ttl < 0:
            client.expire(key, window_seconds)
            ttl = window_seconds

    if current > limit:
        return False, max(1, ttl)
    return True, 0

