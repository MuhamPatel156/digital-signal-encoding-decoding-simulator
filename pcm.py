"""Analog sampling, uniform PCM encoding, and PCM reconstruction.

Samples occur at n / sampling_rate; the duration endpoint is excluded. The
quantizer has 2**bits_per_sample evenly spaced levels including both endpoints.
It rounds to the closest level, choosing the higher level for an exact tie.
Codes are emitted most-significant bit first, using a fixed number of bits.
"""

from __future__ import annotations

import argparse
import math
from dataclasses import dataclass
from typing import Iterable


MAX_SAMPLES = 200_000


@dataclass(frozen=True)
class PCMResult:
    """The emitted stream and the values represented by its sample codes."""

    bits: str
    codes: list[int]
    quantized: list[float]
    bits_per_sample: int
    minimum: float
    maximum: float
    clipped_count: int


def _finite(value: float, name: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a finite number.")
    try:
        converted = float(value)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError(f"{name} must be a finite number.") from error
    if not math.isfinite(converted):
        raise ValueError(f"{name} must be a finite number.")
    return converted


def _pcm_parameters(
    bits_per_sample: int, minimum: float, maximum: float
) -> tuple[int, float, float, float]:
    if isinstance(bits_per_sample, bool) or not isinstance(bits_per_sample, int):
        raise ValueError("Bits per sample must be an integer from 1 to 16.")
    if not 1 <= bits_per_sample <= 16:
        raise ValueError("Bits per sample must be an integer from 1 to 16.")
    minimum = _finite(minimum, "Minimum")
    maximum = _finite(maximum, "Maximum")
    span = maximum - minimum
    if maximum <= minimum or not math.isfinite(span):
        raise ValueError("Maximum must exceed minimum with a finite range.")
    return 1 << bits_per_sample, minimum, maximum, span


def make_analog_samples(
    waveform: str,
    frequency: float,
    amplitude: float,
    sampling_rate: float,
    duration: float,
    offset: float = 0.0,
) -> tuple[list[float], list[float]]:
    """Return sample times and amplitudes for Sine, Square, or Triangle.

    Frequency and sampling rate are in Hz, duration is in seconds, and amplitude
    is the peak departure from offset. Sine and Triangle start at offset and
    rise; Square starts at offset + amplitude. At most MAX_SAMPLES are allowed.
    Sampling may alias if the chosen rate is too low; callers should explain
    this when displaying the waveform rather than silently changing its rate.
    """
    if not isinstance(waveform, str):
        raise ValueError("Waveform must be Sine, Square, or Triangle.")
    waveform = waveform.strip().lower()
    if waveform not in {"sine", "square", "triangle"}:
        raise ValueError("Waveform must be Sine, Square, or Triangle.")
    frequency = _finite(frequency, "Frequency")
    amplitude = _finite(amplitude, "Amplitude")
    sampling_rate = _finite(sampling_rate, "Sampling rate")
    duration = _finite(duration, "Duration")
    offset = _finite(offset, "Offset")
    if frequency <= 0 or sampling_rate <= 0 or duration <= 0:
        raise ValueError("Frequency, sampling rate, and duration must be positive.")
    if amplitude < 0 or not math.isfinite(abs(offset) + amplitude):
        raise ValueError("Amplitude must be nonnegative with finite extrema.")
    sample_product = sampling_rate * duration
    if not math.isfinite(sample_product) or sample_product > MAX_SAMPLES:
        raise ValueError(f"Choose parameters producing at most {MAX_SAMPLES:,} samples.")
    count = max(1, math.ceil(sample_product))
    times = [index / sampling_rate for index in range(count)]
    # fs * duration can round just above an integer (for example 100 * 0.07).
    # Check actual times so the stated endpoint exclusion remains exact.
    while times[-1] >= duration:
        times.pop()
    count = len(times)

    # Reducing the sampled frequency modulo fs avoids huge angle calculations.
    # Adding a whole multiple of fs gives the same phases at n / fs.
    phase_increment = math.fmod(frequency, sampling_rate) / sampling_rate
    values: list[float] = []
    for index in range(count):
        phase = (index * phase_increment) % 1.0
        if waveform == "sine":
            unit_value = math.sin(math.tau * phase)
        elif waveform == "square":
            unit_value = 1.0 if phase < 0.5 else -1.0
        else:
            unit_value = 1.0 - 4.0 * abs(((phase + 0.25) % 1.0) - 0.5)
        values.append(offset + amplitude * unit_value)
    return times, values


def encode_pcm(
    samples: Iterable[float],
    bits_per_sample: int = 4,
    minimum: float = -1.0,
    maximum: float = 1.0,
) -> PCMResult:
    """Quantize finite samples and encode each code as a fixed-width binary word.

    Values outside [minimum, maximum] are clipped and counted. One-bit PCM has
    the two endpoint levels. A nonempty stream of at most MAX_SAMPLES is allowed.
    Time is O(number of samples * bits per sample), including the output bits.
    """
    levels, minimum, maximum, span = _pcm_parameters(
        bits_per_sample, minimum, maximum
    )
    codes: list[int] = []
    quantized: list[float] = []
    words: list[str] = []
    clipped_count = 0
    try:
        iterator = iter(samples)
    except TypeError as error:
        raise ValueError("Samples must be an iterable of finite numbers.") from error
    for index, sample in enumerate(iterator):
        if index >= MAX_SAMPLES:
            raise ValueError(f"PCM accepts at most {MAX_SAMPLES:,} samples.")
        sample = _finite(sample, f"Sample {index}")
        if sample < minimum or sample > maximum:
            clipped_count += 1
        clipped = min(maximum, max(minimum, sample))
        scaled = ((clipped - minimum) / span) * (levels - 1)
        code = min(levels - 1, max(0, math.floor(scaled + 0.5)))
        codes.append(code)
        quantized.append(minimum + span * (code / (levels - 1)))
        words.append(format(code, f"0{bits_per_sample}b"))
    if not codes:
        raise ValueError("Provide at least one analog sample.")
    return PCMResult(
        bits="".join(words),
        codes=codes,
        quantized=quantized,
        bits_per_sample=bits_per_sample,
        minimum=minimum,
        maximum=maximum,
        clipped_count=clipped_count,
    )


def decode_pcm(
    bits: str,
    bits_per_sample: int = 4,
    minimum: float = -1.0,
    maximum: float = 1.0,
) -> list[float]:
    """Reconstruct quantized samples using only the bits and PCM parameters.

    The caller can draw a staircase by holding each sample for one sample period.
    This returns the quantized amplitudes, not the original continuous waveform.
    """
    levels, minimum, maximum, span = _pcm_parameters(
        bits_per_sample, minimum, maximum
    )
    if not isinstance(bits, str) or not bits:
        raise ValueError("Provide a nonempty binary string.")
    if len(bits) > MAX_SAMPLES * bits_per_sample:
        raise ValueError(f"PCM accepts at most {MAX_SAMPLES:,} sample codes.")
    if len(bits) % bits_per_sample:
        raise ValueError("Bit count must be a multiple of bits per sample.")
    if any(bit not in "01" for bit in bits):
        raise ValueError("PCM bits must contain only 0 and 1, without spaces.")
    return [
        minimum + span * (int(bits[index : index + bits_per_sample], 2) / (levels - 1))
        for index in range(0, len(bits), bits_per_sample)
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--waveform", choices=["Sine", "Square", "Triangle"], default="Sine")
    parser.add_argument("--frequency", type=float, default=5.0, help="Frequency in Hz")
    parser.add_argument("--amplitude", type=float, default=1.0)
    parser.add_argument("--sampling-rate", type=float, default=100.0, help="Samples per second")
    parser.add_argument("--duration", type=float, default=1.0, help="Duration in seconds")
    parser.add_argument("--offset", type=float, default=0.0)
    parser.add_argument("--bits-per-sample", type=int, default=4)
    parser.add_argument("--minimum", type=float, default=-1.0)
    parser.add_argument("--maximum", type=float, default=1.0)
    args = parser.parse_args()
    try:
        times, samples = make_analog_samples(
            args.waveform, args.frequency, args.amplitude,
            args.sampling_rate, args.duration, args.offset,
        )
        encoded = encode_pcm(samples, args.bits_per_sample, args.minimum, args.maximum)
        reconstructed = decode_pcm(
            encoded.bits, encoded.bits_per_sample, encoded.minimum, encoded.maximum
        )
    except ValueError as error:
        parser.error(str(error))
    print(f"{args.waveform}: {len(samples):,} samples, {len(encoded.bits):,} PCM bits")
    print(f"Quantizer: {1 << encoded.bits_per_sample} levels, {encoded.minimum:g} to {encoded.maximum:g}")
    print(f"Clipped samples: {encoded.clipped_count:,}")
    if args.sampling_rate <= 2 * args.frequency:
        print("Sampling warning: use a rate above twice the sine frequency to avoid aliasing.")
    elif args.waveform != "Sine":
        print("Sampling note: Square and Triangle contain harmonics beyond their fundamental frequency.")
    print("PCM preview:", encoded.bits[:128] + ("..." if len(encoded.bits) > 128 else ""))
    print("First 8 reconstructed samples:", [round(value, 6) for value in reconstructed[:8]])
    print("Decoder agrees with quantizer:", reconstructed == encoded.quantized)


if __name__ == "__main__":
    main()
