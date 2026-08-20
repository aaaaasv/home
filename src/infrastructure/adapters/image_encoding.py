import base64


def read_image_base64(path: str) -> str:
    """Reads a photo off disk as the base64 every vision API wants it in."""
    with open(path, "rb") as photo:
        return base64.standard_b64encode(photo.read()).decode("utf-8")
