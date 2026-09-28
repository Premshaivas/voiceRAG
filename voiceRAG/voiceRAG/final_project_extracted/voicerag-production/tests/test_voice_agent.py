from backend.voice_agent import ToolState, inline_session_update


def test_inline_session_registers_search_tool():
    message = inline_session_update()
    assert message["type"] == "session.update"
    assert message["session"]["tools"][0]["name"] == "search_lecture"


def test_tool_results_wait_until_reply_done():
    state = ToolState()
    state.add_call("call-1")
    state.set_result("call-1", {"sources": []})
    # The state does not emit by itself; the websocket bridge drains it on reply.done.
    assert state.pending["call-1"].result is not None
    drained = state.drain_results()
    assert drained == [{"type": "tool.result", "call_id": "call-1", "result": '{"sources": []}'}]
    assert state.pending == {}
