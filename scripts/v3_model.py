"""Pinned model registry for V3; adopting a model requires verified local weights."""
from pathlib import Path

HOME = Path('/workspace/.hf_home/hub')
MODELS = {
    'qwen3-1.7b': dict(repo='Qwen/Qwen3-1.7B', revision='70d244cc86ccca08cf5af4e1e306ecf908b1ad5e',
                      bytes_per_token=114688, adoption=None),
    'qwen3-4b': dict(repo='Qwen/Qwen3-4B', revision='1cfa9a7208912126459214e8b04321603b3df60c',
                    bytes_per_token=147456, adoption='results/v3/qwen3_4b_adoption.json'),
}


def get_model(key):
    spec = MODELS[key].copy()
    spec['path'] = str(HOME / ('models--'+spec['repo'].replace('/', '--')) / 'snapshots' / spec['revision'])
    spec['served_name'] = 'cacheflow-'+key
    return spec
