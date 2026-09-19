"""Pre-dispatch input measurement using pinned official tokenizers/APIs."""
import json
import os
import urllib.error
import urllib.request

from huggingface_hub import hf_hub_download
from tokenizers import Tokenizer
from transformers import PreTrainedTokenizerFast


class TokenMeasurementError(RuntimeError):
    pass


class InputTokenCounter:
    def __init__(self):
        self._counters = {}

    def count(self, messages, model):
        method = model['token_count_method']
        if method == 'glm_official_hf_template':
            return self._count_glm(messages, model)
        if method == 'deepseek_official_encoding':
            return self._count_deepseek(messages, model)
        if method == 'anthropic_count_tokens_api':
            return self._count_anthropic(messages, model)
        raise TokenMeasurementError(f'Unsupported token-count method: {method}')

    def _download(self, model, filename):
        return hf_hub_download(model['tokenizer_repo'], filename,
                               revision=model['tokenizer_revision'])

    def _count_glm(self, messages, model):
        key = (model['tokenizer_repo'], model['tokenizer_revision'], 'glm')
        tokenizer = self._counters.get(key)
        if tokenizer is None:
            tokenizer = PreTrainedTokenizerFast(tokenizer_file=self._download(model, 'tokenizer.json'))
            with open(self._download(model, 'chat_template.jinja')) as stream:
                tokenizer.chat_template = stream.read()
            self._counters[key] = tokenizer
        ids = tokenizer.apply_chat_template(messages, tokenize=True, add_generation_prompt=True,
                                            tools=None, reasoning_effort='low')
        return {'tokens': len(ids), 'method': model['token_count_method'],
                'source_revision': model['tokenizer_revision']}

    def _count_deepseek(self, messages, model):
        key = (model['tokenizer_repo'], model['tokenizer_revision'], 'deepseek')
        tokenizer = self._counters.get(key)
        if tokenizer is None:
            tokenizer = Tokenizer.from_file(self._download(model, 'tokenizer.json'))
            self._counters[key] = tokenizer
        # Restricted text-only rendering from DeepSeek-V3.2's official
        # encoding/encoding_dsv32.py, chat (non-thinking) mode.
        prompt = '<｜begin▁of▁sentence｜>'
        for message in messages:
            role, content = message['role'], message['content']
            if role == 'system':
                prompt += content
            elif role == 'user':
                prompt += '<｜User｜>' + content + '<｜Assistant｜></think>'
            elif role == 'assistant':
                prompt += content + '<｜end▁of▁sentence｜>'
            else:
                raise TokenMeasurementError(f'Unsupported DeepSeek role: {role}')
        return {'tokens': len(tokenizer.encode(prompt).ids), 'method': model['token_count_method'],
                'source_revision': model['tokenizer_revision']}

    def _count_anthropic(self, messages, model):
        key = os.environ.get('ANTHROPIC_API_KEY')
        if not key:
            raise TokenMeasurementError('ANTHROPIC_API_KEY is required for Claude token counting')
        payload = {'model': model['native_model_id'], 'messages': messages}
        request = urllib.request.Request(
            'https://api.anthropic.com/v1/messages/count_tokens',
            data=json.dumps(payload).encode('utf-8'), method='POST',
            headers={'x-api-key': key, 'anthropic-version': '2023-06-01',
                     'content-type': 'application/json'})
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                result = json.load(response)
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
            raise TokenMeasurementError(f'Claude token measurement failed; inference not dispatched: {exc}') from exc
        return {'tokens': int(result['input_tokens']), 'method': model['token_count_method'],
                'source_revision': model['native_model_id']}
