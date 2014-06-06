# pylint: disable-msg = C0103
# pylint: disable-msg = C0301

import logging
LOGGER = logging.getLogger(__name__)

from corr2.fpgadevice.memory import Memory
import corr2.bitfield as bitfield
from corr2.misc import log_runtime_error
from corr2.fpgadevice.register import Register

class Snap(Memory):
    '''Snap blocks are triggered/controlled blocks of RAM on FPGAs.
    '''
    def __init__(self, parent, name, info):
        Memory.__init__(self, name=name, width=1, length=1)
        self.parent = parent
        self.block_info = info
        self.width = int(info['data_width'])
        self.length = pow(2, int(info['nsamples']))
        self.field_add(bitfield.Field(name='data', numtype=0, width=self.width, binary_pt=0, lsb_offset=0))
        self.control_registers = {}
        self.control_registers['control'] = {'register': None, 'name': self.name + '_ctrl'}
        self.control_registers['status'] = {'register': None, 'name': self.name + '_status'}
        self.control_registers['trig_offset'] = {'register': None, 'name': self.name + '_trig_offset'}
        self.control_registers['extra_value'] = {'register': None, 'name': self.name + '_val'}
        self.control_registers['tr_en_cnt'] = {'register': None, 'name': self.name + '_tr_en_cnt'}
        LOGGER.info('New Snap - %s', self)

    def post_create_update(self, raw_device_info):
        '''Update the device with information not available at creation.
        @param raw_device_info: dictionary of device information
        '''
        # is this snap block inside a bitsnap block?
        for device_name, dev_info in raw_device_info.items():
            if device_name != '':
                if dev_info['tag'] == 'casper:bitsnap':
                    if self.name == device_name + '_ss':
                        self.update_from_bitsnap(dev_info)
                        break
        # find control registers for this snap block
        self._link_control_registers(self.parent.device_names_by_container('registers'), raw_device_info)

    def update_from_bitsnap(self, info):
        '''Update this device with information from a bitsnap container.
        '''
        self.block_info = info
        if self.width != int(info['snap_data_width']):
            log_runtime_error(LOGGER, 'Snap and matched bitsnap widths do not match.')
        if self.length != pow(2, int(info['snap_nsamples'])):
            log_runtime_error(LOGGER, 'Snap and matched bitsnap lengths do not match.')
        def clean_fields(fstr):
            _fstr = fstr.replace('[', '').replace(']', '').rstrip().lstrip().replace(', ', ',')
            if (_fstr.find(' ') > -1) and (_fstr.find(',') > -1):
                LOGGER.error('Parameter string %s contains spaces and commas as delimiters. This is confusing.', fstr)
            if _fstr.find(' ') > -1:
                return _fstr.split(' ')
            else:
                return _fstr.split(',')
        field_names = clean_fields(info['io_names'])
        field_widths = clean_fields(info['io_widths'])
        field_types = clean_fields(info['io_types'])
        field_bps = clean_fields(info['io_bps'])
        field_names.reverse()
        field_widths.reverse()
        field_types.reverse()
        field_bps.reverse()
        self.fields_clear()
        for n, fn in enumerate(field_names):
            field = bitfield.Field(name=fn,
                numtype=int(field_types[n]),
                width=int(field_widths[n]),
                binary_pt=int(field_bps[n]), lsb_offset=-1)
            self.field_add(field, auto_offset=True)

    def _link_control_registers(self, available_registers, raw_device_info):
        '''Link available registers to this snapshot block's control registers.
        '''
        for controlreg in self.control_registers.values():
            for register_name in available_registers:
                regobj = getattr(self.parent.registers, register_name)
                assert isinstance(regobj, Register)
                if regobj.name == controlreg['name']:
                    controlreg['register'] = regobj
                    break
        if (self.control_registers['control']['register'] == None) or (self.control_registers['status']['register'] == None):
            log_runtime_error(LOGGER, 'Critical control registers for snap %s missing.' % self.name)
        if self.block_info.has_key('value'):
            self.block_info['snap_value'] = self.block_info.has_key('value')
        if self.block_info['snap_value'] == 'on':
            if self.control_registers['extra_value']['register'] == None:
                log_runtime_error(LOGGER, 'snap %s extra value register specified, but not found. Problem.' % self.name)
            extra_info = raw_device_info[self.control_registers['extra_value']['name']]
            extra_info['mode'] = 'fields of arbitrary size'
            if self.block_info.has_key('extra_names'):
                extra_info['names'] = self.block_info['extra_names']
                extra_info['bitwidths'] = self.block_info['extra_widths']
                extra_info['arith_types'] = self.block_info['extra_types']
                extra_info['bin_pts'] = self.block_info['extra_bps']
            else:
                extra_info['names'] = '[reg]'
                extra_info['bitwidths'] = '[32]'
                extra_info['arith_types'] = '[0]'
                extra_info['bin_pts'] = '[0]'
            self.control_registers['extra_value']['register'].process_info(extra_info)

    def _arm(self, man_trig=False, man_valid=False, offset=-1, circular_capture=False):
        '''Arm the snapshot block.
        '''
        if offset >= 0:
            self.control_registers['trig_offset']['register'].write_int(offset)
        self.control_registers['control']['register'].write_int((0 + (man_trig << 1) + (man_valid << 2) + (circular_capture << 3)))
        self.control_registers['control']['register'].write_int((1 + (man_trig << 1) + (man_valid << 2) + (circular_capture << 3)))

    def print_snap(self, limit_lines=-1, man_valid=False, man_trig=False, circular_capture=False):
        '''Read and print a snap block.
        '''
        snapdata = self.read(man_valid=man_valid, man_trig=man_trig, circular_capture=circular_capture)
        for ctr in range(0, len(snapdata['data'][snapdata['data'].keys()[0]])):
            print '%5d' % ctr,
            for key in snapdata['data'].keys():
                print '%s(%d)' % (key, snapdata['data'][key][ctr]), '\t',
            print ''
            if (limit_lines > 0) and (ctr == limit_lines):
                break
        if circular_capture == True:
            print 'Circular capture offset: ', snapdata['offset']

    def read(self, **kwargs):
        '''Override Memory.read to handle the extra value register.
        '''
        rawdata, rawtime = self.read_raw(**kwargs)
        processed = self._process_data(rawdata['data'])
        if rawdata.has_key('offset'):
            offset = rawdata['offset']
        else:
            offset = 0
        return {'data': processed, 'offset': offset, 'timestamp': rawtime, 'extra_value': rawdata['extra_value']}

    def read_raw(self, **kwargs):
        '''Read snap data from the memory device.
        '''
        def getkwarg(key, default):
            try:
                return kwargs[key]
            except KeyError:
                return default
        man_trig = getkwarg('man_trig', False)
        man_valid = getkwarg('man_valid', False)
        timeout = getkwarg('timeout', -1)
        offset = getkwarg('offset', -1)
        circular_capture = getkwarg('circular_capture', False)
        arm = getkwarg('arm', True)
        if arm:
            self._arm(man_trig=man_trig, man_valid=man_valid, offset=offset, circular_capture=circular_capture)
        # wait
        done = False
        import time
        start_time = time.time()
        while not done and ((time.time() - start_time) < timeout or (timeout < 0)):
            addr = self.control_registers['status']['register'].read_uint()
            done = not bool(addr & 0x80000000)
        bram_dmp = {}
        bram_dmp['extra_value'] = None
        bram_dmp['data'] = []
        bram_dmp['length'] = addr & 0x7fffffff
        bram_dmp['offset'] = 0
        status_val = self.control_registers['status']['register'].read_uint()
        now_status = bool(status_val & 0x80000000)
        now_addr = status_val & 0x7fffffff
        if (bram_dmp['length'] != now_addr) or (bram_dmp['length'] == 0) or (now_status == True):
            # if address is still changing, then the snap block didn't finish capturing. we return empty.
            error_info = "timeout %2.2f seconds. Addr at stop time: %i. Now: Still running :%s, addr: %i." % \
                              (timeout, bram_dmp['length'], 'yes' if now_status else 'no', now_addr)
            if bram_dmp['length'] != now_addr:
                log_runtime_error(LOGGER, "Snap %s error: Address still changing after %s" % (self.name, error_info))
            elif bram_dmp['length'] == 0:
                log_runtime_error(LOGGER, "Snap %s error: Returned 0 bytes after %s" % (self.name, error_info))
            else:
                log_runtime_error(LOGGER, "Snap %s error: %s" % (self.name, error_info))
            bram_dmp['length'] = 0
            bram_dmp['offset'] = 0
        if circular_capture:
            val = self.control_registers['tr_en_cnt']['register'].read_uint()
            bram_dmp['offset'] = val - bram_dmp['length']
        else:
            bram_dmp['offset'] = 0
        if bram_dmp['length'] == 0:
            bram_dmp['data'] = []
        else:
            bram_dmp['data'] = self.parent.read(self.name + '_bram', bram_dmp['length'])
            datatime = time.time()
        bram_dmp['offset'] += offset
        if bram_dmp['offset'] < 0:
            bram_dmp['offset'] = 0
        if bram_dmp['length'] != self.length * (self.width / 8):
            log_runtime_error(LOGGER, '%s.read_uint() - expected %i bytes, got %i' % (self.name, self.length, bram_dmp['length'] / (self.width / 8)))
        # read the extra value
        if self.control_registers['extra_value']['register'] != None:
            bram_dmp['extra_value'] = self.control_registers['extra_value']['register'].read()
        # done
        return bram_dmp, datatime

    def __str__(self):
        return '%s: %s' % (self.name, self.block_info)

#     def __repr__(self):
#         return '[' + self.__str__() + ']'
