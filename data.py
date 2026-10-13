from __future__ import annotations

import argparse
import random
from dataclasses import dataclass

MAX_BITS = 200_000


def clean_bits(value: str) -> str:
    """Allow whitespace between bits, but reject any other character."""
    if not isinstance(value, str):
        raise ValueError("Binary input must be text.")
    bits = "".join(value.split())
    if not bits or set(bits) - {"0", "1"}:
        raise ValueError("Enter at least one bit using only 0, 1, and whitespace.")
    if len(bits) > MAX_BITS:
        raise ValueError(f"The maximum input length is {MAX_BITS:,} bits.")
    return bits


def random_bits(length: int, seed: int | None = None, zero_run: int = 0) -> str:
    """Generate uniform random bits and optionally insert a guaranteed zero run.

    A seed makes demonstrations reproducible. The inserted run can merge with
    surrounding zeros, so it guarantees at least, rather than exactly, its length.
    """
    if isinstance(length, bool) or not isinstance(length, int) or not 1 <= length <= MAX_BITS:
        raise ValueError(f"Length must be an integer from 1 to {MAX_BITS:,}.")
    if isinstance(zero_run, bool) or not isinstance(zero_run, int) or zero_run not in (0, 4, 8) or zero_run > length:
        raise ValueError("Zero run must be 0, 4, or 8 and cannot exceed the data length.")
    rng = random.Random(seed)
    bits = [str(rng.getrandbits(1)) for _ in range(length)]
    if zero_run:
        start = rng.randrange(length - zero_run + 1)
        bits[start:start + zero_run] = ["0"] * zero_run
    return "".join(bits)


@dataclass(frozen=True)
class Palindrome:
    start: int
    length: int
    text: str


def longest_palindrome(value: str) -> Palindrome:
    """Manacher's algorithm: O(n) time, O(n) memory; earliest tie wins.

    Both odd and even centres are processed. Radii already inside the rightmost
    known palindrome are reused, so only new boundaries require expansion.
    The result is a contiguous substring with a zero-based starting position.
    """
    bits = clean_bits(value)
    n = len(bits)
    best_start, best_length = 0, 1
    odd = [0] * n
    left, right = 0, -1
    for i in range(n):
        radius = 1 if i > right else min(odd[left + right - i], right - i + 1)
        while i - radius >= 0 and i + radius < n and bits[i - radius] == bits[i + radius]:
            radius += 1
        odd[i] = radius
        start, length = i - radius + 1, 2 * radius - 1
        if length > best_length or (length == best_length and start < best_start):
            best_start, best_length = start, length
        if i + radius - 1 > right:
            left, right = start, i + radius - 1

    even = [0] * n
    left, right = 0, -1
    for i in range(n):
        radius = 0 if i > right else min(even[left + right - i + 1], right - i + 1)
        while i - radius - 1 >= 0 and i + radius < n and bits[i - radius - 1] == bits[i + radius]:
            radius += 1
        even[i] = radius
        start, length = i - radius, 2 * radius
        if length > best_length or (length == best_length and start < best_start):
            best_start, best_length = start, length
        if i + radius - 1 > right:
            left, right = start, i + radius - 1
    return Palindrome(best_start, best_length, bits[best_start:best_start + best_length])


def longest_zero_run(value: str) -> int:
    """Find the largest contiguous zero run with one scan."""
    bits = clean_bits(value)
    longest = current = 0
    for bit in bits:
        current = current + 1 if bit == "0" else 0
        longest = max(longest, current)
    return longest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bits", help="Manual binary stream; whitespace is accepted")
    parser.add_argument("--length", type=int, default=64)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--zero-run", type=int, choices=(0, 4, 8), default=0)
    args = parser.parse_args()
    try:
        bits = clean_bits(args.bits) if args.bits is not None else random_bits(args.length, args.seed, args.zero_run)
        palindrome = longest_palindrome(bits)
    except ValueError as exc:
        parser.error(str(exc))
    print("Digital data:", bits)
    print("Longest palindrome:", palindrome.text)
    print("Length:", palindrome.length, "Start (zero-based):", palindrome.start)
    print("Longest zero run:", longest_zero_run(bits))


if __name__ == "__main__":
    main()



