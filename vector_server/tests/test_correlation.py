"""Tests for correlation engine: token generation, registration, callback matching."""

from correlation import CorrelationEngine, generate_token, _zb32_encode, VECTOR_CODES
from models import Protocol, VectorType


class TestTokenGeneration:
    def test_token_length(self):
        token = generate_token()
        assert len(token) == 20  # 8 + 4 + 8

    def test_token_uniqueness(self):
        tokens = {generate_token() for _ in range(100)}
        assert len(tokens) == 100

    def test_token_dns_safe(self):
        for _ in range(50):
            token = generate_token()
            assert token == token.lower()
            assert all(c.isalnum() for c in token)

    def test_token_with_prefix(self):
        token = generate_token(session_prefix="abcdefgh", vector_code="shok")
        assert token.startswith("abcdefgh")
        assert token[8:12] == "shok"
        assert len(token) == 20

    def test_zb32_encode_deterministic(self):
        result = _zb32_encode(b"\x00")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_vector_codes_all_four_chars(self):
        for vtype, code in VECTOR_CODES.items():
            assert len(code) == 4, f"{vtype}: code {code!r} is not 4 chars"


class TestCorrelationEngine:
    def test_register_and_lookup(self):
        engine = CorrelationEngine()
        meta = engine.register_payload("sess1", VectorType.SETTINGS_HOOK, "test-case")
        assert meta.token
        assert meta.session_id == "sess1"
        assert meta.vector_type == VectorType.SETTINGS_HOOK

        found = engine.get_payload(meta.token)
        assert found is not None
        assert found.token == meta.token

    def test_callback_matching(self):
        engine = CorrelationEngine()
        meta = engine.register_payload("sess1", VectorType.HTML_HIDDEN)
        event = engine.on_callback(meta.token, Protocol.DNS, source_ip="1.2.3.4")
        assert event.payload is not None
        assert event.payload.token == meta.token
        assert event.callback.protocol == Protocol.DNS

    def test_callback_unmatched(self):
        engine = CorrelationEngine()
        event = engine.on_callback("nonexistent12345678", Protocol.HTTP)
        assert event.payload is None
        assert event.callback.token == "nonexistent12345678"

    def test_multiple_callbacks_per_token(self):
        engine = CorrelationEngine()
        meta = engine.register_payload("sess1", VectorType.PDF_INVISIBLE)
        engine.on_callback(meta.token, Protocol.DNS)
        engine.on_callback(meta.token, Protocol.HTTP)
        cbs = engine.get_callbacks(meta.token)
        assert len(cbs) == 2

    def test_get_all_events_filtered(self):
        engine = CorrelationEngine()
        m1 = engine.register_payload("sess-a", VectorType.SETTINGS_HOOK)
        m2 = engine.register_payload("sess-b", VectorType.MCP_CONFIG)
        engine.on_callback(m1.token, Protocol.DNS)
        engine.on_callback(m2.token, Protocol.HTTP)

        all_events = engine.get_all_events()
        assert len(all_events) == 2

        filtered = engine.get_all_events(session_id="sess-a")
        assert len(filtered) == 1
        assert filtered[0].payload.session_id == "sess-a"

    def test_stats(self):
        engine = CorrelationEngine()
        meta = engine.register_payload("s", VectorType.UNICODE_TAGS)
        engine.on_callback(meta.token, Protocol.DNS)
        engine.on_callback("unknown99999999999", Protocol.HTTP)

        stats = engine.stats()
        assert stats["registered_payloads"] == 1
        assert stats["total_callbacks"] == 2
        assert stats["matched_tokens"] == 1
        assert stats["unmatched_tokens"] == 1
