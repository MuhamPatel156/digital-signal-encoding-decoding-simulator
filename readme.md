# Digital Signal Encoding and Decoding Simulator

This is a Python project for understanding how digital data is represented as a signal. It supports different line coding methods, scrambling, and Pulse Code Modulation (PCM). Streamlit is used for the interface and Plotly is used to draw the waveforms.

## Features

- Enter binary data manually or generate random bits.
- Generate random data containing at least four or eight consecutive zeros.
- Find the longest palindrome in the digital stream.
- Encode data using NRZ-L, NRZ-I, Manchester, Differential Manchester, or AMI.
- Apply B8ZS or HDB3 scrambling when using AMI.
- Generate sine, square, or triangle waves and convert their samples into PCM bits.
- Reconstruct PCM samples and display the decoder's staircase signal.
- Decode the generated line-coded waveform back into bits.
- Compare ordinary AMI with its scrambled signal and download the results.

## Requirements

- Python 3.10 or later
- Streamlit and Plotly, installed through `requirements.txt`

## How to run

Clone the repository and enter the project folder:

```bash
git clone https://github.com/MuhamPatel156/digital-signal-encoding-decoding-simulator.git
cd digital-signal-encoding-decoding-simulator
```

Install the libraries:

```bash
python -m pip install -r requirements.txt
```

Start the application:

```bash
python -m streamlit run app.py
```

Open the local URL shown in the terminal. A virtual environment can also be used, but it is optional.

## How to use

For digital input, select **Digital** in the sidebar. Paste a binary stream or choose one of the random generation options. Select the line coding method and click **Generate and encode**. For AMI, scrambling can be enabled using the checkbox.

The results show the encoded waveform, digital data, and longest palindrome. Use **Start at bit** and **Bits in view** to move through the waveform. The **Decode current waveform** button recovers the bits from the signal levels and transitions.

For analog input, select **Analog (PCM)**. Choose the waveform and enter its frequency, amplitude, sampling rate, duration, and PCM settings. After generating the signal, open **PCM reconstruction** to see the sampled input and reconstructed staircase.

## Project files

| File | Purpose |
| --- | --- |
| `app.py` | Streamlit interface, charts, and downloads |
| `data.py` | Binary data generation, longest palindrome, and zero-run search |
| `line_coding.py` | Line encoders, scrambling, and waveform decoding |
| `pcm.py` | Analog samples, PCM encoding, and PCM decoding |
| `requirements.txt` | Required external libraries |

The processing modules can also be run from the terminal. For example:

```bash
python data.py --length 64 --seed 7 --zero-run 8
python line_coding.py 1000000001 --scheme AMI --scrambling B8ZS --decode
python pcm.py
```

## Notes

- The app supports up to 200,000 bits per run. The graph displays a selected window, while downloads contain the complete results.
- A palindrome means a consecutive sequence that reads the same forward and backward. The search uses Manacher's algorithm.
- Signal levels are normalized to -1, 0, and +1. The conventions and starting levels are explained in the interface and code.
- Line decoding uses the generated waveform's levels and timing. It does not read pixels from an uploaded image.
- PCM reconstruction gives quantized sample values. Samples outside the chosen quantizer range are clipped and counted.
