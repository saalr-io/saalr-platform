from saalr_api.strategies.stepup import issue_step_up, verify_step_up


class _FakeRedis:
    def __init__(self):
        self.store: dict[str, str] = {}

    async def set(self, key, value, ex=None):
        self.store[key] = value

    async def getdel(self, key):
        return self.store.pop(key, None)


async def test_issue_then_verify_consumes_single_use():
    r = _FakeRedis()
    token = await issue_step_up(r, "user-1")
    assert token
    assert await verify_step_up(r, "user-1", token) is True
    assert await verify_step_up(r, "user-1", token) is False  # single-use


async def test_blank_token_is_false():
    assert await verify_step_up(_FakeRedis(), "user-1", None) is False
    assert await verify_step_up(_FakeRedis(), "user-1", "") is False


async def test_token_is_scoped_to_user():
    r = _FakeRedis()
    token = await issue_step_up(r, "user-1")
    assert await verify_step_up(r, "user-2", token) is False
