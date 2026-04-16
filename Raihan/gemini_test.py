from google import genai
import os

client = genai.Client()
response = client.models.generate_content(model="gemini-1.5-pro",   contents="What is the capital of France?")

print(response.text)