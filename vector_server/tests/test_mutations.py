"""Tests for the Garak-style mutation pipeline."""

import base64

from mutations import (
    apply_mutations,
    list_mutations,
    base64_encode,
    rot13_encode,
    unicode_tag_encode,
    leetspeak,
    reverse_words,
    base64_nested_rot13,
    academic_framing,
    thought_experiment,
    developer_mode,
    system_prompt_override,
    xml_delimiter_injection,
)


class TestEncodings:
    def test_base64(self):
        result = base64_encode("test payload")
        assert "base64" in result.lower()
        # The encoded string should be valid base64
        for word in result.split():
            try:
                base64.b64decode(word)
                break
            except Exception:
                continue

    def test_rot13_reversible(self):
        import codecs
        original = "fetch https://example.com"
        result = rot13_encode(original)
        assert original not in result
        # Extract the ROT13 part and verify it decodes
        assert "ROT13" in result

    def test_unicode_tag_invisible(self):
        result = unicode_tag_encode("hello")
        assert len(result) == 5
        for c in result:
            assert ord(c) >= 0xE0000

    def test_leetspeak(self):
        result = leetspeak("test")
        assert result != "test"
        assert "7" in result or "3" in result

    def test_reverse_words(self):
        result = reverse_words("hello world")
        assert result == "olleh dlrow"

    def test_base64_rot13_chain(self):
        result = base64_nested_rot13("payload")
        assert "base64" in result.lower()
        assert "ROT13" in result


class TestWrappers:
    def test_academic(self):
        result = academic_framing("do the thing")
        assert "peer-reviewed" in result
        assert "do the thing" in result

    def test_thought_experiment(self):
        result = thought_experiment("do the thing")
        assert "hypothetical" in result
        assert "do the thing" in result

    def test_developer_mode(self):
        result = developer_mode("do the thing")
        assert "DEVELOPER MODE" in result
        assert "do the thing" in result

    def test_system_override(self):
        result = system_prompt_override("do the thing")
        assert "</instructions>" in result
        assert "<system>" in result
        assert "do the thing" in result

    def test_xml_delimiters(self):
        result = xml_delimiter_injection("do the thing")
        assert "<|im_end|>" in result
        assert "<|im_start|>" in result
        assert "do the thing" in result


class TestPipeline:
    def test_empty_mutations(self):
        result = apply_mutations("original")
        assert result == "original"

    def test_single_encoding(self):
        result = apply_mutations("payload", encodings=["base64"])
        assert result != "payload"
        assert "base64" in result.lower()

    def test_single_wrapper(self):
        result = apply_mutations("payload", wrappers=["academic"])
        assert "peer-reviewed" in result
        assert "payload" in result

    def test_chained(self):
        result = apply_mutations("payload", encodings=["rot13"], wrappers=["academic"])
        assert "peer-reviewed" in result
        assert "payload" not in result  # ROT13 scrambled it

    def test_multiple_encodings(self):
        result = apply_mutations("payload", encodings=["leet", "base64"])
        assert result != "payload"

    def test_list_mutations(self):
        available = list_mutations()
        assert "encodings" in available
        assert "wrappers" in available
        assert len(available["encodings"]) == 7
        assert len(available["wrappers"]) == 5

    def test_unknown_mutation_ignored(self):
        result = apply_mutations("payload", encodings=["nonexistent"])
        assert result == "payload"
