"""Locate the exact failing loop, keeping receive/send/cause distinct."""
import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path('scripts').resolve()))
from v9_failure_postmortem import fatal_site


def fixture(tmp_path):
    path=tmp_path/'scheduler.py'
    path.write_text('def _update_from_kv_xfer_finished(self, output):\n    for req_id in output.finished_recving or ():\n        assert req_id in self.requests\n    for req_id in output.finished_sending or ():\n        assert req_id in self.requests\n')
    return path


@pytest.mark.parametrize('line,iterator',[(3,'output.finished_recving or ()'),(5,'output.finished_sending or ()')])
def test_receive_and_send_assertions_are_not_conflated(tmp_path,line,iterator):
    path=fixture(tmp_path);trace=f'File "{path}", line {line}, in _update_from_kv_xfer_finished\nAssertionError'
    result=fatal_site(trace,path)
    assert result['loop_iterator']==iterator and result['line']==line and result['assertion']=='req_id in self.requests'


@pytest.mark.parametrize('bad',['missing_frame','two_frames','wrong_line','not_assertion'])
def test_ambiguous_or_missing_fatal_evidence_is_rejected(tmp_path,bad):
    path=fixture(tmp_path);trace=f'File "{path}", line 3, in _update_from_kv_xfer_finished\nAssertionError'
    if bad=='missing_frame':trace='AssertionError'
    elif bad=='two_frames':trace+=f'\nFile "{path}", line 5, in _update_from_kv_xfer_finished'
    elif bad=='wrong_line':trace=trace.replace('line 3','line 2')
    else:trace=trace.replace('AssertionError','ValueError')
    with pytest.raises(AssertionError):fatal_site(trace,path)
