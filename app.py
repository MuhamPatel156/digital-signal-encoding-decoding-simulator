"""Digital signal encoding and decoding simulator. Run: python -m streamlit run app.py

Core modules stay independent of Streamlit. Binary input is limited to 200,000
bits; the complete stream is processed, while plots show an adjustable window.
The optional line decoder reads waveform levels, not raster image pixels.
"""

import csv
import io
import math

import plotly.graph_objects as go
import streamlit as st

from data import MAX_BITS, clean_bits, longest_palindrome, longest_zero_run, random_bits
from line_coding import SCHEMES, decode_signal, encode
from pcm import decode_pcm, encode_pcm, make_analog_samples

st.set_page_config(page_title="Digital Signal Encoding and Decoding Simulator", page_icon="📶", layout="wide")
st.markdown("""
<style>
 .block-container {padding-top: 2rem; max-width: 1550px;}
 .hero {background: linear-gradient(110deg,#10263d,#174856); padding: 2rem 2.2rem;
        border-radius: 18px; margin-bottom: 1.5rem; color: white;}
 .hero .eyebrow {color:#8be5d0; letter-spacing: .16em; font-size: .78rem; font-weight: 700;}
 .hero h1 {color: white; margin: .3rem 0; font-size: 2.7rem;}
 .hero p {color: #d3e1eb; margin: .3rem 0 0; max-width: 850px;}
 [data-testid="stMetric"] {padding:1rem; border-radius:12px;
                           border:1px solid rgba(128,128,128,.28);}
 [data-testid="stForm"] {border-radius: 14px;}
</style>
<div class="hero">
 <div class="eyebrow">DIGITAL COMMUNICATION SYSTEMS</div>
 <h1>Digital Signal Encoding and Decoding Simulator</h1>
 <p>From bits to waveforms. Explore line coding, zero-run scrambling,
 and analog-to-digital conversion in one workspace.</p>
</div>
""", unsafe_allow_html=True)

CONVENTIONS = {
    "NRZ-L": "0 = +1; 1 = −1. Each bit holds its level for one interval.",
    "NRZ-I": "Initial level −1. A 1 changes the level at the start; a 0 keeps it.",
    "Manchester": "0 = high → low; 1 = low → high. Every bit changes level in its middle.",
    "Differential Manchester": "Initial level +1. A 0 changes level at the start; a 1 does not. Every bit changes in its middle.",
    "AMI": "0 = zero voltage. Ones alternate +1 and −1, starting with +1.",
}


def layout_chart(figure, x_title, y_title, height=390):
    # Streamlit applies the current light/dark palette in the browser.
    # Leave backgrounds, text, and grid colors to that native theme.
    figure.update_layout(
        height=height, template="streamlit",
        margin=dict(l=35, r=25, t=35, b=45), xaxis_title=x_title, yaxis_title=y_title,
        font=dict(family="Arial, sans-serif"),
        legend=dict(orientation="h", y=1.12, x=0), hovermode="x unified",
    )
    figure.update_xaxes(zeroline=False)
    figure.update_yaxes(zeroline=False)
    return figure


def waveform_chart(signal, bits, start, count, color=None):
    slots = signal.slots_per_bit
    levels = signal.levels[start * slots:(start + count) * slots]
    x = [start + i / slots for i in range(len(levels) + 1)]
    figure = go.Figure(go.Scatter(
        x=x, y=levels + [levels[-1]], name=signal.scheme,
        mode="lines", line=dict(color=color, width=2.5, shape="hv"),
        hovertemplate="Interval %{x:.2f}<br>Level %{y}<extra></extra>",
    ))
    if count <= 64:
        figure.add_trace(go.Scatter(
            x=[start + i + .5 for i in range(count)], y=[1.3] * count,
            text=list(bits[start:start + count]), mode="text", showlegend=False,
            textfont=dict(size=13), hoverinfo="skip",
        ))
    layout_chart(figure, "Bit interval (zero-based)", "Signal level")
    figure.update_yaxes(range=[-1.5, 1.6], tickvals=[-1, 0, 1])
    figure.update_xaxes(range=[start, start + count], dtick=1 if count <= 32 else None)
    return figure


def signal_csv(signal):
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["time_in_bit_intervals", "level"])
    writer.writerows((i / signal.slots_per_bit, value) for i, value in enumerate(signal.levels))
    return output.getvalue()


def pcm_csv(analog):
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["time_seconds", "input_sample", "pcm_code", "reconstructed_sample"])
    writer.writerows(zip(analog["times"], analog["samples"], analog["pcm"].codes, analog["decoded"]))
    return output.getvalue()


with st.sidebar:
    st.header("Configure your signal")
    mode = st.radio("Input type", ["Digital", "Analog (PCM)"])
    scheme = st.selectbox("Line coding method", SCHEMES)
    scrambling = "None"
    if scheme == "AMI":
        use_scrambling = st.checkbox("Apply scrambling")
        if use_scrambling:
            scrambling = st.selectbox("Scrambling method", ["B8ZS", "HDB3"])
    st.divider()
    st.caption(CONVENTIONS[scheme])
    if scrambling == "B8ZS":
        st.caption("Replace eight zeros with 000VB0VB. V breaks AMI alternation; B follows it.")
    elif scrambling == "HDB3":
        st.caption("Replace four zeros with 000V or B00V, using pulse parity since the previous substitution.")
    st.caption(f"Up to {MAX_BITS:,} bits per run. Full data is processed; the waveform view is adjustable.")

st.markdown("### 1 · Build your input")
source = st.radio("Digital source", ["Paste bits", "Random", "Random + zero run"], horizontal=True) if mode == "Digital" else None

with st.form("signal_input"):
    if mode == "Digital":
        if source == "Paste bits":
            text = st.text_area("Binary data", "10110000000010100100", height=160,
                                help="Paste a binary stream. Spaces, tabs, and newlines are ignored.")
        else:
            left, right = st.columns(2)
            with left:
                length = st.number_input("Number of bits", 1, MAX_BITS, 128)
            with right:
                seed = st.number_input("Random seed", 0, 2**31 - 1, 7,
                                       help="The same seed and settings produce the same data.")
            zero_run = st.selectbox("Guaranteed zero run", [4, 8]) if source == "Random + zero run" else 0
            if zero_run:
                st.caption("The inserted zeros can join adjacent zeros, creating a longer run.")
    else:
        left, middle, right = st.columns(3)
        with left:
            waveform = st.selectbox("Waveform", ["Sine", "Square", "Triangle"])
            frequency = st.number_input("Frequency (Hz)", .1, 10_000.0, 5.0)
            amplitude = st.number_input("Amplitude", .01, 1000.0, 1.0)
        with middle:
            sampling_rate = st.number_input("Sampling rate (Hz)", 1.0, 100_000.0, 100.0)
            duration = st.number_input("Duration (seconds)", .001, 30.0, 1.0, format="%.3f")
            offset = st.number_input("DC offset", value=0.0)
        with right:
            bit_depth = st.number_input("Bits per sample", 1, 16, 4)
            minimum = st.number_input("Quantizer minimum", value=-1.0)
            maximum = st.number_input("Quantizer maximum", value=1.0)
        st.caption("PCM uses equally spaced amplitude levels including the minimum and maximum. Values outside the range are clipped.")
    submitted = st.form_submit_button("Generate and encode", type="primary")

if submitted:
    try:
        with st.spinner("Processing the complete signal…"):
            analog = None
            if mode == "Digital":
                bits = clean_bits(text) if source == "Paste bits" else random_bits(int(length), int(seed), int(zero_run))
            else:
                if math.ceil(sampling_rate * duration) * bit_depth > MAX_BITS:
                    raise ValueError(f"PCM output exceeds {MAX_BITS:,} bits. Reduce sample rate, duration, or bit depth.")
                times, samples = make_analog_samples(waveform, frequency, amplitude, sampling_rate, duration, offset)
                pcm = encode_pcm(samples, int(bit_depth), minimum, maximum)
                bits = clean_bits(pcm.bits)
                decoded = decode_pcm(pcm.bits, pcm.bits_per_sample, pcm.minimum, pcm.maximum)
                analog = dict(times=times, samples=samples, pcm=pcm, decoded=decoded,
                              waveform=waveform, frequency=frequency, amplitude=amplitude,
                              offset=offset, sampling_rate=sampling_rate)
            signal = encode(bits, scheme, scrambling)
            st.session_state.result = dict(bits=bits, palindrome=longest_palindrome(bits),
                                           signal=signal, analog=analog, zeros=longest_zero_run(bits))
            st.session_state.show_decode = False
        st.success("Signal generated. Explore the result below.")
    except ValueError as exc:
        st.error(str(exc))

if "result" not in st.session_state:
    st.info("Choose a source and coding method, then select Generate and encode.")
    st.stop()

result = st.session_state.result
bits, palindrome, signal, analog = (result[name] for name in ("bits", "palindrome", "signal", "analog"))
st.caption("Results reflect the last completed run. Generate again to apply changed input settings.")
st.markdown("### 2 · Explore the result")
a, b, c, d = st.columns(4)
a.metric("Digital stream", f"{len(bits):,} bits")
b.metric("Longest palindrome", f"{palindrome.length:,} bits")
c.metric("Longest zero run", f"{result['zeros']:,} bits")
d.metric("Method", signal.scheme, signal.scrambling if signal.scrambling != "None" else None)

wave_tab, data_tab, analog_tab = st.tabs(["Encoded waveform", "Data & palindrome", "PCM reconstruction"])
with wave_tab:
    left, right = st.columns(2)
    with left:
        start = int(st.number_input("Start at bit (one-based)", 1, len(bits), 1, key=f"window_start_{len(bits)}")) - 1
    with right:
        window = int(st.number_input("Bits in view", 1, 512, min(64, len(bits)), key=f"window_size_{len(bits)}"))
    count = min(window, len(bits) - start)
    st.plotly_chart(waveform_chart(signal, bits, start, count), width="stretch", theme="streamlit", key="encoded_waveform")
    st.caption(f"Viewing bits {start + 1:,}–{start + count:,} of {len(bits):,}. Drag to zoom, double-click to reset, or use the chart toolbar to save an image.")
    st.caption(CONVENTIONS[signal.scheme])
    if signal.scrambling != "None":
        st.markdown("#### Original AMI for comparison")
        original = encode(bits, "AMI")
        st.plotly_chart(waveform_chart(original, bits, start, count, "#8a91a4"), width="stretch", theme="streamlit", key="original_ami")
        st.caption("Both plots use the same bit window. The upper plot contains scrambling substitutions.")
    st.download_button("Download complete waveform CSV", signal_csv(signal), "encoded_signal.csv", "text/csv")
    st.markdown("#### Decode the waveform")
    st.caption("This decoder analyses voltage levels and transitions in the complete encoded waveform. It does not read image pixels.")
    if st.button("Decode current waveform"):
        st.session_state.show_decode = True
    if st.session_state.get("show_decode", False):
        try:
            recovered = decode_signal(signal.levels, signal.scheme, signal.slots_per_bit, signal.scrambling)
            if recovered == bits:
                st.success(f"Recovered all {len(recovered):,} bits correctly from the signal.")
            else:
                st.error("The decoded stream does not match the input.")
            st.code(recovered[:2000], language=None)
            if len(recovered) > 2000:
                st.caption("Showing the first 2,000 decoded bits; the download contains every bit.")
            st.download_button("Download recovered bits", recovered, "decoded_stream.txt", "text/plain")
        except ValueError as exc:
            st.error(str(exc))

with data_tab:
    st.markdown("#### Digital stream")
    st.code(bits[:4000], language=None)
    st.caption(f"Showing {min(4000, len(bits)):,} of {len(bits):,} bits.")
    st.download_button("Download full digital stream", bits, "digital_stream.txt", "text/plain")
    st.markdown("#### Longest contiguous palindrome")
    st.code(palindrome.text[:4000], language=None)
    st.caption(f"Length {palindrome.length:,}; bits {palindrome.start + 1:,}–{palindrome.start + palindrome.length:,}. Earliest occurrence wins ties. Preview is limited to 4,000 bits.")
    st.download_button("Download full palindrome", palindrome.text, "longest_palindrome.txt", "text/plain")
    with st.expander("How the search works"):
        st.write("Manacher's algorithm reuses known palindrome radii around odd and even centres. It finds a contiguous substring in O(n) time and O(n) memory. Zero-run detection and each line encoder also use O(n) time.")

with analog_tab:
    if analog is None:
        st.info("Select Analog (PCM) and generate a signal to see sampling, quantization, and the decoder's staircase.")
    else:
        times, samples, reconstructed, pcm = (analog[name] for name in ("times", "samples", "decoded", "pcm"))
        preview = min(1000, len(times))
        end_time = times[preview - 1] + 1 / analog["sampling_rate"]
        dense_times, dense_values = make_analog_samples(
            analog["waveform"], analog["frequency"], analog["amplitude"],
            2000 / end_time, end_time, analog["offset"],
        )
        figure = go.Figure()
        figure.add_trace(go.Scatter(x=dense_times, y=dense_values, name="Analog input", line=dict(width=1.5)))
        figure.add_trace(go.Scatter(x=times[:preview], y=samples[:preview], name="Input samples", mode="markers", marker=dict(size=5)))
        figure.add_trace(go.Scatter(x=times[:preview] + [end_time], y=reconstructed[:preview] + [reconstructed[preview - 1]],
                                   name="PCM decoder staircase", line=dict(width=2, shape="hv")))
        layout_chart(figure, "Time (seconds)", "Amplitude", 430)
        st.plotly_chart(figure, width="stretch", theme="streamlit", key="pcm_waveform")
        mse = sum((x - y)**2 for x, y in zip(samples, reconstructed)) / len(samples)
        a, b, c = st.columns(3)
        a.metric("PCM samples", f"{len(samples):,}")
        b.metric("Quantization levels", f"{2**pcm.bits_per_sample:,}")
        c.metric("Mean squared error", f"{mse:.6g}")
        st.caption(f"First {preview:,} samples shown. The decoder reconstructs each value from {pcm.bits_per_sample}-bit codes and holds it for one sample interval.")
        if pcm.clipped_count:
            st.warning(f"{pcm.clipped_count:,} sample(s) were outside the quantizer range and clipped. Widen the range or reduce amplitude/offset.")
        if analog["sampling_rate"] <= 2 * analog["frequency"]:
            st.warning("Sampling rate is at or below twice the fundamental frequency; aliasing may occur.")
        if analog["waveform"] != "Sine":
            st.caption("Square and triangle waves have higher harmonics. A rate above twice the fundamental alone does not capture every harmonic.")
        st.download_button("Download all PCM samples", pcm_csv(analog), "pcm_samples.csv", "text/csv")

st.divider()
st.caption("Digital Signal Simulator · NRZ-L / NRZ-I / Manchester / Differential Manchester / AMI / B8ZS / HDB3 / PCM")
