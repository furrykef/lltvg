#!/usr/bin/env python
# By hcs with tweaks by Kef Schecter
# Requires Python 2.7 or greater
from __future__ import division
from contextlib import contextmanager
from struct import unpack, pack
import argparse
import sys
import wave


EN_SAMPLE_RATES = (
    12000,  # File 0
    15000,  # File 1
    7000,   # File 2
)

JA_SAMPLE_RATES = (
    12000,  # File 0
    15000,  # File 1
    6000,   # File 2
)


# Wave_write objects can raise an exception on close.
# This fixes it so that it will not throw on close if used with the
# 'with' statement.
@contextmanager
def my_wave_open(filename, mode=None):
    wav = wave.open(filename, mode)
    try:
        yield wav
    finally:
        try:
            wav.close()
        except:
            pass


def main(argv=None):
    global header_base_offset
    global data_max_offset
    global data_base_offset

    if argv is None:
        argv = sys.argv[1:]

    args = parseArgs(argv)

    header_infile = args.ctl_file
    data_infile = args.tbl_file

    with header_infile, data_infile:
        header_base_offset = 0
        data_max_offset = 0
        data_base_offset = 0

        bank_sizes = (1, 1, 0x13)
        file_idx = 0
        for file_banks in bank_sizes:
            for bank_idx in range(file_banks):
                print "doing file %d, bank %d at %08x, %08x" % (file_idx, bank_idx, header_base_offset, data_base_offset)
                header_max_offset = 0
                for sample_idx in xrange(0, 128):
                    header_infile.seek(header_base_offset + sample_idx * 4)
                    sample_offset = unpack('>I', header_infile.read(4))[0]

                    if sample_offset == 0:
                        continue

                    header_max_offset = max(header_max_offset, header_base_offset+sample_offset)

                    outfile_name_base = '%s%02x_%02x_%02x' % (args.prefix, file_idx, bank_idx, sample_idx)
                    if args.japanese:
                        sample_rate = JA_SAMPLE_RATES[file_idx]
                    else:
                        sample_rate = EN_SAMPLE_RATES[file_idx]
                    process_sample_pair(header_infile, data_infile, sample_offset, outfile_name_base, sample_rate)

                # next bank
                header_base_offset = header_max_offset + 0x20

            # next file
            data_base_offset = (data_max_offset + 15)//16*16
            #print data_max_offset,data_base_offset

            file_idx += 1


def process_sample_pair(header_infile, data_infile, sample_header_offset, outfile_name_base, sample_rate):
    global header_base_offset

    header_infile.seek(header_base_offset+sample_header_offset+0x10)
    true_header_offset1, true_header_offset2 = unpack('>IxxxxI', header_infile.read(12))

    outfile_name = outfile_name_base + "_0"
    process_sample(header_infile, data_infile, true_header_offset1, sample_rate, outfile_name)
    if true_header_offset2 != 0:
        outfile_name = outfile_name_base + "_1"
        process_sample(header_infile, data_infile, true_header_offset2, sample_rate, outfile_name)

def process_sample(header_infile, data_infile, true_header_offset, sample_rate, outfile_name):
    global data_max_offset, header_base_offset, data_base_offset

    header_infile.seek(header_base_offset+true_header_offset)

    sample_size, sample_offset, info_offset, coef_offset = \
        unpack('>IIII', header_infile.read(16))

    format = 0
    if sample_size >= 0x20000000:
        sample_size -= 0x20000000
        format = 1

    data_max_offset = max(data_max_offset, data_base_offset+sample_offset+sample_size)

    if format == 1:
        outfile_name += '.bin'
        print 'dumping %s at %08x, size %08x' % (outfile_name, data_base_offset+sample_offset, sample_size)
        data_infile.seek(sample_offset+data_base_offset)
        with open(outfile_name, 'wb') as outfile:
            for i in range(sample_size):
                outfile.write(data_infile.read(1))
        return

    # read general header
    header_infile.seek(header_base_offset+info_offset)
    unk1, sample_count, unk2, unk3 = unpack('>IIII', header_infile.read(16))

    # read coefficient bank
    header_infile.seek(header_base_offset+coef_offset)
    channels1, npredictors = unpack('>II', header_infile.read(8))

    coefs = {}
    for i in range(0,npredictors*16):
        coefs[i] = unpack('>h', header_infile.read(2))[0]

    outfile_name += '.wav'
    print 'decoding %s at %08x, size %08x, samples %d' % (outfile_name, data_base_offset+sample_offset, sample_size, sample_count)

    with my_wave_open(outfile_name, 'wb') as outfile:
        outfile.setnchannels(1)
        outfile.setsampwidth(2)
        outfile.setframerate(sample_rate)
        outfile.setnframes(sample_count)
        decode_VADPCM(npredictors, coefs, sample_offset, sample_count, data_infile, outfile)


# based on icemario's code as found in N64AIFCAudio.cpp
# clips a little...
def decode_VADPCM(npredictors, coefs, sample_offset, sample_count, data_infile, outfile):
    #print "decode at %08x" % (data_base_offset+sample_offset)
    data_infile.seek(data_base_offset+sample_offset)

    clip_count = 0

    hist = (0,0,0,0,0,0,0,0)
    out = {}

    for i in xrange(0, sample_count, 16):
        frame = data_infile.read(9)

        scale = 1<<(ord(frame[0])>>4)
        pred = (ord(frame[0])&0xf) * 16

        for k in range(2):
            samples = {}
            for j in range(8):
                sample = ord(frame[1+k*4+j//2])
                if (j&1):
                    sample = sample&0xf
                else:
                    sample = sample>>4

                if sample >= 8:
                    sample -= 16

                samples[j] = sample * scale

            for j in range(8):
                total = coefs[pred+0+j] * hist[6]
                total += coefs[pred+8+j] * hist[7]

                if j>0:
                    for x in range(j):
                        total += samples[((j-1)-x)] * coefs[pred+8+x]

                total = ((samples[j] << 11) + total) >> 11

                if (total > 32767):
                    total = 32767
                    clip_count += 1
                elif total < -32768:
                    total = -32768
                    clip_count += 1

                outfile.writeframesraw(pack('<h', total))

                out[j] = total
            hist = out
            out = {}

    if clip_count > 0:
        print "clipped %d times" % clip_count


# @TODO@ -- argparse calls sys.exit() in case of '--help' or failure
# @TODO@ -- I do not like argparse.FileType at all
def parseArgs(argv):
    parser = argparse.ArgumentParser(description="Star Fox 64 sound ripper")
    parser.add_argument(
        "ctl_file",
        type=argparse.FileType('rb'),
        help="filename of the CTL file"
    )
    parser.add_argument(
        "tbl_file",
        type=argparse.FileType('rb'),
        help="filename of the TBL file"
    )
    parser.add_argument(
        "--prefix",
        default="sample_",
        help="prefix for output files"
    )
    parser.add_argument(
        "--japanese", "--ja", "--jp",
        action="store_true",
        default=False,
        help="use sample rates for Japanese ROM"
    )
    return parser.parse_args(argv)


if __name__ == '__main__':
    sys.exit(main())
