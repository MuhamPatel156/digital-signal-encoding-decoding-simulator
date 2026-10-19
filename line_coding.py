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


def _decode_nrz_l(levels: list[int]) -> str:
    return "".join("0" if level == 1 else "1" for level in levels)


def _decode_nrz_i(levels: list[int]) -> str:
    previous = -1
    bits = []
    for level in levels:
        bits.append("1" if level != previous else "0")
        previous = level
    return "".join(bits)


def _decode_manchester(levels: list[int]) -> str:
    bits = []
    for index in range(0, len(levels), 2):
        first, second = levels[index:index + 2]
        if second != -first:
            raise ValueError(f"Missing middle transition at bit {index // 2 + 1}.")
        bits.append("0" if first == 1 else "1")
    return "".join(bits)


def _decode_differential_manchester(levels: list[int]) -> str:
    previous = 1
    bits = []
    for index in range(0, len(levels), 2):
        first, second = levels[index:index + 2]
        if second != -first:
            raise ValueError(f"Missing middle transition at bit {index // 2 + 1}.")
        bits.append("1" if first == previous else "0")
        previous = second
    return "".join(bits)


def _decode_ami_family(levels: list[int], scrambling: str) -> str:
    last_pulse = -1
    marks_since_violation = 0
    bits = []
    index = 0
    while index < len(levels):
        if scrambling == "B8ZS":
            pattern = [0, 0, 0, last_pulse, -last_pulse,
                       0, -last_pulse, last_pulse]
            if levels[index:index + 8] == pattern:
                bits.extend("00000000")
                index += 8
                continue
        elif scrambling == "HDB3":
            if marks_since_violation % 2:
                pattern = [0, 0, 0, last_pulse]
            else:
                pattern = [-last_pulse, 0, 0, -last_pulse]
            if levels[index:index + 4] == pattern:
                bits.extend("0000")
                last_pulse = pattern[-1]
                marks_since_violation = 0
                index += 4
                continue
        level = levels[index]
        if level == 0:
            bits.append("0")
        elif level == -last_pulse:
            bits.append("1")
            last_pulse = level
            marks_since_violation += 1
        else:
            raise ValueError(
                f"Unexpected AMI polarity violation at bit {index + 1}; "
                "check the signal and scrambling method."
            )
        index += 1
    return "".join(bits)


_DECODERS: dict[str, Callable[[list[int]], str]] = {
    "NRZ-L": _decode_nrz_l,
    "NRZ-I": _decode_nrz_i,
    "Manchester": _decode_manchester,
    "Differential Manchester": _decode_differential_manchester,
}


def decode_signal(
    levels: Sequence[int],
    scheme: str,
    slots_per_bit: int | None = None,
    scrambling: str = "None",
) -> str:
    """Recover bits from voltage slots, without access to original bits.

    Bit alignment and the initial signal state follow this module's
    documented conventions. This is ideal waveform-sample decoding; it
    does not perform image recognition or recover clock timing from noise.
    An invalid line-code pattern raises ValueError. A valid pattern can
    still represent different data if transmission errors change it.
    """
    scheme = _method_name(scheme, SCHEMES, "line coding")
    scrambling = _method_name(scrambling, SCRAMBLING, "scrambling")
    if scrambling != "None" and scheme != "AMI":
        raise ValueError("B8ZS and HDB3 scrambling are available only for AMI.")
    expected_slots = _ENCODERS[scheme][1]
    if slots_per_bit is None:
        slots_per_bit = expected_slots
    if type(slots_per_bit) is not int or slots_per_bit != expected_slots:
        raise ValueError(f"{scheme} requires {expected_slots} slot(s) per bit.")
    try:
        samples = list(levels)
    except TypeError as error:
        raise ValueError("Supply a sequence of voltage levels.") from error
    if not samples:
        raise ValueError("Supply at least one complete bit of voltage samples.")
    allowed = (-1, 0, 1) if scheme == "AMI" else (-1, 1)
    if any(type(level) is not int or level not in allowed for level in samples):
        raise ValueError(f"{scheme} voltage levels must be integers in {allowed}.")
    if len(samples) % slots_per_bit:
        raise ValueError("The signal ends with an incomplete bit interval.")
    if scheme == "AMI":
        bits = _decode_ami_family(samples, scrambling)
    else:
        bits = _DECODERS[scheme](samples)
    # Reject illegal unsubstituted zero runs and incorrect scramble parity.
    # This checks the bits recovered above, not saved encoder input.
    if encode(bits, scheme, scrambling).levels != samples:
        raise ValueError("The signal is not valid for the selected coding conventions.")
    return bits


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bits", nargs="?", default="1011000000001001")
    parser.add_argument("--scheme", choices=SCHEMES, default="AMI")
    parser.add_argument("--scrambling", choices=SCRAMBLING, default="None")
    parser.add_argument("--decode", action="store_true")
    arguments = parser.parse_args()
    try:
        signal = encode(arguments.bits, arguments.scheme, arguments.scrambling)
    except ValueError as error:
        parser.error(str(error))
    print(f"Input: {arguments.bits}")
    print(f"Method: {signal.scheme}; scrambling: {signal.scrambling}")
    print(f"Slots per bit: {signal.slots_per_bit}")
    print("Voltage slots:", " ".join(f"{level:+d}" for level in signal.levels))
    if arguments.decode:
        decoded = decode_signal(signal.levels, signal.scheme,
                                signal.slots_per_bit, signal.scrambling)
        print(f"Decoded from voltage slots: {decoded}")


if __name__ == "__main__":
    main()
