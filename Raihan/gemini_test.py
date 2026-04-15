from google import genai
import os
os.environ["GEMINI_API_KEY"] = "AIzaSyDeOlsnRi7_eR8xM5YpIM-RQ6P6c4bu0tA"

client = genai.Client()
response = client.models.generate_content(model="gemini-1.5-pro",   contents="What is the capital of France?")

print(response.text)