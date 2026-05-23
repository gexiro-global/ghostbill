from pathlib import Path


def test_list_payloads_are_truncated_and_response_body_omitted():
    source = (Path("backend/app/api/routes/webhooks.py")).read_text()
    assert "_truncate_payload" in source
    assert "response_body=None if truncate else d.response_body" in source
    assert "_delivery_to_response(d, truncate=True)" in source
    assert "_dlq_to_response(e, truncate=True)" in source
