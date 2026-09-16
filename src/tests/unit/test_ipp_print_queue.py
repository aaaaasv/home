import socket
import struct
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

from src.infrastructure.adapters.ipp_print_queue import (
    OPERATION_CANCEL_JOB,
    OPERATION_GET_JOB_ATTRIBUTES,
    OPERATION_PRINT_JOB,
    TAG_ENUM,
    TAG_INTEGER,
    IppAttribute,
    IppPrintQueue,
    decode_response,
    encode_request,
)

SUCCESS = 0x0000
NOT_POSSIBLE = 0x0404
JOB_PROCESSING = 5
JOB_COMPLETED = 9


def ipp_response(status: int, attributes: list[IppAttribute]) -> bytes:
    """A response is a request with a status in place of the operation, so the same encoder builds it."""
    return encode_request(status, 1, attributes)


class StubCupsHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802 — the name is BaseHTTPRequestHandler's
        body = self.rfile.read(int(self.headers["Content-Length"]))
        operation = struct.unpack(">H", body[2:4])[0]
        self.server.operations.append(operation)
        reply = self.server.replies[operation]
        self.send_response(200)
        self.send_header("Content-Type", "application/ipp")
        self.send_header("Content-Length", str(len(reply)))
        self.end_headers()
        self.wfile.write(reply)

    def log_message(self, format: str, *args) -> None:
        pass


class IppEncodingTestCase(unittest.TestCase):
    def test_decode_response_of_an_encoded_message_reads_back_every_attribute(self):
        body = ipp_response(
            SUCCESS,
            [IppAttribute(TAG_INTEGER, "job-id", 42), IppAttribute(TAG_ENUM, "job-state", JOB_COMPLETED)],
        )

        response = decode_response(body)

        self.assertEqual((response.status_code, response.attributes), (0, {"job-id": [42], "job-state": [9]}))

    def test_encode_request_carries_the_document_after_the_end_of_attributes(self):
        attributes = [IppAttribute(TAG_INTEGER, "job-id", 1)]

        body = encode_request(OPERATION_PRINT_JOB, 7, attributes, document=b"%PDF-1.4")

        self.assertTrue(body.endswith(b"\x03%PDF-1.4"))


class IppPrintQueueTestCase(unittest.IsolatedAsyncioTestCase):
    """Only a job the printer reports completed counts, because an accepted job is not a page on paper."""

    def setUp(self):
        self.server = HTTPServer(("127.0.0.1", 0), StubCupsHandler)
        self.server.operations = []
        self.server.replies = {
            OPERATION_PRINT_JOB: ipp_response(SUCCESS, [IppAttribute(TAG_INTEGER, "job-id", 3)]),
            OPERATION_GET_JOB_ATTRIBUTES: ipp_response(SUCCESS, [IppAttribute(TAG_ENUM, "job-state", JOB_COMPLETED)]),
            OPERATION_CANCEL_JOB: ipp_response(SUCCESS, []),
        }
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.queue = IppPrintQueue(
            queue_uri=f"ipp://127.0.0.1:{self.server.server_port}/printers/epson",
            requesting_user_name="bot",
            completion_timeout_seconds=0.5,
            poll_interval_seconds=0.05,
            request_timeout_seconds=2,
        )

    async def test_print_document_that_the_printer_completes_reports_it_printed(self):
        document = b"%PDF-1.4"

        printed = await self.queue.print_document(document, "Щотижневик № 1")

        self.assertTrue(printed)
        self.assertEqual(self.server.operations, [OPERATION_PRINT_JOB, OPERATION_GET_JOB_ATTRIBUTES])

    async def test_print_document_still_processing_when_the_wait_ends_is_cancelled_and_not_counted(self):
        self.server.replies[OPERATION_GET_JOB_ATTRIBUTES] = ipp_response(
            SUCCESS, [IppAttribute(TAG_ENUM, "job-state", JOB_PROCESSING)]
        )

        printed = await self.queue.print_document(b"%PDF-1.4", "Щотижневик № 1")

        self.assertFalse(printed)
        self.assertEqual(self.server.operations[-1], OPERATION_CANCEL_JOB)

    async def test_print_document_the_queue_refuses_reports_it_not_printed(self):
        self.server.replies[OPERATION_PRINT_JOB] = ipp_response(NOT_POSSIBLE, [])

        printed = await self.queue.print_document(b"%PDF-1.4", "Щотижневик № 1")

        self.assertFalse(printed)
        self.assertEqual(self.server.operations, [OPERATION_PRINT_JOB])

    async def test_print_document_with_the_queue_off_the_network_reports_it_not_printed(self):
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            closed_port = probe.getsockname()[1]
        queue = IppPrintQueue(queue_uri=f"ipp://127.0.0.1:{closed_port}/printers/epson", requesting_user_name="bot")

        printed = await queue.print_document(b"%PDF-1.4", "Щотижневик № 1")

        self.assertFalse(printed)
