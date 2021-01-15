# Electrum - lightweight Bitcoin client
# Copyright (C) 2012 thomasv@ecdsa.org
#
# Permission is hereby granted, free of charge, to any person
# obtaining a copy of this software and associated documentation files
# (the "Software"), to deal in the Software without restriction,
# including without limitation the rights to use, copy, modify, merge,
# publish, distribute, sublicense, and/or sell copies of the Software,
# and to permit persons to whom the Software is furnished to do so,
# subject to the following conditions:
#
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS
# BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN
# ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
# CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
import os
import threading
from typing import Optional, Dict, Mapping, Sequence

from . import util
from .bitcoin import hash_encode, int_to_hex, rev_hex
from .crypto import sha256d
from . import constants
from .util import bfh, bh2u
from .simple_config import SimpleConfig
from .logging import get_logger, Logger


_logger = get_logger(__name__)

MIN_POW = 0x00000FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF
DGW_TARGET_SPACING = int(1 * 60)   # Wagerr : Target difficulty adjust spacing for dark gravity
DGW_PAST_BLOCKS = 24
LAST_POW_BLOCK = 1001

MAX_TARGET = 0x00000FFFF0000000000000000000000000000000000000000000000000000000


class MissingHeader(Exception):
    pass

class InvalidHeader(Exception):
    pass

def serialize_header(header_dict: dict) -> str:
    s = int_to_hex(header_dict['version'], 4) \
        + rev_hex(header_dict['prev_block_hash']) \
        + rev_hex(header_dict['merkle_root']) \
        + int_to_hex(int(header_dict['timestamp']), 4) \
        + int_to_hex(int(header_dict['bits']), 4) \
        + int_to_hex(int(header_dict['nonce']), 4)
    if len(header_dict['acc_check_point']) > 0:
        s += rev_hex(header_dict['acc_check_point'])
    return s

def deserialize_header(s: bytes, height: int) -> dict:
    if not s:
        raise InvalidHeader('Invalid header: {}'.format(s))
    if not constants.net.COIN.check_header_size(s):
        raise InvalidHeader('Invalid header length: {}'.format(len(s)))
    hex_to_int = lambda s: int.from_bytes(s, byteorder='little')
    h = {}
    h['version'] = hex_to_int(s[0:4])
    h['prev_block_hash'] = hash_encode(s[4:36])
    h['merkle_root'] = hash_encode(s[36:68])
    h['timestamp'] = hex_to_int(s[68:72])
    h['bits'] = hex_to_int(s[72:76])
    h['nonce'] = hex_to_int(s[76:80])
    h['block_height'] = height
    h['acc_check_point'] = []
    if len(s) > constants.net.COIN.PRE_ZEROCOIN_HEADER_SIZE:
        h['acc_check_point'] = hash_encode(s[constants.net.COIN.PRE_ZEROCOIN_HEADER_SIZE:len(s)])
    return h

def hash_header(header: dict) -> str:
    if header is None:
        return '0' * 64
    if header.get('prev_block_hash') is None:
        header['prev_block_hash'] = '00'*32
    return hash_raw_header(serialize_header(header))


def hash_raw_header(header: str) -> str:
    if header[:2] == '01':
        import quark_hash
        return hash_encode(quark_hash.getPoWHash(bfh(header)))
    else:
        return hash_encode(sha256d(bfh(header)))


# key: blockhash hex at forkpoint
# the chain at some key is the best chain that includes the given hash
blockchains = {}  # type: Dict[str, Blockchain]
blockchains_lock = threading.RLock()


def read_blockchains(config: 'SimpleConfig'):
    best_chain = Blockchain(config=config,
                            forkpoint=0,
                            parent=None,
                            forkpoint_hash=constants.net.GENESIS,
                            prev_hash=None)
    blockchains[constants.net.GENESIS] = best_chain
    # consistency checks
    if best_chain.height() > constants.net.max_checkpoint():
        header_after_cp = best_chain.read_header(constants.net.max_checkpoint()+1)
        if not header_after_cp or not best_chain.can_connect(header_after_cp, check_height=False):
            _logger.info("[blockchain] deleting best chain. cannot connect header after last cp to last cp.")
            os.unlink(best_chain.path())
            best_chain.update_size()
    # forks
    fdir = os.path.join(util.get_headers_dir(config), 'forks')
    util.make_dir(fdir)
    # files are named as: fork2_{forkpoint}_{prev_hash}_{first_hash}
    l = filter(lambda x: x.startswith('fork2_') and '.' not in x, os.listdir(fdir))
    l = sorted(l, key=lambda x: int(x.split('_')[1]))  # sort by forkpoint

    def delete_chain(filename, reason):
        _logger.info(f"[blockchain] deleting chain {filename}: {reason}")
        os.unlink(os.path.join(fdir, filename))

    def instantiate_chain(filename):
        __, forkpoint, prev_hash, first_hash = filename.split('_')
        forkpoint = int(forkpoint)
        prev_hash = (64-len(prev_hash)) * "0" + prev_hash  # left-pad with zeroes
        first_hash = (64-len(first_hash)) * "0" + first_hash
        # forks below the max checkpoint are not allowed
        if forkpoint <= constants.net.max_checkpoint():
            delete_chain(filename, "deleting fork below max checkpoint")
            return
        # find parent (sorting by forkpoint guarantees it's already instantiated)
        for parent in blockchains.values():
            if parent.check_hash(forkpoint - 1, prev_hash):
                break
        else:
            delete_chain(filename, "cannot find parent for chain")
            return
        b = Blockchain(config=config,
                       forkpoint=forkpoint,
                       parent=parent,
                       forkpoint_hash=first_hash,
                       prev_hash=prev_hash)
        # consistency checks
        h = b.read_header(b.forkpoint)
        if first_hash != hash_header(h):
            delete_chain(filename, "incorrect first hash for chain")
            return
        if not b.parent.can_connect(h, check_height=False):
            delete_chain(filename, "cannot connect chain to parent")
            return
        chain_id = b.get_id()
        assert first_hash == chain_id, (first_hash, chain_id)
        blockchains[chain_id] = b

    for filename in l:
        instantiate_chain(filename)


def get_best_chain() -> 'Blockchain':
    return blockchains[constants.net.GENESIS]

# block hash -> chain work; up to and including that block
_CHAINWORK_CACHE = {
    "0000000000000000000000000000000000000000000000000000000000000000": 0,  # virtual block at height -1
}  # type: Dict[str, int]


class Blockchain(Logger):
    """
    Manages blockchain headers and their verification
    """

    def __init__(self, config: SimpleConfig, forkpoint: int, parent: Optional['Blockchain'],
                 forkpoint_hash: str, prev_hash: Optional[str]):
        assert isinstance(forkpoint_hash, str) and len(forkpoint_hash) == 64, forkpoint_hash
        assert (prev_hash is None) or (isinstance(prev_hash, str) and len(prev_hash) == 64), prev_hash
        # assert (parent is None) == (forkpoint == 0)
        if 0 < forkpoint <= constants.net.max_checkpoint():
            raise Exception(f"cannot fork below max checkpoint. forkpoint: {forkpoint}")
        Logger.__init__(self)
        self.config = config
        self.forkpoint = forkpoint  # height of first header
        self.parent = parent
        self._forkpoint_hash = forkpoint_hash  # blockhash at forkpoint. "first hash"
        self._prev_hash = prev_hash  # blockhash immediately before forkpoint
        self.lock = threading.RLock()
        self.update_size()

    def with_lock(func):
        def func_wrapper(self, *args, **kwargs):
            with self.lock:
                return func(self, *args, **kwargs)
        return func_wrapper

  

    def get_max_child(self) -> Optional[int]:
        children = self.get_direct_children()
        return max([x.forkpoint for x in children]) if children else None

    def get_max_forkpoint(self) -> int:
        """Returns the max height where there is a fork
        related to this chain.
        """
        mc = self.get_max_child()
        return mc if mc is not None else self.forkpoint

    def get_direct_children(self) -> Sequence['Blockchain']:
        with blockchains_lock:
            return list(filter(lambda y: y.parent==self, blockchains.values()))

    def get_parent_heights(self) -> Mapping['Blockchain', int]:
        """Returns map: (parent chain -> height of last common block)"""
        with blockchains_lock:
            result = {self: self.height()}
            chain = self
            while True:
                parent = chain.parent
                if parent is None: break
                result[parent] = chain.forkpoint - 1
                chain = parent
            return result

    def get_height_of_last_common_block_with_chain(self, other_chain: 'Blockchain') -> int:
        last_common_block_height = 0
        our_parents = self.get_parent_heights()
        their_parents = other_chain.get_parent_heights()
        for chain in our_parents:
            if chain in their_parents:
                h = min(our_parents[chain], their_parents[chain])
                last_common_block_height = max(last_common_block_height, h)
        return last_common_block_height

    @with_lock
    def get_branch_size(self) -> int:
        return self.height() - self.get_max_forkpoint() + 1

    def get_name(self) -> str:
        return self.get_hash(self.get_max_forkpoint()).lstrip('0')[0:10]

    def check_header(self, header: dict) -> bool:
        header_hash = hash_header(header)
        height = header.get('block_height')
        return self.check_hash(height, header_hash)

    def check_hash(self, height: int, header_hash: str) -> bool:
        """Returns whether the hash of the block at given height
        is the given hash.
        """
        assert isinstance(header_hash, str) and len(header_hash) == 64, header_hash  # hex
        try:
            return header_hash == self.get_hash(height)
        except Exception:
            return False

    def fork(parent, header: dict) -> 'Blockchain':
        if not parent.can_connect(header, check_height=False):
            raise Exception("forking header does not connect to parent chain")
        forkpoint = header.get('block_height')
        self = Blockchain(config=parent.config,
                          forkpoint=forkpoint,
                          parent=parent,
                          forkpoint_hash=hash_header(header),
                          prev_hash=parent.get_hash(forkpoint-1))
        open(self.path(), 'w+').close()
        self.save_header(header)
        # put into global dict. note that in some cases
        # save_header might have already put it there but that's OK
        chain_id = self.get_id()
        with blockchains_lock:
            blockchains[chain_id] = self
        return self

    @with_lock
    def height(self) -> int:
        return self.forkpoint + self.size() - 1

    @with_lock
    def size(self) -> int:
        return self._size

    @with_lock
    def update_size(self) -> None:
        p = self.path()
        if os.path.exists(p):
            fileSize = os.path.getsize(p)
            preMtpSize = constants.net.COIN.static_header_offset(constants.net.COIN.PRE_ZEROCOIN_BLOCKS)
            V7MtpSize = constants.net.COIN.static_header_offset(constants.net.COIN.HEADER_V7_BLOCKS)
            if fileSize > V7MtpSize:
                self._size = constants.net.COIN.HEADER_V7_BLOCKS + (fileSize - V7MtpSize) // constants.net.COIN.HEADER_V7_SIZE
            elif fileSize > preMtpSize:
                self._size = constants.net.COIN.PRE_ZEROCOIN_BLOCKS + (fileSize - preMtpSize) // constants.net.COIN.ZEROCOIN_HEADER_SIZE
            else:
                self._size = fileSize // constants.net.COIN.PRE_ZEROCOIN_HEADER_SIZE
        else:
            self._size = 0

    @classmethod
    def verify_header(cls, header: dict, prev_hash: str, target: int, expected_header_hash: str=None, proof_was_provided: bool=False) -> None:
        _hash = hash_header(header)
        if expected_header_hash and expected_header_hash != _hash:
            raise Exception("hash mismatches with expected: {} vs {}".format(expected_header_hash, _hash))
        if prev_hash != header.get('prev_block_hash'):
            raise Exception("prev hash mismatch: %s vs %s" % (prev_hash, header.get('prev_block_hash')))
        if constants.net.TESTNET:
            return
        # We do not need to check the block difficulty if the chain of linked header hashes was proven correct against our checkpoint.
        if not proof_was_provided:
            bits = cls.target_to_bits(target)
            if bits != header.get('bits'):
                raise Exception("bits mismatch: %s vs %s" % (bits, header.get('bits')))
            if header.get('block_height') <= LAST_POW_BLOCK:
                block_hash_as_num = int.from_bytes(bfh(_hash), byteorder='big')
                if block_hash_as_num > target:
                    raise Exception(f"insufficient proof of work: {block_hash_as_num} vs target {target}")

    def verify_chunk(self, index: int, data: bytes) -> None:
        chain = []
        CHUNK_SIZE = 2016
        start_height = index * CHUNK_SIZE
        prev_hash = self.get_hash(start_height - 1)
        i = 0
        dataHandled = 0
        while dataHandled < len(data):
            height = start_height + i
            try:
                expected_header_hash = self.get_hash(height)
            except MissingHeader:
                expected_header_hash = None
            headerSize = constants.net.COIN.get_header_size(data[dataHandled : dataHandled + constants.net.COIN.PRE_ZEROCOIN_HEADER_SIZE])
            raw_header = data[dataHandled : dataHandled + headerSize]
            header = deserialize_header(raw_header, height)
            chain.append(header)
            target = self.get_target(height,chain)
            self.verify_header(header, prev_hash, target, expected_header_hash)
            prev_hash = hash_header(header)
            i += 1
            dataHandled += headerSize

    @with_lock
    def path(self):
        d = util.get_headers_dir(self.config)
        if self.parent is None:
            filename = 'blockchain_headers'
        else:
            assert self.forkpoint > 0, self.forkpoint
            prev_hash = self._prev_hash.lstrip('0')
            first_hash = self._forkpoint_hash.lstrip('0')
            basename = f'fork2_{self.forkpoint}_{prev_hash}_{first_hash}'
            filename = os.path.join('forks', basename)
        return os.path.join(d, filename)

    @with_lock
    def save_chunk(self, index: int, chunk: bytes):
        assert index >= 0, index
        chunk_within_checkpoint_region = index * 2016 < constants.net.max_checkpoint()
        # chunks in checkpoint region are the responsibility of the 'main chain'
        if chunk_within_checkpoint_region and self.parent is not None:
            main_chain = get_best_chain()
            main_chain.save_chunk(index, chunk)
            return

        delta_bytes = constants.net.COIN.static_header_offset(index * 2016)  -  constants.net.COIN.static_header_offset(self.forkpoint)
        # if this chunk contains our forkpoint, only save the part after forkpoint
        # (the part before is the responsibility of the parent)
        if delta_bytes < 0:
            chunk = chunk[-delta_bytes:]
            delta_bytes = 0
        truncate = not chunk_within_checkpoint_region
        self.write(chunk, delta_bytes, truncate)
        self.swap_with_parent()

    def swap_with_parent(self) -> None:
        with self.lock, blockchains_lock:
            # do the swap; possibly multiple ones
            cnt = 0
            while True:
                old_parent = self.parent
                if not self._swap_with_parent():
                    break
                # make sure we are making progress
                cnt += 1
                if cnt > len(blockchains):
                    raise Exception(f'swapping fork with parent too many times: {cnt}')
                # we might have become the parent of some of our former siblings
                for old_sibling in old_parent.get_direct_children():
                    if self.check_hash(old_sibling.forkpoint - 1, old_sibling._prev_hash):
                        old_sibling.parent = self

    def _swap_with_parent(self) -> bool:
        """Check if this chain became stronger than its parent, and swap
        the underlying files if so. The Blockchain instances will keep
        'containing' the same headers, but their ids change and so
        they will be stored in different files."""
        if self.parent is None:
            return False
        if self.parent.get_chainwork() >= self.get_chainwork():
            return False
        self.logger.info(f"swapping {self.forkpoint} {self.parent.forkpoint}")
        parent_branch_size = self.parent.height() - self.forkpoint + 1
        forkpoint = self.forkpoint  # type: Optional[int]
        parent = self.parent  # type: Optional[Blockchain]
        child_old_id = self.get_id()
        parent_old_id = parent.get_id()
        # swap files
        # child takes parent's name
        # parent's new name will be something new (not child's old name)
        self.assert_headers_file_available(self.path())
        child_old_name = self.path()
        with open(self.path(), 'rb') as f:
            my_data = f.read()
        self.assert_headers_file_available(parent.path())
        assert forkpoint > parent.forkpoint, (f"forkpoint of parent chain ({parent.forkpoint}) "
                                              f"should be at lower height than children's ({forkpoint})")
        with open(parent.path(), 'rb') as f:
            f.seek( constants.net.COIN.static_header_offset(forkpoint) - constants.net.COIN.static_header_offset(parent.forkpoint))
            parent_data = f.read(parent_branch_size * constants.net.COIN.get_header_size_height(forkpoint))
        self.write(parent_data, 0)
        parent.write(my_data, constants.net.COIN.static_header_offset(forkpoint) - constants.net.COIN.static_header_offset(parent.forkpoint) )
        # swap parameters
        self.parent, parent.parent = parent.parent, self  # type: Optional[Blockchain], Optional[Blockchain]
        self.forkpoint, parent.forkpoint = parent.forkpoint, self.forkpoint
        self._forkpoint_hash, parent._forkpoint_hash = parent._forkpoint_hash, hash_raw_header(bh2u(parent_data[:constants.net.COIN.get_header_size_height(parent.forkpoint + parent.size() - 1)]))
        self._prev_hash, parent._prev_hash = parent._prev_hash, self._prev_hash
        # parent's new name
        os.replace(child_old_name, parent.path())
        self.update_size()
        parent.update_size()
        # update pointers
        blockchains.pop(child_old_id, None)
        blockchains.pop(parent_old_id, None)
        blockchains[self.get_id()] = self
        blockchains[parent.get_id()] = parent
        return True

    def get_id(self) -> str:
        return self._forkpoint_hash

    def assert_headers_file_available(self, path):
        if os.path.exists(path):
            return
        elif not os.path.exists(util.get_headers_dir(self.config)):
            raise FileNotFoundError('Electrum headers_dir does not exist. Was it deleted while running?')
        else:
            raise FileNotFoundError('Cannot find headers file but headers_dir is there. Should be at {}'.format(path))

    @with_lock
    def write(self, data: bytes, offset: int, truncate: bool=True) -> None:
        filename = self.path()
        self.assert_headers_file_available(filename)
        with open(filename, 'rb+') as f:
            if truncate and offset != constants.net.COIN.static_header_offset(self._size):
                f.seek(offset)
                f.truncate()
            f.seek(offset)
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        self.update_size()

    @with_lock
    def save_header(self, header: dict) -> None:
        assert self.size() == header.get('block_height') - self.forkpoint
        delta = constants.net.COIN.static_header_offset(header.get('block_height')) - constants.net.COIN.static_header_offset(self.forkpoint)
        data = bfh(serialize_header(header))
        # headers are only _appended_ to the end:
        self.write(data, delta)
        self.swap_with_parent()

    @with_lock
    def read_header(self, height: int) -> Optional[dict]:
        if height < 0:
            return
        if height < self.forkpoint:
            return self.parent.read_header(height)
        if height > self.height():
            return
        delta = constants.net.COIN.static_header_offset(height) - constants.net.COIN.static_header_offset(self.forkpoint)
        name = self.path()
        self.assert_headers_file_available(name)
        with open(name, 'rb') as f:
            f.seek(delta)
            hdrSz = constants.net.COIN.get_header_size_height(height)
            h = f.read(hdrSz)
            if len(h) == 0:
                raise MissingHeader('Header is missing')
            if len(h) < hdrSz:
                raise Exception('Expected to read a full header. This was only {} bytes'.format(len(h)))
        if h == bytes([0])*hdrSz:
            return None
        return deserialize_header(h, height)

    def header_at_tip(self) -> Optional[dict]:
        """Return latest header."""
        height = self.height()
        return self.read_header(height)

    def get_hash(self, height: int) -> str:
       

        if height == -1:
            return '0000000000000000000000000000000000000000000000000000000000000000'
        elif height == 0:
            return constants.net.GENESIS
        else:
            header = self.read_header(height)
            if header is None:
                raise MissingHeader(height)
            return hash_header(header)

    def get_target(self, height: int, chain=None) -> int:
        if chain is None:
            chain = []
        # compute target from chunk x, used in chunk x+1
        if constants.net.TESTNET:
            return 0
        if height == 0:
            return MAX_TARGET
        
        # if index < len(self.checkpoints):
        #     h, t = self.checkpoints[index]
        #     return t
        
        return self.get_target_wagerr(height, chain)
    
    def get_target_wagerr(self, height, chain):
        """ Calculate the difficulty using DGW. """

        def header_from_chain(block_height):
            header = self.read_header(block_height)
            if header is not None:
                return header
            for hdr in chain:
                if hdr.get('block_height') == block_height:
                    return hdr
        def isfTimeV2(height):
            return height >= 1501000 #nBlockTimeProtocolV2 '7 January 2021

        assert height > 0, "Using dark gravity before fork block"

        last = header_from_chain(height - 1)

        if last is None or height < DGW_PAST_BLOCKS:
            return MIN_POW

        if (height-1) > LAST_POW_BLOCK:
            bnTargetLimit = 0x000000FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF
            fTimeV2 = isfTimeV2(height)
            nTargetSpacing = 60
            nTimeSlotLength = 15
            nTargetTimespan_V2 = 2 * nTimeSlotLength * 60
            nTargetTimespan_V1 = 40 * 60
            nTargetTimespan = nTargetTimespan_V2 if fTimeV2 == True else nTargetTimespan_V1

            nActualSpacing = 0
            if (height-1) != 0:
                lastToLast = header_from_chain(height - 2)
                nActualSpacing = int(last.get('timestamp') - lastToLast.get('timestamp'))

            if nActualSpacing < 0:
                nActualSpacing = 1
            if fTimeV2 == True and nActualSpacing > nTargetSpacing*10:
                nActualSpacing = nTargetSpacing*10

            new_target = self.bits_to_target(last.get('bits'))

            if fTimeV2 == True and not isfTimeV2(height-1):
                new_target = new_target << 4

            nInterval = nTargetTimespan // nTargetSpacing

            new_target = new_target* ( (nInterval-1) * nTargetSpacing + nActualSpacing + nActualSpacing)
            new_target = new_target // ((nInterval+1) * nTargetSpacing)
            if new_target <= 0 or new_target > bnTargetLimit:
                new_target = bnTargetLimit
            return new_target

        end_time = last.get('timestamp')

        for count in [i+1 for i in range(DGW_PAST_BLOCKS)]:
            if count <= DGW_PAST_BLOCKS:
                target = self.bits_to_target(last.get('bits'))
                if count == 1:
                    past_target_average = target
                else:
                    past_target_average = ((past_target_average * count) + target) // (count + 1)

            if count != DGW_PAST_BLOCKS:
                last = header_from_chain(last['block_height'] - 1)

        time_span = end_time - last.get('timestamp')
        target_timespan = DGW_PAST_BLOCKS * DGW_TARGET_SPACING

        time_span = max(time_span, target_timespan // 3)
        time_span = min(time_span, target_timespan * 3)

        # retarget
        new_target = past_target_average * time_span
        new_target = new_target // target_timespan
        new_target = min(new_target, MIN_POW)

        return new_target

    @classmethod
    def bits_to_target(cls, bits: int) -> int:
        bitsN = (bits >> 24) & 0xff
        if not (0x03 <= bitsN <= 0x1e):
            raise Exception("First part of bits should be in [0x03, 0x1e]")
        bitsBase = bits & 0xffffff
        if not (0x8000 <= bitsBase <= 0x7fffff):
            raise Exception("Second part of bits should be in [0x8000, 0x7fffff]")
        return bitsBase << (8 * (bitsN-3))

    @classmethod
    def target_to_bits(cls, target: int) -> int:
        c = ("%064x" % target)[2:]
        while c[:2] == '00' and len(c) > 6:
            c = c[2:]
        bitsN, bitsBase = len(c) // 2, int.from_bytes(bfh(c[:6]), byteorder='big')
        if bitsBase >= 0x800000:
            bitsN += 1
            bitsBase >>= 8
        return bitsN << 24 | bitsBase

    def chainwork_of_header_at_height(self, height: int) -> int:
        """work done by single header at given height"""
        chunk_idx = height // 2016 - 1
        target = self.get_target(height)
        work = ((2 ** 256 - target - 1) // (target + 1)) + 1
        return work

    @with_lock
    def get_chainwork(self, height=None) -> int:
        if height is None:
            height = max(0, self.height())
        if constants.net.TESTNET:
            # On testnet/regtest, difficulty works somewhat different.
            # It's out of scope to properly implement that.
            return height
        last_retarget = height // 2016 * 2016 - 1
        cached_height = last_retarget
        while _CHAINWORK_CACHE.get(self.get_hash(cached_height)) is None:
            if cached_height <= -1:
                break
            cached_height -= 2016
        assert cached_height >= -1, cached_height
        running_total = _CHAINWORK_CACHE[self.get_hash(cached_height)]
        while cached_height < last_retarget:
            cached_height += 2016
            work_in_single_header = self.chainwork_of_header_at_height(cached_height)
            work_in_chunk = 2016 * work_in_single_header
            running_total += work_in_chunk
            _CHAINWORK_CACHE[self.get_hash(cached_height)] = running_total
        cached_height += 2016
        work_in_single_header = self.chainwork_of_header_at_height(cached_height)
        work_in_last_partial_chunk = (height % 2016 + 1) * work_in_single_header
        return running_total + work_in_last_partial_chunk

    def can_connect(self, header: dict, check_height: bool=True, proof_was_provided: bool=False) -> bool:
        if header is None:
            return False
        if proof_was_provided:
            return True
        height = header['block_height']
        if check_height and self.height() != height - 1:
            return False
        if height == 0:
            return hash_header(header) == constants.net.GENESIS
        try:
            prev_hash = self.get_hash(height - 1)
        except:
            return False
        if prev_hash != header.get('prev_block_hash'):
            return False
        try:
            target = self.get_target(height)
        except MissingHeader:
            return False
        try:
            self.verify_header(header, prev_hash, target)
        except BaseException as e:
            return False
        return True

    def connect_chunk(self, idx: int, hexdata: str, proof_was_provided: bool=False) -> bool:
        assert idx >= 0, idx
        try:
            data = bfh(hexdata)
            if not proof_was_provided:
                self.verify_chunk(idx, data)
            self.save_chunk(idx, data)
            return True
        except BaseException as e:
            self.logger.info(f'verify_chunk idx {idx} failed: {repr(e)}')
            return False


def check_header(header: dict) -> Optional[Blockchain]:
    if type(header) is not dict:
        return None
    with blockchains_lock: chains = list(blockchains.values())
    for b in chains:
        if b.check_header(header):
            return b
    return None


def can_connect(header: dict, proof_was_provided: bool=False) -> Optional[Blockchain]:
    with blockchains_lock: chains = list(blockchains.values())
    for b in chains:
        if b.can_connect(header, proof_was_provided=proof_was_provided):
            return b
    return None
def verify_proven_chunk(chunk_base_height, chunk_data):
    #chain = []
    #CHUNK_SIZE = 2016
    #start_height = index * CHUNK_SIZE
    prev_header = None
    prev_header_hash = None
    i = 0
    dataHandled = 0
    while dataHandled < len(chunk_data):
        height = chunk_base_height + i
            
        headerSize = constants.net.COIN.get_header_size(chunk_data[dataHandled : dataHandled + constants.net.COIN.PRE_ZEROCOIN_HEADER_SIZE])
        raw_header = chunk_data[dataHandled : dataHandled + headerSize]
        header = deserialize_header(raw_header, height)
        # Check the chain of hashes for all headers preceding the proven one.
        this_header_hash = hash_header(header)
        if i > 0:
            if prev_header_hash != header.get('prev_block_hash'):
                raise Exception("prev hash mismatch: %s vs %s" % (prev_header_hash, header.get('prev_block_hash')))
        prev_header_hash = this_header_hash

        i += 1
        dataHandled += headerSize

# Copied from electrumx
def root_from_proof(hash, branch, index):
    hash_func = sha256d
    for elt in branch:
        if index & 1:
            hash = hash_func(elt + hash)
        else:
            hash = hash_func(hash + elt)
        index >>= 1
    if index:
        raise ValueError('index out of range for branch')
    return hash


