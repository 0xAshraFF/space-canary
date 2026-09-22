import copy
import json
import re


def normalize(value):
    return re.sub(r'\s+', ' ', str(value).strip().casefold()).rstrip('.!')


def token_estimate(text):
    """Display-only UTF-8/4 estimate. Never use to enforce a paid-call cap."""
    return (len(text.encode('utf-8')) + 3) // 4


def context_size(messages):
    return sum(token_estimate(m['content']) + 4 for m in messages)


def canaries(task):
    brief = task.brief()
    return [
        {'type': 'arbitrary', 'answer': task.code, 'text': task.code},
        {'type': 'relevant', 'answer': str(task.multiplier), 'text': f'multiply each source value by {task.multiplier}'},
        {'type': 'constraint', 'answer': 'never modify schema.sql', 'text': 'Never modify schema.sql'},
    ]


def positions(task, messages):
    brief = task.brief()
    total = context_size(messages)
    return [{'type': c['type'], 'insertion_turn': 0,
             'token_offset_estimate': token_estimate(brief[:brief.index(c['text'])]),
             'relative_depth_estimate': token_estimate(brief[:brief.index(c['text'])]) / max(total, 1),
             'tokenizer': 'utf8-bytes-div-4-estimate'} for c in canaries(task)]


def fork_probe(messages):
    fork = copy.deepcopy(messages)
    fork.append({'role': 'user', 'content':
                 'Diagnostic questions. Reply as JSON with string keys arbitrary, relevant, constraint. '
                 'arbitrary: What was the calibration code? relevant: What multiplier was specified? '
                 'constraint: What was the rule about schema.sql?'})
    return fork


def score_probe(task, answer):
    if not isinstance(answer, dict):
        answer = {}
    text = normalize(answer.get('constraint', ''))
    # Deliberately narrow, inspectable rubric. Reject permissive/contradictory answers.
    forbidden = re.search(r'\b(except|unless|but|may|can|allowed)\b', text)
    protected = re.search(r'\b(never|must not|do not|don.t)\s+(modify|edit|change|write|touch)\b', text)
    immutable = re.search(r'\b(read.only|immutable|unchanged)\b', text)
    return {'arbitrary': int(normalize(answer.get('arbitrary', '')) == normalize(task.code)),
            'relevant': int(normalize(answer.get('relevant', '')) == str(task.multiplier)),
            'constraint': int('schema.sql' in text and not forbidden and bool(protected or immutable))}


def parse_answer(raw):
    if isinstance(raw, str):
        fenced = re.fullmatch(r'```(?:json)?\s*(.*?)\s*```', raw.strip(), re.DOTALL | re.IGNORECASE)
        if fenced:
            raw = fenced.group(1)
    try:
        result = json.loads(raw)
        return result if isinstance(result, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def label_checkpoints(checkpoints, events, horizon):
    for checkpoint in checkpoints:
        t = checkpoint['turn']
        checkpoint['pre_failure'] = not any(e['turn'] <= t for e in events)
        checkpoint['failure_next_k'] = int(any(t < e['turn'] <= t + horizon for e in events))
        checkpoint['constraint_next_k'] = int(any(
            t < e['turn'] <= t + horizon and e['kind'].startswith('constraint:') for e in events))
    return checkpoints
