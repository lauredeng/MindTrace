import argparse
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core import backup
from core.repository import Repository


def main():
    parser=argparse.ArgumentParser(description='Create a verified backup or restore into a new empty location.')
    sub=parser.add_subparsers(dest='command',required=True)
    create=sub.add_parser('create');create.add_argument('--database',required=True);create.add_argument('--data-root',required=True);create.add_argument('--to',required=True)
    restore=sub.add_parser('restore');restore.add_argument('--from',dest='source',required=True);restore.add_argument('--to',required=True)
    args=parser.parse_args()
    if args.command=='create':backup.create(Repository(args.database),args.data_root,args.to)
    else:backup.restore(args.source,args.to)
    print('Backup operation completed; source records were not overwritten.')


if __name__=='__main__':main()
