"""Line coding with explicit voltage conventions and linear-time encoders.

NRZ-L: 0 = +1, 1 = -1.
NRZ-I: initial level -1; 1 changes the level at the bit boundary.
AMI: initial previous pulse -1, so the first data 1 is +1.
Manchester: 0 = (+1, -1), 1 = (-1, +1).
Differential Manchester: initial level +1; 0 changes at the boundary,
1 does not, and every bit changes in the middle.

An encoded signal stores voltage samples, one or two equal slots per bit.
"""

from dataclasses import dataclass
from typing import Callable, Sequence


@dataclass
class EncodedSignal:
    """Uniform slots of voltage, plus timing and method metadata."""

    levels: list[int]
    slots_per_bit: int
    scheme: str
    scrambling: str
    bit_count: int


def _validate_bits(bits: str) -> None:
    if not isinstance(bits, str) or not bits:
        raise ValueError("Enter a nonempty string of 0s and 1s.")
    if any(bit not in "01" for bit in bits):
        raise ValueError("Binary input must contain only 0s and 1s.")


def _method_name(value: str, choices: tuple[str, ...], label: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be one of: {', '.join(choices)}.")
    names = {name.casefold(): name for name in choices}
    name = names.get(value.strip().casefold())
    if name is None:
        raise ValueError(f"Choose {label} from: {', '.join(choices)}.")
    return name


def _nrz_l(bits: str) -> list[int]:
    return [1 if bit == "0" else -1 for bit in bits]


def _nrz_i(bits: str) -> list[int]:
    level = -1
    result = []
    for bit in bits:
        if bit == "1":
            level = -level
        result.append(level)
    return result


def _ami(bits: str) -> list[int]:
    last_pulse = -1
    result = []
    for bit in bits:
        if bit == "1":
            last_pulse = -last_pulse
            result.append(last_pulse)
        else:
            result.append(0)
    return result


def _manchester(bits: str) -> list[int]:
    result = []
    for bit in bits:
        first = 1 if bit == "0" else -1
        result.extend((first, -first))
    return result


def _differential_manchester(bits: str) -> list[int]:
    previous = 1
    result = []
    for bit in bits:
        first = -previous if bit == "0" else previous
        second = -first
        result.extend((first, second))
        previous = second
    return result


def _b8zs(bits: str) -> list[int]:
    """Substitute 000VB0VB; V repeats polarity, B alternates it."""
    last_pulse = -1
    result = []
    index = 0
    while index < len(bits):
        if bits.startswith("00000000", index):
            result.extend((0, 0, 0, last_pulse, -last_pulse,
                           0, -last_pulse, last_pulse))
            # The last substitution pulse equals the preceding pulse.
            index += 8
        elif bits[index] == "1":
            last_pulse = -last_pulse
            result.append(last_pulse)
            index += 1
        else:
            result.append(0)
            index += 1
    return result


def _hdb3(bits: str) -> list[int]:
    """Substitute 000V for odd mark parity, B00V for even parity.

    Parity starts at zero and resets after each substitution. In B00V,
    B and V have the same polarity, opposite the preceding pulse.
    """
    last_pulse = -1
    marks_since_violation = 0
    result = []
    index = 0
    while index < len(bits):
        if bits.startswith("0000", index):
            if marks_since_violation % 2:
                result.extend((0, 0, 0, last_pulse))
            else:
                last_pulse = -last_pulse
                result.extend((last_pulse, 0, 0, last_pulse))
            marks_since_violation = 0
            index += 4
        elif bits[index] == "1":
            last_pulse = -last_pulse
            result.append(last_pulse)
            marks_since_violation += 1
            index += 1
        else:
            result.append(0)
            index += 1
    return result


SCHEMES = ('NRZ-L', 'NRZ-I', 'Manchester', 'Differential Manchester', 'AMI')
SCRAMBLING = ('None', 'B8ZS', 'HDB3')

_ENCODERS: dict[str, tuple[Callable[[str], list[int]], int]] = {
    'NRZ-L': (_nrz_l, 1),
    'NRZ-I': (_nrz_i, 1),
    'Manchester': (_manchester, 2),
    'Differential Manchester': (_differential_manchester, 2),
    'AMI': (_ami, 1),
}
_SCRAMBLERS: dict[str, Callable[[str], list[int]]] = {"B8ZS": _b8zs, "HDB3": _hdb3}


def encode(bits: str, scheme: str, scrambling: str = "None") -> EncodedSignal:
    """Encode any nonempty binary string in O(n) time and O(n) space."""
    _validate_bits(bits)
    scheme = _method_name(scheme, SCHEMES, "line coding")
    scrambling = _method_name(scrambling, SCRAMBLING, "scrambling")
    if scrambling != "None" and scheme != "AMI":
        raise ValueError("B8ZS and HDB3 scrambling are available only for AMI.")
    encoder, slots = _ENCODERS[scheme]
    if scrambling != "None":
        encoder = _SCRAMBLERS[scrambling]
    return EncodedSignal(encoder(bits), slots, scheme, scrambling, len(bits))


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bits", nargs="?", default="1011000000001001")
    parser.add_argument("--scheme", choices=SCHEMES, default="AMI")
    parser.add_argument("--scrambling", choices=SCRAMBLING, default="None")

    arguments = parser.parse_args()
    try:
        signal = encode(arguments.bits, arguments.scheme, arguments.scrambling)
    except ValueError as error:
        parser.error(str(error))
    print(f"Input: {arguments.bits}")
    print(f"Method: {signal.scheme}; scrambling: {signal.scrambling}")
    print(f"Slots per bit: {signal.slots_per_bit}")
    print("Voltage slots:", " ".join(f"{level:+d}" for level in signal.levels))



if __name__ == "__main__":
    main()
