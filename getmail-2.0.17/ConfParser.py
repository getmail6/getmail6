#!/usr/bin/python
'''Configuration file parser for files similar to MS-Windows .ini files.
Meant as a replacement for the broken ConfigParser module in the Python
standard library.

Copyright (C) 2000 Charles Cazabon <getmail @ discworld.dyndns.org>

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
		delimiter.  Also, anything after a section title (same line) is assumed
		to be a comment.
	o Leading and trailing whitespace is ignored.
	o Whitespace surrounding the '=' sign is ignored.
	o Option values can be quoted with single or double quotes, to preserve
		leading or trailing whitespace, or if they contain a "#" symbol which
		would otherwise mark the start of a comment.
	o If an option is supplied without a value, the empty string ('') is
		assumed.
	o Option values are returned as either:
		o a string, if the option name occurs once in the section
		o a list of strings, if the option name occurs multiple times
	o All the limitations on what characters can be in section headers and
		option values are gone, except that '#' is forbidden (because it
		starts a comment), and option names cannot contain '=' (because that
		starts a value).

I welcome questions and comments at <software @ discworld.dyndns.org>.
'''

__version__ = '2.0'
__author__ = 'Charles Cazabon <software @ discworld.dyndns.org>'

#
# Imports
#

import string, re, UserDict
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

class InterpolationError (ConfParserException):
	 '''Exception raised when problems occur performing string interpolation.
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


#
# Globals
#

# Regular expression strings
s_section = r'^\s*\[(?P<name>.*?)\].*?$(?P<contents>.*?)(?=^\s*\[)'
s_lastsection = r'^\s*\[(?P<name>.*?)\](\s*(#.*?)?$)(?P<contents>.*)'
s_option = r'''^(\s|#.*$)*(?P<name>.+?)\s*(\=\s*(?P<quote>['"]?)(?P<value>.*?)(?P=quote)(\s*)(#.*?)?)?$'''

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

		self.re_section = re.compile (s_section,
			re.MULTILINE | re.IGNORECASE | re.DOTALL)
		self.re_lastsection = re.compile (s_lastsection,
			re.MULTILINE | re.IGNORECASE | re.DOTALL)
		self.re_option = re.compile (s_option, re.MULTILINE)

	#######################################
	def read (self, filelist):
		'''Read configuration file(s) from list of 1 or more filenames.
		'''
		if type (filelist) not in (ListType, TupleType):
			filelist = [filelist]

		try:
			for filename in filelist:
				f = open (filename, 'r')
				self.__rawdata = self.__rawdata + f.readlines ()
				f.close ()
	
		except IOError:
			raise ParsingError, 'error reading configuration file (%s)' \
				% filename

		self.__parse ()
		return self

	#######################################
	def __parse (self):
		'''Parse the read-in configuration file.
		'''
		config = string.join (self.__rawdata, '\n')
		sect_start = 0
		re_sect = self.re_section
		while 1:
			if sect_start >= len (config):
				break
			sectmatch = re_sect.search (config, sect_start)
			if not sectmatch:
				if re_sect == self.re_lastsection:
					break
				re_sect = self.re_lastsection
				continue

			sect = SmartDict ()
			# Collapse case on section names
			section_name = string.lower (sectmatch.group ('name'))

			if section_name in self.__sectionlist:
				raise DuplicateSectionError, \
					'duplicate section (%s)' % section_name

			sect['__name__'] = section_name[:]
			contents = sectmatch.group ('contents') or ''

			opt_start = 0
			while 1:
				if opt_start >= len (contents):
					break
				optmatch = self.re_option.search (contents, opt_start)
				if not optmatch:
					break

				opt_name = optmatch.group ('name')
				opt_value = optmatch.group ('value') or ''
	
				if sect.has_key (opt_name):
					if type (sect[opt_name]) == ListType:
						sect[opt_name].append (opt_value)
					else:
						sect[opt_name] = [sect[opt_name], opt_value]
				else:
					sect[opt_name] = opt_value

				opt_start = optmatch.end () + 1

			if sect['__name__'] == 'default':
				self.__defaults.update (sect)

			self.__sectionlist.append (section_name)
			self.__sections.append (sect.copy ())
			sect_start = sectmatch.end () + 1
		
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
		except TypeError, txt:
			raise InterpolationError, 'invalid conversion or specification' \
				' for option %s (%s (%s))' % (option, rawval, txt)

	#######################################
	def getint (self, section, option):
		'''A convenience method which coerces the option in the specified
		section to an integer.
		'''
		val = self.get (section, option)
		try:
			return int (val)
		except ValueError:
			raise InterpolationError, 'option %s not an integer (%s)' \
				% (option, val)

	#######################################
	def getfloat (self, section, option):
		'''A convenience method which coerces the option in the specified
		section to a floating point number.
		'''
		val = self.get (section, option)
		try:
			return float (val)
		except ValueError:
			raise InterpolationError, 'option %s not a float (%s)' \
				% (option, val)

	#######################################
	def getboolean (self, section, option):
		'''A convenience method which coerces the option in the specified
		section to a boolean value. Note that the only accepted values for the
		option are "0" and "1", any others will raise ValueError.
		'''
		val = self.getint (section, option)
		return val != 0		
		
	#######################################
	def dump (self):
		'''Dump the parsed contents of the configuration file.
		'''
		import sys
		from types import *
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
			