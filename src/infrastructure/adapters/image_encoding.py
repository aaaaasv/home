import base64


def read_image_bytes(path: str) -> bytes:
    """Reads a photo off disk as the raw bytes a multimodal request inlines."""
    with open(path, "rb") as photo:
        return photo.read()


def read_image_base64(path: str) -> str:
    """Reads a photo off disk as the base64 every vision API wants it in."""
    return base64.standard_b64encode(read_image_bytes(path)).decode("utf-8")
