"""Day 6: functional Streamlit interface. Run: streamlit run app.py"""

import plotly.graph_objects as go
import streamlit as st

from data import MAX_BITS, clean_bits, longest_palindrome, random_bits
from line_coding import SCHEMES, encode
from pcm import decode_pcm, encode_pcm, make_analog_samples

st.set_page_config(page_title="Signal Lab", page_icon="📶", layout="wide")
st.title("Signal Lab")
st.caption("Generate a digital stream or sample an analog wave, then explore its encoded signal.")


def plot_levels(signal):
    # Step interpolation represents constant levels during each time slot.
    count = min(signal.bit_count, 128)
    levels = signal.levels[:count * signal.slots_per_bit]
    x = [i / signal.slots_per_bit for i in range(len(levels) + 1)]
    figure = go.Figure(go.Scatter(x=x, y=levels + [levels[-1]], mode="lines", line_shape="hv"))
    figure.update_layout(height=400, xaxis_title="Bit interval", yaxis_title="Signal level")
    figure.update_yaxes(range=[-1.4, 1.4], tickvals=[-1, 0, 1])
    return figure


with st.sidebar:
    st.header("Encoding settings")
    mode = st.radio("Input type", ["Digital", "Analog (PCM)"])
    scheme = st.selectbox("Line coding", SCHEMES)
    scrambling = st.selectbox("Scrambling", ["None", "B8ZS", "HDB3"]) if scheme == "AMI" else "None"

source = st.radio("Digital input", ["Manual", "Random", "Random + zero run"], horizontal=True) if mode == "Digital" else None
with st.form("input"):
    if mode == "Digital":
        if source == "Manual":
            text = st.text_area("Binary data", "1011000000001010", height=160)
        else:
            length = st.number_input("Number of bits", 1, MAX_BITS, 64)
            seed = st.number_input("Random seed", 0, 2**31 - 1, 7)
            zero_run = st.selectbox("Guaranteed zero run", [4, 8]) if source == "Random + zero run" else 0
    else:
        left, right = st.columns(2)
        with left:
            waveform = st.selectbox("Analog wave", ["Sine", "Square", "Triangle"])
            frequency = st.number_input("Frequency (Hz)", 0.1, 10_000.0, 5.0)
            amplitude = st.number_input("Amplitude", 0.01, 1000.0, 1.0)
            duration = st.number_input("Duration (seconds)", 0.001, 30.0, 1.0, format="%.3f")
        with right:
            sampling_rate = st.number_input("Sampling rate (Hz)", 1.0, 100_000.0, 100.0)
            bit_depth = st.number_input("Bits per sample", 1, 16, 4)
            minimum = st.number_input("Quantizer minimum", value=-1.0)
            maximum = st.number_input("Quantizer maximum", value=1.0)
    submitted = st.form_submit_button("Generate and encode", type="primary")

if submitted:
    try:
        analog = None
        if mode == "Digital":
            bits = clean_bits(text) if source == "Manual" else random_bits(int(length), int(seed), int(zero_run))
        else:
            if sampling_rate * duration * bit_depth > MAX_BITS:
                raise ValueError(f"Reduce duration, sampling rate, or bit depth to stay below {MAX_BITS:,} bits.")
            times, samples = make_analog_samples(waveform, frequency, amplitude, sampling_rate, duration)
            result = encode_pcm(samples, int(bit_depth), minimum, maximum)
            bits = clean_bits(result.bits)
            reconstructed = decode_pcm(bits, int(bit_depth), minimum, maximum)
            analog = (times, samples, reconstructed, result.clipped_count, frequency, sampling_rate)
        signal = encode(bits, scheme, scrambling)
        st.session_state.result = (bits, longest_palindrome(bits), signal, analog)
    except ValueError as exc:
        st.error(str(exc))

if "result" in st.session_state:
    bits, palindrome, signal, analog = st.session_state.result
    st.caption("Results from your last run. Press Generate and encode to apply changed settings.")
    a, b, c = st.columns(3)
    a.metric("Bits", f"{len(bits):,}")
    b.metric("Palindrome length", f"{palindrome.length:,}")
    c.metric("Encoding", signal.scheme + (" / " + signal.scrambling if signal.scrambling != "None" else ""))
    st.write("Digital data (first 2,000 bits)")
    st.code(bits[:2000], language=None)
    st.write(f"Longest palindrome, starting at bit {palindrome.start + 1} (first 2,000 bits)")
    st.code(palindrome.text[:2000], language=None)
    st.download_button("Download complete digital stream", bits, "digital_stream.txt", "text/plain")
    st.plotly_chart(plot_levels(signal), width="stretch")
    st.caption("Waveform preview: first 128 bits. The complete stream was encoded.")
    if analog:
        times, samples, reconstructed, clipped, frequency, sampling_rate = analog
        preview = min(1000, len(times))
        figure = go.Figure()
        figure.add_trace(go.Scatter(x=times[:preview], y=samples[:preview], name="Input samples", mode="markers"))
        staircase_times = times[:preview] + [times[preview - 1] + 1 / sampling_rate]
        staircase_values = reconstructed[:preview] + [reconstructed[preview - 1]]
        figure.add_trace(go.Scatter(x=staircase_times, y=staircase_values, name="PCM decoder", line_shape="hv"))
        figure.update_layout(height=400, xaxis_title="Time (seconds)", yaxis_title="Amplitude")
        st.plotly_chart(figure, width="stretch")
        st.caption(f"PCM staircase: first {preview:,} samples. Clipped samples: {clipped:,}.")
        if sampling_rate <= 2 * frequency:
            st.warning("Sampling rate is at or below twice the fundamental frequency; aliasing may occur.")
else:
    st.info("Choose your input and encoding settings, then press Generate and encode.")
