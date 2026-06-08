import os
import google.generativeai as genai
from decouple import config

# Ensure we have the key
api_key = config("GEMINI_API_KEY")
genai.configure(api_key=api_key)

print("Available models:")
for m in genai.list_models():
    if "generateContent" in m.supported_generation_methods:
        print(f"- {m.name}")
