"""Poll a Databento batch job once a minute; download and hash its files when done.

Run (detached):  nohup python3 -u data/poll_batch.py JOB_ID >> data/raw/batch_poll.log 2>&1 &
"""

from __future__ import annotations

import sys
import time
from datetime import datetime

import download


def main(job_id: str) -> None:
    import databento as db

    client = db.Historical(download.api_key())
    last = None
    while True:
        try:
            jobs = client.batch.list_jobs(states="queued,processing,done,expired", since="2026-10-01")
            job = next((j for j in jobs if j.get("id") == job_id), None)
        except Exception as e:  # transient API errors: keep polling
            print(f"{datetime.now():%H:%M:%S} poll error: {e}", flush=True)
            job = None
        if job is not None:
            state = job.get("state")
            info = (state, job.get("progress"))
            if info != last:
                print(f"{datetime.now():%H:%M:%S} {job_id} state={state} progress={job.get('progress')} "
                      f"cost_usd={job.get('cost_usd')} size={job.get('package_size')}", flush=True)
                last = info
            if state == "done":
                download.fetch_batch(job_id)
                print(f"{datetime.now():%H:%M:%S} FETCHED", flush=True)
                return
            if state == "expired":
                print(f"{datetime.now():%H:%M:%S} EXPIRED", flush=True)
                return
        time.sleep(60)


if __name__ == "__main__":
    main(sys.argv[1])
