from src.common.domain import DomainModel


class ModelSpend(DomainModel):
    """What the paid models have cost over a period, against what they were allowed."""

    spent_micro_usd: int
    allowed_micro_usd: int

    @property
    def is_spent(self) -> bool:
        return self.spent_micro_usd >= self.allowed_micro_usd

    @property
    def spent_usd(self) -> float:
        return self.spent_micro_usd / 1_000_000

    @property
    def allowed_usd(self) -> float:
        return self.allowed_micro_usd / 1_000_000
