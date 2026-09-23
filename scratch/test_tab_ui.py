import gradio as gr
from fastapi import FastAPI
from fastapi.testclient import TestClient

with gr.Blocks() as demo:
    with gr.Tabs(elem_id="wizard-tabs") as tabs:
        with gr.Tab("1. Audio Siswa", id="tab-audio"):
            a = gr.Audio()
            b1 = gr.Button("Lanjut →")
        with gr.Tab("2. Topik & Evaluasi", id="tab-topik"):
            t = gr.Textbox()
            b2 = gr.Button("↺ Ganti Audio")

    def go(audio):
        return gr.Tabs(selected="tab-topik")

    def back():
        return gr.Tabs(selected="tab-audio")

    b1.click(go, inputs=[a], outputs=[tabs])
    b2.click(back, outputs=[tabs])

app = gr.mount_gradio_app(FastAPI(), demo, path="/")
tc = TestClient(app)
res = tc.get("/")
print("Rendered successfully with status code:", res.status_code)
