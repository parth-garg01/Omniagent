import time

from nova_api.cache.store import InMemoryCache, cache_key, retrieval_version

BASE = dict(user_id="u1", role="user", model="m", prompt_version="1", retrieval_version="r1",
            message="hi")


def test_disabled_by_default():
    c = InMemoryCache()
    c.set("k", "v")
    assert c.get("k") is None


def test_hit_when_enabled():
    c = InMemoryCache(enabled=True)
    c.set("k", "v")
    assert c.get("k") == "v"


def test_keys_isolate_users_roles_models_prompts_and_index():
    base = cache_key(**BASE)
    for field, other in [("user_id", "u2"), ("role", "admin"), ("model", "m2"),
                         ("prompt_version", "2"), ("retrieval_version", "r2"), ("message", "bye")]:
        assert cache_key(**{**BASE, field: other}) != base, field
    assert cache_key(**BASE) == base


def test_other_user_never_hits():
    c = InMemoryCache(enabled=True)
    c.set(cache_key(**BASE), "alice-private-answer")
    assert c.get(cache_key(**{**BASE, "user_id": "u2"})) is None


def test_index_change_invalidates():
    v1 = retrieval_version([("d1", "hash", 1)])
    assert retrieval_version([("d1", "hash", 2)]) != v1  # reindex
    assert retrieval_version([("d1", "hash", 1), ("d2", "h", 1)]) != v1  # new doc
    assert retrieval_version([]) != v1  # deletion


def test_ttl_expiry_and_bound():
    c = InMemoryCache(ttl_seconds=0, enabled=True)
    c.set("k", "v")
    time.sleep(0.01)
    assert c.get("k") is None
    small = InMemoryCache(max_entries=2, enabled=True)
    for i in range(5):
        small.set(str(i), "v")
    assert len(small._data) == 2
