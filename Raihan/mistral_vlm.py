
from io import BytesIO
from PIL import Image
import requests, base64

invoke_url = "https://integrate.api.nvidia.com/v1/chat/completions"
stream = False

def local_image_to_base64(image_path):
    with Image.open(image_path) as img:
        buffered = BytesIO()
        img.save(buffered, format="JPEG")
        return base64.b64encode(buffered.getvalue()).decode("utf-8")

images_b64 = [
    local_image_to_base64("graphImage_page_1.png"),
    local_image_to_base64("graphImage_page_2.png")
]

headers = {
  "Authorization": "Bearer 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",
  "Accept": "text/event-stream" if stream else "application/json"
}

payload = {
  "model": "mistralai/mistral-large-3-675b-instruct-2512",
  "messages": [
    {
      "role": "user",
      "content": [
        {"type": "text", "text": "from the given images, find the dropout voltage at input current = 20ma or input voltage = 4v, if you are not able to find it, say NF, if it is not applicable, say NA. give it to me in json format, with attributes dropout_voltage, input_current(if used), input_voltage(if used), status(success/failure)"},
        {
          "type": "image_url",
          "image_url": {
            "url": f"data:image/jpeg;base64,{images_b64[0]}"
          }
        },
        {
          "type": "image_url",
          "image_url": {
            "url": f"data:image/jpeg;base64,{images_b64[1]}"
          }
        }
      ]
    }
  ],
  "max_tokens": 2048,
  "temperature": 0.15,
  "top_p": 1.0,
  "stream": stream
}

response = requests.post(invoke_url, headers=headers, json=payload)

if stream:
    for line in response.iter_lines():
        if line:
            print(line.decode("utf-8"))
else:
    print(response.json()['choices'][0]['message']['content'])
