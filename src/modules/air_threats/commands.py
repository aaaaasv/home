from pydantic import BaseModel, Field


class TrackAirThreatsCommand(BaseModel):
    """
    Where we are, and how much warning is worth a message — in minutes, not kilometres.

    a radius in kilometres means a different amount of time depending on what is flying: 70 km is twenty-three
    minutes for a piston Shahed and forty-one seconds for something at Mach 5. the person needs time, because
    what they do with the warning — put shoes on and leave — costs minutes.
    """

    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    # basically here: close enough to matter whatever it is and whichever way it points
    overhead_kilometres: float = Field(gt=0)
    # and further out, only what is aimed at us, and only once it is this few minutes away
    warning_minutes: float = Field(gt=0)
    approach_degrees: float = Field(gt=0, le=180)
    # the map gives a course but never a speed, so the speed comes from what the thing is
    speeds_by_kind: dict[str, float]
    default_speed: float = Field(gt=0)
