#!/usr/bin/env python
# Battletoads script extractor by Kef Schecter
# Written for Python 2.7
from __future__ import division
import sys

BASE = 0x28010

def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    romname = argv[0]
    ZERO_TABLE = BASE + int(argv[1], 16)
    ONE_TABLE = BASE + int(argv[2], 16)
    END_TABLE = BASE + int(argv[3], 16)
    txtptr = BASE + int(argv[4], 16)
    num_blocks = int(argv[5])
    with open(romname, 'rb') as f:
        romdata = [ord(ch) for ch in f.read()]
    out = []
    node = 0
    blocks_processed = 0
    while blocks_processed < num_blocks:
        byte = romdata[txtptr]
        for i in range(8):
            if byte & 0x80:
                node = romdata[ONE_TABLE+node]
            else:
                node = romdata[ZERO_TABLE+node]
            if node >= 0x80:
                node = romdata[END_TABLE+node]
                if node == 0xfd:
                    blocks_processed += 1
                out.append(chr(node))
                node = 0
            byte <<= 1
            byte &= 0xff
        txtptr += 1
    sys.stdout.write("".join(out))

if __name__ == '__main__':
    sys.exit(main())
