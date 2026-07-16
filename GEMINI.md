# GEMINI Project Context: ASR & Diarization Web App

This document provides instructional context for the Gemini CLI, based on an analysis of the current project directory.

## Project Overview

This project is a Python-based web application for **Automatic Speech Recognition (ASR)** and **Speaker Diarization**. It allows users to upload an audio file and receive a transcription of the speech, along with timestamps identifying different speakers.

### Core Technologies:

*   **Backend:** Python
*   **Speech-to-Text:** `openai-whisper` (using the "medium" model)
*   **Speaker Diarization:** `pyannote.audio`
*   **Web UI:** `gradio`
*   **Core Libraries:** `torch`, `numpy`, `speechbrain`

### Architecture

The application is a single-script service defined in `app.py`:

1.  **Model Loading:** At startup, it loads the Whisper and Pyannote models into memory.
2.  **Processing Pipeline:** When a user uploads an audio file via the web UI, the `asr_pipeline` function is triggered.
3.  **Transcription & Diarization:** The pipeline first transcribes the audio using Whisper, then processes it with Pyannote to identify speaker segments.
4.  **NLP Correction:** A simple local NLP function performs basic text replacement for common Indonesian informal words (e.g., "gak" -> "tidak").
5.  **UI Display:** The results (transcription, speaker timeline, and NLP corrections) are displayed back to the user in separate text boxes in the Gradio interface.

## Building and Running

### 1. Environment Setup

It is highly recommended to use the existing Python virtual environment (`.venv`) to manage dependencies.

To activate it, run:

```sh
# On Windows
.\.venv\Scripts\activate
```

### 2. Install Dependencies

Install all the required Python packages using the `requirements.txt` file.

```sh
pip install -r requirements.txt
```

### 3. Running the Application

The application can be started by running the `app.py` script. This will launch a local Gradio web server.

```sh
python app.py
```

You can then access the user interface by navigating to the URL provided in the console (usually `http://127.0.0.1:7860`).

## Development Conventions

*   **Environment Variables:** The `app.py` script sets specific environment variables required for the libraries to function correctly on Windows (`SB_NO_SYMLINK`, `TORCH_AUDIOMENTATIONS_DISABLE_WARNINGS`).
*   **Code Structure:** The code is organized sequentially in `app.py`:
    1.  Imports and environment variable setup.
    2.  Model loading functions.
    3.  NLP and Diarization processing functions.
    4.  The main processing pipeline function.
    5.  Gradio UI layout and component definitions.
    6.  The main execution block (`if __name__ == "__main__":`) to launch the app.
*   **Modularity:** The core functions (`local_nlp_processing`, `pyannote_diarization`, `asr_pipeline`) are self-contained, making them easy to test or modify individually.
