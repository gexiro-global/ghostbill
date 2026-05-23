from pathlib import Path

SOURCE = Path("backend/app/services/monero_rpc.py")


def test_retryable_rpc_error_codes_are_retried():
    source = SOURCE.read_text()
    call_start = source.index("async def _call")
    call_body = source[call_start : source.index("async def get_height")]
    assert "RETRYABLE_RPC_ERRORS" in source
    assert "except MoneroRPCError as exc" in call_body
    assert "if exc.code not in RETRYABLE_RPC_ERRORS" in call_body
    assert "await asyncio.sleep(wait)" in call_body
