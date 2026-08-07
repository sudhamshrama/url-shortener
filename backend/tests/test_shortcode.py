"""Tests for short-code generation."""

from app.shortcode import ALPHABET, collision_probability, generate_code


def test_generated_code_has_requested_length() -> None:
    for length in (3, 7, 16):
        assert len(generate_code(length)) == length


def test_generated_code_is_base62() -> None:
    assert set(generate_code(200)) <= set(ALPHABET)


def test_codes_are_not_repeated() -> None:
    """Not a randomness proof — a smoke test that we are not returning a constant.

    A real statistical test belongs in a crypto library's suite, not here. What
    this catches is the plausible regression: someone replaces `secrets.choice`
    with a seeded generator and every pod starts issuing identical codes.
    """
    codes = {generate_code(7) for _ in range(1000)}
    assert len(codes) == 1000


def test_collision_probability_scales_with_existing_rows() -> None:
    assert collision_probability(7, 0) == 0
    assert collision_probability(7, 1_000_000) < 1e-5
    # Shorter codes saturate much faster — the argument for 7 over 4.
    assert collision_probability(4, 1_000_000) > collision_probability(7, 1_000_000)
