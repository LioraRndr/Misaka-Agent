"""Transcripts written before the pi 0.86-0.87 port carry ``addedToolNames`` on toolResult
messages, a field that port removed from the model. pi has no runtime validation and reads
such transcripts unchanged; the strict model here refused the whole session at load
(2026-09-23: the 20 September Last Order transcript, 345 occurrences, a pane that crashed at
every panel start). The one retired key is dropped from the wire copy; any other unknown key
still fails, so the validation keeps catching real shape bugs."""
import pytest
from pydantic import ValidationError

from misaka.agent.harness.messages import convert_to_llm
from misaka.core.session_manager import _copy_context_messages


def _tool_result(**extra):
    return {"role": "toolResult", "toolCallId": "call_1", "toolName": "read",
            "content": [{"type": "text", "text": "ok"}], "isError": False, "timestamp": 1, **extra}


def test_legacy_added_tool_names_is_dropped_before_validation():
    converted = convert_to_llm([_tool_result(addedToolNames=None), _tool_result(addedToolNames=["x"])])
    assert [message.role for message in converted] == ["toolResult", "toolResult"]
    assert all(not hasattr(message, "addedToolNames") for message in converted)


def test_compaction_snapshot_with_the_legacy_key_loads_and_keeps_its_native_shape():
    original = [{"role": "user", "content": [{"type": "text", "text": "q"}], "timestamp": 1},
                _tool_result(addedToolNames=None)]
    snapshot = _copy_context_messages(original)
    assert "addedToolNames" in snapshot[1]         # the stored snapshot is untouched
    assert "addedToolNames" in original[1]         # and so is the caller's copy


def test_other_unknown_keys_still_fail():
    with pytest.raises(ValidationError, match="bogus"):
        convert_to_llm([_tool_result(bogus=1)])
