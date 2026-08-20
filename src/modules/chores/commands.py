from datetime import date

from pydantic import BaseModel, Field

from src.modules.chores.constants import CHORE_NAME_MAX_LENGTH


class AddChoreCommand(BaseModel):
    name: str = Field(min_length=1, max_length=CHORE_NAME_MAX_LENGTH)
    due_on: date | None = None
    assignee_telegram_user_id: int | None = None
    assignee_display_name: str | None = None


class RenameChoreCommand(BaseModel):
    chore_id: int
    name: str = Field(min_length=1, max_length=CHORE_NAME_MAX_LENGTH)


class SetChoreAssigneeCommand(BaseModel):
    chore_id: int
    assignee_telegram_user_id: int | None = None
    assignee_display_name: str | None = None


class SetChoreDeadlineCommand(BaseModel):
    chore_id: int
    due_on: date | None = None


class CompleteChoreCommand(BaseModel):
    chore_id: int


class RemoveChoreCommand(BaseModel):
    chore_id: int
