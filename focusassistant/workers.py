"""A bounded daemon worker: a blocked local API cannot keep a closed GUI alive."""
from concurrent.futures import Future
from queue import Empty, Queue
from threading import Thread


class Worker:
    def __init__(self, name):
        self.queue = Queue(maxsize=2)
        self.closed = False
        self.thread = Thread(target=self.run, name=name, daemon=True)
        self.thread.start()

    def submit(self, function, *args):
        if self.closed:
            raise RuntimeError("Worker is closed")
        future = Future()
        self.queue.put_nowait((future, function, args))
        return future

    def run(self):
        while True:
            job = self.queue.get()
            if job is None:
                return
            future, function, args = job
            if future.set_running_or_notify_cancel():
                try:
                    future.set_result(function(*args))
                except BaseException as exc:
                    future.set_exception(exc)

    def shutdown(self):
        self.closed = True
        while True:
            try:
                job = self.queue.get_nowait()
                if job:
                    job[0].cancel()
            except Empty:
                break
        self.queue.put_nowait(None)
