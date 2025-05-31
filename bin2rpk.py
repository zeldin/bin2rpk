#!/usr/bin/env python

import argparse
import pathlib
import sys
import xml.etree.ElementTree as ET
import zipfile

from collections import defaultdict
from enum import Enum, auto

paged_pcbs = {'7': "paged7", '12k': "paged12k", '16k': "paged",
              '377': "paged377", '378': "paged378", '379': "paged379i"}


class BinfileType(Enum):
    C = auto()
    D = auto()
    G = auto()


def get_bankinghint(fn):
    fn = fn.lower()
    if fn.endswith(".bin"):
        fn = fn[:-4]
    if len(fn) > 0:
        return fn[-1]
    else:
        return None


def binfile_type_from_name(fn):
    fn = fn.lower()
    if fn.endswith(".bin"):
        fn = fn[:-4]
    if fn.endswith("g"):
        return BinfileType.G
    elif fn.endswith("d"):
        return BinfileType.D
    else:
        return BinfileType.C


def binfile_name_change_to_type(fn, target):
    if binfile_type_from_name(fn) == target:
        return fn
    if fn.lower().endswith(".bin"):
        p = -5
    else:
        p = -1
    if len(fn) < -p:
        return None
    c = fn[p].lower()
    rep = target.name
    if c == fn[p]:
        rep = rep.lower()
    if c == 'g' or c == 'c' or c == 'd':
        fn = list(fn)
        fn[p] = rep
        return "".join(fn)
    else:
        return None


def needs_gromemul(data):
    if data is None:
        return False
    for b in range(0, len(data), 8192):
        slice = data[b:b+8192]
        if len(slice) > 6144:
            extra = slice[6144:]
            garbage = bytearray(len(extra))
            for o in range(0, len(extra)):
                garbage[o] = slice[o+0x800] | slice[o+0x1000]
            if (extra.count(b'\0') < len(extra) and extra != garbage):
                return True
    return False


def find_main_file_in_zip(zip):
    bins = defaultdict(list)
    for f in zip.namelist():
        if (f.lower().endswith(".bin")):
            bins[binfile_type_from_name(f)].append(f)
    if len(bins[BinfileType.G]) == 1:
        choice = bins[BinfileType.G].pop()
    elif len(bins[BinfileType.C]) == 1:
        choice = bins[BinfileType.C].pop()
    else:
        raise RuntimeError("Unable to guess main bin in provided zip")
    return zipfile.Path(zip, at=choice)


class Cartridge:

    def __init__(self, path=None):
        self.pcbtype = None
        self.cbin = None
        self.dbin = None
        self.gbin = None
        self.mainbin = None
        self.bankinghint = None
        self.cname = "c.bin"
        self.dname = "d.bin"
        self.gname = "g.bin"
        if path is not None:
            self.load(path)

    def _load_bin(self, path, target):
        newname = binfile_name_change_to_type(path.name, target)
        if newname is None:
            return None
        elif newname != path.name:
            path = path.parent.joinpath(newname)
            if not path.exists():
                return None
        if target == BinfileType.C:
            # self.cname = path.name
            self.bankinghint = get_bankinghint(path.name)
        # elif target == BinfileType.D:
        #     self.dname = path.name
        # elif target == BinfileType.G:
        #     self.gname = path.name
        print("Loading %s" % (path,))
        return path.read_bytes()

    def load(self, path):
        if not isinstance(path, zipfile.Path) and zipfile.is_zipfile(path):
            with zipfile.ZipFile(path) as zip:
                self.load(find_main_file_in_zip(zip))
            return
        self.cbin = self._load_bin(path, BinfileType.C)
        self.dbin = self._load_bin(path, BinfileType.D)
        self.gbin = self._load_bin(path, BinfileType.G)
        if self.dbin is not None and self.cbin is None:
            raise RuntimeError("Found d.bin without c.bin!")
        if self.gbin is not None:
            self.mainbin = self.gbin
        elif self.cbin is not None:
            self.mainbin = self.cbin
        elif self.dbin is not None:
            raise RuntimeError("Missing main bin (only d.bin provided)")
        else:
            raise RuntimeError("Missing main bin")

    def select_pcb_type(self, paged=None):
        if self.mainbin[3] in {ord('R'), ord('G'), ord('X')}:
            raise RuntimeError("FinalGROM advanced modes not supported")
        if paged is not None:
            self.pcbtype = paged_pcbs[paged]
        else:
            if needs_gromemul(self.gbin):
                print("Selected pcbtype gromemu because of 8K/GROM data")
                self.pcbtype = "gromemu"
            elif self.dbin is not None:
                if len(self.cbin) == 4096:
                    print("Selected pcbtype paged12k because c.bin is 4K")
                    self.pcbtype = "paged12k"
                elif len(self.cbin) == 8192:
                    print("Selected pcbtype paged because c.bin is 8K")
                    self.pcbtype = "paged"
                else:
                    raise RuntimeError("d.bin found together with a c.bin "
                                       "that is neither 4K or 8K!?")
            elif self.cbin is None or len(self.cbin) <= 8192:
                print("Selected pcbtype standard because no bank switching "
                      "is needed")
                self.pcbtype = "standard"
            else:
                if self.bankinghint == '3' or self.bankinghint == '9':
                    print("Selected pcbtype paged379i because name "
                          "ends with a %s" % (self.bankinghint,))
                    self.pcbtype = "paged379i"
                elif self.bankinghint == '7':
                    print("Selected pcbtype paged377 because name "
                          "ends with a 7")
                    self.pcbtype = "paged377"
                elif self.bankinghint == '8':
                    print("Selected pcbtype paged378 because name "
                          "ends with a 8")
                    self.pcbtype = "paged378"
                elif len(self.cbin) > 524288:
                    print("Selected pcbtype paged377 because c.bin "
                          "is larger than 512K")
                    self.pcbtype = "paged377"
                else:
                    print("Selected pcbtype paged378")
                    self.pcbtype = "paged378"
        if needs_gromemul(self.gbin) and self.pcbtype != "gromemu":
            raise RuntimeError("8K/GROM data can not be used with pcbtype %s"
                               % (self.pcbtype,))
        if (self.gbin is not None and len(self.gbin) > 40960 and
                self.pcbtype != "paged378"):
            raise RuntimeError(">40K GROM data can not be used with pcbtype %s"
                               % (self.pcbtype,))
        if (self.dbin is not None and self.pcbtype != "paged" and
                self.pcbtype != "paged12k" and self.pcbtype != "gromemu"):
            raise RuntimeError("d.bin can not be used with pcbtype %s"
                               % (self.pcbtype,))
        if self.dbin is None and (
                self.pcbtype == "paged" or self.pcbtype == "paged12k"):
            raise RuntimeError("pcbtype %s requires d.bin" % (self.pcbtype,))
        if self.cbin is None and self.pcbtype.startswith("paged"):
            raise RuntimeError("pcbtype %s requires c.bin" % (self.pcbtype,))
        if self.pcbtype == "standard":
            if self.cbin is not None and len(self.cbin) > 8192:
                raise RuntimeError("pcbtype standard can not handle ROM "
                                   "larger than 8K")
        elif self.pcbtype == "gromemu":
            if self.dbin is not None:
                if len(self.cbin) == 8192:
                    self.cbin = self.cbin + self.dbin
                    self.dbin = None
                else:
                    raise RuntimeError("Can't use d.bin with pcbtype "
                                       "gromemu unless c.bin is 8K")
            if self.cbin is not None and len(self.cbin) > 33554432:
                raise RuntimeError("pcbtype gromemu can not handle ROM "
                                   "larger than 32M")
        elif self.pcbtype == "paged7":
            if len(self.cbin) > 16384:
                raise RuntimeError("pcbtype paged7 can not handle ROM "
                                   "larger than 16K")
        elif self.pcbtype == "paged12k":
            if len(self.cbin) > 4096:
                raise RuntimeError("pcbtype paged12k can not handle c.bin "
                                   "larger than 4K")
            if len(self.dbin) > 8192:
                raise RuntimeError("pcbtype paged12k can not handle d.bin "
                                   "larger than 8K")
        elif self.pcbtype == "paged":
            if len(self.cbin) > 8192 or len(self.dbin) > 8192:
                raise RuntimeError("pcbtype paged can not handle c.bin "
                                   "or d.bin larger than 8K")
        elif self.pcbtype == "paged377":
            if len(self.cbin) > 2097152:
                raise RuntimeError("pcbtype paged377 can not handle ROM "
                                   "larger than 2M")
        elif self.pcbtype == "paged378":
            if self.gbin is not None and len(self.gbin) > 40960:
                raise RuntimeError(">40K GROM data not currently supported "
                                   "for pcbtype paged378")
            if len(self.cbin) > 524288:
                raise RuntimeError("pcbtype paged378 can not handle ROM "
                                   "larger than 512K")
        elif self.pcbtype == "paged379i":
            if len(self.cbin) > 131072:
                raise RuntimeError("pcbtype paged379i can not handle ROM "
                                   "larger than 128K")
        else:
            raise RuntimeError("Unhandled pcbtype %s" % (self.pcbtype,))

    def write_rpk(self, rpk):
        if self.pcbtype is None:
            self.select_pcb_type()
        if self.gbin is not None:
            rpk.writestr(self.gname, self.gbin)
        if self.cbin is not None:
            rpk.writestr(self.cname, self.cbin)
        if self.dbin is not None:
            rpk.writestr(self.dname, self.dbin)
        romset = ET.Element('romset', {'version': "1.0"})
        resources = ET.SubElement(romset, 'resources')
        configuration = ET.SubElement(romset, 'configuration')
        pcb = ET.SubElement(configuration, 'pcb', type=self.pcbtype)
        if self.gbin is not None:
            ET.SubElement(resources, 'rom', id="gromimage", file=self.gname)
            ET.SubElement(pcb, 'socket', id="grom_socket", uses="gromimage")
        if self.cbin is not None:
            ET.SubElement(resources, 'rom', id="romimage", file=self.cname)
            ET.SubElement(pcb, 'socket', id="rom_socket", uses="romimage")
        if self.dbin is not None:
            ET.SubElement(resources, 'rom', id="rom2image", file=self.dname)
            ET.SubElement(pcb, 'socket', id="rom2_socket", uses="rom2image")
        ET.indent(romset, '   ')
        layout = ET.tostring(romset, encoding='utf-8', xml_declaration=True)
        rpk.writestr('layout.xml', layout+b'\n')


def main():
    parser = argparse.ArgumentParser("bin2rpk",
                                     description="Generate an RPK file from "
                                     "bin file(s)")
    parser.add_argument('main_file', help="Main .bin file", type=pathlib.Path)
    parser.add_argument('--paged', '-p', choices=paged_pcbs.keys(),
                        help="force a certain paged variant")
    parser.add_argument('--output', '-o', type=pathlib.Path,
                        help="rpk filename (automatically chosen if omitted)")
    parser.add_argument('--debug', '-d', help="enable python tracebacks",
                        action='store_true')
    args = parser.parse_args()
    if not args.debug:
        sys.tracebacklimit = 0
    if args.output is None:
        args.output = args.main_file.parent.joinpath(args.main_file.stem
                                                     + ".rpk")

    cart = Cartridge(args.main_file)
    cart.select_pcb_type(paged=args.paged)
    print("Writing RPK to %s" % (args.output,))
    with zipfile.ZipFile(args.output, 'x', compression=zipfile.ZIP_DEFLATED,
                         compresslevel=9) as rpk:
        cart.write_rpk(rpk)


if __name__ == '__main__':
    main()
