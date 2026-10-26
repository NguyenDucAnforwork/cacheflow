"""Opt-in event subscriber for isolated KV-path profiling, disabled for final runs."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path


def main():
    from lmcache.v1.mp_observability import config
    from lmcache.v1.mp_observability.event import EventType
    from lmcache.v1.mp_observability.event_bus import EventSubscriber

    target = Path(os.environ['CACHEFLOW_KV_EVENTS'])
    target.parent.mkdir(parents=True, exist_ok=True)

    class Recorder(EventSubscriber):
        def __init__(self):
            self.file = target.open('a', buffering=1)

        def get_subscriptions(self):
            return {kind: self.record for kind in EventType
                    if kind.name.startswith('MP_') and kind.name not in ('MP_TOKENS', 'MP_LOOKUP')}

        def record(self, event):
            payload = dict(event_type=event.event_type.value, timestamp=event.timestamp,
                           observed_wall=time.time(), observed_monotonic_ns=time.monotonic_ns(),
                           session_id=event.session_id, metadata={k:v for k,v in event.metadata.items()
                               if v is None or isinstance(v, (str,int,float,bool))})
            self.file.write(json.dumps(payload, default=str)+'\n')

        def shutdown(self):
            self.file.close()

    original = config.init_observability

    def instrumented(*args, **kwargs):
        bus = original(*args, **kwargs)
        bus.register_subscriber(Recorder())
        return bus

    config.init_observability = instrumented
    from lmcache.cli.main import main as cli_main
    cli_main()


if __name__ == '__main__':
    main()
