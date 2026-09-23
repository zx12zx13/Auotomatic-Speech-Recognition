import gradio as gr
from gradio_client import Client

with gr.Blocks() as demo:
    with gr.Tabs() as tabs:
        with gr.Tab("1. Audio", id="tab1") as t1:
            a = gr.Audio()
            b1 = gr.Button("Lanjut")
        with gr.Tab("2. Evaluasi", id="tab2") as t2:
            txt = gr.Textbox()
            b2 = gr.Button("Kembali")

    def go():
        return gr.update(selected="tab2")

    def back():
        return gr.update(selected="tab1")

    b1.click(go, outputs=[tabs])
    b2.click(back, outputs=[tabs])

demo.launch(prevent_thread_lock=True, server_port=7870)

client = Client("http://127.0.0.1:7870/")
res = client.predict(fn_index=0)
print("Result of tabs toggle:", res)
demo.close()
