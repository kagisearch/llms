from __future__ import annotations

import json
import typing as t
from dataclasses import dataclass

import tiktoken
from openai import AsyncOpenAI, OpenAI

from .base import StreamProvider, msg_as_str


@dataclass
class OpenAIProvider(StreamProvider):
    # cost is per million tokens
    MODEL_INFO = {
        "gpt-3.5-turbo": {
            "prompt": 2.0,
            "completion": 2.0,
            "token_limit": 16_385,
            "is_chat": True,
            "output_limit": 4_096,
        },
        "gpt-3.5-turbo-instruct": {
            "prompt": 2.0,
            "completion": 2.0,
            "token_limit": 4096,
            "is_chat": False,
        },
        "gpt-4": {
            "prompt": 30.0,
            "completion": 60.0,
            "token_limit": 8192,
            "is_chat": True,
        },
        "gpt-4-turbo": {
            "prompt": 10.0,
            "completion": 30.0,
            "token_limit": 128_000,
            "is_chat": True,
            "output_limit": 4_096,
        },
        "gpt-4o": {
            "prompt": 2.5,
            "completion": 10.0,
            "token_limit": 128_000,
            "is_chat": True,
            "output_limit": 4_096,
        },
        "gpt-4o-mini": {
            "prompt": 0.15,
            "completion": 0.60,
            "token_limit": 128_000,
            "is_chat": True,
            "output_limit": 4_096,
        },
        "o1-preview": {
            "prompt": 15.0,
            "completion": 60.0,
            "token_limit": 128_000,
            "is_chat": True,
            "output_limit": 4_096,
            "use_max_completion_tokens": True,
        },
        "o1-mini": {
            "prompt": 3.0,
            "completion": 12.0,
            "token_limit": 128_000,
            "is_chat": True,
            "output_limit": 4_096,
            "use_max_completion_tokens": True,
        },
        "o1": {
            "prompt": 15.0,
            "completion": 60.0,
            "token_limit": 200_000,
            "is_chat": True,
            "output_limit": 100_000,
            "use_max_completion_tokens": True,
        },
    }

    def __post_init__(self):
        super().__post_init__()
        self.client = OpenAI(api_key=self.api_key)
        self.async_client = AsyncOpenAI(api_key=self.api_key)

    def _count_tokens(self, content: list[dict]) -> int:
        enc = tiktoken.encoding_for_model(self.model)
        # When field name is present, ChatGPT will ignore the role token.
        # Adopted from OpenAI cookbook
        # https://github.com/openai/openai-cookbook/blob/main/examples/How_to_count_tokens_with_tiktoken.ipynb
        # every message follows <im_start>{role/name}\n{content}<im_end>\n
        formatting_token_count = 4

        messages = content
        messages_text = [msg_as_str([message]) for message in messages]
        tokens = [enc.encode(t, disallowed_special=()) for t in messages_text]

        n_tokens_list = []
        for token, message in zip(tokens, messages):
            n_tokens = len(token) + formatting_token_count
            if "name" in message:
                n_tokens += -1
            n_tokens_list.append(n_tokens)
        return sum(n_tokens_list)

    def prepare_input(
        self,
        **kwargs,
    ) -> dict:
        if not kwargs.get("max_completion_tokens") and self.MODEL_INFO[self.model].get(
            "use_max_completion_tokens", False
        ):
            kwargs["max_completion_tokens"] = kwargs.pop("max_tokens", 300)
        return kwargs

    def complete(self, messages: list[dict], **kwargs) -> dict:
        kwargs = self.prepare_input(**kwargs)
        response = self.client.chat.completions.create(
            model=self.model, messages=t.cast(t.Any, messages), stream=False, **kwargs
        )
        if response.choices[0].message.function_call:
            function_call = {
                "name": response.choices[0].message.function_call.name,
                "arguments": json.loads(response.choices[0].message.function_call.arguments),
            }
            completion = ""
        else:
            function_call = {}
            completion = response.choices[0].message.content

        assert response.usage
        return {
            "completion": completion,
            "function_call": function_call,
            "prompt_tokens": response.usage.prompt_tokens,
            "completion_tokens": response.usage.completion_tokens,
        }

    async def acomplete(self, messages: list[dict], **kwargs) -> dict:
        kwargs = self.prepare_input(**kwargs)
        response = await self.async_client.chat.completions.create(
            model=self.model, messages=t.cast(t.Any, messages), stream=False, **kwargs
        )

        assert response.usage
        return {
            "completion": response.choices[0].message.content,
            "prompt_tokens": response.usage.prompt_tokens,
            "completion_tokens": response.usage.completion_tokens,
        }

    def complete_stream(self, messages: list[dict], **kwargs) -> t.Iterator[str]:
        kwargs = self.prepare_input(**kwargs)
        for chunk in self.client.chat.completions.create(
            model=self.model, messages=t.cast(t.Any, messages), stream=True, **kwargs
        ):
            if c := chunk.choices[0].delta.content:
                yield c

    async def acomplete_stream(self, messages: list[dict], **kwargs) -> t.AsyncIterator[str]:
        kwargs = self.prepare_input(**kwargs)
        async for chunk in await self.async_client.chat.completions.create(
            model=self.model, messages=t.cast(t.Any, messages), stream=True, **kwargs
        ):
            if c := chunk.choices[0].delta.content:
                yield c
