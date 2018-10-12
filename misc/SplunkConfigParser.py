#!/usr/bin/env python2

import ConfigParser
import re


class SplunkConfigParser(ConfigParser.RawConfigParser):
    SECTCRE = re.compile(
        r'\['  # [
        r'(?P<header>[^]]*)'  # very permissive! Includes zero-length strings
        r'\]'  # ]
    )
    OPTCRE = re.compile(
        r'(?P<option>[^:=\s][^:=]*)'  # very permissive!
        r'\s*(?P<vi>[:=])\s*'  # any number of space/tab,
        # followed by separator
        # (either : or =), followed
        # by any # space/tab
        r'(?P<value>.*?)(?P<continued>\\)?$'  # everything up to eol
    )
    OPTCRE_NV = re.compile(
        r'(?P<option>[^:=\s][^:=]*)'  # very permissive!
        r'\s*(?:'  # any number of space/tab,
        r'(?P<vi>[:=])\s*'  # optionally followed by
        # separator (either : or
        # =), followed by any #
        # space/tab
        r'(?P<value>.*?)(?P<continued>\\)?)?$'  # everything up to eol
    )
    OPTCRE_CONTINUED = re.compile(
        r'(?P<value>.*?)(?P<continued>\\)?$'  # continued line, parse for escaped newline ('\\' is last character)
    )

    def _read(self, fp, fpname):
        """Parse a sectioned setup file.

        The sections in setup file contains a title line at the top,
        indicated by a name in square brackets (`[]'), plus rel_path/value
        options lines, indicated by `name: value' format lines.
        Continuations are represented by an embedded newline then
        leading whitespace.  Blank lines, lines beginning with a '#',
        and just about everything else are ignored.
        """
        cursect = None  # None, or a dictionary
        optname = None
        lineno = 0
        e = None  # None, or an exception
        while True:
            line = fp.readline()
            if not line:
                break
            lineno = lineno + 1
            # comment or blank line?
            if line.strip() == '' or line[0] in '#;':
                continue
            if line.split(None, 1)[0].lower() == 'rem' and line[0] in "rR":
                # no leading whitespace
                continue
            # continuation line?
            # REPLACED FOR SPLUNK CONF LINE CONTINUATION (e.g. \\\n)
            # if line[0].isspace() and cursect is not None and optname:
            #     value = line.strip()
            #     if value:
            #         cursect[optname].append(value)
            # a section header or option header?
            else:
                # is it a section header?
                mo = self.SECTCRE.match(line)
                if mo:
                    sectname = mo.group('header')
                    if sectname in self._sections:
                        cursect = self._sections[sectname]
                    elif sectname == ConfigParser.DEFAULTSECT:
                        cursect = self._defaults
                    else:
                        cursect = self._dict()
                        cursect['__name__'] = sectname
                        self._sections[sectname] = cursect
                    # So sections can't start with a continuation line
                    optname = None
                # no section header in the file?
                elif cursect is None:
                    raise ConfigParser.MissingSectionHeaderError(fpname, lineno, line)
                # an option line?
                else:
                    mo = self._optcre.match(line)
                    if mo:
                        optname, vi, optval, continued = mo.group('option', 'vi', 'value', 'continued')
                        optname = self.optionxform(optname.rstrip())
                        # This check is fine because the OPTCRE cannot
                        # match if it would set optval to None
                        if optval is not None:
                            optval = optval.strip()
                            if continued:
                                optval = [optval]
                                # loop until we reach end of multi-line value
                                while continued:
                                    line = fp.readline()
                                    if not line:
                                        break
                                    lineno = lineno + 1
                                    match = self.OPTCRE_CONTINUED.match(line)
                                    if match:
                                        value, continued = match.group('value', 'continued')
                                        optval.append(value)
                            elif optval == '""':
                                optval = ['']
                            else:
                                optval = [optval]
                            # allow empty values
                            cursect[optname] = optval
                        else:
                            # valueless option handling
                            cursect[optname] = optval
                    else:
                        # a non-fatal parsing error occurred.  set up the
                        # exception but keep going. the exception will be
                        # raised at the end of the file and will contain a
                        # list of all bogus lines
                        if not e:
                            e = ConfigParser.ParsingError(fpname)
                        e.append(lineno, repr(line))
        # if any parsing errors occurred, raise an exception
        if e:
            raise e

        # join the multi-line values collected while reading
        all_sections = [self._defaults]
        all_sections.extend(self._sections.values())
        for options in all_sections:
            for name, val in options.items():
                if isinstance(val, list):
                    options[name] = '\n'.join(val)

    def add_section(self, section):
        """Create a new section in the configuration.

        Raise DuplicateSectionError if a section by the specified name
        already exists. Raise ValueError if name is DEFAULT or any of it's
        case-insensitive variants.
        """
        if section in self._sections:
            raise ConfigParser.DuplicateSectionError(section)
        self._sections[section] = self._dict()

    def optionxform(self, optionstr):
        return str(optionstr)

    def write(self, fp):
        """Write an .ini-format representation of the configuration state."""
        if self._defaults:
            fp.write("[%s]\n" % ConfigParser.DEFAULTSECT)
            for (key, value) in self._defaults.items():
                fp.write("%s = %s\n" % (key, str(value).replace('\n', '\\\n')))
            fp.write("\n")
        for section in self._sections:
            fp.write("[%s]\n" % section)
            for (key, value) in self._sections[section].items():
                if key == "__name__":
                    continue
                if (value is not None) or (self._optcre == self.OPTCRE):
                    key = " = ".join((key, str(value).replace('\n', '\\\n')))
                fp.write("%s\n" % (key))
            fp.write("\n")
