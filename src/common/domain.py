from pydantic import BaseModel, ConfigDict


class DomainModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Actor(DomainModel):
    telegram_user_id: int
    display_name: str
