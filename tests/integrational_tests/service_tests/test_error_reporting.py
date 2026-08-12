"""
A failure that logs nothing is a failure nobody can act on.

The exceptions that matter most here carry no message: a download that
timed out, a connection reset mid-transfer and a truncated payload all
stringify to the empty string, which used to render as a log line
ending in a bare colon.
"""

import asyncio

import aiohttp
import pytest

from src.video_probe.video_prober import describe_exception

SILENT_EXCEPTIONS = [
    asyncio.TimeoutError(),
    TimeoutError(),
    ConnectionResetError(),
    aiohttp.ServerTimeoutError(),
    aiohttp.ClientPayloadError(),
    aiohttp.ClientOSError(),
]


@pytest.mark.parametrize("exc", SILENT_EXCEPTIONS, ids=lambda e: type(e).__name__)
def test_silent_exceptions_still_name_themselves(exc):
    described = describe_exception(exc)

    assert described.strip()
    assert type(exc).__name__ in described


def test_message_is_kept_when_there_is_one():
    described = describe_exception(aiohttp.ServerDisconnectedError())

    assert "ServerDisconnectedError" in described
    assert "Server disconnected" in described


def test_whitespace_only_message_is_treated_as_empty():
    described = describe_exception(ValueError("   \n  "))

    assert described == "ValueError"
