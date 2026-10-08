import inspect

import app as app_module


def test_chat_runs_start_after_redis_connects_and_stop_before_it_closes():
    source = inspect.getsource(app_module.lifespan)
    connect = source.index("AsyncRedisPool.connect")
    start = source.index("start_chat_runs(")
    # The bare word appears in an unrelated startup comment ("yields 401"),
    # so anchor on the statement's own indentation.
    yield_index = source.index("\n            yield")
    stop = source.index("stop_chat_runs(")
    close = source.index("AsyncRedisPool.close()")
    assert connect < start < yield_index < stop < close
