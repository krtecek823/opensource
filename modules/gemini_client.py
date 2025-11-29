# modules/gemini_client.py
import google.generativeai as genai

def init_gemini(api_key, model_name):
    genai.configure(api_key=api_key)
    return genai.GenerativeModel(model_name)


def ask_gemini(model, prompt):
    try:
        res = model.generate_content(prompt)
        return res.text if hasattr(res, "text") else None
    except Exception as e:
        return f"Gemini 오류: {e}"
