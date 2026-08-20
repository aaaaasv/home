from src.tests.integration.base import BaseIntegrationTestCase


class PostedMessageRepositoryTestCase(BaseIntegrationTestCase):
    async def seed(self, kind: str, message_id: int) -> None:
        async with self.uow as uow:
            await uow.posted_messages.create({"kind": kind, "chat_id": 1, "message_id": message_id})

    async def list_kind(self, kind: str) -> list[int]:
        async with self.uow as uow:
            return [message.message_id for message in await uow.posted_messages.list_by_kind(kind)]

    async def test_list_by_kind_returns_every_message_of_that_kind(self):
        await self.seed("care_digest", 10)
        await self.seed("care_digest", 11)
        await self.seed("ac_card", 20)

        message_ids = await self.list_kind("care_digest")

        self.assertEqual(sorted(message_ids), [10, 11])

    async def test_delete_by_kind_removes_only_that_kind(self):
        await self.seed("care_digest", 10)
        await self.seed("ac_card", 20)

        async with self.uow as uow:
            await uow.posted_messages.delete_by_kind("care_digest")

        self.assertEqual(await self.list_kind("care_digest"), [])
        self.assertEqual(await self.list_kind("ac_card"), [20])
