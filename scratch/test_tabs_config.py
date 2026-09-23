import gradio as gr

with gr.Blocks() as demo:
    with gr.Tabs() as tabs:
        with gr.Tab("1. Audio", id="step1"):
            a = gr.Audio()
            b1 = gr.Button("Lanjut")
        with gr.Tab("2. Evaluasi", id="step2"):
            t = gr.Textbox(label="Pertanyaan")
            b2 = gr.Button("Kembali")

    def go(audio):
        return gr.Tabs(selected="step2")

    def back():
        return gr.Tabs(selected="step1")

    b1.click(go, inputs=[a], outputs=[tabs])
    b2.click(back, outputs=[tabs])

config = demo.get_config_file()
import json
print("Tabs config:")
for c in config["components"]:
    if c["type"] == "tabs":
        print(c["id"], c["props"].get("selected"))
for d in config["dependencies"]:
    print("Dep target:", d.get("targets"), "outputs:", d.get("outputs"))
