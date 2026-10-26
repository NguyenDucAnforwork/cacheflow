"""Canonical QA prompt repair: consistent abstention without changing evidence."""
from cacheflow.locomo import context_prefix,question_prompt

LEGACY_FOOTER="\nAnswer the question using only the conversation above. If the answer is not stated, say 'I don't know'.\nQuestion:\n"
OFFICIAL_FOOTER='\nAnswer the question using only the conversation above. If the answer is not stated, respond with exactly: No information available.\nQuestion:\n'
SYSTEM=('Answer the question using only the supplied conversation. Return only a concise answer, '
        'without explanation, reasoning, repetition, or restating the question. '
        'If the answer is not present in the conversation, answer "No information available.".')


def user_prompt(conversation,question):
    prefix=context_prefix(conversation)
    if not prefix.endswith(LEGACY_FOOTER):
        raise ValueError('Canonical context footer changed; refuse broad string replacement')
    repaired=prefix[:-len(LEGACY_FOOTER)]+OFFICIAL_FOOTER
    return question_prompt(repaired,question)


def render(tokenizer,conversation,question):
    user=user_prompt(conversation,question)
    return tokenizer.apply_chat_template([{'role':'system','content':SYSTEM},{'role':'user','content':user}],
        tokenize=False,add_generation_prompt=True,enable_thinking=False)
