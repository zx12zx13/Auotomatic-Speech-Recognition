import gradio as gr
from fastapi import FastAPI
from fastapi.testclient import TestClient
import json

with gr.Blocks() as demo:
    with gr.Column(visible=True) as col1:
        a = gr.Audio()
        b1 = gr.Button("Lanjut")
    with gr.Column(visible=False) as col2:
        t = gr.Textbox()
        b2 = gr.Button("Kembali")

    def go(audio):
        print("go() running, returning updates for col1 and col2")
        return gr.update(visible=False), gr.update(visible=True)

    b1.click(go, inputs=[a], outputs=[col1, col2])

app = gr.mount_gradio_app(FastAPI(), demo, path="/gradio/analisis")
tc = TestClient(app)

res = tc.post("/gradio/analisis/gradio_api/queue/join", json={
    "data": [None],
    "event_data": None,
    "fn_index": 0,
    "trigger_id": 4
})
print("Join response:", res.status_code, res.text)
event_id = res.json().get("event_id")
res_data = tc.get(f"/gradio/analisis/gradio_api/queue/data?session_hash={event_id}")
print("SSE Stream lines:")
for line in res_data.text.splitlines():
    if "process_completed" in line:
        data_json = json.loads(line.replace("data: ", ""))
        print("process_completed data:", json.dumps(data_json, indent=2))
