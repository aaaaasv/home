from src.common.domain import DomainModel
from src.infrastructure.db.models import FamilyMember as FamilyMemberRow


class FamilyMember(DomainModel):
    telegram_user_id: int
    display_name: str

    @classmethod
    def from_row(cls, member: FamilyMemberRow) -> "FamilyMember":
        return cls(telegram_user_id=member.telegram_user_id, display_name=member.display_name)

    @property
    def first_name(self) -> str:
        # the short name people actually type and read — «Марта», not «Марта Пупкіна»
        parts = self.display_name.split()
        return parts[0] if parts else self.display_name
