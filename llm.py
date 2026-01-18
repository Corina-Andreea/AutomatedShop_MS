from openai import AzureOpenAI
import json

# --------------------
# Azure OpenAI config
# --------------------
endpoint = "https://hera-corina-lab-resource.cognitiveservices.azure.com/"
model_name = "gpt-4o"
deployment = "gpt-4o"

subscription_key = "1nreL7pZR3YABTUqPcUe8MMeP0Mr2HgmIJbjXJ8LZEx2fuB9CJP8JQQJ99BLACfhMk5XJ3w3AAAAACOGzrBc"
api_version = "2024-12-01-preview"

client = AzureOpenAI(
    api_version = api_version,
    azure_endpoint = endpoint,
    api_key = subscription_key,
)


def call_llm(messages: list):
    """
    messages = [
        {"role": "system", "content": "..."},
        {"role": "user", "content": "..."},
        {"role": "assistant", "content": "..."},
        ...
    ]
    """

    response = client.chat.completions.create(
        model=model_name,
        messages=messages,
        temperature=0.4
    )

    return response.choices[0].message.content
