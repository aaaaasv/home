from src.bot.handlers.weather.board import WeatherDigestBoard
from src.infrastructure.db.uow import UnitOfWork
from src.tests.integration.base import KYIV, BaseIntegrationTestCase


class StubWeatherProvider:
    def __init__(self, fetch_result, recent_result):
        self._fetch_result = fetch_result
        self._recent_result = recent_result
        self.fetch_calls = 0
        self.recent_calls = 0

    async def fetch(self):
        self.fetch_calls += 1
        return self._fetch_result

    def recent(self):
        self.recent_calls += 1
        return self._recent_result


class WeatherDigestFallbackTestCase(BaseIntegrationTestCase):
    def uow_factory(self) -> UnitOfWork:
        return UnitOfWork(session_factory=self.session_factory)

    def build_board(self, provider: StubWeatherProvider) -> WeatherDigestBoard:
        return WeatherDigestBoard(
            bot=None,
            chat_id=0,
            weather_topic=None,
            uow_factory=self.uow_factory,
            weather_provider=provider,
            timezone=KYIV,
        )

    async def test_compose_falls_back_to_the_cached_reading_when_the_live_fetch_fails(self):
        cached = object()
        provider = StubWeatherProvider(fetch_result=None, recent_result=cached)

        _, outdoor, _ = await self.build_board(provider)._compose()

        self.assertIs(outdoor, cached)
        self.assertEqual((provider.fetch_calls, provider.recent_calls), (1, 1))

    async def test_compose_uses_the_live_fetch_and_skips_the_cache_when_it_succeeds(self):
        live = object()
        provider = StubWeatherProvider(fetch_result=live, recent_result=object())

        _, outdoor, _ = await self.build_board(provider)._compose()

        self.assertIs(outdoor, live)
        self.assertEqual((provider.fetch_calls, provider.recent_calls), (1, 0))
