"""Unit tests for the prompt builder."""

from services.prompt_builder import build_system_message


def test_system_prompt_contains_verbatim_hint():
    prompt = build_system_message()

    # Verify key phrases from the original decoded course hint
    assert (
        "Do odczytywania i generowania plików JSON możesz użyć narzędzia 'jq'" in prompt
    )
    assert (
        "Niemal wszystkie potrzebne informacje można uzyskać także za pomocą polecenia 'grep'"
        in prompt
    )
    assert (
        'echo \'{"date":"2020-01-01","city":"nazwa miasta","longitude":10.000001,"latitude":12.345678}\''
        in prompt
    )
    assert (
        "UWAGA! Pamiętaj, że musisz zwrócić datę DZIEŃ PRZED znalezieniem ciała Rafała"
        in prompt
    )


def test_system_prompt_forbids_interpreters():
    prompt = build_system_message()
    assert "python" in prompt
    assert "zsh" in prompt
    assert "ABSOLUTELY FORBIDDEN" in prompt
    assert "ONLY pure shell commands" in prompt
