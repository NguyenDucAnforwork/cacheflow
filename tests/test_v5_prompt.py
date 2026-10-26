from dataclasses import replace
from cacheflow.locomo import Conversation,Session,Turn,Question,context_prefix,question_prompt
from cacheflow.v5_prompt import LEGACY_FOOTER,OFFICIAL_FOOTER,user_prompt


def test_only_canonical_instruction_changes_and_question_or_conversation_quotation_is_preserved():
    question=Question(0,'Why quote '+LEGACY_FOOTER+'?', 'SECRET_GOLD', 'SECRET_DISTRACTOR',5,('SECRET_EVIDENCE',),(),False)
    conversation=Conversation('test','A','B',(Session(1,'2026-01-01',(Turn('A','D1:1','A literal quote:'+LEGACY_FOOTER,None),)),),(question,))
    expected=question_prompt(context_prefix(conversation)[:-len(LEGACY_FOOTER)]+OFFICIAL_FOOTER,question)
    actual=user_prompt(conversation,question)
    assert actual==expected
    assert 'A literal quote:'+LEGACY_FOOTER in actual and question.text in actual
    assert all(secret not in actual for secret in ['SECRET_GOLD','SECRET_DISTRACTOR','SECRET_EVIDENCE'])
    assert user_prompt(conversation,replace(question,answer='OTHER_GOLD',category=1,evidence=('OTHER',)))==actual
