import asyncio
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.model import ModelFailure


class FakeModel:
    def __init__(self, decisions):
        self.decisions = list(decisions)
        self.calls = []

    async def decide(self, messages, knowledge, navigation):
        self.calls.append((messages, knowledge, navigation))
        result = self.decisions.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    async def health(self):
        return {"status": "ready", "detail": "测试模型"}


def decision(action, service_id=None, fact_ids=None, reply=""):
    return {
        "action": action,
        "service_id": service_id,
        "fact_ids": fact_ids or [],
        "reply": reply,
    }


def client_for(*decisions):
    model = FakeModel(decisions)
    return TestClient(create_app(model=model)), model


def start(client):
    result = client.post("/api/v1/sessions")
    assert result.status_code == 200
    return result.json()["session_id"]


def message(client, session_id, text):
    return client.post(f"/api/v1/sessions/{session_id}/messages", json={"text": text})


def event(client, session_id, name):
    return client.post(f"/api/v1/sessions/{session_id}/events", json={"event": name})


@pytest.mark.parametrize(
    "service,led,location",
    [
        ("calligraphy", 4, "活动室"), ("taichi", 4, "活动室"),
        ("bloodPressure", 3, "卫生站"), ("socialSecurity", 5, "服务大厅"),
        ("elderAllowance", 5, "服务大厅"), ("meal", 2, "社区中心"),
        ("repair", 6, "便民驿站"),
    ],
)
def test_services_use_authoritative_destination_and_button_boundaries(service, led, location):
    client, model = client_for(decision("start", service, [f"{service}.schedule"]))
    session = start(client)
    response = message(client, session, "我想咨询这个服务")
    assert response.status_code == 200
    result = response.json()
    assert (result["device"]["service_id"], result["device"]["led"], result["device"]["location"]) == (service, led, location)
    assert result["device"]["step_index"] == 0
    assert result["sources"][0]["id"] == f"{service}.schedule"
    assert any(item["line"] == f"LED|{led}" for item in result["protocol"])
    assert event(client, session, "BUTTON_A").json()["device"]["step_index"] == 0
    total = result["device"]["step_count"]
    for index in range(1, total):
        assert event(client, session, "BUTTON_B").json()["device"]["step_index"] == index
    end = event(client, session, "BUTTON_B").json()["device"]
    assert end["mode"] == "idle" and end["led"] == 0
    assert len(model.calls) == 1


def test_followup_preserves_navigation_and_passes_real_history_and_all_knowledge():
    client, model = client_for(
        decision("start", "calligraphy", ["calligraphy.location"]),
        decision("answer", "calligraphy", ["calligraphy.schedule"], "编造的时间不应显示"),
    )
    session = start(client)
    message(client, session, "我想学写字")
    event(client, session, "BUTTON_B")
    result = message(client, session, "刚才那个班什么时候上课？").json()
    assert result["device"]["step_index"] == 1
    assert result["device"]["led"] == 4
    assert result["sources"][0]["value"] in result["reply"]
    assert "编造的时间" not in result["reply"]
    previous_messages, knowledge, navigation = model.calls[1]
    assert any(item["content"] == "我想学写字" for item in previous_messages)
    assert previous_messages[-1]["content"] == "刚才那个班什么时候上课？"
    assert len(knowledge["services"]) == 7
    assert navigation["step_index"] == 1


def test_ambiguous_or_unsupported_request_clears_old_led_but_retains_chat():
    client, model = client_for(
        decision("start", "meal"),
        decision("clarify", reply="您想先咨询助餐还是水电报修？"),
        decision("unknown", reply="不应编造护照政策"),
    )
    session = start(client)
    message(client, session, "助餐在哪里")
    result = message(client, session, "我想咨询助餐和报修").json()
    assert result["device"]["led"] == 0 and result["device"]["mode"] == "clarify"
    assert "助餐" in result["reply"]
    result = message(client, session, "我还想办护照").json()
    assert result["device"]["led"] == 0
    assert "工作人员" in result["reply"]
    assert "编造" not in result["reply"]
    assert any(entry["content"] == "助餐在哪里" for entry in model.calls[-1][0])


def test_invalid_facts_retry_once_then_preserve_current_navigation_on_error():
    client, model = client_for(
        decision("start", "meal"),
        decision("answer", "meal", ["repair.schedule"]),
        decision("answer", "meal", ["does-not-exist"]),
    )
    session = start(client)
    message(client, session, "助餐")
    result = message(client, session, "什么时候开放")
    assert result.status_code == 502
    assert result.json()["device"]["led"] == 2
    assert result.json()["error"]
    assert len(model.calls) == 3
    assert event(client, session, "BUTTON_B").json()["device"]["step_index"] == 1


def test_connection_failure_is_visible_and_does_not_generate_a_preset_answer():
    client, model = client_for(ModelFailure("模型连接失败"))
    session = start(client)
    result = message(client, session, "书法班")
    assert result.status_code == 502
    assert "模型连接失败" in result.json()["error"]
    assert result.json()["device"]["led"] == 0
    assert result.json()["reply"] == ""
    assert len(model.calls) == 1


def test_text_navigation_commands_and_new_session_are_independent():
    client, _ = client_for(
        decision("start", "taichi"), decision("next"), decision("repeat"), decision("end")
    )
    old = start(client)
    message(client, old, "我要打太极")
    assert message(client, old, "下一步").json()["device"]["step_index"] == 1
    assert message(client, old, "重说一遍").json()["device"]["step_index"] == 1
    assert message(client, old, "结束导航").json()["device"]["led"] == 0
    fresh = client.post("/api/v1/sessions", json={"previous_session_id": old}).json()["session_id"]
    assert fresh != old
    assert client.get(f"/api/v1/sessions/{fresh}").json()["device"]["mode"] == "idle"
    assert client.get(f"/api/v1/sessions/{old}").status_code == 404


def test_a_different_service_starts_at_first_step_and_answer_uses_its_own_facts():
    client, _ = client_for(
        decision("start", "calligraphy"),
        decision("answer", "repair", ["repair.materials"]),
    )
    session = start(client)
    message(client, session, "我想报名书法班")
    event(client, session, "BUTTON_B")
    result = message(client, session, "另外家里水管坏了要准备什么？").json()
    assert result["device"]["service_id"] == "repair"
    assert result["device"]["led"] == 6 and result["device"]["step_index"] == 0
    assert result["sources"][0]["id"] == "repair.materials"


def test_malformed_output_is_corrected_once_before_navigation_changes():
    client, model = client_for(
        {"action": "start", "service_id": "not-a-service"},
        decision("start", "bloodPressure", ["bloodPressure.location"]),
    )
    session = start(client)
    result = message(client, session, "哪里能测血压？")
    assert result.status_code == 200
    assert result.json()["device"]["led"] == 3
    assert len(model.calls) == 2
    assert "重新输出 JSON" in model.calls[-1][0][-1]["content"]


def test_protocol_speech_matches_the_spoken_message_and_step():
    client, _ = client_for(decision("start", "calligraphy", ["calligraphy.schedule"]))
    session = start(client)
    result = message(client, session, "我想参加书法课").json()
    assert result["reply"] in result["speech"]
    assert result["device"]["screen"]["body"] in result["speech"]
    assert any(item["line"] == "SPEAK|" + result["speech"] for item in result["protocol"])
    after_button = event(client, session, "BUTTON_B").json()
    assert after_button["speech"] == after_button["device"]["screen"]["body"]


def test_answer_without_a_source_requests_confirmation_and_turns_off_the_old_led():
    client, _ = client_for(decision("start", "meal"), decision("answer", "meal", []))
    session = start(client)
    message(client, session, "我想咨询助餐")
    result = message(client, session, "是否有某种未记录的补贴？").json()
    assert "工作人员" in result["reply"]
    assert result["device"]["mode"] == "clarify" and result["device"]["led"] == 0


def test_new_session_discards_an_old_request_while_concurrent_events_are_rejected():
    async def scenario():
        started, release = asyncio.Event(), asyncio.Event()

        class WaitingModel(FakeModel):
            async def decide(self, messages, knowledge, navigation):
                started.set()
                await release.wait()
                return decision("start", "calligraphy")

        app = create_app(model=WaitingModel([]))
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://local") as client:
            old = (await client.post("/api/v1/sessions")).json()["session_id"]
            pending = asyncio.create_task(client.post(f"/api/v1/sessions/{old}/messages", json={"text": "书法班"}))
            await started.wait()
            assert (await client.post(f"/api/v1/sessions/{old}/events", json={"event": "BUTTON_B"})).status_code == 409
            fresh = (await client.post("/api/v1/sessions", json={"previous_session_id": old})).json()["session_id"]
            release.set()
            assert (await pending).json()["device"]["led"] == 4
            assert (await client.get(f"/api/v1/sessions/{old}")).status_code == 404
            assert (await client.get(f"/api/v1/sessions/{fresh}")).json()["device"]["led"] == 0

    asyncio.run(scenario())


def test_html_and_configuration_do_not_expose_cloud_credentials():
    client, _ = client_for()
    response = client.get("/")
    assert response.status_code == 200
    assert "CLOUD_API_KEY" not in response.text
    assert "离线模拟演示" in response.text
    assert client.get("/api/v1/health").status_code == 200
