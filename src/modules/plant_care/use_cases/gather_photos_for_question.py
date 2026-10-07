from src.common.use_case import BaseUseCase
from src.modules.plant_care.domain import QuestionPhoto

# the newest frame and the one before it, so «що змінилось» has something to compare against
PHOTOS_PER_PLANT = 2
# a question that happens to name half the collection must not send half the collection: the free tier is
# counted in requests per day, and a refused request answers nobody
PLANTS_PER_QUESTION = 2


class GatherPhotosForQuestionUseCase(BaseUseCase):
    """
    The stored photos of the plants a question actually names.

    a typed question used to carry no image at all, so «що з листям Бубика» was answered from the written record
    while the model was free to imply it had looked at the pot — which is worse than saying it cannot see it
    """

    async def __call__(self, question: str) -> list[QuestionPhoto]:
        if not question:
            return []

        asked = question.casefold()
        gathered: list[QuestionPhoto] = []
        async with self.uow as uow:
            named = [plant for plant in await uow.plants.list_active() if plant.name.casefold() in asked]
            for plant in named[:PLANTS_PER_QUESTION]:
                photos = [photo for photo in await uow.plant_photos.list_by_plant_id(plant.id) if photo.local_path]
                gathered.extend(
                    QuestionPhoto(plant_name=plant.name, taken_at=photo.taken_at, local_path=photo.local_path)
                    for photo in photos[-PHOTOS_PER_PLANT:]
                )
        return gathered
