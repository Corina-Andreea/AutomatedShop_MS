from openai import AzureOpenAI
import json
#OPENAI_API_KEY = "1nreL7pZR3YABTUqPcUe8MMeP0Mr2HgmIJbjXJ8LZEx2fuB9CJP8JQQJ99BLACfhMk5XJ3w3AAAAACOGzrBc"
# OPENAI_API_KEY= "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"
# MODEL = "gpt-4o"
#
#
# client = OpenAI(api_key=OPENAI_API_KEY)
endpoint = "https://hera-corina-lab-resource.cognitiveservices.azure.com/"
model_name = "gpt-4o"
deployment = "gpt-4o"

subscription_key = "1nreL7pZR3YABTUqPcUe8MMeP0Mr2HgmIJbjXJ8LZEx2fuB9CJP8JQQJ99BLACfhMk5XJ3w3AAAAACOGzrBc"
api_version = "2024-12-01-preview"

client = AzureOpenAI(
    api_version=api_version,
    azure_endpoint=endpoint,
    api_key=subscription_key,
)

def call_llm(system_prompt: str, user_input: str, state: dict):
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"""
USER_MESSAGE:
{user_input}

CURRENT_ORDER_STATE:
{json.dumps(state, indent=2)}
"""}
    ]

    response = client.chat.completions.create(
        model=model_name,
        temperature=0.4,
        messages=messages
    )

    return response.choices[0].message.content
