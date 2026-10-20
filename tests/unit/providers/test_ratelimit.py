from heatmap_core.providers.ratelimit import TokenBucket
from tests.support import FakeClock


def test_bucket_allows_burst_then_refills() -> None:
    clock = FakeClock()
    bucket = TokenBucket(rate=2, clock=clock)
    assert bucket.try_acquire()
    assert bucket.try_acquire()
    assert not bucket.try_acquire()
    assert bucket.wait_time() == 0.5
    clock.advance(0.5)
    assert bucket.try_acquire()


def test_drain_forces_wait() -> None:
    clock = FakeClock()
    bucket = TokenBucket(rate=1, clock=clock)
    bucket.drain()
    assert not bucket.try_acquire()
    clock.advance(1)
    assert bucket.try_acquire()
