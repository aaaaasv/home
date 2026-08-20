from src.common.domain import Actor
from src.modules.shopping.commands import (
    AddShoppingItemCommand,
    BuyShoppingItemCommand,
    PromoteShoppingItemCommand,
    RemoveShoppingItemCommand,
    RenameShoppingItemCommand,
    SetShoppingItemNoteCommand,
    SetShoppingItemPhotoCommand,
)
from src.modules.shopping.constants import ShoppingHorizon
from src.modules.shopping.use_cases.add_shopping_item import AddShoppingItemUseCase
from src.modules.shopping.use_cases.buy_shopping_item import BuyShoppingItemUseCase
from src.modules.shopping.use_cases.promote_shopping_item import PromoteShoppingItemUseCase
from src.modules.shopping.use_cases.remove_shopping_item import RemoveShoppingItemUseCase
from src.modules.shopping.use_cases.rename_shopping_item import RenameShoppingItemUseCase
from src.modules.shopping.use_cases.retrieve_shopping_list import RetrieveShoppingListUseCase
from src.modules.shopping.use_cases.set_shopping_item_note import SetShoppingItemNoteUseCase
from src.modules.shopping.use_cases.set_shopping_item_photo import SetShoppingItemPhotoUseCase
from src.tests.integration.base import BaseIntegrationTestCase

MARTA = Actor(telegram_user_id=1, display_name="Марта")
BOHDAN = Actor(telegram_user_id=2, display_name="Богдан")


class ShoppingListTestCase(BaseIntegrationTestCase):
    def add_item(self, actor: Actor = MARTA) -> AddShoppingItemUseCase:
        return AddShoppingItemUseCase(uow=self.uow, actor=actor)

    async def test_add_shopping_item_puts_it_in_the_next_trip_with_the_name_of_whoever_asked(self):
        command = AddShoppingItemCommand(name="олія")

        shopping_list = await self.add_item()(command)

        self.assertEqual([item.name for item in shopping_list.needed_now], ["олія"])
        self.assertEqual(shopping_list.needed_now[0].added_by_display_name, "Марта")
        self.assertEqual(shopping_list.wanted_later, [])

    async def test_add_shopping_item_for_later_keeps_it_out_of_the_next_trip(self):
        command = AddShoppingItemCommand(name="пилосос Dyson", horizon=ShoppingHorizon.LATER)

        shopping_list = await self.add_item()(command)

        self.assertEqual(shopping_list.needed_now, [])
        self.assertEqual([item.name for item in shopping_list.wanted_later], ["пилосос Dyson"])

    async def test_add_shopping_item_that_is_already_on_the_list_does_not_duplicate_it(self):
        await self.add_item()(AddShoppingItemCommand(name="олія"))

        shopping_list = await self.add_item(BOHDAN)(AddShoppingItemCommand(name="ОЛІЯ"))

        self.assertEqual([item.name for item in shopping_list.needed_now], ["олія"])
        self.assertEqual(shopping_list.needed_now[0].added_by_display_name, "Марта")

    async def test_add_shopping_item_keeps_the_order_in_which_the_family_asked(self):
        await self.add_item()(AddShoppingItemCommand(name="олія"))
        await self.add_item(BOHDAN)(AddShoppingItemCommand(name="кава"))

        shopping_list = await self.add_item()(AddShoppingItemCommand(name="хліб"))

        self.assertEqual([item.name for item in shopping_list.needed_now], ["олія", "кава", "хліб"])

    async def test_buy_shopping_item_takes_it_off_the_list(self):
        shopping_list = await self.add_item()(AddShoppingItemCommand(name="олія"))
        await self.add_item()(AddShoppingItemCommand(name="кава"))

        remaining = await BuyShoppingItemUseCase(uow=self.uow, actor=BOHDAN)(
            BuyShoppingItemCommand(item_id=shopping_list.needed_now[0].id)
        )

        self.assertEqual([item.name for item in remaining.needed_now], ["кава"])

    async def test_buy_shopping_item_twice_leaves_the_rest_of_the_list_alone(self):
        shopping_list = await self.add_item()(AddShoppingItemCommand(name="олія"))
        await self.add_item()(AddShoppingItemCommand(name="кава"))
        item_id = shopping_list.needed_now[0].id
        await BuyShoppingItemUseCase(uow=self.uow, actor=BOHDAN)(BuyShoppingItemCommand(item_id=item_id))

        remaining = await BuyShoppingItemUseCase(uow=self.uow, actor=MARTA)(BuyShoppingItemCommand(item_id=item_id))

        self.assertEqual([item.name for item in remaining.needed_now], ["кава"])

    async def test_buy_shopping_item_from_the_someday_section_needs_no_detour(self):
        shopping_list = await self.add_item()(
            AddShoppingItemCommand(name="пилосос Dyson", horizon=ShoppingHorizon.LATER)
        )

        remaining = await BuyShoppingItemUseCase(uow=self.uow, actor=BOHDAN)(
            BuyShoppingItemCommand(item_id=shopping_list.wanted_later[0].id)
        )

        self.assertTrue(remaining.is_empty)

    async def test_promote_shopping_item_moves_it_into_the_next_trip(self):
        shopping_list = await self.add_item()(
            AddShoppingItemCommand(name="пилосос Dyson", horizon=ShoppingHorizon.LATER)
        )

        promoted = await PromoteShoppingItemUseCase(uow=self.uow)(
            PromoteShoppingItemCommand(item_id=shopping_list.wanted_later[0].id)
        )

        self.assertEqual([item.name for item in promoted.needed_now], ["пилосос Dyson"])
        self.assertEqual(promoted.wanted_later, [])

    async def test_remove_shopping_item_drops_it_without_marking_it_bought(self):
        shopping_list = await self.add_item()(AddShoppingItemCommand(name="олія"))

        remaining = await RemoveShoppingItemUseCase(uow=self.uow)(
            RemoveShoppingItemCommand(item_id=shopping_list.needed_now[0].id)
        )

        self.assertTrue(remaining.is_empty)
        self.assertTrue((await RetrieveShoppingListUseCase(uow=self.uow)()).is_empty)

    async def test_retrieve_shopping_list_leaves_out_what_was_already_bought(self):
        shopping_list = await self.add_item()(AddShoppingItemCommand(name="олія"))
        await self.add_item()(AddShoppingItemCommand(name="пилосос", horizon=ShoppingHorizon.LATER))
        await BuyShoppingItemUseCase(uow=self.uow, actor=MARTA)(
            BuyShoppingItemCommand(item_id=shopping_list.needed_now[0].id)
        )

        remaining = await RetrieveShoppingListUseCase(uow=self.uow)()

        self.assertEqual(remaining.needed_now, [])
        self.assertEqual([item.name for item in remaining.wanted_later], ["пилосос"])

    async def test_buy_shopping_item_that_someone_already_removed_changes_nothing(self):
        shopping_list = await self.add_item()(AddShoppingItemCommand(name="олія"))
        item_id = shopping_list.needed_now[0].id
        await RemoveShoppingItemUseCase(uow=self.uow)(RemoveShoppingItemCommand(item_id=item_id))

        remaining = await BuyShoppingItemUseCase(uow=self.uow, actor=MARTA)(BuyShoppingItemCommand(item_id=item_id))

        self.assertTrue(remaining.is_empty)


class RenameShoppingItemTestCase(BaseIntegrationTestCase):
    async def test_rename_shopping_item_fixes_the_name_and_leaves_the_rest(self):
        await AddShoppingItemUseCase(uow=self.uow, actor=MARTA)(AddShoppingItemCommand(name="марта"))
        item_id = (await RetrieveShoppingListUseCase(uow=self.uow)()).needed_now[0].id

        shopping_list = await RenameShoppingItemUseCase(uow=self.uow)(
            RenameShoppingItemCommand(item_id=item_id, name="олія")
        )

        self.assertEqual([item.name for item in shopping_list.needed_now], ["олія"])
        self.assertEqual(shopping_list.needed_now[0].added_by_display_name, "Марта")

    async def test_rename_a_bought_item_changes_nothing(self):
        await AddShoppingItemUseCase(uow=self.uow, actor=MARTA)(AddShoppingItemCommand(name="олія"))
        item_id = (await RetrieveShoppingListUseCase(uow=self.uow)()).needed_now[0].id
        await BuyShoppingItemUseCase(uow=self.uow, actor=MARTA)(BuyShoppingItemCommand(item_id=item_id))

        shopping_list = await RenameShoppingItemUseCase(uow=self.uow)(
            RenameShoppingItemCommand(item_id=item_id, name="щось інше")
        )

        self.assertTrue(shopping_list.is_empty)


class ShoppingItemPhotoTestCase(BaseIntegrationTestCase):
    async def test_add_shopping_item_without_a_photo_has_none(self):
        shopping_list = await AddShoppingItemUseCase(uow=self.uow, actor=MARTA)(AddShoppingItemCommand(name="дриль"))

        self.assertIs(shopping_list.needed_now[0].has_photo, False)
        self.assertIsNone(shopping_list.needed_now[0].photo_telegram_file_id)

    async def test_add_shopping_item_with_a_photo_keeps_the_file_id(self):
        shopping_list = await AddShoppingItemUseCase(uow=self.uow, actor=MARTA)(
            AddShoppingItemCommand(name="дриль", photo_telegram_file_id="file-123")
        )

        self.assertIs(shopping_list.needed_now[0].has_photo, True)
        self.assertEqual(shopping_list.needed_now[0].photo_telegram_file_id, "file-123")

    async def test_add_a_photo_captioned_with_an_existing_name_attaches_to_that_item(self):
        await AddShoppingItemUseCase(uow=self.uow, actor=MARTA)(AddShoppingItemCommand(name="дриль"))

        shopping_list = await AddShoppingItemUseCase(uow=self.uow, actor=BOHDAN)(
            AddShoppingItemCommand(name="Дриль", photo_telegram_file_id="file-456")
        )

        self.assertEqual([item.name for item in shopping_list.needed_now], ["дриль"])
        self.assertEqual(shopping_list.needed_now[0].photo_telegram_file_id, "file-456")

    async def test_set_shopping_item_photo_attaches_to_an_item_added_by_text(self):
        await AddShoppingItemUseCase(uow=self.uow, actor=MARTA)(AddShoppingItemCommand(name="дриль"))
        item_id = (await RetrieveShoppingListUseCase(uow=self.uow)()).needed_now[0].id

        shopping_list = await SetShoppingItemPhotoUseCase(uow=self.uow)(
            SetShoppingItemPhotoCommand(item_id=item_id, photo_telegram_file_id="file-789")
        )

        self.assertEqual(shopping_list.needed_now[0].photo_telegram_file_id, "file-789")

    async def test_set_shopping_item_photo_on_a_missing_item_changes_nothing(self):
        shopping_list = await SetShoppingItemPhotoUseCase(uow=self.uow)(
            SetShoppingItemPhotoCommand(item_id=999, photo_telegram_file_id="file-000")
        )

        self.assertTrue(shopping_list.is_empty)


class SetShoppingItemNoteTestCase(BaseIntegrationTestCase):
    async def test_set_note_on_an_item_attaches_it_and_leaves_the_name(self):
        await AddShoppingItemUseCase(uow=self.uow, actor=MARTA)(AddShoppingItemCommand(name="шафка"))
        item_id = (await RetrieveShoppingListUseCase(uow=self.uow)()).needed_now[0].id

        shopping_list = await SetShoppingItemNoteUseCase(uow=self.uow)(
            SetShoppingItemNoteCommand(item_id=item_id, note="60x45x200, біла")
        )

        self.assertEqual([item.name for item in shopping_list.needed_now], ["шафка"])
        self.assertEqual(shopping_list.needed_now[0].note, "60x45x200, біла")
        self.assertTrue(shopping_list.needed_now[0].has_note)

    async def test_set_note_with_empty_text_clears_it(self):
        await AddShoppingItemUseCase(uow=self.uow, actor=MARTA)(AddShoppingItemCommand(name="шафка"))
        item_id = (await RetrieveShoppingListUseCase(uow=self.uow)()).needed_now[0].id
        await SetShoppingItemNoteUseCase(uow=self.uow)(SetShoppingItemNoteCommand(item_id=item_id, note="60x45x200"))

        shopping_list = await SetShoppingItemNoteUseCase(uow=self.uow)(
            SetShoppingItemNoteCommand(item_id=item_id, note="")
        )

        self.assertIsNone(shopping_list.needed_now[0].note)
        self.assertFalse(shopping_list.needed_now[0].has_note)

    async def test_set_note_on_a_bought_item_changes_nothing(self):
        await AddShoppingItemUseCase(uow=self.uow, actor=MARTA)(AddShoppingItemCommand(name="шафка"))
        item_id = (await RetrieveShoppingListUseCase(uow=self.uow)()).needed_now[0].id
        await BuyShoppingItemUseCase(uow=self.uow, actor=MARTA)(BuyShoppingItemCommand(item_id=item_id))

        shopping_list = await SetShoppingItemNoteUseCase(uow=self.uow)(
            SetShoppingItemNoteCommand(item_id=item_id, note="60x45x200")
        )

        self.assertEqual(shopping_list.needed_now, [])
