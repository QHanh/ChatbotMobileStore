import os
import google.generativeai as genai
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

def get_gemini_response(prompt: str) -> str:
    """
    Sends a prompt to the Gemini 1.5 Flash model and returns the response.

    Args:
        prompt: The text prompt to send to the model.

    Returns:
        The model's response as a string.
    """
    try:
        genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
        model = genai.GenerativeModel('gemini-2.0-flash')
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"An error occurred with Gemini API: {e}"

def get_gpt_response(prompt: str) -> str:
    """
    Sends a prompt to the GPT-4o mini model and returns the response.

    Args:
        prompt: The text prompt to send to the model.

    Returns:
        The model's response as a string.
    """
    try:
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": prompt}
            ]
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"An error occurred with OpenAI API: {e}"

if __name__ == '__main__':
    prompt = "Hello, who are you?"
    response = get_gemini_response(prompt)
    print(f"Gemini Flash Response: {response}")

    response = get_gpt_response(prompt)
    print(f"GPT-4o Mini Response: {response}") 