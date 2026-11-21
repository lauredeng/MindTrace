"""Explicit independent worker process: survives browser disconnects."""
import argparse
import os
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core.background import Worker,configured_repository


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--once',action='store_true')
    args=parser.parse_args()
    os.environ['MINDTRACE_HEADLESS']='1'
    repository=configured_repository()
    if repository is None:raise SystemExit('请设置 MINDTRACE_DATABASE 为持久数据库路径。')
    worker=Worker(repository)
    if args.once:worker.tick()
    else:worker.run()


if __name__=='__main__':main()
