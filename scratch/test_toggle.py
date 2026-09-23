import gradio as gr
from gradio_client import Client

with gr.Blocks() as demo:
    with gr.Column(scale=4, elem_id="panel-masukan") as panel:
        with gr.Column(visible=True, elem_id="step-1-col") as col1:
            a = gr.Audio()
            b1 = gr.Button("Lanjut")
        with gr.Column(visible=False, elem_id="step-2-col") as col2:
            t = gr.Textbox(value="Ini tahap 2")
            b2 = gr.Button("Kembali")

    def go(audio):
        print("go() CALLED with audio:", audio)
        return gr.update(visible=False), gr.update(visible=True)

    def back():
        print("back() CALLED")
        return gr.update(visible=True), gr.update(visible=False)

    b1.click(go, inputs=[a], outputs=[col1, col2])
    b2.click(back, outputs=[col1, col2])

demo.launch(prevent_thread_lock=True, server_port=7869)

client = Client("http://127.0.0.1:7869/")
print("Calling /go via Client...")
try:
    # predict on b1.click
    res = client.predict(None, fn_index=0)
    print("Result of go:", res)
except Exception as e:
    print("Error calling go:", e)

demo.close()
