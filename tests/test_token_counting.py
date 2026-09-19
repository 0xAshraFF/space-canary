from pathlib import Path

import yaml

from space_canary.token_counting import InputTokenCounter


def test_pinned_open_model_tokenizers_measure_full_chat():
    config = yaml.safe_load(Path('config.glm.yaml').read_text())
    counter = InputTokenCounter()
    messages = [{'role': 'user', 'content': 'hello'},
                {'role': 'assistant', 'content': '{"tool":"finish"}'},
                {'role': 'user', 'content': 'continue'}]
    for model in config['models'][:2]:
        short = counter.count(messages[:1], model)
        full = counter.count(messages, model)
        assert full['tokens'] > short['tokens'] > 0
        assert full['source_revision'] == model['tokenizer_revision']
