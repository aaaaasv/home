from typing import Protocol

from src.modules.plant_care.domain import PlantPhotoReview, PlantPhotoReviewContext


class PhotoAnalyst(Protocol):
    """Looks at a new plant photo next to the previous one and says whether anything needs attention"""

    async def review_photo(self, context: PlantPhotoReviewContext) -> PlantPhotoReview | None:
        ...
