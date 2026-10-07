"""A picture answered in words, for a model that cannot see it.

The image goes to a vision model the user named (``provider/model``) with a question, and the
answer comes back as text. The browser's screenshots used this first (``browser.vision_model``);
the corpus's page and figure images use it as well (``documents.vision_model``). FrontierAgent's
reader works the same way through its READDOC_VISION_* gateway: a main model without vision is
handed a transcription instead of pixels.
"""
import time

from misaka.core.web import config


async def describe(image, question, ctx, selected, *, setting, purpose, max_tokens=2048):
    """The text the vision model ``selected`` answers ``question`` with about ``image`` (a content
    block). ``setting`` names the knob that chose the model, for the errors; ``purpose`` is the
    accounting label. Raises ValueError when the model cannot be used or the call fails."""
    from misaka.ai.stream import complete_simple
    from misaka.ai.types import SimpleStreamOptions
    from misaka.ai.utils.headers import provider_headers_to_record
    from misaka.core.web.accounting import account_call

    provider, separator, model_id = selected.partition('/')
    registry = getattr(ctx, 'modelRegistry', None)
    model = registry.find(provider, model_id) if registry is not None and separator else None
    if model is None or 'image' not in model.input:
        raise ValueError(f'{setting} must identify an available vision model as provider/model')
    auth = await registry.getAuth(model)
    if auth is None:
        raise ValueError(f'The vision model {setting} names has no authentication')
    if auth.auth.baseUrl:
        model = model.model_copy(update={'baseUrl': auth.auth.baseUrl})
    options = SimpleStreamOptions(apiKey=auth.auth.apiKey, headers=provider_headers_to_record(auth.auth.headers),
                                  env=auth.env, signal=getattr(ctx, 'signal', None), maxTokens=max_tokens)
    async with account_call(purpose, provider, question, unit='provider_operation') as facts:
        result = await complete_simple(model, {'messages': [{'role': 'user', 'content': [
            {'type': 'text', 'text': question}, image], 'timestamp': int(time.time() * 1000)}]}, options)
        usage = getattr(result, 'usage', None)
        if usage is not None:
            facts['model_usage'] = usage.model_dump()
    if getattr(result, 'stopReason', None) in {'error', 'aborted'}:
        raise ValueError(getattr(result, 'errorMessage', None) or f'The vision model {setting} names failed')
    return config.redact_secrets(''.join(getattr(item, 'text', '') for item in result.content))
