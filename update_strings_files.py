#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Localize.py - Incremental localization on Xcode projects
# João Moreno 2009
# http://joaomoreno.com/

# Modified by Steve Streeting 2010 http://www.stevestreeting.com
# Changes
# - Use .strings files encoded as UTF-8
#   This is useful because Mercurial and Git treat UTF-16 as binary and can't
#   diff/merge them. For use on iPhone you can run an iconv script during build to
#   convert back to UTF-16 (Mac OS X will happily use UTF-8 .strings files).
# - Clean up .old and .new files once we're done

# Modified by Yoichi Tagaya 2015 http://github.com/yoichitgy
# Changes
# - Use command line arguments to execute as `mergegenstrings.py path routine`
#       path: Path to the directory containing source files and lproj directories.
#       routine: Routine argument for genstrings command specified with '-s' option.
# - Support both .swift and .m files.
# - Support .storyboard and .xib files.

# Modified by Stefan Brighiu 2019 https://github.com/sbrighiu
#
# Documentation / Nice to know information for less headaches:
#
# IMPORTANT It is highly recommended to use Base internationalisation option and not use/delete
#   English (development language) to prevent localized string values mismatch between
#   storyboard strings and the en.lproj/Main.strings file. This will allow all unsupported
#   languages to use the Base.lproj folder strings when the language in question is not
#   specifically supported. This will also remove the mismatch between en.lproj/.strings
#   and Base.lproj/.strings files (modifying the en.lproj strings file and not modifying
#   the storyboard will leave the storyboard out of date). Experiment and see what is good
#   for you
# IMPORTANT Please delete unused `.lproj' folders for removed languages as to not lose time
#   finding them them during Xcode error messages
# To cover all your .swift, .m, .xib and .storyboard files, please configure folders containing
#   interface files with the arg -int=""
# The output of the script can be seen in the Build Log and is pretty printed ;)
# Please make sure you keep a lot of commits to avoid localized data loss. The script re-generates
#   all .strings files based on your source code and interface files and may remove strings that
#   are not referenced anymore. This usually is a good thing :D
# If the script prints out Failed to create new/merge into Localizable.strings file, try deleting
#   the .strings file from Finder/terminal and run the script again. Modifying the .strings files
#   manually may result in this error.
# This version of the script uses temp string tags to allow developers to have the proper control
#   over what strings are localized and what strings are not
# This version of the script uses default values of strings (values that are the same as the key)
#   to remind developers to set temporary or permanent version of the code, before they can run
#   their code. This will enable developers to stop invalid localized strings so they never again
#   reach production.
# To run the script, copy it in the root of your project and then either run it from terminal using
#   the command ./update_strings_files.py -src=<path_to_source_directory)> or by creating a build
#   phase with this command to be ran automatically when building your project.
#
# Changes
#
# Rename script to update_strings_files.py for readability
# Update syntax to Python 3+ versions
# Add Python 3+ requirement and
# Add more documentation and nice to know facts and warnings
# Fix issue with empty *.strings files breaking the script instead of just re-generate it.
# Clean junk files before creating new temporary files in case of script fail
# Clean up .old files in case of script fail
# Introduce functionality that enforces fully localized builds
# This will trigger a Xcode build error if added as a project Build Phase
# Introduce functionality that adds a warning if the project has temporary localized strings
# This will trigger a Xcode build warning if added as a project Build Phase
# Change the way the arguments are passed to the command (-src=, -int=, -tag=, -rou=, -dev=)
# Add an argument to allow for interface folder locations
# By default, the interface location will be in the root path specified with arg -src=
# Add an argument to allow for temporary localized strings tag customization
# This tag is by default set as * and is optional.
# Usage in .strings file: ... "" = "* "; ...
# Add extended logging of what strings are removed, added, default (have key == value) and
#   translated
# (have key != value)
# As this version of the script is based on the existence of Base.lproj for storyboards, the
#   default tag will be associated with the development language set in the arguments of the
#   executed script and will be ignored when checking if the Xcode project is allowed to run
#   without errors.
# Default tags have an extra letter associated c (if the comment was updated) or o (if not).
#
#
# Requirements:
# - Python 3+
# - a bit of time to read
#
# Old information updated
#
# - Place the script update_strings_files.py in the root of your project. Also please observe how to use
#   Base.lproj instead of en.lproj (development language) in this following screenshot. This is a workspace
#   including other projects/frameworks.
#   <img width="601" alt="Screen Shot 2019-05-28 at 18 25 20"
#   src="https://user-images.githubusercontent.com/6714874/58490623-01951580-815d-11e9-95f5-740cc08181fd.png">
# - To run the script automatically, you can create a build phase and add it on your Target.
#   <img width="973" alt="Screen Shot 2019-05-28 at 18 25 44"
#   src="https://user-images.githubusercontent.com/6714874/58491595-d57a9400-815e-11e9-8255-7aeb11c0f44d.png">
# - To use a custom routine, instead of MyLocalizedString, use -rou="MyString" argument (MyString).
# - To change the development language, use -dev="ja" (Japanese).
# - If the script does not have rights to be executed, run command `chmod +x update_strings_files.py`.

# Version 1.0.1
# - Remove implicit error when untranslated strings.
# - Add --strict and --nowarn to enable error triggering and ignore warnings.
# - Remove interface localization to encourage all strings to be added from code.

from sys import argv
from codecs import open
from re import compile
from copy import copy
import os

re_translation = compile(r'^"(.+)" = "(.+)";$')
left_side_of_translation = compile(r'^"(.+)" = ')
re_comment_single = compile(r'^/\*.*\*/$')
re_comment_start = compile(r'^/\*.*$')
re_comment_end = compile(r'^.*\*/$')

STRINGS_FILE = 'Localizable.strings'
LPROJ_EXTENSION = '.lproj'

TEMP_TAG = ''
SHOULD_TRIGGER_WARNING_BECAUSE_OF_TEMP_STRINGS = 0
TEMP_WARNING_DETAILS = ''
SHOULD_TRIGGER_ERROR_BECAUSE_OF_DEFAULT_STRINGS = 0

DID_INITIALIZE = 0
IGNORE_WARN = 0


class LocalizedString():
    def __init__(self, comments, translation):
        self.comments, self.translation = comments, translation
        self.key, self.value = re_translation.match(self.translation).groups()

    def __unicode__(self):
        return u'%s%s\n' % (u''.join(self.comments), self.translation)

    def update_translation(self):
        left = left_side_of_translation.match(self.translation).group(0)
        self.translation = left + '\"%s\"' % self.value + ';\n'


class LocalizedFile():
    def __init__(self, fname=None, auto_read=False):
        self.fname = fname
        self.strings = []
        self.strings_d = {}

        if auto_read:
            self.read_from_file(fname)

    def read_from_file(self, fname=None):
        fname = self.fname if fname == None else fname
        try:
            f = open(fname, encoding='utf_8', mode='r')
        except:
            print('File %s does not exist.' % fname)
            f.close()
            exit(-1)

        found_one = 0

        line = None
        try:
            line = f.readline()
        except:
            f.close()

        while line:
            comments = [line]

            if not re_comment_single.match(line):
                while line and not re_comment_end.match(line):
                    line = f.readline()
                    comments.append(line)

            line = f.readline()
            if line and re_translation.match(line):
                found_one = 1
                translation = line
            else:
                last_comment = comments and comments[-1]
                if last_comment is not None and (last_comment == '' or found_one == 0):
                    break

                raise Exception('Invalid file.')

            line = f.readline()
            while line and line == u'\n':
                line = f.readline()

            string = LocalizedString(comments, translation)
            self.strings.append(string)
            self.strings_d[string.key] = string

        f.close()

    def save_to_file(self, fname=None):
        fname = self.fname if fname == None else fname
        try:
            f = open(fname, encoding='utf_8', mode='w')
        except:
            print('Couldn\'t open file %s.' % fname)
            exit(-1)

        for string in self.strings:
            f.write(string.__unicode__())

        f.close()

    def make_all_strings_temporary(self):
        new_strings = []
        for string in self.strings:
            if not string.value.startswith(TEMP_TAG.strip("'").strip('"')):
                new_string = copy(string)
                new_string.value = TEMP_TAG.strip("'").strip('"') + new_string.value
                new_string.update_translation()
                new_strings.append(new_string)
                self.strings_d[string.key] = new_string
        self.strings = new_strings

    def merge_with(self, new, final_filename, development_language_folder):
        global SHOULD_TRIGGER_WARNING_BECAUSE_OF_TEMP_STRINGS
        global TEMP_WARNING_DETAILS

        merged = LocalizedFile()

        is_dev_language = final_filename.find(development_language_folder) != -1 or final_filename.find('Base.lproj') != -1

        added_strings = []
        translated_strings = []
        temporary_strings = []
        for string in new.strings:
            if string.key not in self.strings_d:
                new_string = copy(string)

                if not is_dev_language:
                    new_string.value = TEMP_TAG.strip("'").strip('"') + new_string.value
                    new_string.update_translation()
                    temporary_strings.append(new_string)

                added_strings.append(new_string)
                string = new_string
            else:
                old = self.strings_d[string.key]
                new_string = copy(old)
                new_string.comments = string.comments

                if not is_dev_language:
                    if new_string.value.startswith(TEMP_TAG.strip("'").strip('"')):
                        temporary_strings.append(new_string)
                    else:
                        translated_strings.append(new_string)
                else:
                    translated_strings.append(new_string)

                string = new_string

            merged.strings.append(string)
            merged.strings_d[string.key] = string

        separator = "~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"
        if is_dev_language:
            added = len(added_strings)
            total = len(merged.strings)

            print('  %s' % separator)

            print('  => ' + str(added) + (' string was' if len(added_strings) == 1 else ' strings were') + ' added' \
                  ' [Total: ' + str(total) + ']')
            print('  => All strings are automatically marked as translated')

        else:
            # Show Added/Removed strings print statements
            show_once = 1

            for string in added_strings:
                print('    [.....Added] "%s" = "%s"' % (string.key, string.value))

            for oldString in self.strings:
                if show_once and len(temporary_strings) > 0:
                    TEMP_WARNING_DETAILS = TEMP_WARNING_DETAILS + '\n\n+ %s:\n' % final_filename
                    show_once = 0

                found = 0

                for string in temporary_strings:
                    if oldString.key == string.key:
                        data = '"%s" = "%s"' % (string.key, string.value)
                        TEMP_WARNING_DETAILS = TEMP_WARNING_DETAILS + '    ' + data

                        print('    [.Temporary] ' + data)
                        found = 1
                        break

                TEMP_WARNING_DETAILS = TEMP_WARNING_DETAILS + '\n'

                for string in translated_strings:
                    if oldString.key == string.key:
                        print('    [Translated] "%s" = "%s"' % (string.key, string.value))
                        found = 1
                        break
                if not found:
                    print('    [...Removed] "%s" = "%s"' % (oldString.key, oldString.value))

            if len(temporary_strings) != 0:
                SHOULD_TRIGGER_WARNING_BECAUSE_OF_TEMP_STRINGS = 1

            print('\n  %s' % separator)

            translated = len(translated_strings)
            total = len(merged.strings)
            left = total-translated
            percentage = int(translated*100/total) if total != 0 else 0
            temporary = len(temporary_strings)
            temporary_total = total
            percentage_temporary = int(temporary*100/temporary_total) if temporary_total != 0 else 0
            extra = '' if percentage == 100 else ('  => ' + str(left) + ' more ' + ('string' if left == 1 else 'strings') + ' left to translate')
            conjugation = 'has' if translated == 1 else 'have'

            extra_temp_part = ' but ' + str(percentage_temporary) + '% are still temporary strings' if percentage_temporary != 0 else ''

            print('  => ' + str(translated) + ' ' + ('string' if translated == 1 else 'strings') + ' ' + conjugation +
                  ' been translated [Total: ' + str(total) + ']')
            print('  => ' + str(percentage) + '% of all strings were translated' + extra_temp_part)
            print(extra) if len(extra) != 0 else []

        print('\n')
        return merged


def merge(merged_fname, old_fname, new_fname, development_language_folder):
    old = None
    try:
        old = LocalizedFile(old_fname, auto_read=True)
    except:
        old = LocalizedFile()

    new = LocalizedFile(new_fname, auto_read=True)
    merged = old.merge_with(new, merged_fname, development_language_folder)
    merged.save_to_file(merged_fname)


def initialize_file_from(fname, new_fname, development_language_folder):
    is_dev_language = new_fname.find(development_language_folder) != -1 or new_fname.find('Base.lproj') != -1
    if not is_dev_language:
        new = LocalizedFile(fname, auto_read=True)
        new.make_all_strings_temporary()
        new.save_to_file(new_fname)
    else:
        os.rename(fname, new_fname)


def localize_code(rawPath, customPath, routine, development_language_folder):
    global DID_INITIALIZE
    global IGNORE_WARN

    path = rawPath
    if customPath:
        path = os.path.join(path, customPath)

    try:
        languages = [lang for lang in [os.path.join(path, name) for name in os.listdir(path)]
                     if lang.endswith(LPROJ_EXTENSION) and os.path.isdir(lang)]

        if len(languages) == 0:
            print('- No *.lproj folders detected -\n')

        for language in languages:
            print('+ ' + language + '/' + STRINGS_FILE + '\n')

            original = merged = os.path.join(language, STRINGS_FILE)
            old = original + '.old'
            new = original + '.new'
            invalid = original + '.invalid'

            # Clean junk files
            if os.path.isfile(old):
                os.remove(old)
            if os.path.isfile(new):
                os.remove(new)

            gen_strings_command = 'find "%s" -type f -name "*.swift" -print0 -or -name "*.m" -print0' \
                                  ' | tr "\n" "\t" | xargs -0 xcrun extractLocStrings -q -s "%s" -o "%s"' % (path, routine, language)
            if os.path.isfile(original):
                file_type = os.popen('file -b --mime-encoding "%s"' % original).read()
                if file_type.startswith('us-ascii') or file_type.startswith('utf'):
                    os.rename(original, old)
                else:
                    if os.stat(original).st_size == 0:
                        os.remove(original)
                    else:
                        os.rename(original, invalid)

                os.system(gen_strings_command)

                if os.path.isfile(original):
                    os.system('iconv -f UTF-16 -t UTF-8 "%s" > "%s"' % (original, new))
                else:
                    open(new, 'w')

                if os.path.isfile(old):
                    merge(merged, old, new, development_language)
                else:
                    if os.path.isfile(new):
                        os.rename(new, original)
                    else:
                        if os.path.isfile(invalid):
                            os.rename(invalid, original)

            else:
                DID_INITIALIZE = 1
                os.system(gen_strings_command)

                print('    Generated a new Localizable.strings file from source code.')

                if os.path.isfile(original):
                    os.system('iconv -f UTF-16 -t UTF-8 "%s" > "%s"' % (original, old))
                    initialize_file_from(old, new, development_language)
                    os.rename(new, original)
                else:
                    open(original, 'w')

            if os.path.isfile(old):
                os.remove(old)
            if os.path.isfile(new):
                os.remove(new)

    except:
        print('- No language folders present -\n')


if __name__ == '__main__':
    # Check for Python 3+
    print('Executed with: ')
    python_installed = os.system('python3 --version') == 0
    if not python_installed:
        print('This script is written in python and was build compatible to Python 3.7.3. ' +
              '\nIt may run using Python 3+ versions but I recommend this version for ' +
              'any troubleshooting involved.\nTo download Python on your mac, go to ' +
              'https://www.python.org, download and install.')
        quit(-1)

    print('\n')

    help_text = 'Please use only the following arguments and syntax:\n' \
                'Usage: %s\n' \
                '          -src=path_to_source_directory\n' \
                '          -tag=[temporary_string_tag]\n' \
                '          --strict\n' \
                '          --nowarn\n' \
                '          -rou=[routine]\n' \
                '          -dev=[development_language]\n' \
                'Please make sure to use \"\" for the argument values.\n' \
                'For warnings to be treated as errors, add --strict.' % argv[0]

    argc = len(argv)
    if argc < 1 or 6 < argc:
        print(help_text)
        quit(-2)

    path = '.'
    TEMP_TAG = '*'.strip("'").strip('"')
    routine = 'NSLocalizedString'
    development_language = 'en'

    for arg in argv:
        if arg == argv[0]:
            continue
        if arg.startswith('-src='):
            value = arg[5:]
            if value != '':
                path = value
                continue
        if arg.startswith('-tag='):
            value = arg[5:]
            if value != '':
                TEMP_TAG = value.strip("'").strip('"')
                continue
        if arg.startswith('--strict'):
            SHOULD_TRIGGER_ERROR_BECAUSE_OF_DEFAULT_STRINGS = 1
            continue
        if arg.startswith('--nowarn'):
            IGNORE_WARN = 1
            continue
        if arg.startswith('-rou='):
            value = arg[5:]
            if value != '':
                routine = value
                continue
        if arg.startswith('-dev='):
            value = arg[5:]
            if value != '':
                development_language = value
                continue
        print(help_text)
        quit(-3)

    development_language_folder = os.path.splitext(development_language)[0] + LPROJ_EXTENSION

    # Configure these paths to cover all your coding needs
    localize_code(path, '', routine, development_language_folder)

    info_for_temp_tag = '(strings prefixed with \'' + TEMP_TAG + '\')'
    if (not DID_INITIALIZE) and SHOULD_TRIGGER_WARNING_BECAUSE_OF_TEMP_STRINGS and SHOULD_TRIGGER_ERROR_BECAUSE_OF_DEFAULT_STRINGS:
        print('----- Xcode error -----')
        os.system('echo "error: You have strings that are not translated! Replace all temporary strings ' + info_for_temp_tag +
                  ' and add translated ones to be able to build the project without errors.%s"' % TEMP_WARNING_DETAILS)
        quit(-4)

    should_take_warn_into_account = (not IGNORE_WARN) and SHOULD_TRIGGER_WARNING_BECAUSE_OF_TEMP_STRINGS
    if should_take_warn_into_account:
        print('----- Xcode warning -----')
        os.system('echo "warning: There are string keys which need to be translated.%s"' % TEMP_WARNING_DETAILS)

    print('\n')
