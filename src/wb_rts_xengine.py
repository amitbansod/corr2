import logging
LOGGER = logging.getLogger(__name__)

from corr2.xengine_fpga import XengineFpga

from misc import log_runtime_error

class WbRtsXengine(XengineFpga):
    '''
    The RTS wideband X-engine
    '''
    def __init__(self, fpga, engine_id=0, host_instrument=None, config_file=None, descriptor='wb_rts_xengine'):
        '''Constructor
        '''
        XengineFpga.__init__(self, fpga, engine_id, host_instrument, config_file, descriptor)

        self._get_wb_rts_xengine_config()

    def _get_wb_rts_xengine_config(self):
        '''
        '''

    def __getattribute__(self, name):
        '''Overload __getattribute__ to make shortcuts for getting object data.
        '''
        if name == 'tx_cnt':
            return self.host.device_by_name('tx_cnt%s' %self.offset)
        
        return XengineFpga.__getattribute__(self, name)

    # flashy leds on front panel
    def enable_leds(self):
        ''' Turn on the Knightrider effect 
        '''
        self.control.write(leds_en=1)
    
    def disable_leds(self):
        ''' Turn off the Knightrider effect 
        '''
        self.control.write(leds_en=0)

