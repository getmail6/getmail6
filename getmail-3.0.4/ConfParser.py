#!/usr/bin/python
'''Configuration file parser for files similar to MS-Windows .ini files.
Meant as a replacement for the broken ConfigParser module in the Python
standard library.

Copyright (C) 2000-2003 Charles Cazabon <getmail @ discworld.dyndns.org>

This program is free software; you can redistribute it and/or
modify it under the terms of version 2 of the GNU General Public License
as published by the Free Software Foundation.  A copy of this license should
be included in the file COPYING.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program; if not, write to the Free Software
Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA  02111-1307, USA.

For documentation, see the Python standard module ConfigParser documentation.
This module is similar, except:
    o Options are supplied with option_name=option_value pairs only (not ':').
    o Comments are allowed on the same lines as data, with '#' as the comment
        delimiter.
    o Leading and trailing whitespace is ignored.
    o Whitespace surrounding the '=' sign is ignored.
    o Option values can be quoted with single or double quotes, to preserve
        leading or trailing whitespace, or if they contain a whitespace or the 
        "#" symbol which would otherwise mark the start of a comment.
    o Empty option values must be quoted; use the empty string ("" or '')
    o Option values are returned as either:
        o a string, if the option name occurs once in the section
        o a list of strings, if the option name occurs multiple times
    o All the limitations on what characters can be in section headers and
        option values are gone, except that '#' is forbidden (because it
        starts a comment), and option names cannot contain '=' (because that
        starts a value).
'''

__version__ = '3.3'
__author__ = 'Charles Cazabon <software @ discworld.dyndns.org>'

#
# Imports
#

import string
import UserDict
import sys
import shlex
import cStringIO
from types import *


#
# ConfParser exception classes
#

# Base class for all ConfParser exceptions
class ConfParserException (Exception):
    pass

# Specific exceptions
class NoSectionError (ConfParserException):
    '''Exception raised when a specified section is not found.
    '''
    pass

class DuplicateSectionError (ConfParserException):
    '''Exception raised when mutliple sections with the same name are found, or 
    if add_section() is called with the name of a section that is already 
    present.
    '''
    pass

class NoOptionError (ConfParserException):
    '''Exception raised when a specified option is not found in the specified 
    section.
    '''
    pass

class MissingSectionHeaderError (ConfParserException):
    '''Exception raised when attempting to parse a file which has no section
    headers.
    '''
    pass

class ParsingError (ConfParserException):
    '''Exception raised when errors occur attempting to parse a file.
    Also raised if defaults is not a dictionary, or when reading a file fails.
    These errors are not covered by exceptions in the standard Python
    ConfigParser module.
    '''
    pass

class ConversionError (ConfParserException):
    '''Exception raised when a value conversion (i.e. to integer) fails.
    '''
    pass


#
# Globals
#

debug = 0

#
# Helper functions
#

#######################################
def log (msg):
    if not debug:  return
    sys.stderr.write (msg + '\n')
    sys.stderr.flush ()

#
# ConfParser SmartDict class
#

#######################################
class SmartDict (UserDict.UserDict):
    '''Dictionary class which handles lists and singletons intelligently.
    '''
    #######################################
    def __init__ (self, initialdata = {}):
        '''Constructor.
        '''
        UserDict.UserDict.__init__ (self, {})
        for (key, value) in initialdata.items ():
            self.__setitem (key, value)

    #######################################
    def __getitem__ (self, key):
        '''
        '''
        try:
            value = self.data[key]
            if len (value) == 1:
                return value[0]
            return value
        except KeyError, txt:
            raise KeyError, txt

    #######################################
    def __setitem__ (self, key, value):
        '''
        '''
        if type (value) in (ListType, TupleType):
            self.data[key] = list (value)
        else:
            self.data[key] = [value]


#
# Main ConfParser class
#

#######################################
class ConfParser:
    '''Class to parse a configuration file without all the limitations in
    ConfigParser.py, but without the dictionary formatting options either.
    '''
    #######################################
    def __init__ (self, defaults = {}):
        '''Constructor.
        '''
        self.__rawdata = []
        self.__sectionlist = []
        self.__sections = []
        self.__defaults = SmartDict ()

        try:
            for key in defaults.keys ():
                self.__defaults[key] = defaults[key]

        except AttributeError:
            raise ParsingError, 'defaults not a dictionary (%s)' % defaults

    #######################################
    def read (self, filelist):
        '''Read configuration file(s) from list of 1 or more filenames.
        '''
        if type (filelist) not in (ListType, TupleType):
            filelist = [filelist]

        try:
            for filename in filelist:
                log ('Reading configuration file "%s"' % filename)
                f = open (filename, 'r')
                self.__rawdata = self.__rawdata + f.readlines ()
                f.close ()
    
        except IOError, txt:
            raise ParsingError, 'error reading configuration file (%s)' % txt

        self.__parse ()
        return self

    #######################################
    def __parse (self):
        '''Parse the read-in configuration file.
        '''
        config = string.join (self.__rawdata, '\n')
        f = cStringIO.StringIO (config)
        lex = shlex.shlex (f)
        lex.wordchars = lex.wordchars + '|/.,$^\\():;@-+?<>!%&*`~'
        section_name = ''
        option_name = ''
        option_value = ''
        
        while 1:
            token = lex.get_token ()
            if token == '':
                break

            if not (section_name):
                if token != '[':
                    raise ParsingError, 'expected section start, got %s' % token
                section_name = ''
                while 1:
                    token = lex.get_token ()
                    if token == ']':
                        break
                    if token == '':
                        raise ParsingError, 'expected section end, hit EOF'
                    if section_name:
                        section_name = section_name + ' '
                    section_name = section_name + token
                if not section_name:
                    raise ParsingError, 'expected section name, got nothing'

                section = SmartDict ()
                # Collapse case on section names
                section_name = string.lower (section_name)
                if section_name in self.__sectionlist:
                    raise DuplicateSectionError, \
                        'duplicate section (%s)' % section_name
                section['__name__'] = section_name
                continue

            if token == '=':
                raise ParsingError, 'expected option name, got ='

            if token == '[':
                # Start new section
                lex.push_token (token)
                if section_name in self.__sectionlist:
                    raise DuplicateSectionError, \
                        'duplicate section (%s)' % section_name
                if section['__name__'] == 'default':
                    self.__defaults.update (section)
                self.__sectionlist.append (section_name)
                self.__sections.append (section.copy ())
                section_name = ''
                continue

            if not option_name:
                option_name = token
                token = lex.get_token ()
                if token != '=':
                    raise ParsingError, 'Expected =, got %s' % token

                token = lex.get_token ()
                if token in ('[', '='):
                    raise ParsingError, 'expected option value, got %s' % token
                option_value = token

                if option_value[0] in ('"', "'") and option_value[0] == option_value[-1]:
                    option_value = option_value[1:-1]
                                  
                if section.has_key (option_name):
                    if type (section[option_name]) == ListType:
                        section[option_name].append (option_value)
                    else:
                        section[option_name] = [section[option_name], option_value]
                else:
                    section[option_name] = option_value
                
                option_name = ''
                
        # Done parsing        
        if section_name:
            if section_name in self.__sectionlist:
                raise DuplicateSectionError, \
                    'duplicate section (%s)' % section_name
            if section['__name__'] == 'default':
                self.__defaults.update (section)
            self.__sectionlist.append (section_name)
            self.__sections.append (section.copy ())
        
        if not self.__sectionlist:
            raise MissingSectionHeaderError, 'no section headers in file'

    #######################################
    def defaults (self):
        '''Return a dictionary containing the passed-in instance-wide defaults.
        '''
        return self.__defaults.copy ()

    #######################################
    def has_section (self, section):
        '''Indicates whether the named section is present in the configuration. 
        The default section is not acknowledged.
        '''
        section = string.lower (section)
        if section not in self.sections ():
            return 0
        return 1
        
    #######################################
    def sections (self):
        '''Return a list of sections in the configuration file.
        '''
        s = self.__sectionlist[:]
        try:
            # Remove 'default' section from returned list
            i = s.index ('default')
            del s[i]
        except ValueError:
            # No default section
            pass
        
        return s

    #######################################
    def options (self, section):
        '''Return list of options in section.
        '''
        try:
            s = self.__sectionlist.index (string.lower (section))

        except ValueError:
            raise NoSectionError, 'missing section:  "%s"' % section

        return self.__sections[s].keys ()

    #######################################
    def get (self, section, option, raw=0, _vars={}):
        '''Get an option value for the provided section. All the "%" 
        interpolations are expanded in the return values, based on the defaults 
        passed into the constructor, as well as the options _vars provided, 
        unless the raw argument is true.  __vars contents must be lists.
        '''

        try:
            s = self.__sectionlist.index (string.lower (section))
            options = self.__sections[s]
        except ValueError:
            raise NoSectionError, 'missing section (%s)' % section

        expand = self.__defaults.copy ()
        expand.update (_vars)
        
        if not options.has_key (option):
            if expand.has_key (option):
                return expand[option]
            raise NoOptionError, 'section [%s] missing option (%s)' \
                % (section, option)

        rawval = options[option]
        
        if raw:
            return rawval

        try:
            value = []
            if type (rawval) != ListType:
                rawval = [rawval]
            for part in rawval:
                try:
                    part = part % expand
                except:
                    raise
                value.append (part)
            if len (value) == 1:
                return value[0]
            return value                
        except KeyError, txt:
            raise NoOptionError, 'section [%s] missing option (%s)' \
                % (section, option)
        except (TypeError, ValueError), txt:
            raise ConversionError, 'invalid conversion or specification' \
                ' for option %s (%s (%s))' % (option, rawval, txt)

    #######################################
    def getint (self, section, option):
        '''A convenience method which coerces the option in the specified
        section to an integer.
        '''
        val = self.get (section, option)
        try:
            return int (val)
        except (TypeError, ValueError), txt:
            raise ConversionError, 'option %s not an integer (%s)' % (option, val)

    #######################################
    def getfloat (self, section, option):
        '''A convenience method which coerces the option in the specified
        section to a floating point number.
        '''
        val = self.get (section, option)
        try:
            return float (val)
        except (TypeError, ValueError), txt:
            raise ConversionError, 'option %s not a float (%s)' % (option, val)

    #######################################
    def getboolean (self, section, option):
        '''A convenience method which coerces the option in the specified
        section to a boolean value. Note that the only accepted values for the
        option are "0" and "1", any others will raise ValueError.
        '''
        val = self.getint (section, option)
        return val != 0     
        
    #######################################
    def getstring (self, section, option):
        '''A convenience method which enforces that the option value is a 
        single string.  Multiple values will raise ValueError.
        '''
        val = self.get (section, option)
        if type (val) == ListType:
            raise ConversionError, 'expected single value, got list ([%s] %s == "%s")' % (section, option, val)
        return val

    #######################################
    def dump (self):
        '''Dump the parsed contents of the configuration file.
        '''
        sys.stderr.write ('ConfParser dump:\n\n')
        sections = self.__sectionlist[:]
        sections.sort ()
        for section in sections:
            sys.stderr.write ('  Section [%s]:\n' % section)
            options = self.options (section)
            options.sort ()
            for option in options:
                values = self.get (section, option)
                if type (values) == ListType:
                    sys.stderr.write ('    %s:\n' % option)
                    for value in values:
                        sys.stderr.write ('         %s\n' % value)
                else:
                    sys.stderr.write ('    %s:  %s\n' % (option, values))
            sys.stderr.write ('\n')
            