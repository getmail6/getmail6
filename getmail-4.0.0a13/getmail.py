#!/usr/bin/env python2.3

import sys
import os.path
import time
import ConfigParser
import pprint
from optparse import OptionParser, OptionGroup

from getmailcore import __version__, retrievers, destinations, filters, logging
from getmailcore.exceptions import *
from getmailcore.utilities import eval_bool

log = logging.logger()
log.addhandler(sys.stdout, logging.INFO, maxlevel=logging.INFO)
log.addhandler(sys.stderr, logging.WARNING)

defaults = {
    'getmaildir' : '~/.getmail/',
    'rcfile' : 'getmailrc',

    'verbose' : True,
    'read_all' : True,
    'delete' : False,
    'max_message_size' : 0,
    'delete_after' : 0,
    'max_messages_per_session' : 0,
}

#######################################
def go(configs):
    log.info('getmail version %s\n' % __version__)
    log.info('Copyright (C) 1998-2004 Charles Cazabon.  Licensed under the GNU GPL version 2.\n')
    for (retriever, _filters, destination, options) in configs:
        now = int(time.time())
        retrieved_messages = 0
        log.debug('initializing retriever %s\n' % retriever)
        retriever.initialize()
        try:
            for msgid in retriever:
                retrieve = False
                delete = False
                timestamp = retriever.oldmail.get(msgid, None)
                size = retriever.getmsgsize(msgid)
    
                log.info('Message %s (%d bytes) ... ' % (msgid, size))
    
                if options['read_all'] or timestamp is None:
                    retrieve = True
    
                if options['max_message_size'] and size > options['max_message_size']:
                    log.info('message size (%d) > max_message_size %d, not retrieving ... ' % (size, options['max_message_size']))
                    retrieve = False
    
                try:    
                    if retrieve:
                        msg = retriever.getmsg(msgid)
                        retrieved_messages += 1
                        log.info('from <%s> ... ' % msg.sender)
    
                        for mail_filter in _filters:
                            log.debug('passing to filter %s ... ' % mail_filter)
                            msg = mail_filter.filter_message(msg)
                            if msg is None:
                                log.info('dropped by filter %s ... ' % mail_filter)
                                break
                        
                        if msg is not None:
                            r = destination.deliver_message(msg)
                            log.info('delivered to %s ... ' % r)
                        if options['delete']:
                            delete = True
                    else:
                        log.info('not retrieving (timestamp %s)' % timestamp)
    
                    if options['delete_after'] and timestamp and (now - timestamp)/86400 >= options['delete_after']:
                        log.debug('message older than %d days (%s seconds), will delete ... ' % (options['delete_after'], (now - timestamp)))
                        delete = True
        
                    if not retrieve and timestamp is None:
                        # We haven't retrieved this message.  Don't delete it.
                        log.debug('message not yet retrieved, not deleting ... ')
                        delete = False
        
                    if delete:
                        retriever.delmsg(msgid)
                        log.info('deleted')
        
                except getmailDeliveryError, o:
                    log.error('Delivery error (%s)\n' % o)
    
                log.info('\n')

                if options['max_messages_per_session'] and retrieved_messages >= options['max_messages_per_session']:
                    log.info('hit max_messages_per_session (%d), breaking\n' % options['max_messages_per_session'])
                    raise StopIteration('max_messages_per_session %d' % options['max_messages_per_session'])

        except StopIteration:
            pass

        retriever.quit()

#######################################
def main():
    try:
        parser = OptionParser(version='%%prog %s' % __version__)
        parser.add_option('-g', '--getmaildir',
            dest='getmaildir', action='store', default=defaults['getmaildir'],
            help='look in DIR for config/data files', metavar='DIR')
        parser.add_option('-r', '--rcfile',
            dest='rcfile', action='append', default=[],
            help='load configuration from FILE (may be given multiple times)', metavar='FILE')
        parser.add_option('--dump', 
            dest='dump_config', action='store_true', default=False,
            help='dump configuration and exit (debugging)')
        parser.add_option('--trace', 
            dest='trace', action='store_true', default=False,
            help='print extended debugging information')
        overrides = OptionGroup(parser, 'Overrides',
            'The following options override those specified in any getmailrc file.'
        )
        overrides.add_option('-v', '--verbose',
            dest='override_verbose', action='store_true',
            help='print informational messages')
        overrides.add_option('-q', '--quiet',
            dest='override_verbose', action='store_false',
            help='do not print informational messages')
        overrides.add_option('-d', '--delete',
            dest='override_delete', action='store_true',
            help='delete messages from server after retrieving')
        overrides.add_option('-l', '--dont-delete',
            dest='override_delete', action='store_false',
            help='do not delete messages from server after retrieving')
        overrides.add_option('-a', '--all',
            dest='override_read_all', action='store_true',
            help='retrieve all messages')
        overrides.add_option('-n', '--new',
            dest='override_read_all', action='store_false',
            help='retrieve only unread messages')
        parser.add_option_group(overrides)

        (options, args) = parser.parse_args(sys.argv[1:])
        if args:
            raise getmailOperationError('unknown argument(s) %s ; try --help' % args)

        if options.trace:
            log.clearhandlers()

        if not options.rcfile:
            options.rcfile.append(defaults['rcfile'])

        s = ''
        for attr in dir(options):
            if attr.startswith('_'):  continue
            if s:  s += ','
            s += '%s="%s"' % (attr, pprint.pformat(getattr(options, attr)))
        log.debug('parsed options:  %s\n' % s)

        configs = []
        for filename in options.rcfile:
            path = os.path.join(os.path.expanduser(options.getmaildir), filename)
            log.debug('processing rcfile %s\n' % path)
            if not os.path.exists(path):
                raise getmailOperationError('configuration file %s does not exist' % path)
            elif not os.path.isfile(path):
                raise getmailOperationError('%s is not a file' % path)
            f = file(path, 'rb')
            config = {
                'verbose' : defaults['verbose'],
                'read_all' : defaults['read_all'],
                'delete' : defaults['delete'],
                'delete_after' : defaults['delete_after'],
                'max_message_size' : defaults['max_message_size'],
                'max_messages_per_session' : defaults['max_messages_per_session'],
            }
            # Python's ConfigParser .getboolean() can't handle booleans in the defaults.
            # Submitted a patch; we'll see if they take it.  In the meantime, ugly hack....
            parserdefaults = config.copy()
            for (key, value) in parserdefaults.items():
                if type(value) == bool:
                    parserdefaults[key] = str(value)

            configparser = ConfigParser.RawConfigParser(parserdefaults)
            configparser.readfp(f, path)

            try:
                for option in ('verbose', 'read_all', 'delete'):
                    log.debug('  looking for option %s ... ' % option)
                    if configparser.has_option('options', option):
                        log.debug('got "%s"' % configparser.get('options', option))
                        try:
                            config[option] = configparser.getboolean('options', option)
                            log.debug('-> %s' % config[option])
                        except ValueError:
                            raise getmailConfigurationError('configuration file %s incorrect (option %s must be boolean, not %s)' % (path, option, configparser.get('options', option)))
                    else:
                        log.debug('not found')
                    log.debug('\n')

                for option in ('delete_after', 'max_message_size', 'max_messages_per_session'):
                    log.debug('  looking for option %s ... ' % option)
                    if configparser.has_option('options', option):
                        log.debug('got "%s"' % configparser.get('options', option))
                        try:
                            config[option] = configparser.getint('options', option)
                            log.debug('-> %s' % config[option])
                        except ValueError:
                            raise getmailConfigurationError('configuration file %s incorrect (option %s must be integer, not %s)' % (path, option, configparser.get('options', option)))
                    else:
                        log.debug('not found')
                    log.debug('\n')

                # FIXME:  Add handling for message_log, ...

                # Clear out the ConfigParser defaults before processing further sections
                configparser._defaults = {}
                
                # Retriever
                log.debug('  getting retriever\n')
                retriever_type = configparser.get('retriever', 'type')
                log.debug('    type="%s"\n' % retriever_type)
                retriever_func = getattr(retrievers, retriever_type)
                if not callable(retriever_func):
                    raise getmailConfigurationError('configuration file %s specifies incorrect retriever type (%s)' % (path, retriever_type))
                retriever_args = {'getmaildir' : options.getmaildir}
                for (name, value) in configparser.items('retriever'):
                    if name == 'type' : continue
                    log.debug('    parameter %s="%s"\n' % (name, value))
                    retriever_args[name] = value
                log.debug('    instantiating retriever %s with args %s\n' % (retriever_type, retriever_args))
                retriever = retriever_func(**retriever_args)
                log.debug('    checking retriever configuration for %s\n' % retriever)
                retriever.checkconf()

                # Destination
                log.debug('  getting destination\n')
                destination_type = configparser.get('destination', 'type')
                log.debug('    type="%s"\n' % destination_type)
                destination_func = getattr(destinations, destination_type)
                if not callable(destination_func):
                    raise getmailConfigurationError('configuration file %s specifies incorrect destination type (%s)' % (path, destination_type))
                destination_args = {}
                for (name, value) in configparser.items('destination'):
                    if name == 'type' : continue
                    log.debug('    parameter %s="%s"\n' % (name, value))
                    destination_args[name] = value
                log.debug('    instantiating destination %s with args %s\n' % (destination_type, destination_args))
                destination = destination_func(**destination_args)

                # Filters
                log.debug('  getting filters\n')
                _filters = []
                filtersections =  [section.lower() for section in configparser.sections() if section.lower().startswith('filter')]
                filtersections.sort()
                for section in filtersections:
                    log.debug('    processing filter section %s\n' % section)
                    filter_type = configparser.get(section, 'type')
                    log.debug('      type="%s"\n' % filter_type)
                    filter_func = getattr(filters, filter_type)
                    if not callable(filter_func):
                        raise getmailConfigurationError('configuration file %s specifies incorrect filter type (%s)' % (path, filter_type))
                    filter_args = {}
                    for (name, value) in configparser.items(section):
                        if name == 'type' : continue
                        log.debug('      parameter %s="%s"\n' % (name, value))
                        filter_args[name] = value
                    log.debug('      instantiating filter %s with args %s\n' % (filter_type, filter_args))
                    mail_filter = filter_func(**filter_args)
                    _filters.append(mail_filter)

            except ConfigParser.NoSectionError, o:
                raise getmailConfigurationError('configuration file %s missing section (%s)' % (path, o))
            except ConfigParser.NoOptionError, o:
                raise getmailConfigurationError('configuration file %s missing option (%s)' % (path, o))
            #except (AttributeError, ConfigParser.DuplicateSectionError, ConfigParser.InterpolationError, ConfigParser.MissingSectionHeaderError, ConfigParser.ParsingError), o:
            except (ConfigParser.DuplicateSectionError, ConfigParser.InterpolationError, ConfigParser.MissingSectionHeaderError, ConfigParser.ParsingError), o:
                raise getmailConfigurationError('configuration file %s incorrect (%s)' % (path, o))

            # Apply overrides from commandline
            for option in ('read_all', 'delete', 'verbose'):
                val = getattr(options, 'override_%s' % option)
                if val is not None:
                    log.debug('overriding option %s from commandline %s\n' % (option, val))
                    config[option] = val

            if not options.trace and not config['verbose']:
                log.clearhandlers()
                log.addhandler(sys.stderr, logging.WARNING)
            
            if options.dump_config:
                log.info('getmail configuration:\n')
                log.info('  retriever:  ')
                retriever.showconf()
                log.info('  destination:  ')
                destination.showconf()
                log.info('  options:\n')
                names = config.keys()
                names.sort()
                for name in names:
                    log.info('    %s : %s\n' % (name, config[name]))
                log.info('\n')
            else:
                configs.append( (retriever, _filters, destination, config.copy()) )

        go(configs)

    except getmailConfigurationError, o:
        # DEBUG
        raise
        log.error('Configuration error: %s\n' % o)
        sys.exit(2)
    except getmailOperationError, o:
        # DEBUG
        raise
        log.error('Error: %s\n' % o)
        sys.exit(3)

#######################################
if __name__ == '__main__':
    main()
