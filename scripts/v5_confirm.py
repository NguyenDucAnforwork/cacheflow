"""V5 protocol-repair repeats on previously exposed conversations; no fresh-holdout claim."""
import argparse,json
from v4_confirm import build_plan as parent_plan
from v5_validate import execute


def build_plan():
    actions=parent_plan()
    for step in actions:
        if 'run_id' in step:step['run_id']=step['run_id'].replace('v4c1-confirm','v5r2-confirm')
        if 'trace' in step:step['trace']=step['trace'].replace('v4c1-confirm4b','v5-confirm4b').replace('v4-dev4b3','v5-dev4b3')
        if step['kind']=='start_sg':step['budget']=6
    return actions


def main():
    p=argparse.ArgumentParser();p.add_argument('--plan',action='store_true');a=p.parse_args();plan=build_plan()
    if a.plan:
        for step in plan:print(json.dumps(step,sort_keys=True))
    else:execute(plan)


if __name__=='__main__':main()
