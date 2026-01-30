3. [Getting Started](/)
5. Quickstart
Copy markdown

# Quickstart

tip

Looking for the **AI Studio** previously La Plateforme? Head to [console.mistral.ai](https://console.mistral.ai/)

Get Started

Copy section link

# Get Started

## Start using Mistral AI API

To get started with Mistral AI, you need to create an account and set up your payment information; once done you can create an API key and start using our API.

Account Setup

Copy section link

## Account Setup

* Create a Mistral account or sign in at <https://console.mistral.ai>.
* Then, navigate to your "Organization" settings at <https://admin.mistral.ai>.
* To add your payment information and activate payments on your account, find the [billing](https://admin.mistral.ai/organization/billing) section under Administration.
  + You may be later prompted to select a plan; pick between Experiment (free experimental tier) and Scale (pay as you go) plans.
* You can now manage all your [Workspaces](https://admin.mistral.ai/organization/workspaces) and Organization via this page.
* Return to <https://console.mistral.ai> once everything is settled.
* After that, go to the [API keys](https://console.mistral.ai/api-keys) page under your Workspace and create a new API key by clicking "Create new key". Make sure to copy the API key, save it securely, and do not share it with anyone.

Try the API

Copy section link

## Try the API

[Open in Colab ↗](https://colab.research.google.com/github/mistralai/cookbook/blob/main/quickstart.ipynb)

Mistral AI API provides a seamless way for developers to integrate Mistral's state-of-the-art
models into their applications and production workflows with just a few lines of code.
Our API is currently available through [La Plateforme](https://console.mistral.ai/).
You need to activate payments on your account to enable your API keys.
After a few moments, you will be able to use our endpoints.

Below, you can see some quickstart code snippets and examples of a few of our endpoints you can visit!

Chat Completion

Text Embeddings

Document AI - OCR

Audio Transcription

Close

Our Chat Completion endpoint allows you to interact with Mistral AI's models in a **conversational manner**, pretty much how you would interact with a chatbot.

To learn more about the Chat Completion endpoint, check out our [Chat Completions Docs](../capabilities/completion).

pythontypescriptcurl

Output

```
import os
from mistralai import Mistral

api_key = os.environ["MISTRAL_API_KEY"]
model = "mistral-medium-latest"

client = Mistral(api_key=api_key)

chat_response = client.chat.complete(
    model= model,
    messages = [
        {
            "role": "user",
            "content": "What is the best French cheese?",
        },
    ]
)
```

```
import os
from mistralai import Mistral

api_key = os.environ["MISTRAL_API_KEY"]
model = "mistral-medium-latest"

client = Mistral(api_key=api_key)

chat_response = client.chat.complete(
    model= model,
    messages = [
        {
            "role": "user",
            "content": "What is the best French cheese?",
        },
    ]
)
```

Learn More

Copy section link

# Learn More

We offer multiple services and models, from transcription to reasoning and sota document AI and OCR systems;
For a full description of the models offered on the API, head on to the **[models page](../models)**.

[Compare Models](/getting-started/models/compare)[SDK Clients](/getting-started/clients)

#### Contents

* [Get Started](#get-started)
* [Account Setup](#account-setup)
* [Try the API](#getting-started-with-mistral-ai-api)
* [Learn More](#learn-more)

Go to Top