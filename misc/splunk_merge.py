#!/usr/bin/python

import ConfigParser
import argparse
import fnmatch
import os
import re
import shutil
import sys
import urllib
from ConfigParser import NoOptionError
from collections import OrderedDict

from SplunkConfigParser import SplunkConfigParser

ConfigParser.DEFAULTSECT = "!!!!WILLNEVEREXIST!!!!"
DIRS = ['2', '3', '4']
MERGED_DIR = 'merged'

# parse command line args
parser = argparse.ArgumentParser()
parser.add_argument('--debug', action='store_true')
args = parser.parse_args()
DEBUG = args.debug

# Change to script path
abspath = os.path.abspath(__file__)
SCRIPT_HOME_DIR = os.path.dirname(abspath)
os.chdir(SCRIPT_HOME_DIR)


def make_dirs(dir):
    if not os.path.isdir(dir):
        debug("\n  Creating directory: %s" % dir)
        os.makedirs(dir)


def debug(msg):
    if DEBUG:
        sys.stdout.write("%s\n" % msg)


def log(msg):
    sys.stdout.write("%s\n" % msg)


# Each conf file stanza has a corresponding stanza with a timestamp in the local.meta, use the most recent
CONF_OBJECTS = {
    'alert_actions': 'local/alert_actions.conf',
    'settings': 'local/settings.conf',
    'telemetry': 'local/telemetry.conf',
    'savedsearches': 'local/savedsearches.conf',
    'macros': 'local/macros.conf',
    'transforms': 'local/transforms.conf',
    'eventtypes': 'local/eventtypes.conf',
    'datamodels': 'local/datamodels.conf',
    'collections': 'local/collections.conf',
    'dbx-ui-prefs': 'local/dbx-ui-prefs.conf',
    'sourcetypes': 'local/sourcetypes.conf',
    'viewstates': 'local/viewstates.conf',
    'ui-tour': 'local/ui-tour.conf',
    'ui-prefs': 'local/ui-prefs.conf',
    'user-prefs': 'local/user-prefs.conf'
}

# These point to file paths, copy the most recent one to the "merged" tree
FILE_OBJECTS = {
    'views': ('local/data/ui/views', lambda x: "%s.xml" % x),
    'lookups': ('lookups', lambda x: x),
    'models': ('local/data/models', lambda x: "%s.json" % x),
    'panels': ('local/data/ui/panels', lambda x: "%s.xml" % x),
    'html': ('local/data/ui/html', lambda x: "%s.html" % x),
    'nav': ('local/data/ui/nav', lambda x: "%s.xml" % x),
}

# These have triplet entries, e.g. "props/stb_diag_logs/EXTRACT-scheduler_performance_summary", strip the last "/*" and treat same as CONF
# keeping the latest section version from the 3 members
VAR_OBJECTS = {
    'props': 'local/props.conf',
    'tags': 'local/tags.conf'
}

# Just keep the metadata, nothing else needed
EMPTY_OBJECTS = {
    'inputs': 1,  # search heads do not have inputs (kruft config from original standalone search/indexer)
    'indexes': 1,  # I don't want to keep these on search heads, legacy from krufty standalone server
    'app': 1,
    'history': 1,
}


# returns file path, category of object and fixed section name (for var objs)
def get_obj_info(meta_rel_path, meta_full_path, type, name):
    # For configuration local_meta_dict, given local.meta path and type, we can derive conf file path
    rel_base_dir = os.path.dirname(os.path.dirname(meta_rel_path))
    full_base_dir = os.path.dirname(os.path.dirname(meta_full_path))
    debug("    rel_base_dir: %s (from: %s), full_base_dir: %s (from: %s), type: %s, name: %s"
          % (rel_base_dir, meta_rel_path, full_base_dir, meta_full_path, type, name))
    if type in VAR_OBJECTS:
        match = re.match(r'(?P<section_name>[^/]+)(?P<remainder>/.+)?', name)
        section_name = match.group('section_name')
        return os.path.join(rel_base_dir, VAR_OBJECTS[type]), os.path.join(full_base_dir, VAR_OBJECTS[type]), 'VAR', section_name
    if type in CONF_OBJECTS:
        return os.path.join(rel_base_dir, CONF_OBJECTS[type]), os.path.join(full_base_dir, CONF_OBJECTS[type]), 'CONF', name
    if type in FILE_OBJECTS:
        rel_dir = FILE_OBJECTS[type][0]
        filename = FILE_OBJECTS[type][1](name)
        return os.path.join(rel_base_dir, rel_dir, filename), os.path.join(full_base_dir, rel_dir, filename), 'FILE', name
    if type in EMPTY_OBJECTS:
        return None, None, 'EMPTY', name
    raise ValueError('type "%s" not in any category' % type)


def populate_dicts(config, section, full_path, rel_path):
    try:
        modtime = int(config.getfloat(section, 'modtime'))
    except NoOptionError as e:
        debug("    No 'modtime' in section '%s', skipping..." % section)
        return

    if "/" not in section:
        raise ValueError('section "%s" should have "/" in name' % section)

    existing_modtime = 0
    if rel_path in local_meta_files:
        if section in local_meta_files[rel_path]:
            existing_modtime = int(float(local_meta_files[rel_path][section].get('modtime', 1)))
    else:
        local_meta_files[rel_path] = OrderedDict()

    debug("  Comparing modtime:%s (%s) > existing_modtime:%s (%s) {current path: %s[%s]}"
           % (modtime, repr(modtime), existing_modtime, repr(existing_modtime), full_path, section))
    if modtime > existing_modtime:
        # Most recent knowledge object, local.meta and object path/section
        local_meta_files[rel_path][section] = OrderedDict(config.items(section))
        # log(repr(local_meta_files))
        match = re.match(r'^(?P<type>[^/]*)/(?P<name>.*)$', urllib.unquote(section))
        type, name = match.group('type', 'name')
        debug("  Populating... (Found newest modtime for %s[%s])" % (rel_path, section))
        obj_rel_path, obj_full_path, obj_class, section_name = get_obj_info(rel_path, full_path, type, name)
        debug(
            "    obj_rel_path: %s, obj_full_path: %s, obj_class: %s, section_name: %s"
            % (obj_rel_path, obj_full_path, obj_class, section_name)
        )
        if obj_class == "CONF" or obj_class == "VAR":
            # 'section_name' returned by get_obj_path() should be the correct one
            debug("    adding obj_full_path='%s' to local_conf_files[%s][%s]" % (obj_full_path, obj_rel_path, section_name))
            if obj_rel_path not in local_conf_files:
                local_conf_files[obj_rel_path] = OrderedDict()
            local_conf_files[obj_rel_path][section_name] = obj_full_path
        elif obj_class == "FILE":
            # If a 'FILE' we will use full_path for file copy operation
            debug("    adding obj_full_path='%s' to local_file_objects[%s]" % (obj_full_path, obj_rel_path))
            local_file_objects[obj_rel_path] = obj_full_path
        elif obj_class == "EMPTY":
            # just keep stanza with most recent timestamp in local.meta, nothing else to do
            pass
        else:
            # Should never happen
            raise ValueError('obj_class "%s" is unknown' % obj_class)


CACHED_CONFIG = OrderedDict()


def get_section_data(full_conf_path, section_name):
    if full_conf_path not in CACHED_CONFIG:
        config = SplunkConfigParser(allow_no_value=True)
        config.read(full_conf_path)
    else:
        config = CACHED_CONFIG[full_conf_path]
    if section_name in config.sections():
        return OrderedDict(config.items(section_name))
    else:
        return OrderedDict()


def main():
    global local_conf_files, local_meta_files, local_file_objects
    local_meta_files = OrderedDict()
    local_conf_files = OrderedDict()
    local_file_objects = OrderedDict()
    log("Starting...")
    for root_dir in DIRS:
        log("Walking the directory tree '%s'" % root_dir)
        os.chdir(os.path.join(SCRIPT_HOME_DIR, root_dir))
        for root, dirnames, filenames in os.walk("."):
            # find all local.meta files, skip user-prefs
            if ("/users/" in root or "/apps/" in root) \
                    and "/apps/engr_inception/" not in root \
                    and "/alertmanager/engr_inception/" not in root:
                for filename in fnmatch.filter(filenames, 'local.meta'):
                    # read local.meta for app or user/app preserve latest stanzas in local_meta_objects
                    rel_path = os.path.join(root[2:], filename)
                    full_path = os.path.join(root_dir, rel_path)
                    log("Parsing '%s'" % full_path)
                    config = SplunkConfigParser(allow_no_value=True)
                    if os.path.isfile(rel_path):
                        config.read(rel_path)
                    else:
                        log("rel_path '%s' doesn't exist!" % rel_path)
                    for section in config.sections():
                        debug("  Section: [%s]" % section)
                        # There are "null" section names we need to skip (e.g. "[]"), probably garbage
                        if section and len(section) > 0:
                            debug("  Comparing section '%s'..." % section)
                            # Need to URL decode stanza names in local.meta to match up the ones in *.conf
                            populate_dicts(config=config, section=section, full_path=full_path, rel_path=rel_path)

    # Make sure we are back in the script directory
    os.chdir(SCRIPT_HOME_DIR)
    log("\nWrite out merged local.meta files")
    for meta_rel_path, meta_config in local_meta_files.items():
        local_meta_conf = SplunkConfigParser(allow_no_value=True)
        # debug("    DEBUG: meta_config: %s (%s)" % (meta_config, type(meta_config)))
        for section_name, section_data in meta_config.items():
            debug("    %s: Adding section [%s]" % (meta_rel_path, section_name))
            local_meta_conf.add_section(section_name)
            # debug("SECTION DATA: %s (%s)" % (repr(section_data), type(section_data)))
            for option, value in section_data.items():
                debug("      section: %s, option: %s, value: %s" % (section_name, option, value))
                local_meta_conf.set(section_name, option, value)
        merged_meta_path = os.path.join(MERGED_DIR, meta_rel_path)
        merged_meta_dir = os.path.dirname(merged_meta_path)
        make_dirs(merged_meta_dir)
        debug("  Writing out local.meta file: %s" % merged_meta_path)
        with open(merged_meta_path, "w") as f:
            local_meta_conf.write(f)

    log("\nWrite out merged *.conf files")
    for conf_rel_path, conf_config in local_conf_files.items():
        merged_file_conf = SplunkConfigParser(allow_no_value=True)
        for section_name, full_conf_path in conf_config.items():
            debug("    Reading source section: %s\n      full_conf_path: %s" % (section_name, full_conf_path))
            section_data = get_section_data(full_conf_path, section_name)
            merged_file_conf.add_section(section_name)
            for option, value in section_data.items():
                debug("      section: %s, option: %s, value: %s" % (section_name, option, value))
                merged_file_conf.set(section_name, option, value)
        merged_conf_path = os.path.join(MERGED_DIR, conf_rel_path)
        merged_conf_dir = os.path.dirname(merged_conf_path)
        make_dirs(merged_conf_dir)
        debug("  Writing out local.meta file: %s" % merged_conf_path)
        with open(merged_conf_path, "w") as f:
            merged_file_conf.write(f)

    log("\nCopy latest FILE objects to merged tree")
    for file_rel_path, file_full_path in local_file_objects.items():
        merged_file_path = os.path.join(MERGED_DIR, file_rel_path)
        merged_file_dir = os.path.dirname(merged_file_path)
        make_dirs(merged_file_dir)
        debug("  Copying %s => %s" % (file_full_path, merged_file_path))
        if os.path.isfile(file_full_path):
            shutil.copy2(file_full_path, merged_file_path)
        else:
            log("  WARNING: FILE='%s' referenced in local.meta does not exist! (skipping...)" % file_full_path)


main()
