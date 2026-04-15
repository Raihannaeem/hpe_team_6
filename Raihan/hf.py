from huggingface_hub import InferenceClient
from PIL import Image
import base64
from io import BytesIO
import os

client = InferenceClient(token = os.getenv("HUGGINGFACE_API_KEY"))

def local_image_to_base64(image_path):
    with Image.open(image_path) as img:
        buffered = BytesIO()
        img.save(buffered, format="JPEG")
        return base64.b64encode(buffered.getvalue()).decode("utf-8")

vlm_model_id = "HuggingFaceM4/idefics2-8b-chatty"

image_b64 = local_image_to_base64("graphImage_page_1.png")
image_input = f"data:image/jpeg;base64,{image_b64}"

prompt = f"User:![]( {image_input})from the given image, give me a description<|end_of_text|>"


response = client.text_generation(
    prompt,
    model=vlm_model_id,
    max_new_tokens=100,
)
print(response)