"""
A print queue over plain IPP: the CUPS container on the Pi, reached with nothing but an HTTP client.

IPP is a small binary format carried in an HTTP POST, and the bot needs three operations of it — submit a job,
ask how it is going, cancel it — so it is written out here rather than pulling a CUPS client into the image.
"""

import asyncio
import logging
import struct
import time
from dataclasses import dataclass, field
from urllib.parse import urlsplit, urlunsplit

import aiohttp

logger = logging.getLogger(__name__)

IPP_VERSION = b"\x01\x01"
OPERATION_PRINT_JOB = 0x0002
OPERATION_CANCEL_JOB = 0x0008
OPERATION_GET_JOB_ATTRIBUTES = 0x0009

GROUP_OPERATION = 0x01
GROUP_JOB = 0x02
END_OF_ATTRIBUTES = 0x03

TAG_INTEGER = 0x21
TAG_BOOLEAN = 0x22
TAG_ENUM = 0x23
TAG_NAME = 0x42
TAG_KEYWORD = 0x44
TAG_URI = 0x45
TAG_CHARSET = 0x47
TAG_LANGUAGE = 0x48
TAG_MIME_TYPE = 0x49

JOB_CANCELED = 7
JOB_ABORTED = 8
JOB_COMPLETED = 9
FINISHED_JOB_STATES = frozenset({JOB_CANCELED, JOB_ABORTED, JOB_COMPLETED})
# anything below 0x0100 is some flavour of successful-ok
LAST_SUCCESS_STATUS = 0x00FF


@dataclass
class IppAttribute:
    tag: int
    name: str
    value: str | int


@dataclass
class IppResponse:
    status_code: int
    attributes: dict[str, list[str | int | bool | bytes]] = field(default_factory=dict)

    @property
    def is_successful(self) -> bool:
        return self.status_code <= LAST_SUCCESS_STATUS

    def first(self, name: str) -> str | int | bool | bytes | None:
        values = self.attributes.get(name)
        return values[0] if values else None


def encode_request(
    operation: int,
    request_id: int,
    operation_attributes: list[IppAttribute],
    job_attributes: list[IppAttribute] = (),
    document: bytes = b"",
) -> bytes:
    body = bytearray(IPP_VERSION + struct.pack(">HI", operation, request_id))
    for group, attributes in ((GROUP_OPERATION, operation_attributes), (GROUP_JOB, job_attributes)):
        if not attributes:
            continue
        body.append(group)
        for attribute in attributes:
            if isinstance(attribute.value, int):
                value = struct.pack(">i", attribute.value)
            else:
                value = attribute.value.encode("utf-8")
            name = attribute.name.encode("utf-8")
            body += struct.pack(">BH", attribute.tag, len(name)) + name + struct.pack(">H", len(value)) + value
    body.append(END_OF_ATTRIBUTES)
    return bytes(body) + document


def decode_response(body: bytes) -> IppResponse:
    """Every attribute of every group, keyed by name; a nameless attribute is one more value of the one before."""
    status_code = struct.unpack(">H", body[2:4])[0]
    response = IppResponse(status_code=status_code)
    position, last_name = 8, None
    while position < len(body):
        tag = body[position]
        position += 1
        if tag == END_OF_ATTRIBUTES:
            break
        if tag < 0x10:
            continue
        name_length = struct.unpack(">H", body[position : position + 2])[0]
        position += 2
        name = body[position : position + name_length].decode("utf-8")
        position += name_length
        value_length = struct.unpack(">H", body[position : position + 2])[0]
        position += 2
        raw_value = body[position : position + value_length]
        position += value_length
        if name:
            last_name = name
        response.attributes.setdefault(last_name, []).append(_decode_value(tag, raw_value))
    return response


def _decode_value(tag: int, raw_value: bytes) -> str | int | bool | bytes:
    if tag in (TAG_INTEGER, TAG_ENUM) and len(raw_value) == 4:
        return struct.unpack(">i", raw_value)[0]
    if tag == TAG_BOOLEAN and len(raw_value) == 1:
        return raw_value != b"\x00"
    if 0x40 <= tag <= 0x4F or (0x30 <= tag <= 0x3F and tag != 0x31):
        return raw_value.decode("utf-8", errors="replace")
    return raw_value


class IppPrintQueue:
    """
    Submits a pdf to one queue and waits for the printer to report the job finished.

    a job is only counted as printed once its state reaches completed. one still pending when the wait runs out
    is cancelled, so a printer that was off does not wake up hours later and print a stale page on top of the
    next one.
    """

    def __init__(
        self,
        queue_uri: str,
        requesting_user_name: str,
        completion_timeout_seconds: float = 300.0,
        poll_interval_seconds: float = 5.0,
        request_timeout_seconds: float = 30.0,
    ):
        self.queue_uri = queue_uri
        self.http_url = _http_url_for(queue_uri)
        self.requesting_user_name = requesting_user_name
        self.completion_timeout_seconds = completion_timeout_seconds
        self.poll_interval_seconds = poll_interval_seconds
        self.request_timeout_seconds = request_timeout_seconds
        self.request_id = 0

    async def print_document(self, document: bytes, job_name: str) -> bool:
        timeout = aiohttp.ClientTimeout(total=self.request_timeout_seconds)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                job_id = await self._submit(session, document, job_name)
                if job_id is None:
                    return False
                state = await self._wait_until_finished(session, job_id)
                if state == JOB_COMPLETED:
                    return True
                if state not in FINISHED_JOB_STATES:
                    await self._send(session, OPERATION_CANCEL_JOB, self._job_attributes(job_id))
                logger.warning("Print job %s for '%s' ended in state %s", job_id, job_name, state)
                return False
        except (aiohttp.ClientError, asyncio.TimeoutError) as error:
            logger.warning("Print queue %s did not answer: %s", self.queue_uri, type(error).__name__)
            return False

    async def _submit(self, session: aiohttp.ClientSession, document: bytes, job_name: str) -> int | None:
        operation_attributes = self._base_attributes() + [
            IppAttribute(TAG_NAME, "requesting-user-name", self.requesting_user_name),
            IppAttribute(TAG_NAME, "job-name", job_name),
            IppAttribute(TAG_MIME_TYPE, "document-format", "application/pdf"),
        ]
        job_attributes = [
            IppAttribute(TAG_KEYWORD, "print-scaling", "none"),
            # cups gives up on its own too, so a job never outlives the wait by much even if this process dies
            IppAttribute(TAG_INTEGER, "job-cancel-after", int(self.completion_timeout_seconds)),
        ]
        response = await self._send(session, OPERATION_PRINT_JOB, operation_attributes, job_attributes, document)
        job_id = response.first("job-id")
        if not response.is_successful or not isinstance(job_id, int):
            logger.warning("Print queue refused '%s' with status 0x%04x", job_name, response.status_code)
            return None
        return job_id

    async def _wait_until_finished(self, session: aiohttp.ClientSession, job_id: int) -> int | None:
        deadline = time.monotonic() + self.completion_timeout_seconds
        state = None
        while time.monotonic() < deadline:
            attributes = self._job_attributes(job_id) + [IppAttribute(TAG_KEYWORD, "requested-attributes", "job-state")]
            response = await self._send(session, OPERATION_GET_JOB_ATTRIBUTES, attributes)
            job_state = response.first("job-state")
            state = job_state if isinstance(job_state, int) else state
            if state in FINISHED_JOB_STATES:
                return state
            await asyncio.sleep(self.poll_interval_seconds)
        return state

    async def _send(
        self,
        session: aiohttp.ClientSession,
        operation: int,
        operation_attributes: list[IppAttribute],
        job_attributes: list[IppAttribute] = (),
        document: bytes = b"",
    ) -> IppResponse:
        self.request_id += 1
        body = encode_request(operation, self.request_id, operation_attributes, job_attributes, document)
        async with session.post(self.http_url, data=body, headers={"Content-Type": "application/ipp"}) as response:
            response.raise_for_status()
            return decode_response(await response.read())

    def _base_attributes(self) -> list[IppAttribute]:
        return [
            IppAttribute(TAG_CHARSET, "attributes-charset", "utf-8"),
            IppAttribute(TAG_LANGUAGE, "attributes-natural-language", "en"),
            IppAttribute(TAG_URI, "printer-uri", self.queue_uri),
        ]

    def _job_attributes(self, job_id: int) -> list[IppAttribute]:
        return self._base_attributes() + [
            IppAttribute(TAG_INTEGER, "job-id", job_id),
            IppAttribute(TAG_NAME, "requesting-user-name", self.requesting_user_name),
        ]


def _http_url_for(queue_uri: str) -> str:
    parts = urlsplit(queue_uri)
    netloc = parts.netloc if parts.port else f"{parts.hostname}:631"
    return urlunsplit(("http", netloc, parts.path, "", ""))
