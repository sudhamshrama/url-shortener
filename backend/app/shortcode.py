"""Short code generation.

Codes are random rather than sequential. A sequential base62 counter is denser
and shorter, but it makes every link on the service enumerable — anyone can
walk 1, 2, 3 and read every URL that has ever been shortened. Random codes trade
a little density for the property that guessing one is infeasible.

`secrets` rather than `random` because `random` is a Mersenne Twister seeded from
predictable state: observing a handful of outputs is enough to predict the rest.
That distinction is a common interview question and a real CVE class.
"""

import secrets
import string

# Base62. No ambiguity stripping (0/O, 1/l) because these codes are copied and
# pasted, not read aloud or typed from paper.
ALPHABET = string.ascii_letters + string.digits


def generate_code(length: int) -> str:
    """Return a cryptographically random base62 string."""
    return "".join(secrets.choice(ALPHABET) for _ in range(length))


def collision_probability(length: int, existing: int) -> float:
    """Approximate birthday-collision probability, for capacity planning.

    Useful for answering "when does 7 characters stop being enough?" — at 62**7
    (~3.5e12) possible codes, a million existing links collide on a given
    insert roughly 3 times in ten million. The retry loop in the route handles
    the rest, so this is informational rather than load-bearing.
    """
    space: int = len(ALPHABET) ** length
    return existing / space
