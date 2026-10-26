"""Small synthetic source fixtures; not full1986QA regeneration evidence."""
import gzip
import json
import sys
from dataclasses import asdict,replace
from pathlib import Path
from types import SimpleNamespace
import pytest
sys.path.insert(0,str(Path('scripts').resolve()))
import v6_regenerate_full_inputs as module
from cacheflow.locomo import build_trace,load_locomo,trace_digest
from cacheflow.v5_prompt import render


class CharacterTokenizer:
    def encode(self,text,*,add_special_tokens):
        assert not add_special_tokens
        return list(text.encode())
    def apply_chat_template(self,messages,**kwargs):
        assert kwargs==dict(tokenize=False,add_generation_prompt=True,enable_thinking=False)
        return ''.join(f"<{m['role']}>{m['content']}</{m['role']}>" for m in messages)+'<assistant>'


def source(tmp_path):
    data=[]
    for sample,n in [('conv-a',2),('conv-b',1)]:
        data.append(dict(sample_id=sample,conversation=dict(speaker_a='A',speaker_b='B',session_1_date_time='today',
            session_1=[dict(dia_id='D1:1',speaker='A',text='visible conversation')]),
            qa=[dict(question=f'Question{i}?',answer='SECRET_GOLD',category=1 if i==0 else 5,evidence=['D1:1']) for i in range(n)]))
    path=tmp_path/'official.json';path.write_text(json.dumps(data));return path


def test_regeneration_matches_independent_builder_and_never_renders_gold(tmp_path):
    conversations=load_locomo(source(tmp_path));tok=CharacterTokenizer()
    rows,fingerprints=module.source_rows(conversations,tok,['conv-a','conv-b'])
    assert [r.request_id for r in rows]==['conv-a-q000','conv-b-q000','conv-a-q001']
    assert len(fingerprints)==3 and all('SECRET_GOLD' not in r.prompt for r in rows)
    original,_=build_trace(conversations,tok,max_model_len=32768,output_tokens=96,qps=4,seed=901,arrival='interleaved')
    expected=[]
    by={c.sample_id:c for c in conversations}
    for r in original:
        text=render(tok,by[r.sample_id],by[r.sample_id].questions[r.qa_index])
        expected.append(replace(r,prompt=text,input_tokens=len(tok.encode(text,add_special_tokens=False))))
    path=tmp_path/'new.gz';digest=module.write_schedule(rows,path,901,4)
    with gzip.open(path,'rt') as stream:actual=[json.loads(l) for l in stream]
    assert actual==[asdict(r) for r in expected] and digest==trace_digest(expected)
    with pytest.raises(AssertionError):module.write_schedule(rows,path,902,4)
    with pytest.raises(AssertionError):module.source_rows(conversations,tok,['conv-b','conv-a'])


def test_only_arrivals_change_between_regenerated_seeds(tmp_path):
    rows,_=module.source_rows(load_locomo(source(tmp_path)),CharacterTokenizer(),['conv-a','conv-b'])
    schedules=[]
    for seed in [901,902,903]:
        path=tmp_path/f'{seed}.gz';module.write_schedule(rows,path,seed,4)
        with gzip.open(path,'rt') as stream:schedules.append([json.loads(l) for l in stream])
    assert len({tuple(r['offset_ms'] for r in schedule) for schedule in schedules})==3
    base=[{k:v for k,v in r.items() if k!='offset_ms'} for r in schedules[0]]
    assert all([{k:v for k,v in r.items() if k!='offset_ms'} for r in schedule]==base for schedule in schedules)


def test_waiter_handles_only_registered_process_lifetime(monkeypatch):
    sleeps=[];r=dict(after_pid=123,after_create_time=10,after_argv=['controller'])
    def process(pid):
        assert pid==123
        return SimpleNamespace(create_time=lambda:10,is_running=lambda:True,status=lambda:'zombie' if sleeps else 'running',cmdline=lambda:['controller'])
    monkeypatch.setattr(module.psutil,'Process',process);monkeypatch.setattr(module.time,'sleep',lambda seconds:sleeps.append(seconds))
    module.wait_parent(r);assert sleeps==[5]
    monkeypatch.setattr(module.psutil,'Process',lambda pid:SimpleNamespace(create_time=lambda:11))
    module.wait_parent(r);assert sleeps==[5],'Do not wait on a reused PID'


def test_missing_parent_and_idle_guard_prevent_rendering(tmp_path,monkeypatch):
    def missing(pid):raise module.psutil.NoSuchProcess(pid)
    monkeypatch.setattr(module.psutil,'Process',missing)
    module.wait_parent(dict(after_pid=123,after_create_time=10,after_argv=['controller']))
    path=tmp_path/'registration.json';path.write_text(json.dumps(dict(kind='cpu_only_from_official_source_full_input_regeneration',after_pid=123,after_create_time=10)))
    monkeypatch.setattr(module,'wait_parent',lambda r:None)
    def busy():raise AssertionError('Serving must be idle')
    monkeypatch.setattr(module,'idle',busy)
    monkeypatch.setattr(module,'source_rows',lambda *a,**k:pytest.fail('Must not render while serving'))
    with pytest.raises(AssertionError,match='Serving must be idle'):module.execute(path)
    assert not path.with_suffix('.result.json').exists()


def test_parent_exit_during_poll_is_terminal_without_retry(monkeypatch):
    def gone():raise module.psutil.NoSuchProcess(123)
    monkeypatch.setattr(module.psutil,'Process',lambda pid:SimpleNamespace(create_time=lambda:10,is_running=lambda:True,status=gone))
    monkeypatch.setattr(module.time,'sleep',lambda _:pytest.fail('Parent has already exited'))
    module.wait_parent(dict(after_pid=123,after_create_time=10,after_argv=['controller']))
